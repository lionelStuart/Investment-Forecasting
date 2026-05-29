from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from investment_forecasting.advice.generator import check_compliance
from investment_forecasting.ai_analysis import build_expert_ai_analysis, build_model_evidence_packet
from investment_forecasting.communication.templates import render_expert_plan_ready, send_rendered_notification
from investment_forecasting.db import complete_task_log, connect, init_db, list_experts, start_task_log, upsert_ai_analysis_record
from investment_forecasting.portfolio.accounting import ensure_expert_portfolios, record_virtual_order, value_virtual_portfolio


EXPERT_PLAN_VERSION = "expert_plan_v1"


class ExpertPlanningError(RuntimeError):
    pass


def run_expert_daily_plans(
    db_path: str | Path,
    plan_date: str | None = None,
    *,
    notify_recipient_key: str | None = None,
    notification_channel: str = "imessage",
    notification_dry_run: bool | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path)
    target_date = _date_text(plan_date)
    ensure_expert_portfolios(db_path)
    with connect(db_path) as conn:
        target_date = _resolve_expert_plan_date(conn, target_date)
        log_id = start_task_log(conn, "expert_daily_planning", target_date, "Running expert daily plans")
        analysis_log_id = start_task_log(conn, "expert_ai_analysis", target_date, "Running expert AI analyses")
        try:
            experts = list_experts(conn, lifecycle_state="active")
            if not experts:
                raise ExpertPlanningError("Cannot run expert plans without active experts")
            candidates = _latest_candidates(conn, target_date)
            if not candidates:
                raise ExpertPlanningError("Cannot run expert plans without model prediction evidence")
            market = _latest_market_snapshot(conn, target_date)
            results = []
            analysis_count = 0
            provider_status_counts: dict[str, int] = {}
            for expert in experts:
                existing = _existing_plan(conn, int(expert["id"]), target_date)
                portfolio = _expert_portfolio(conn, int(expert["id"]))
                analysis = build_expert_ai_analysis(expert, portfolio, candidates, market, target_date)
                provider_status = (analysis.get("validation") or {}).get("provider", {}).get("status", "unknown")
                provider_status_counts[provider_status] = provider_status_counts.get(provider_status, 0) + 1
                ai_analysis_id = upsert_ai_analysis_record(conn, analysis)
                analysis_count += 1
                if existing is not None:
                    updated_existing = _ensure_existing_plan_ai_analysis(conn, existing, ai_analysis_id)
                    value_virtual_portfolio(conn, portfolio_id=int(updated_existing["portfolio_id"]), valuation_date=target_date)
                    results.append(_deserialize_plan(updated_existing))
                    continue
                plan = build_expert_plan(expert, portfolio, candidates, market, target_date, ai_analysis_id, analysis, capital_flow=_capital_flow_evidence(conn, target_date))
                check_expert_plan_compliance(plan)
                transaction = _execute_plan(conn, portfolio["id"], plan)
                valuation = value_virtual_portfolio(conn, portfolio_id=portfolio["id"], valuation_date=target_date)
                plan_id = _upsert_expert_plan(conn, plan, transaction)
                _upsert_plan_item(conn, plan_id, plan)
                results.append({**plan, "id": plan_id, "transaction": transaction, "valuation": valuation})
            complete_task_log(conn, analysis_log_id, "success", f"Generated {analysis_count} expert AI analyses; provider_status={json.dumps(provider_status_counts, ensure_ascii=False)}")
            complete_task_log(conn, log_id, "success", f"Generated {len(results)} expert plans")
            if notify_recipient_key:
                _send_expert_plan_notification(
                    conn,
                    plan_date=target_date,
                    recipient_key=notify_recipient_key,
                    channel=notification_channel,
                    dry_run=notification_dry_run,
                )
        except Exception as exc:
            complete_task_log(conn, analysis_log_id, "failed", error=str(exc))
            complete_task_log(conn, log_id, "failed", error=str(exc))
            conn.commit()
            raise
    return results


