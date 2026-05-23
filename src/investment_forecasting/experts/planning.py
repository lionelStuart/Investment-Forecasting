from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from investment_forecasting.advice.generator import check_compliance
from investment_forecasting.db import complete_task_log, connect, init_db, list_experts, start_task_log
from investment_forecasting.portfolio.accounting import ensure_expert_portfolios, record_virtual_order


EXPERT_PLAN_VERSION = "expert_plan_v1"


class ExpertPlanningError(RuntimeError):
    pass


def run_expert_daily_plans(db_path: str | Path, plan_date: str | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    target_date = _date_text(plan_date)
    ensure_expert_portfolios(db_path)
    with connect(db_path) as conn:
        log_id = start_task_log(conn, "expert_daily_planning", target_date, "Running expert daily plans")
        try:
            experts = list_experts(conn, lifecycle_state="active")
            if not experts:
                raise ExpertPlanningError("Cannot run expert plans without active experts")
            candidates = _latest_candidates(conn, target_date)
            if not candidates:
                raise ExpertPlanningError("Cannot run expert plans without model prediction evidence")
            market = _latest_market_snapshot(conn, target_date)
            results = []
            for expert in experts:
                existing = _existing_plan(conn, int(expert["id"]), target_date)
                if existing is not None:
                    results.append(_deserialize_plan(existing))
                    continue
                portfolio = _expert_portfolio(conn, int(expert["id"]))
                plan = build_expert_plan(expert, portfolio, candidates, market, target_date)
                check_expert_plan_compliance(plan)
                transaction = _execute_plan(conn, portfolio["id"], plan)
                plan_id = _upsert_expert_plan(conn, plan, transaction)
                _upsert_plan_item(conn, plan_id, plan)
                results.append({**plan, "id": plan_id, "transaction": transaction})
            complete_task_log(conn, log_id, "success", f"Generated {len(results)} expert plans")
        except Exception as exc:
            complete_task_log(conn, log_id, "failed", error=str(exc))
            conn.commit()
            raise
    return results


def build_expert_plan(expert, portfolio, candidates, market, plan_date: str) -> dict[str, Any]:
    focus = json.loads(expert["focus_weights_json"])
    best = max(candidates, key=lambda row: _candidate_score(row, focus))
    score = _candidate_score(best, focus)
    risk_checks = _risk_checks(best, expert, market)
    action = _action_for_expert(expert["expert_key"], score, risk_checks, market)
    target_weight = _target_weight(expert, action)
    target_amount = round(float(portfolio["cash"]) * target_weight, 2) if action == "buy" else 0.0
    quantity = int(target_amount / float(best["price_value"])) if action == "buy" and best["price_value"] else 0
    if action == "buy" and quantity <= 0:
        action = "no_trade"
        target_weight = 0.0
        target_amount = 0.0

    rationale = _rationale(expert, best, score, action, market)
    evidence = {
        "version": EXPERT_PLAN_VERSION,
        "prediction_id": best["prediction_id"],
        "feature_date": best["feature_date"],
        "price_date": best["price_date"],
        "market_snapshot_id": market["id"] if market else None,
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


def check_expert_plan_compliance(plan: dict[str, Any]) -> None:
    if not plan.get("evidence") or not plan["evidence"].get("prediction_id"):
        raise ExpertPlanningError("Expert plan must reference stored prediction evidence")
    check_compliance(" ".join([plan["rationale"], plan["risk_warnings"]]))


def _execute_plan(conn, portfolio_id: int, plan: dict[str, Any]) -> dict[str, Any]:
    if plan["action"] != "buy":
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
        side="buy",
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
        LEFT JOIN features_daily f
          ON f.asset_id = p.asset_id
         AND f.feature_date = (
            SELECT MAX(feature_date) FROM features_daily WHERE asset_id = p.asset_id AND feature_date <= ?
         )
        LEFT JOIN price_daily pr
          ON pr.asset_id = p.asset_id
         AND pr.trade_date = (
            SELECT MAX(trade_date)
            FROM price_daily
            WHERE asset_id = p.asset_id
              AND trade_date <= ?
              AND COALESCE(close, nav, adjusted_close) IS NOT NULL
         )
        WHERE p.prediction_date = (
            SELECT MAX(prediction_date) FROM model_predictions WHERE prediction_date <= ?
        )
          AND p.horizon_days = 20
          AND pr.id IS NOT NULL
        ORDER BY p.confidence DESC, p.expected_return DESC
        """,
        (target_date, target_date, target_date),
    ).fetchall()


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
    return {
        "drawdown_within_tolerance": max_drawdown <= tolerance,
        "downside_within_tolerance": downside <= tolerance,
        "confidence": row["confidence"],
        "market_sentiment": sentiment,
        "risk_off_market": sentiment == "risk_off",
    }


def _action_for_expert(expert_key: str, score: float, risk_checks: dict[str, Any], market) -> str:
    if risk_checks["risk_off_market"] and expert_key == "defensive_income":
        return "no_trade"
    if not risk_checks["downside_within_tolerance"]:
        return "no_trade"
    if expert_key == "momentum_growth" and score > 0.08:
        return "buy"
    if expert_key == "balanced_rotation" and score > 0.05:
        return "buy"
    if expert_key == "defensive_income" and score > 0.03 and risk_checks["drawdown_within_tolerance"]:
        return "buy"
    return "no_trade"


def _target_weight(expert, action: str) -> float:
    if action != "buy":
        return 0.0
    risk_budget = float(expert["risk_budget_pct"])
    cash_buffer = float(expert["default_cash_buffer_pct"])
    return max(0.02, min(0.15, risk_budget * 0.2, 1.0 - cash_buffer))


def _rationale(expert, asset, score: float, action: str, market) -> str:
    sentiment = market["sentiment"] if market else "unknown"
    if action == "buy":
        return (
            f"{expert['name']}按{expert['style_label']}筛选到{asset['asset_name']}，"
            f"综合分数{score:.3f}，市场状态{sentiment}，以小仓位执行虚拟买入。"
        )
    return (
        f"{expert['name']}按{expert['style_label']}评估后选择不交易；"
        f"候选资产{asset['asset_name']}综合分数{score:.3f}，市场状态{sentiment}，风险检查未满足加仓条件。"
    )


def _upsert_expert_plan(conn, plan: dict[str, Any], transaction: dict[str, Any]) -> int:
    execution_status = transaction["status"]
    cursor = conn.execute(
        """
        INSERT INTO expert_plans(
            expert_id, portfolio_id, plan_date, action, target_asset_id,
            target_weight, target_amount, rationale, evidence_json,
            risk_checks_json, risk_warnings, execution_status, transaction_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(expert_id, plan_date) DO UPDATE SET
            portfolio_id = excluded.portfolio_id,
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
