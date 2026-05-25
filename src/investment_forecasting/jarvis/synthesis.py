from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from investment_forecasting.advice.generator import check_compliance
from investment_forecasting.ai_analysis import build_jarvis_ai_analysis, build_model_evidence_packet, deserialize_ai_analysis
from investment_forecasting.communication.templates import render_jarvis_daily_summary, send_rendered_notification
from investment_forecasting.db import (
    active_user_preference,
    complete_task_log,
    connect,
    init_db,
    latest_backtest_runs,
    latest_capital_flow_observations,
    latest_market_snapshot,
    latest_model_predictions,
    start_task_log,
    get_jarvis_daily_brief,
    upsert_ai_analysis_record,
    upsert_jarvis_daily_brief,
)
from investment_forecasting.jarvis.persistence import DEFAULT_JARVIS_VERSION, build_jarvis_brief_record, deserialize_jarvis_brief


class JarvisSynthesisError(RuntimeError):
    pass


def generate_jarvis_brief(
    db_path: str | Path,
    brief_date: str | None = None,
    *,
    target_evidence_date: str | None = None,
    agent_run_id: int | None = None,
    agent_readiness: dict[str, Any] | None = None,
    agent_output: dict[str, Any] | None = None,
    notify_recipient_key: str | None = None,
    notification_channel: str = "imessage",
    notification_dry_run: bool | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    target_date = _date_text(brief_date) if brief_date else date.today().isoformat()
    evidence_date = _date_text(target_evidence_date) if target_evidence_date else target_date
    with connect(db_path) as conn:
        log_id = start_task_log(
            conn,
            task_name="jarvis_brief_generation",
            run_date=target_date,
            message=f"Generating Jarvis brief for {target_date}",
        )
        try:
            evidence = collect_jarvis_evidence(conn, evidence_date)
            payload = synthesize_jarvis_payload(target_date, evidence)
            payload["evidence"]["target_evidence_date"] = evidence_date
            if agent_run_id is not None:
                payload["evidence"]["agent_run_id"] = agent_run_id
            if agent_readiness is not None:
                payload["evidence"]["expert_agent_readiness"] = agent_readiness
            if agent_output is not None:
                payload["evidence"]["jarvis_agent_output"] = agent_output
                payload["source"] = "codex_agent_runtime_v1"
            analysis_log_id = start_task_log(
                conn,
                task_name="jarvis_ai_analysis",
                run_date=target_date,
                message=f"Generating Jarvis AI analysis for {target_date}",
            )
            check_compliance(
                " ".join(
                    [
                        payload["one_line_stance"],
                        payload["combined_recommendation"],
                        payload["risk_warnings"],
                        json.dumps(payload["focus_directions"], ensure_ascii=False),
                        json.dumps(payload["model_summary"], ensure_ascii=False),
                        json.dumps(payload["expert_summary"], ensure_ascii=False),
                    ]
                )
            )
            jarvis_analysis = build_jarvis_ai_analysis(target_date, evidence, payload)
            provider_status = (jarvis_analysis.get("validation") or {}).get("provider", {}).get("status", "unknown")
            record = build_jarvis_brief_record(**payload)
            brief_id = upsert_jarvis_daily_brief(conn, record)
            jarvis_analysis["jarvis_brief_id"] = brief_id
            jarvis_ai_analysis_id = upsert_ai_analysis_record(conn, jarvis_analysis)
            payload["evidence"]["jarvis_ai_analysis_id"] = jarvis_ai_analysis_id
            record = build_jarvis_brief_record(**payload)
            brief_id = upsert_jarvis_daily_brief(conn, record)
            row = get_jarvis_daily_brief(conn, target_date, payload["version"])
            if row is None:
                raise JarvisSynthesisError("Jarvis brief was not readable after save")
            saved = deserialize_jarvis_brief(row, brief_id=brief_id)
            if notify_recipient_key:
                saved["notification"] = _send_jarvis_notification(
                    conn,
                    saved,
                    recipient_key=notify_recipient_key,
                    channel=notification_channel,
                    dry_run=notification_dry_run,
                )
            complete_task_log(conn, analysis_log_id, status="success", message=f"Generated Jarvis AI analysis id={jarvis_ai_analysis_id}; provider_status={provider_status}")
            complete_task_log(conn, log_id, status="success", message=f"Generated Jarvis brief id={saved['id']}")
            return saved
        except Exception as exc:
            if "analysis_log_id" in locals():
                complete_task_log(conn, analysis_log_id, status="failed", error=str(exc))
            complete_task_log(conn, log_id, status="failed", error=str(exc))
            conn.commit()
            raise


def _send_jarvis_notification(
    conn,
    brief: dict[str, Any],
    *,
    recipient_key: str,
    channel: str,
    dry_run: bool | None,
) -> dict[str, Any]:
    try:
        message = send_rendered_notification(
            conn,
            channel=channel,
            recipient_key=recipient_key,
            notification=render_jarvis_daily_summary(brief),
            dry_run=dry_run,
        )
        return {
            "id": message.get("id"),
            "status": message.get("status"),
            "duplicate": message.get("duplicate"),
            "template_key": message.get("template_key"),
            "error": message.get("error"),
        }
    except Exception as exc:
        return {"status": "failed", "error": str(exc), "template_key": "jarvis_daily_summary"}


def collect_jarvis_evidence(conn: Any, target_date: str) -> dict[str, Any]:
    predictions = [dict(row) for row in latest_model_predictions(conn)]
    backtests = [dict(row) for row in latest_backtest_runs(conn)]
    market_snapshot = latest_market_snapshot(conn)
    preference = active_user_preference(conn)
    experts = _active_expert_context(conn, target_date)
    task_logs = _latest_task_logs(conn, target_date)
    macro_observations = _latest_macro_observations(conn, target_date)
    capital_flows = _latest_capital_flows(conn, target_date)
    return {
        "target_date": target_date,
        "predictions": predictions,
        "backtests": backtests,
        "market_snapshot": dict(market_snapshot) if market_snapshot else None,
        "user_preference": dict(preference) if preference else None,
        "experts": experts,
        "task_logs": task_logs,
        "macro_observations": macro_observations,
        "capital_flows": capital_flows,
    }


def synthesize_jarvis_payload(target_date: str, evidence: dict[str, Any]) -> dict[str, Any]:
    predictions = evidence["predictions"]
    experts = evidence["experts"]
    missing = _missing_evidence(evidence)
    stale = _stale_evidence(evidence, target_date)
    model_summary = _model_summary(predictions, evidence["backtests"])
    expert_summary = [_expert_summary(item) for item in experts]
    disagreement = _disagreement(model_summary, expert_summary)
    capital_flow_summary = _capital_flow_summary(evidence["capital_flows"])
    model_summary["capital_flow"] = capital_flow_summary
    confidence_gates = _confidence_gates(model_summary, stale)
    model_summary["confidence_gates"] = confidence_gates
    model_summary["model_risk_summary"] = _model_risk_summary(confidence_gates)
    model_summary["excluded_horizons"] = _excluded_horizons(confidence_gates)
    model_summary["degraded_model_families"] = _degraded_model_families(confidence_gates)
    focus_directions = _focus_directions(model_summary, expert_summary, evidence["market_snapshot"], capital_flow_summary, missing, confidence_gates)
    one_line_stance = _one_line_stance(model_summary, disagreement, missing, stale)
    risk_warnings = _risk_warnings(missing, stale, evidence["user_preference"], confidence_gates)
    combined = _combined_recommendation(one_line_stance, model_summary, expert_summary, disagreement)
    source_evidence = _source_evidence(evidence, model_summary)
    source_evidence["confidence_gates"] = confidence_gates
    model_summary["disagreement"] = disagreement
    return {
        "brief_date": target_date,
        "version": DEFAULT_JARVIS_VERSION,
        "focus_directions": focus_directions,
        "one_line_stance": one_line_stance,
        "model_summary": model_summary,
        "expert_summary": expert_summary,
        "combined_recommendation": combined,
        "risk_warnings": risk_warnings,
        "evidence": source_evidence,
        "missing_evidence": missing,
        "stale_evidence": stale,
        "source": "jarvis_synthesis_v1",
    }


def _active_expert_context(conn: Any, target_date: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT e.*, vp.id AS portfolio_id, vp.initial_capital, vp.cash AS portfolio_cash
        FROM experts e
        LEFT JOIN virtual_portfolios vp ON vp.owner_type = 'expert' AND vp.owner_id = e.id
        WHERE e.lifecycle_state = 'active'
        ORDER BY e.expert_key
        """
    ).fetchall()
    contexts = []
    for row in rows:
        expert = dict(row)
        plan = conn.execute(
            """
            SELECT p.*, a.code AS asset_code, a.name AS asset_name
            FROM expert_plans p
            LEFT JOIN assets a ON a.id = p.target_asset_id
            WHERE p.expert_id = ? AND p.plan_date <= ?
            ORDER BY p.plan_date DESC, p.id DESC
            LIMIT 1
            """,
            (expert["id"], target_date),
        ).fetchone()
        scorecard = conn.execute(
            """
            SELECT *
            FROM expert_scorecards
            WHERE expert_id = ? AND score_date <= ?
            ORDER BY score_date DESC, id DESC
            LIMIT 1
            """,
            (expert["id"], target_date),
        ).fetchone()
        valuation = None
        if expert["portfolio_id"] is not None:
            valuation = conn.execute(
                """
                SELECT *
                FROM virtual_valuations
                WHERE portfolio_id = ? AND valuation_date <= ?
                ORDER BY valuation_date DESC, id DESC
                LIMIT 1
                """,
                (expert["portfolio_id"], target_date),
            ).fetchone()
        analysis = conn.execute(
            """
            SELECT *
            FROM ai_analysis_records
            WHERE analysis_type = 'expert'
              AND expert_id = ?
              AND analysis_date <= ?
            ORDER BY analysis_date DESC, id DESC
            LIMIT 1
            """,
            (expert["id"], target_date),
        ).fetchone()
        contexts.append(
            {
                "expert": expert,
                "plan": dict(plan) if plan else None,
                "scorecard": dict(scorecard) if scorecard else None,
                "valuation": dict(valuation) if valuation else None,
                "ai_analysis": deserialize_ai_analysis(analysis),
            }
        )
    return contexts


def _latest_task_logs(conn: Any, target_date: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, task_name, run_date, status, message, error
        FROM task_logs
        WHERE run_date <= ?
        ORDER BY run_date DESC, id DESC
        LIMIT 12
        """,
        (target_date,),
    ).fetchall()
    return [dict(row) for row in rows]


def _latest_macro_observations(conn: Any, target_date: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, series_id, observation_date, value
        FROM macro_observations
        WHERE observation_date <= ?
        ORDER BY observation_date DESC, series_id
        LIMIT 12
        """,
        (target_date,),
    ).fetchall()
    return [dict(row) for row in rows]


def _latest_capital_flows(conn: Any, target_date: str) -> list[dict[str, Any]]:
    rows = latest_capital_flow_observations(conn, limit=20)
    return [dict(row) for row in rows if row["flow_date"] <= target_date]


def _model_summary(predictions: list[dict[str, Any]], backtests: list[dict[str, Any]]) -> dict[str, Any]:
    if not predictions:
        return {
            "status": "missing",
            "prediction_date": None,
            "average_expected_return": None,
            "average_downside_risk": None,
            "average_confidence": None,
            "top_forecasts": [],
            "model_quality": {"status": "missing", "backtest_run_ids": []},
        }
    expected = _mean(row.get("expected_return") for row in predictions)
    downside = _mean(row.get("downside_risk") for row in predictions)
    confidence = _mean(row.get("confidence") for row in predictions)
    ranked = sorted(
        predictions,
        key=lambda row: (
            float(row["rank_score"] if row.get("rank_score") is not None else row["expected_return"] or 0),
            float(row["risk_adjusted_score"] if row.get("risk_adjusted_score") is not None else row["expected_return"] or 0),
            float(row["confidence"] or 0),
            -abs(float(row["downside_risk"] or 0)),
        ),
        reverse=True,
    )
    quality_scores = [_backtest_score(row) for row in backtests]
    quality_score = _mean(score for score in quality_scores if score is not None)
    return {
        "status": _model_status(expected, downside, quality_score),
        "prediction_date": max(row["prediction_date"] for row in predictions),
        "average_expected_return": expected,
        "average_downside_risk": downside,
        "average_confidence": confidence,
        "top_forecasts": [build_model_evidence_packet(row) for row in ranked[:5]],
        "model_quality": {
            "status": "available" if backtests else "missing",
            "average_score": quality_score,
            "backtest_run_ids": [row["id"] for row in backtests],
        },
    }


def _expert_summary(item: dict[str, Any]) -> dict[str, Any]:
    expert = item["expert"]
    plan = item["plan"]
    scorecard = item["scorecard"]
    valuation = item["valuation"]
    ai_analysis = item.get("ai_analysis")
    ai_output = ai_analysis["output"] if ai_analysis else {}
    current_return = None
    if valuation and expert.get("initial_capital"):
        current_return = (float(valuation["total_value"]) / float(expert["initial_capital"])) - 1.0
    return {
        "expert_id": expert["id"],
        "expert_key": expert["expert_key"],
        "expert_name": expert["name"],
        "style_label": expert["style_label"],
        "lifecycle_state": expert["lifecycle_state"],
        "plan_id": plan["id"] if plan else None,
        "ai_analysis_id": ai_analysis["id"] if ai_analysis else None,
        "ai_analysis_date": ai_analysis["analysis_date"] if ai_analysis else None,
        "ai_thesis": ai_output.get("thesis"),
        "ai_confidence": ai_output.get("confidence"),
        "ai_stance": ai_output.get("stance"),
        "plan_date": plan["plan_date"] if plan else None,
        "action": plan["action"] if plan else "missing_plan",
        "target": _target_text(plan),
        "rationale": plan["rationale"] if plan else "没有可用的专家计划。",
        "scorecard_id": scorecard["id"] if scorecard else None,
        "score": scorecard["overall_score"] if scorecard else None,
        "current_return": current_return,
        "max_drawdown": scorecard["max_drawdown"] if scorecard else None,
        "risk_state": _expert_risk_state(plan, scorecard, valuation),
        "valuation_id": valuation["id"] if valuation else None,
        "valuation_date": valuation["valuation_date"] if valuation else None,
    }


def _focus_directions(
    model_summary: dict[str, Any],
    expert_summary: list[dict[str, Any]],
    market_snapshot: dict[str, Any] | None,
    capital_flow_summary: dict[str, Any],
    missing: list[dict[str, Any]],
    confidence_gates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    directions = []
    if missing:
        directions.append({"direction": "先补证据", "reason": "部分市场、模型或专家证据缺失，先降低解释强度。"})
    sentiment = market_snapshot["sentiment"] if market_snapshot else None
    if sentiment in {"risk_off", "weak"}:
        directions.append({"direction": "防守现金", "reason": "市场快照偏弱，优先观察回撤和流动性。"})
    if capital_flow_summary.get("status") == "available" and capital_flow_summary.get("negative_count", 0) > capital_flow_summary.get("positive_count", 0):
        directions.append({"direction": "观察资金流", "reason": "最新资金流样本里主力净流出对象更多，相关方向先降权。"})
    top = model_summary.get("top_forecasts", [])
    if top:
        asset = top[0].get("asset_name") or top[0].get("asset_code") or "高分资产"
        gated = any(item.get("prediction_id") == top[0].get("prediction_id") for item in confidence_gates)
        reason = "模型预测里收益和置信度相对靠前。"
        if gated:
            reason = "该信号触发 Jarvis 信心门，只作为观察线索，不作为强行动作方向。"
        directions.append({"direction": f"观察 {asset}", "reason": reason, "gate_status": "watch_only" if gated else "clear"})
    actions = {row["action"] for row in expert_summary}
    if actions & {"buy", "rebalance"}:
        directions.append({"direction": "专家进攻信号", "reason": "至少一名专家给出买入或再平衡计划。"})
    elif expert_summary:
        directions.append({"direction": "专家防守共识", "reason": "当前专家计划以持有、观望或不交易为主。"})
    return directions[:3] or [{"direction": "等待数据", "reason": "还没有足够证据形成方向。"}]


def _one_line_stance(
    model_summary: dict[str, Any],
    disagreement: dict[str, Any],
    missing: list[dict[str, Any]],
    stale: list[dict[str, Any]],
) -> str:
    if missing or stale:
        return "偏防守，先确认数据"
    expected = model_summary.get("average_expected_return") or 0.0
    downside = model_summary.get("average_downside_risk") or 0.0
    if disagreement["has_disagreement"]:
        return "模型与专家分歧，谨慎观察"
    if expected > 0.02 and downside > -0.05:
        return "小幅进攻但控制回撤"
    if expected < 0 or downside <= -0.08:
        return "偏防守，等待确认"
    return "均衡观察"


def _combined_recommendation(
    stance: str,
    model_summary: dict[str, Any],
    expert_summary: list[dict[str, Any]],
    disagreement: dict[str, Any],
) -> str:
    expert_text = f"{len(expert_summary)} 名活跃专家已纳入评估"
    if expert_summary:
        active_actions = ", ".join(sorted({row["action"] for row in expert_summary}))
        expert_text += f"，最新动作包括 {active_actions}"
    model_text = "模型证据缺失"
    if model_summary.get("status") != "missing":
        model_text = (
            f"模型平均预期收益 {_fmt_pct(model_summary['average_expected_return'])}，"
            f"平均下行风险 {_fmt_pct(model_summary['average_downside_risk'])}"
        )
    capital_flow = model_summary.get("capital_flow") or {}
    flow_text = ""
    if capital_flow.get("status") == "available":
        flow_text = (
            f"；资金流观测 {capital_flow['count']} 个对象，"
            f"净流入 {capital_flow['positive_count']}、净流出 {capital_flow['negative_count']}"
        )
    conflict = f" 分歧提示：{disagreement['summary']}" if disagreement["has_disagreement"] else ""
    gates = model_summary.get("confidence_gates") or []
    gate_text = " 触发信心门的预测仅作为观察信号。" if gates else ""
    return f"{stance}。{model_text}{flow_text}；{expert_text}。关注证据更新和风险边界，不把单一专家短期表现当作结论。{gate_text}{conflict}"


def _risk_warnings(
    missing: list[dict[str, Any]],
    stale: list[dict[str, Any]],
    preference: dict[str, Any] | None,
    confidence_gates: list[dict[str, Any]] | None = None,
) -> str:
    parts = ["Jarvis 仅作本地投资研究辅助，不构成直接买卖指令。"]
    if preference:
        parts.append(
            f"当前偏好约束为权益上限 {float(preference['max_equity_pct']):.0%}、现金下限 {float(preference['min_cash_pct']):.0%}。"
        )
    if missing:
        parts.append("存在缺失证据，相关结论需要降权。")
    if stale:
        parts.append("存在过期证据，需等待最新运行结果确认。")
    if confidence_gates:
        parts.append("部分模型信号触发风险官信心门，只能作为观察或排除依据。")
    parts.append("市场、模型和专家虚拟组合都可能出现回撤，需结合个人风险承受能力复核。")
    return "".join(parts)


def _confidence_gates(model_summary: dict[str, Any], stale: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    stale_sources = {item["source"] for item in stale}
    if "model_predictions" in stale_sources:
        gates.append(_gate("stale_model_predictions", "warning", "downgrade_to_watch", "模型预测证据已过期。"))
    if "backtest_runs" in stale_sources:
        gates.append(_gate("stale_validation", "warning", "downgrade_to_watch", "模型验证证据已过期，不能放大预测结论。"))
    quality = model_summary.get("model_quality") or {}
    if quality.get("status") == "missing":
        gates.append(_gate("missing_backtest", "warning", "downgrade_to_watch", "缺少回测质量证据。"))
    elif quality.get("average_score") is not None and float(quality["average_score"]) < 55:
        gates.append(_gate("degraded_backtest", "warning", "downgrade_to_watch", "回测质量评分偏低。"))
    gates.extend(_model_family_disagreement_gates(model_summary.get("top_forecasts") or []))
    for forecast in model_summary.get("top_forecasts") or []:
        expected = float(forecast.get("expected_return") or 0.0)
        confidence = float(forecast.get("confidence") or 0.0)
        validation_status = forecast.get("validation_status")
        recent_rank_ic = forecast.get("recent_rank_ic")
        bucket_spread = forecast.get("bucket_spread")
        same_category_count = forecast.get("same_category_count")
        common = {
            "prediction_id": forecast.get("prediction_id"),
            "asset": forecast.get("asset_name") or forecast.get("asset_code"),
            "horizon_days": forecast.get("horizon_days"),
            "model_version": forecast.get("model_version"),
        }
        if validation_status in {"degraded", "insufficient_sample", "unvalidated"}:
            reason = {
                "degraded": forecast.get("degraded_reason") or "模型验证状态为 degraded，只能作为观察信号。",
                "insufficient_sample": "模型验证样本不足，不能作为主结论。",
                "unvalidated": "模型信号尚未通过验证，只能作为观察上下文。",
            }[validation_status]
            gates.append(_gate(f"{validation_status}_model_signal", "warning", "watch_only", reason, **common))
        if same_category_count is not None and int(same_category_count) < 3:
            gates.append(
                _gate(
                    "insufficient_same_category_sample",
                    "warning",
                    "watch_only",
                    "同类资产样本不足，不能使用同类排名做强结论。",
                    **common,
                )
            )
        if recent_rank_ic is not None and float(recent_rank_ic) < 0:
            gates.append(
                _gate("negative_rank_ic", "warning", "watch_only", "最近 Rank IC 为负，排序信号不能作为主结论。", **common)
            )
        elif recent_rank_ic is not None and float(recent_rank_ic) < 0.02:
            gates.append(
                _gate("weak_rank_ic", "info", "watch_only", "最近 Rank IC 偏弱，排序证据只适合观察。", **common)
            )
        if bucket_spread is not None and float(bucket_spread) < 0:
            gates.append(
                _gate("negative_bucket_spread", "warning", "watch_only", "高分桶历史表现弱于低分桶，模型信号降级观察。", **common)
            )
        elif bucket_spread is not None and float(bucket_spread) < 0.005:
            gates.append(
                _gate("weak_bucket_spread", "info", "watch_only", "分桶价差偏弱，不能放大为强信号。", **common)
            )
        if abs(expected) >= 0.15:
            gates.append(
                _gate("outlier_expected_return", "warning", "watch_only", "预期收益幅度异常，不能作为强推荐。", **common)
            )
        if confidence < 0.45:
            gates.append(
                _gate("low_confidence_forecast", "warning", "watch_only", "预测置信度偏低，只能作为观察信号。", **common)
            )
    return gates


def _gate(gate: str, severity: str, action: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"gate": gate, "severity": severity, "action": action, "reason": reason, **{k: v for k, v in extra.items() if v is not None}}


def _model_family_disagreement_gates(forecasts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_horizon: dict[int, list[dict[str, Any]]] = {}
    for forecast in forecasts:
        horizon = forecast.get("horizon_days")
        if horizon is None:
            continue
        by_horizon.setdefault(int(horizon), []).append(forecast)
    gates = []
    for horizon, rows in by_horizon.items():
        model_versions = {row.get("model_version") for row in rows if row.get("model_version")}
        signs = {1 if float(row.get("expected_return") or 0.0) > 0 else -1 if float(row.get("expected_return") or 0.0) < 0 else 0 for row in rows}
        statuses = {row.get("validation_status") for row in rows if row.get("validation_status")}
        if len(model_versions) >= 2 and (len(signs) > 1 or len(statuses) > 1):
            gates.append(
                _gate(
                    "model_family_disagreement",
                    "warning",
                    "downgrade_to_watch",
                    f"{horizon}日模型家族在方向或验证状态上不一致，不能形成强结论。",
                    horizon_days=horizon,
                    model_versions=sorted(model_versions),
                )
            )
    return gates


def _model_risk_summary(gates: list[dict[str, Any]]) -> dict[str, Any]:
    warning_count = sum(1 for gate in gates if gate.get("severity") == "warning")
    excluded_count = sum(1 for gate in gates if gate.get("action") == "exclude")
    watch_only_count = sum(1 for gate in gates if gate.get("action") in {"watch_only", "downgrade_to_watch"})
    return {
        "status": "blocked" if excluded_count else "watch_only" if warning_count or watch_only_count else "clear",
        "gate_count": len(gates),
        "warning_count": warning_count,
        "watch_only_count": watch_only_count,
        "excluded_count": excluded_count,
        "top_reasons": [gate["reason"] for gate in gates[:3]],
    }


def _excluded_horizons(gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    horizons: dict[int, set[str]] = {}
    for gate in gates:
        if gate.get("horizon_days") is None:
            continue
        if gate.get("action") in {"watch_only", "downgrade_to_watch", "exclude"}:
            horizons.setdefault(int(gate["horizon_days"]), set()).add(str(gate["gate"]))
    return [{"horizon_days": horizon, "reasons": sorted(reasons)} for horizon, reasons in sorted(horizons.items())]


def _degraded_model_families(gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    families: dict[str, set[str]] = {}
    for gate in gates:
        version = gate.get("model_version")
        if not version:
            continue
        families.setdefault(str(version), set()).add(str(gate["gate"]))
    return [{"model_version": version, "reasons": sorted(reasons)} for version, reasons in sorted(families.items())]


def _disagreement(model_summary: dict[str, Any], experts: list[dict[str, Any]]) -> dict[str, Any]:
    model_expected = model_summary.get("average_expected_return")
    offensive_experts = [row for row in experts if row["action"] in {"buy", "rebalance"}]
    defensive_experts = [row for row in experts if row["action"] in {"hold", "no_trade", "missing_plan"}]
    has_conflict = False
    reasons = []
    if model_expected is not None and model_expected > 0.02 and len(defensive_experts) > len(offensive_experts):
        has_conflict = True
        reasons.append("模型偏正向，但多数专家保持防守或观望")
    if model_expected is not None and model_expected <= 0 and offensive_experts:
        has_conflict = True
        reasons.append("模型偏弱，但有专家计划提高风险暴露")
    if not experts:
        reasons.append("没有活跃专家观点可比较")
    return {
        "has_disagreement": has_conflict,
        "summary": "；".join(reasons) if reasons else "模型与专家观点暂未出现显著冲突",
        "offensive_expert_count": len(offensive_experts),
        "defensive_expert_count": len(defensive_experts),
    }


def _source_evidence(evidence: dict[str, Any], model_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "market_snapshot_ids": [evidence["market_snapshot"]["id"]] if evidence["market_snapshot"] else [],
        "macro_observation_ids": [row["id"] for row in evidence["macro_observations"]],
        "capital_flow_ids": [row["id"] for row in evidence["capital_flows"]],
        "model_prediction_ids": [row["prediction_id"] for row in model_summary.get("top_forecasts", [])],
        "model_prediction_count": len(evidence["predictions"]),
        "backtest_run_ids": [row["id"] for row in evidence["backtests"]],
        "expert_plan_ids": [item["plan"]["id"] for item in evidence["experts"] if item["plan"]],
        "expert_ai_analysis_ids": [item["ai_analysis"]["id"] for item in evidence["experts"] if item.get("ai_analysis")],
        "expert_scorecard_ids": [item["scorecard"]["id"] for item in evidence["experts"] if item["scorecard"]],
        "virtual_valuation_ids": [item["valuation"]["id"] for item in evidence["experts"] if item["valuation"]],
        "user_preference_id": evidence["user_preference"]["id"] if evidence["user_preference"] else None,
        "task_log_ids": [row["id"] for row in evidence["task_logs"]],
    }


def _missing_evidence(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    missing = []
    checks = [
        ("market_snapshots", evidence["market_snapshot"], "缺少市场环境快照"),
        ("capital_flow_observations", evidence["capital_flows"], "缺少资金流观测"),
        ("model_predictions", evidence["predictions"], "缺少模型预测"),
        ("backtest_runs", evidence["backtests"], "缺少回测质量证据"),
        ("experts", evidence["experts"], "缺少活跃专家"),
        ("user_preferences", evidence["user_preference"], "缺少活跃用户偏好"),
    ]
    for source, value, reason in checks:
        if not value:
            missing.append({"source": source, "reason": reason})
    for item in evidence["experts"]:
        expert = item["expert"]
        if not item["plan"]:
            missing.append({"source": "expert_plans", "expert": expert["name"], "reason": "缺少专家计划"})
        if not item.get("ai_analysis"):
            missing.append({"source": "expert_ai_analysis", "expert": expert["name"], "reason": "缺少专家独立 AI 分析"})
        if not item["scorecard"]:
            missing.append({"source": "expert_scorecards", "expert": expert["name"], "reason": "缺少专家评分"})
        if not item["valuation"]:
            missing.append({"source": "virtual_valuations", "expert": expert["name"], "reason": "缺少虚拟组合估值"})
    return missing


def _stale_evidence(evidence: dict[str, Any], target_date: str) -> list[dict[str, Any]]:
    stale = []
    target = datetime.fromisoformat(target_date).date()
    dated_sources = []
    snapshot = evidence["market_snapshot"]
    if snapshot:
        dated_sources.append(("market_snapshots", snapshot["snapshot_date"]))
    if evidence["predictions"]:
        dated_sources.append(("model_predictions", max(row["prediction_date"] for row in evidence["predictions"])))
    if evidence["capital_flows"]:
        dated_sources.append(("capital_flow_observations", max(row["flow_date"] for row in evidence["capital_flows"])))
    for item in evidence["experts"]:
        if item["plan"]:
            dated_sources.append(("expert_plans", item["plan"]["plan_date"]))
        if item.get("ai_analysis"):
            dated_sources.append(("expert_ai_analysis", item["ai_analysis"]["analysis_date"]))
        if item["scorecard"]:
            dated_sources.append(("expert_scorecards", item["scorecard"]["score_date"]))
        if item["valuation"]:
            dated_sources.append(("virtual_valuations", item["valuation"]["valuation_date"]))
    for source, source_date in dated_sources:
        try:
            age_days = (target - datetime.fromisoformat(source_date).date()).days
        except ValueError:
            continue
        if age_days > 3:
            stale.append({"source": source, "last_date": source_date, "age_days": age_days})
    return stale


def _expert_risk_state(plan: dict[str, Any] | None, scorecard: dict[str, Any] | None, valuation: dict[str, Any] | None) -> str:
    if not plan or not scorecard or not valuation:
        return "证据不足"
    if scorecard["mature_enough"] == 0:
        return "样本不足"
    if scorecard["max_drawdown"] is not None and float(scorecard["max_drawdown"]) <= -0.08:
        return "回撤偏高"
    if plan["execution_status"] in {"unfilled", "pending"}:
        return "执行待确认"
    return "正常观察"


def _target_text(plan: dict[str, Any] | None) -> str:
    if not plan:
        return "暂无目标"
    asset = f"{plan.get('asset_code') or ''} {plan.get('asset_name') or ''}".strip()
    return asset or "现金/观望"


def _backtest_score(row: dict[str, Any]) -> float | None:
    try:
        metrics = json.loads(row["metrics_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    score = metrics.get("mean_overall_score") or metrics.get("overall_score")
    return float(score) if score is not None else None


def _model_status(expected: float | None, downside: float | None, quality_score: float | None) -> str:
    if expected is None or downside is None:
        return "missing"
    if downside <= -0.08 or (quality_score is not None and quality_score < 55):
        return "defensive"
    if expected >= 0.02 and downside > -0.05 and (quality_score is None or quality_score >= 65):
        return "constructive"
    return "neutral"


def _mean(values: Any) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return mean(clean) if clean else None


def _capital_flow_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"status": "missing", "count": 0, "latest_date": None, "positive_count": 0, "negative_count": 0, "top_inflows": [], "top_outflows": []}
    positive = [row for row in rows if (row.get("main_net_inflow") or 0) > 0]
    negative = [row for row in rows if (row.get("main_net_inflow") or 0) < 0]
    top_inflows = sorted(positive, key=lambda row: float(row.get("main_net_inflow") or 0), reverse=True)[:3]
    top_outflows = sorted(negative, key=lambda row: float(row.get("main_net_inflow") or 0))[:3]
    return {
        "status": "available",
        "count": len(rows),
        "latest_date": max(row["flow_date"] for row in rows if row.get("flow_date")),
        "positive_count": len(positive),
        "negative_count": len(negative),
        "top_inflows": [_capital_flow_view(row) for row in top_inflows],
        "top_outflows": [_capital_flow_view(row) for row in top_outflows],
    }


def _capital_flow_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "flow_date": row.get("flow_date"),
        "scope": row.get("scope"),
        "subject_code": row.get("subject_code"),
        "subject_name": row.get("subject_name"),
        "main_net_inflow": row.get("main_net_inflow"),
        "main_net_inflow_pct": row.get("main_net_inflow_pct"),
    }


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "暂无"
    return f"{float(value):.2%}"


def _date_text(value: str | None) -> str:
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    if value:
        return value
    return date.today().isoformat()