def run_expert_agent_plan_from_output(
    db_path: str | Path,
    *,
    plan_date: str,
    expert_key: str,
    agent_run_id: int,
    agent_output: dict[str, Any],
) -> dict[str, Any]:
    """Persist one validated Codex expert run through the existing plan engine."""
    init_db(db_path)
    target_date = _date_text(plan_date)
    ensure_expert_portfolios(db_path)
    _validate_expert_agent_output(expert_key, agent_output)
    with connect(db_path) as conn:
        target_date = _resolve_expert_plan_date(conn, target_date)
        expert = conn.execute(
            "SELECT * FROM experts WHERE expert_key = ? AND lifecycle_state = 'active'",
            (expert_key,),
        ).fetchone()
        if expert is None:
            raise ExpertPlanningError(f"Cannot persist agent plan without active expert: {expert_key}")
        existing = _existing_plan(conn, int(expert["id"]), target_date)
        portfolio = _expert_portfolio(conn, int(expert["id"]))
        agent_output = _merge_agent_submission_payload(conn, agent_run_id, int(portfolio["id"]), agent_output)
        if existing is not None and agent_output.get("action") == "no_trade":
            _attach_agent_evidence(conn, int(existing["id"]), agent_run_id, agent_output)
            _mark_existing_plan_no_trade(conn, int(existing["id"]), agent_output)
            value_virtual_portfolio(conn, portfolio_id=int(existing["portfolio_id"]), valuation_date=target_date)
            return _deserialize_plan(conn.execute("SELECT * FROM expert_plans WHERE id = ?", (existing["id"],)).fetchone())
        candidates = _latest_candidates(conn, target_date)
        if not candidates:
            raise ExpertPlanningError("Cannot persist expert agent plan without model prediction evidence")
        market = _latest_market_snapshot(conn, target_date)
        analysis = build_expert_ai_analysis(expert, portfolio, candidates, market, target_date)
        analysis["source"] = "codex_agent_runtime_v1"
        analysis["evidence_packet"]["agent_run_id"] = agent_run_id
        analysis["output"]["agent_summary"] = agent_output.get("summary")
        analysis["output"]["agent_analysis"] = agent_output.get("analysis")
        analysis["output"]["agent_reflection"] = agent_output.get("reflection")
        ai_analysis_id = upsert_ai_analysis_record(conn, analysis)
        if existing is not None:
            updated = _ensure_existing_plan_ai_analysis(conn, existing, ai_analysis_id)
            _attach_agent_evidence(conn, int(updated["id"]), agent_run_id, agent_output)
            if agent_output.get("outcome") in {"skipped", "failed"} or agent_output.get("action") == "no_trade":
                _mark_existing_plan_no_trade(conn, int(updated["id"]), agent_output)
                value_virtual_portfolio(conn, portfolio_id=int(updated["portfolio_id"]), valuation_date=target_date)
                return _deserialize_plan(conn.execute("SELECT * FROM expert_plans WHERE id = ?", (updated["id"],)).fetchone())
            plan = _existing_plan_with_agent_action(updated, agent_output)
            check_expert_plan_compliance(plan)
            transaction = _execute_plan(conn, int(updated["portfolio_id"]), plan)
            valuation = value_virtual_portfolio(conn, portfolio_id=int(updated["portfolio_id"]), valuation_date=target_date)
            plan_id = _upsert_expert_plan(conn, plan, transaction)
            _upsert_plan_item(conn, plan_id, plan)
            saved = _deserialize_plan(conn.execute("SELECT * FROM expert_plans WHERE id = ?", (plan_id,)).fetchone())
            return {**saved, "transaction": transaction, "valuation": valuation}
        plan = build_expert_plan(expert, portfolio, candidates, market, target_date, ai_analysis_id, analysis, capital_flow=_capital_flow_evidence(conn, target_date))
        plan["evidence"]["agent_run_id"] = agent_run_id
        plan["evidence"]["agent_output"] = agent_output
        if agent_output.get("outcome") in {"skipped", "failed"}:
            plan["action"] = "no_trade"
            plan["target_asset_id"] = None
            plan["target_weight"] = 0.0
            plan["target_amount"] = 0.0
            plan["quantity"] = 0
            plan["rationale"] = f"{expert['name']} agent outcome={agent_output.get('outcome')}：{agent_output.get('reason') or agent_output.get('summary')}"
        elif agent_output.get("action") in {"buy", "sell"}:
            _apply_agent_action_to_plan(plan, agent_output)
        check_expert_plan_compliance(plan)
        transaction = _execute_plan(conn, portfolio["id"], plan)
        valuation = value_virtual_portfolio(conn, portfolio_id=portfolio["id"], valuation_date=target_date)
        plan_id = _upsert_expert_plan(conn, plan, transaction)
        _upsert_plan_item(conn, plan_id, plan)
        saved = _deserialize_plan(conn.execute("SELECT * FROM expert_plans WHERE id = ?", (plan_id,)).fetchone())
        return {**saved, "transaction": transaction, "valuation": valuation}


def _send_expert_plan_notification(
    conn,
    *,
    plan_date: str,
    recipient_key: str,
    channel: str,
    dry_run: bool | None,
) -> None:
    try:
        send_rendered_notification(
            conn,
            channel=channel,
            recipient_key=recipient_key,
            notification=render_expert_plan_ready(conn, plan_date=plan_date),
            dry_run=dry_run,
        )
    except Exception:
        return


def build_expert_plan(
    expert,
    portfolio,
    candidates,
    market,
    plan_date: str,
    ai_analysis_id: int | None = None,
    ai_analysis: dict[str, Any] | None = None,
    capital_flow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    focus = json.loads(expert["focus_weights_json"])
    best = max(candidates, key=lambda row: _candidate_score(row, focus))
    score = _candidate_score(best, focus)
    risk_checks = _risk_checks(best, expert, market)
    action = _action_for_expert(expert["style_label"], score, risk_checks, market)
    target_weight = _target_weight(expert, action)
    target_amount = round(float(portfolio["cash"]) * target_weight, 2) if action == "buy" else 0.0
    quantity = int(target_amount / float(best["price_value"])) if action == "buy" and best["price_value"] else 0
    if action == "buy" and quantity <= 0:
        action = "no_trade"
        target_weight = 0.0
        target_amount = 0.0

    rationale = _rationale(expert, best, score, action, market, ai_analysis)
    evidence = {
        "version": EXPERT_PLAN_VERSION,
        "ai_analysis_id": ai_analysis_id,
        "prediction_id": best["prediction_id"],
        "feature_date": best["feature_date"],
        "price_date": best["price_date"],
        "market_snapshot_id": market["id"] if market else None,
        "model_evidence_packet": build_model_evidence_packet(best),
        "capital_flow": capital_flow or {"status": "missing", "latest_date": None, "stale": False},
        "asset": {
            "id": best["asset_id"],
            "code": best["asset_code"],
            "name": best["asset_name"],
            "asset_type": best["asset_type"],
        },
    }
    risk_warnings = (
        "该专家计划仅用于虚拟研究组合模拟，不构成真实买卖指令；模型预测、回测和历史价格都可能失效。"
    )
    return {
        "expert_id": expert["id"],
        "expert_key": expert["expert_key"],
        "portfolio_id": portfolio["id"],
        "ai_analysis_id": ai_analysis_id,
        "plan_date": plan_date,
        "action": action,
        "target_asset_id": best["asset_id"] if action == "buy" else None,
        "target_weight": target_weight,
        "target_amount": target_amount,
        "quantity": quantity,
        "rationale": rationale,
        "evidence": evidence,
        "risk_checks": risk_checks,
        "risk_warnings": risk_warnings,
    }


def _capital_flow_evidence(conn: Any, target_date: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT MAX(flow_date) AS latest_date, COUNT(*) AS count
        FROM capital_flow_observations
        WHERE flow_date <= ?
        """,
        (target_date,),
    ).fetchone()
    latest_date = row["latest_date"] if row else None
    if not latest_date:
        return {"status": "missing", "latest_date": None, "stale": False, "count": 0}
    age_days = (datetime.fromisoformat(target_date).date() - datetime.fromisoformat(str(latest_date)).date()).days
    stale = age_days > 3
    return {
        "status": "degraded" if stale else "available",
        "latest_date": latest_date,
        "stale": stale,
        "age_days": age_days,
        "count": int(row["count"] or 0),
    }


def check_expert_plan_compliance(plan: dict[str, Any]) -> None:
    if not plan.get("evidence") or not plan["evidence"].get("prediction_id"):
        raise ExpertPlanningError("Expert plan must reference stored prediction evidence")
    if not plan["evidence"].get("ai_analysis_id"):
        raise ExpertPlanningError("Expert plan must reference stored AI analysis evidence")
    check_compliance(" ".join([plan["rationale"], plan["risk_warnings"]]))


def _validate_expert_agent_output(expert_key: str, output: dict[str, Any]) -> None:
    if not isinstance(output, dict):
        raise ExpertPlanningError("Expert agent output must be a JSON object")
    if output.get("role") != "expert":
        raise ExpertPlanningError("Expert agent output role must be expert")
    if output.get("role_key") != expert_key:
        raise ExpertPlanningError("Expert agent output role_key does not match expert")
    if output.get("outcome") not in {"plan_action", "skipped", "failed"}:
        raise ExpertPlanningError("Expert agent output outcome is invalid")
    if output.get("action") not in {"buy", "sell", "rebalance", "hold", "no_trade"}:
        raise ExpertPlanningError("Expert agent output action is invalid")
    for key in ("summary", "reason", "analysis", "reflection", "risk_note"):
        if not isinstance(output.get(key), str) or not output[key].strip():
            raise ExpertPlanningError(f"Expert agent output missing {key}")
    check_compliance(" ".join([output["summary"], output["reason"], output["analysis"], output["reflection"], output["risk_note"]]))


def _attach_agent_evidence(conn, plan_id: int, agent_run_id: int, agent_output: dict[str, Any]) -> None:
    row = conn.execute("SELECT evidence_json FROM expert_plans WHERE id = ?", (plan_id,)).fetchone()
    evidence = json.loads(row["evidence_json"])
    evidence["agent_run_id"] = agent_run_id
    evidence["agent_output"] = agent_output
    rationale = f"Agent outcome={agent_output.get('outcome')}：{agent_output.get('reason') or agent_output.get('summary')}"
    conn.execute(
        """
        UPDATE expert_plans
        SET evidence_json = ?,
            rationale = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (
            json.dumps(evidence, ensure_ascii=False),
            rationale,
            plan_id,
        ),
    )


def _mark_existing_plan_no_trade(conn, plan_id: int, agent_output: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE expert_plans
        SET action = 'no_trade',
            target_asset_id = NULL,
            target_weight = 0,
            target_amount = 0,
            execution_status = 'no_trade',
            transaction_id = NULL,
            rationale = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (f"Agent outcome={agent_output.get('outcome')}：{agent_output.get('reason') or agent_output.get('summary')}", plan_id),
    )
    conn.execute("DELETE FROM expert_plan_items WHERE plan_id = ?", (plan_id,))
    conn.execute(
        """
        INSERT INTO expert_plan_items(asset_id, plan_id, action, target_weight, target_amount, rationale)
        VALUES (NULL, ?, 'no_trade', 0, 0, ?)
        """,
        (plan_id, agent_output.get("reason") or agent_output.get("summary") or "agent skipped action"),
    )


def _merge_agent_submission_payload(conn, agent_run_id: int, portfolio_id: int, agent_output: dict[str, Any]) -> dict[str, Any]:
    merged = dict(agent_output)
    rows = conn.execute(
        """
        SELECT arguments_json
        FROM agent_tool_calls
        WHERE agent_run_id = ?
          AND tool_name = 'submit_expert_virtual_action'
          AND status IN ('allowed', 'submitted')
        ORDER BY id ASC
        """,
        (agent_run_id,),
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["arguments_json"] or "{}").get("payload") or {}
        except (TypeError, json.JSONDecodeError):
            continue
        if payload.get("action") == merged.get("action"):
            for key in ("target_asset_id", "target_asset_code", "target_asset_name", "target_amount", "target_weight", "quantity", "rationale"):
                if payload.get(key) is not None and merged.get(key) is None:
                    merged[key] = payload[key]
    if merged.get("action") == "sell":
        _fill_sell_target_from_position(conn, portfolio_id, merged)
    return merged


def _fill_sell_target_from_position(conn, portfolio_id: int, agent_output: dict[str, Any]) -> None:
    asset_id = agent_output.get("target_asset_id")
    asset_code = agent_output.get("target_asset_code")
    if asset_id is None and asset_code:
        row = conn.execute("SELECT id FROM assets WHERE code = ? ORDER BY id LIMIT 1", (str(asset_code),)).fetchone()
        if row:
            asset_id = int(row["id"])
            agent_output["target_asset_id"] = asset_id
    if asset_id is None:
        positions = conn.execute(
            """
            SELECT p.asset_id, p.quantity
            FROM virtual_positions p
            WHERE p.portfolio_id = ? AND p.quantity > 0
            ORDER BY p.quantity DESC
            """,
            (portfolio_id,),
        ).fetchall()
        if len(positions) == 1:
            asset_id = int(positions[0]["asset_id"])
            agent_output["target_asset_id"] = asset_id
            agent_output.setdefault("quantity", float(positions[0]["quantity"]))
    if asset_id is not None and not agent_output.get("quantity"):
        position = conn.execute(
            "SELECT quantity FROM virtual_positions WHERE portfolio_id = ? AND asset_id = ?",
            (portfolio_id, asset_id),
        ).fetchone()
        if position:
            agent_output["quantity"] = float(position["quantity"])


def _existing_plan_with_agent_action(row: Any, agent_output: dict[str, Any]) -> dict[str, Any]:
    plan = _deserialize_plan(row)
    plan["quantity"] = 0
    _apply_agent_action_to_plan(plan, agent_output)
    return plan


def _apply_agent_action_to_plan(plan: dict[str, Any], agent_output: dict[str, Any]) -> None:
    action = str(agent_output.get("action") or "no_trade")
    if action not in {"buy", "sell"}:
        plan["action"] = "no_trade"
        plan["target_asset_id"] = None
        plan["target_weight"] = 0.0
        plan["target_amount"] = 0.0
        plan["quantity"] = 0
        plan["rationale"] = f"Agent outcome={agent_output.get('outcome')}：{agent_output.get('reason') or agent_output.get('summary')}"
        return
    target_asset_id = agent_output.get("target_asset_id")
    quantity = float(agent_output.get("quantity") or 0)
    if target_asset_id is None or quantity <= 0:
        plan["action"] = "no_trade"
        plan["target_asset_id"] = None
        plan["target_weight"] = 0.0
        plan["target_amount"] = 0.0
        plan["quantity"] = 0
        plan["rationale"] = f"Agent action={action} 缺少可执行资产或数量，降级为 no_trade：{agent_output.get('reason') or agent_output.get('summary')}"
        return
    plan["action"] = action
    plan["target_asset_id"] = int(target_asset_id)
    plan["target_weight"] = float(agent_output.get("target_weight") or 0.0)
    plan["target_amount"] = float(agent_output.get("target_amount") or 0.0)
    plan["quantity"] = quantity
    plan["rationale"] = agent_output.get("rationale") or f"Agent outcome={agent_output.get('outcome')}：{agent_output.get('reason') or agent_output.get('summary')}"


def _execute_plan(conn, portfolio_id: int, plan: dict[str, Any]) -> dict[str, Any]:
    if plan["action"] not in {"buy", "sell"}:
        return record_virtual_order(
            conn,
            portfolio_id=portfolio_id,
            trade_date=plan["plan_date"],
            side="no_trade",
            reason=plan["rationale"],
        )
    return record_virtual_order(
        conn,
        portfolio_id=portfolio_id,
        trade_date=plan["plan_date"],
        side=plan["action"],
        asset_id=plan["target_asset_id"],
        quantity=plan["quantity"],
        reason=plan["rationale"],
    )


def _latest_candidates(conn, target_date: str):
    return conn.execute(
        """
        SELECT
            p.id AS prediction_id,
            p.asset_id,
            p.prediction_date,
            p.horizon_days,
            p.up_probability,
            p.expected_return,
            p.downside_risk,
            p.confidence,
            p.model_version,
            r.rank_score,
            r.rank_position,
            r.rank_count,
            r.same_category_key,
            r.same_category_rank,
            r.same_category_count,
            r.risk_adjusted_score,
            r.validation_status,
            r.recent_rank_ic,
            r.bucket_spread,
            r.degraded_reason,
            r.evidence_json AS reliability_evidence_json,
            a.code AS asset_code,
            a.name AS asset_name,
            a.asset_type,
            f.feature_date,
            f.return_20d,
            f.return_60d,
            f.volatility_20d,
            f.max_drawdown_60d,
            f.sharpe_60d,
            f.calmar_60d,
            f.win_rate_60d,
            f.market_state,
            pr.trade_date AS price_date,
            COALESCE(pr.close, pr.nav, pr.adjusted_close) AS price_value
        FROM model_predictions p
        JOIN assets a ON a.id = p.asset_id
        LEFT JOIN model_prediction_reliability r ON r.prediction_id = p.id
        LEFT JOIN features_daily f
          ON f.asset_id = p.asset_id
         AND f.feature_date = p.prediction_date
        LEFT JOIN price_daily pr
          ON pr.asset_id = p.asset_id
         AND pr.trade_date = p.prediction_date
         AND COALESCE(pr.close, pr.nav, pr.adjusted_close) IS NOT NULL
        WHERE p.prediction_date = (
            SELECT MAX(prediction_date) FROM model_predictions WHERE prediction_date <= ?
        )
          AND p.horizon_days = 20
          AND f.asset_id IS NOT NULL
          AND pr.id IS NOT NULL
        ORDER BY p.confidence DESC, p.expected_return DESC
        """,
        (target_date,),
    ).fetchall()


def latest_expert_evidence_date(db_path: str | Path, requested_date: str | None = None) -> str | None:
    init_db(db_path)
    target_date = _date_text(requested_date)
    with connect(db_path) as conn:
        return _latest_expert_evidence_date(conn, target_date)


def _resolve_expert_plan_date(conn, requested_date: str) -> str:
    return _latest_expert_evidence_date(conn, requested_date) or requested_date


def _latest_expert_evidence_date(conn, requested_date: str) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(p.prediction_date) AS evidence_date
        FROM model_predictions p
        JOIN features_daily f
          ON f.asset_id = p.asset_id
         AND f.feature_date = p.prediction_date
        JOIN price_daily pr
          ON pr.asset_id = p.asset_id
         AND pr.trade_date = p.prediction_date
         AND COALESCE(pr.close, pr.nav, pr.adjusted_close) IS NOT NULL
        WHERE p.prediction_date <= ?
          AND p.horizon_days = 20
        """,
        (requested_date,),
    ).fetchone()
    return row["evidence_date"] if row and row["evidence_date"] else None


def _latest_market_snapshot(conn, target_date: str):
    return conn.execute(
        """
        SELECT *
        FROM market_snapshots
        WHERE snapshot_date <= ?
        ORDER BY snapshot_date DESC, id DESC
        LIMIT 1
        """,
        (target_date,),
    ).fetchone()


def _expert_portfolio(conn, expert_id: int):
    row = conn.execute(
        """
        SELECT *
        FROM virtual_portfolios
        WHERE owner_type = 'expert' AND owner_id = ?
        """,
        (expert_id,),
    ).fetchone()
    if row is None:
        raise ExpertPlanningError(f"Missing virtual portfolio for expert_id={expert_id}")
    return row


def _existing_plan(conn, expert_id: int, plan_date: str):
    return conn.execute(
        """
        SELECT *
        FROM expert_plans
        WHERE expert_id = ? AND plan_date = ?
        """,
        (expert_id, plan_date),
    ).fetchone()


def _deserialize_plan(row) -> dict[str, Any]:
    result = dict(row)
    result["evidence"] = json.loads(result.pop("evidence_json"))
    result["risk_checks"] = json.loads(result.pop("risk_checks_json"))
    return result


def _ensure_existing_plan_ai_analysis(conn, row, ai_analysis_id: int):
    evidence = json.loads(row["evidence_json"])
    if row["ai_analysis_id"] == ai_analysis_id and evidence.get("ai_analysis_id") == ai_analysis_id:
        return row
    evidence["ai_analysis_id"] = ai_analysis_id
    conn.execute(
        """
        UPDATE expert_plans
        SET ai_analysis_id = ?,
            evidence_json = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (ai_analysis_id, json.dumps(evidence, ensure_ascii=False), row["id"]),
    )
    return conn.execute("SELECT * FROM expert_plans WHERE id = ?", (row["id"],)).fetchone()


def _candidate_score(row, focus: dict[str, float]) -> float:
    values = {
        "return_20d": row["return_20d"] or 0.0,
        "return_60d": row["return_60d"] or 0.0,
        "up_probability": (row["up_probability"] or 0.5) - 0.5,
        "expected_return": row["expected_return"] or 0.0,
        "confidence": row["confidence"] or 0.0,
        "market_breadth": 0.0,
        "volatility": -(row["volatility_20d"] or 0.0),
        "max_drawdown": row["max_drawdown_60d"] or 0.0,
        "cash_buffer": 0.0,
        "market_snapshot_risk": 0.0,
        "fund_metadata_quality": 0.02 if row["asset_type"] == "fund" else 0.0,
        "sharpe": row["sharpe_60d"] or 0.0,
        "calmar": row["calmar_60d"] or 0.0,
        "benchmark_excess": 0.0,
        "category_diversification": 0.0,
        "backtest_quality": row["confidence"] or 0.0,
        "prediction_confidence": row["confidence"] or 0.0,
    }
    return sum(float(weight) * values.get(key, 0.0) for key, weight in focus.items())


def _risk_checks(row, expert, market) -> dict[str, Any]:
    max_drawdown = abs(row["max_drawdown_60d"] or 0.0)
    downside = abs(row["downside_risk"] or 0.0)
    tolerance = float(expert["max_drawdown_tolerance"])
    sentiment = market["sentiment"] if market else "unknown"
    validation_status = row["validation_status"] or "unvalidated"
    recent_rank_ic = row["recent_rank_ic"]
    bucket_spread = row["bucket_spread"]
    degraded_signal = (
        validation_status == "degraded"
        or (recent_rank_ic is not None and float(recent_rank_ic) < 0)
        or (bucket_spread is not None and float(bucket_spread) < 0)
    )
    return {
        "drawdown_within_tolerance": max_drawdown <= tolerance,
        "downside_within_tolerance": downside <= tolerance,
        "confidence": row["confidence"],
        "market_sentiment": sentiment,
        "risk_off_market": sentiment == "risk_off",
        "validation_status": validation_status,
        "recent_rank_ic": recent_rank_ic,
        "bucket_spread": bucket_spread,
        "degraded_reason": row["degraded_reason"],
        "degraded_model_signal": degraded_signal,
        "watch_only_model_signal": degraded_signal,
    }


def _action_for_expert(style_label: str, score: float, risk_checks: dict[str, Any], market) -> str:
    if risk_checks.get("watch_only_model_signal"):
        return "no_trade"
    if risk_checks["risk_off_market"] and "防守" in style_label:
        return "no_trade"
    if not risk_checks["downside_within_tolerance"]:
        return "no_trade"
    if "趋势" in style_label and score > 0.08:
        return "buy"
    if "均衡" in style_label and score > 0.05:
        return "buy"
    if "宏观" in style_label and score > 0.04 and not risk_checks["risk_off_market"]:
        return "buy"
    if "防守" in style_label and score > 0.03 and risk_checks["drawdown_within_tolerance"]:
        return "buy"
    return "no_trade"


def _target_weight(expert, action: str) -> float:
    if action != "buy":
        return 0.0
    risk_budget = float(expert["risk_budget_pct"])
    cash_buffer = float(expert["default_cash_buffer_pct"])
    return max(0.02, min(0.15, risk_budget * 0.2, 1.0 - cash_buffer))


def _rationale(expert, asset, score: float, action: str, market, ai_analysis: dict[str, Any] | None = None) -> str:
    sentiment = market["sentiment"] if market else "unknown"
    validation_status = asset["validation_status"] or "unvalidated"
    reliability_note = (
        f" 模型验证状态{validation_status}，"
        f"Rank IC {asset['recent_rank_ic'] if asset['recent_rank_ic'] is not None else '暂无'}，"
        f"分桶价差 {asset['bucket_spread'] if asset['bucket_spread'] is not None else '暂无'}。"
    )
    if validation_status == "degraded" or (asset["recent_rank_ic"] is not None and float(asset["recent_rank_ic"]) < 0):
        reliability_note += " 该模型信号只能作为观察线索。"
    ai_note = ""
    if ai_analysis:
        ai_output = ai_analysis["output"]
        ai_note = f" AI分析结论：{ai_output['stance']}，置信度{(ai_output.get('confidence') or 0):.2f}。"
    if action == "buy":
        return (
            f"{expert['name']}按{expert['style_label']}筛选到{asset['asset_name']}，"
            f"综合分数{score:.3f}，市场状态{sentiment}，以小仓位执行虚拟买入。{reliability_note}{ai_note}"
        )
    return (
        f"{expert['name']}按{expert['style_label']}评估后选择不交易；"
        f"候选资产{asset['asset_name']}综合分数{score:.3f}，市场状态{sentiment}，风险检查未满足加仓条件。{reliability_note}{ai_note}"
    )


def _upsert_expert_plan(conn, plan: dict[str, Any], transaction: dict[str, Any]) -> int:
    execution_status = transaction["status"]
    cursor = conn.execute(
        """
        INSERT INTO expert_plans(
            expert_id, portfolio_id, ai_analysis_id, plan_date, action, target_asset_id,
            target_weight, target_amount, rationale, evidence_json,
            risk_checks_json, risk_warnings, execution_status, transaction_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(expert_id, plan_date) DO UPDATE SET
            portfolio_id = excluded.portfolio_id,
            ai_analysis_id = excluded.ai_analysis_id,
            action = excluded.action,
            target_asset_id = excluded.target_asset_id,
            target_weight = excluded.target_weight,
            target_amount = excluded.target_amount,
            rationale = excluded.rationale,
            evidence_json = excluded.evidence_json,
            risk_checks_json = excluded.risk_checks_json,
            risk_warnings = excluded.risk_warnings,
            execution_status = excluded.execution_status,
            transaction_id = excluded.transaction_id,
            updated_at = datetime('now')
        RETURNING id
        """,
        (
            plan["expert_id"],
            plan["portfolio_id"],
            plan["ai_analysis_id"],
            plan["plan_date"],
            plan["action"],
            plan["target_asset_id"],
            plan["target_weight"],
            plan["target_amount"],
            plan["rationale"],
            json.dumps(plan["evidence"], ensure_ascii=False),
            json.dumps(plan["risk_checks"], ensure_ascii=False),
            plan["risk_warnings"],
            execution_status,
            transaction["id"],
        ),
    )
    return int(cursor.fetchone()["id"])


def _upsert_plan_item(conn, plan_id: int, plan: dict[str, Any]) -> None:
    conn.execute("DELETE FROM expert_plan_items WHERE plan_id = ?", (plan_id,))
    conn.execute(
        """
        INSERT INTO expert_plan_items(asset_id, plan_id, action, target_weight, target_amount, rationale)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            plan["target_asset_id"],
            plan_id,
            plan["action"],
            plan["target_weight"],
            plan["target_amount"],
            plan["rationale"],
        ),
    )


def _date_text(value: str | None) -> str:
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value or date.today().isoformat()
