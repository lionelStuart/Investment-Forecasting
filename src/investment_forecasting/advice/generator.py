from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

from investment_forecasting.db import (
    active_user_preference,
    complete_task_log,
    connect,
    init_db,
    latest_backtest_runs,
    latest_market_snapshot,
    latest_model_predictions,
    start_task_log,
    upsert_daily_advice,
)


ADVICE_VERSION = "daily_advice_v1"
PROHIBITED_PHRASES = (
    "保本",
    "稳赚",
    "确定收益",
    "必然上涨",
    "一定上涨",
    "无风险",
    "guaranteed",
    "risk-free",
    "certain profit",
)


class AdviceGenerationError(RuntimeError):
    """Raised when daily advice cannot be generated from structured evidence."""


class ComplianceError(AdviceGenerationError):
    """Raised when generated advice contains prohibited certainty language."""


def generate_daily_advice(db_path: str | Path, advice_date: str | None = None) -> int:
    init_db(db_path)
    target_date = _date_text(advice_date) if advice_date else date.today().isoformat()

    with connect(db_path) as conn:
        log_id = start_task_log(
            conn,
            task_name="daily_advice_generation",
            run_date=target_date,
            message=f"Generating daily advice for {target_date}",
        )
        try:
            predictions = latest_model_predictions(conn)
            backtest_runs = latest_backtest_runs(conn)
            market_snapshot = latest_market_snapshot(conn)
            user_preference = active_user_preference(conn)
            if not predictions:
                raise AdviceGenerationError("Cannot generate advice without model_predictions evidence")
            if not backtest_runs:
                raise AdviceGenerationError("Cannot generate advice without backtest_runs evidence")

            record = build_daily_advice_record(
                target_date,
                predictions,
                backtest_runs,
                market_snapshot=market_snapshot,
                user_preference=user_preference,
            )
            check_compliance(
                " ".join(
                    [
                        record["market_summary"],
                        record["aggressive_advice"],
                        record["balanced_advice"],
                        record["conservative_advice"],
                        record["assumptions"],
                        record["risk_warnings"],
                    ]
                )
            )
            advice_id = upsert_daily_advice(conn, record)
            complete_task_log(conn, log_id, status="success", message=f"Generated daily advice id={advice_id}")
            return advice_id
        except Exception as exc:
            complete_task_log(conn, log_id, status="failed", error=str(exc))
            conn.commit()
            raise


def build_daily_advice_record(
    target_date: str,
    predictions: list[Any],
    backtest_runs: list[Any],
    market_snapshot: Any | None = None,
    user_preference: Any | None = None,
) -> dict[str, Any]:
    avg_expected = mean(float(row["expected_return"]) for row in predictions if row["expected_return"] is not None)
    avg_downside = mean(float(row["downside_risk"]) for row in predictions if row["downside_risk"] is not None)
    avg_confidence = mean(float(row["confidence"]) for row in predictions if row["confidence"] is not None)
    backtest_scores = [_overall_from_metrics(row["metrics_json"]) for row in backtest_runs]
    backtest_score = mean(score for score in backtest_scores if score is not None) if any(score is not None for score in backtest_scores) else None

    risk_level = _risk_level(avg_expected, avg_downside, backtest_score)
    policy = _allocation_policy(risk_level)
    preferred_horizon = int(user_preference["investment_horizon_days"]) if user_preference else 20
    if user_preference:
        policy = _apply_user_constraints(policy, user_preference)
    source_prediction_ids = [int(row["id"]) for row in predictions]
    backtest_run_ids = [int(row["id"]) for row in backtest_runs]
    latest_prediction_date = max(row["prediction_date"] for row in predictions)
    ranked_predictions = _rank_predictions(predictions, preferred_horizon=preferred_horizon)
    focus_assets = ranked_predictions[:3]
    cautious_assets = sorted(
        ranked_predictions,
        key=lambda item: (item["downside_risk"], item["expected_return"]),
    )[:3]

    market_summary = (
        f"基于 SQLite 中截至 {latest_prediction_date} 的 baseline_mean_v1 预测，"
        f"跟踪资产平均预期收益为 {avg_expected:.2%}，平均下行风险为 {avg_downside:.2%}，"
        f"当前研究风险等级为 {risk_level}。"
    )
    if market_snapshot:
        market_summary += (
            f" 市场环境快照显示情绪为 {market_snapshot['sentiment']}，"
            f"宽度为 {_fmt_pct(market_snapshot['breadth'])}，"
            f"流动性热度为 {_fmt_num(market_snapshot['liquidity_heat'])}。"
        )
    if user_preference:
        market_summary += (
            f" 当前活跃风险设置为 {user_preference['profile_name']}，"
            f"偏好为 {_risk_profile_label(user_preference['risk_profile'])}，"
            f"关注周期 {preferred_horizon} 天。"
        )
    assumptions = (
        "本记录仅使用已入库的行情、特征、预测和回测结果；上午运行时通常反映上一交易日数据。"
        f" 平均模型置信度为 {avg_confidence:.2%}，历史回测综合分为 "
        f"{backtest_score:.1f}/100。" if backtest_score is not None else
        "本记录仅使用已入库的行情、特征、预测和回测结果；上午运行时通常反映上一交易日数据。"
        f" 平均模型置信度为 {avg_confidence:.2%}，历史回测综合分暂不可用。"
    )
    if user_preference:
        assumptions += (
            f" 仓位区间已应用用户约束：权益上限 {float(user_preference['max_equity_pct']):.0%}，"
            f"现金下限 {float(user_preference['min_cash_pct']):.0%}。"
        )
    risk_warnings = (
        "本系统输出是投资研究和辅助决策参考，不构成直接买卖指令。市场可能受政策、流动性、"
        "行业事件和数据延迟影响，预测区间和仓位范围需要结合个人风险承受能力复核。"
    )

    allocation = {
        "risk_level": risk_level,
        "confidence": avg_confidence,
        "profiles": policy,
        "triggers": {
            "add_exposure": "若后续预测置信度提升且20/60日预期收益改善，可在对应风险档位内分批提高权益暴露。",
            "reduce_exposure": "若下行风险扩大、回测得分走弱或出现连续大幅回撤，应降低权益暴露并提高现金/短债比例。",
        },
        "evidence": {
            "source_prediction_ids": source_prediction_ids,
            "backtest_run_ids": backtest_run_ids,
            "market_snapshot_id": int(market_snapshot["id"]) if market_snapshot else None,
        },
        "user_preference": _preference_payload(user_preference),
        "focus_assets": focus_assets,
        "cautious_assets": cautious_assets,
    }

    return {
        "advice_date": target_date,
        "market_summary": market_summary,
        "risk_level": risk_level,
        "aggressive_advice": _profile_text("激进型", policy["aggressive"], "可承受较大波动，分批配置权益和弹性资产。", focus_assets),
        "balanced_advice": _profile_text("中等型", policy["balanced"], "保持权益、债券和现金类资产均衡，优先控制组合波动。", focus_assets[:2]),
        "conservative_advice": _profile_text("保守型", policy["conservative"], "以现金、货币基金、短债和低波动资产为主，谨慎增加权益暴露。", focus_assets[:1]),
        "allocation_json": json.dumps(allocation, ensure_ascii=False),
        "assumptions": assumptions,
        "risk_warnings": risk_warnings,
        "evidence_json": json.dumps(allocation["evidence"], ensure_ascii=False),
        "prediction_score": None,
        "risk_score": None,
        "advice_score": None,
        "overall_score": backtest_score,
        "model_version": ADVICE_VERSION,
    }


def check_compliance(text: str) -> None:
    lower_text = text.lower()
    for phrase in PROHIBITED_PHRASES:
        if phrase.lower() in lower_text:
            raise ComplianceError(f"Prohibited advice language detected: {phrase}")


def _risk_level(avg_expected: float, avg_downside: float, backtest_score: float | None) -> str:
    if avg_downside <= -0.08 or (backtest_score is not None and backtest_score < 55):
        return "high"
    if avg_expected >= 0.03 and avg_downside > -0.05 and (backtest_score is None or backtest_score >= 70):
        return "low"
    return "medium"


def _allocation_policy(risk_level: str) -> dict[str, dict[str, str]]:
    if risk_level == "high":
        return {
            "aggressive": {"equity": "40%-60%", "fixed_income": "20%-35%", "cash": "10%-25%"},
            "balanced": {"equity": "25%-45%", "fixed_income": "30%-50%", "cash": "15%-30%"},
            "conservative": {"equity": "5%-20%", "fixed_income": "40%-65%", "cash": "25%-45%"},
        }
    if risk_level == "low":
        return {
            "aggressive": {"equity": "60%-80%", "fixed_income": "10%-25%", "cash": "5%-15%"},
            "balanced": {"equity": "40%-60%", "fixed_income": "25%-45%", "cash": "10%-25%"},
            "conservative": {"equity": "15%-30%", "fixed_income": "40%-60%", "cash": "20%-35%"},
        }
    return {
        "aggressive": {"equity": "50%-70%", "fixed_income": "15%-30%", "cash": "10%-20%"},
        "balanced": {"equity": "35%-55%", "fixed_income": "30%-45%", "cash": "10%-25%"},
        "conservative": {"equity": "10%-25%", "fixed_income": "45%-65%", "cash": "20%-40%"},
    }


def _apply_user_constraints(policy: dict[str, dict[str, str]], user_preference: Any) -> dict[str, dict[str, str]]:
    constrained = json.loads(json.dumps(policy))
    max_equity = float(user_preference["max_equity_pct"])
    min_cash = float(user_preference["min_cash_pct"])
    for profile_policy in constrained.values():
        profile_policy["equity"] = _cap_range(profile_policy["equity"], upper_cap=max_equity)
        profile_policy["cash"] = _floor_range(profile_policy["cash"], lower_floor=min_cash)
    return constrained


def _cap_range(value: str, upper_cap: float) -> str:
    low, high = _parse_pct_range(value)
    high = min(high, upper_cap)
    low = min(low, high)
    return _pct_range(low, high)


def _floor_range(value: str, lower_floor: float) -> str:
    low, high = _parse_pct_range(value)
    low = max(low, lower_floor)
    high = max(high, low)
    return _pct_range(low, high)


def _parse_pct_range(value: str) -> tuple[float, float]:
    low_text, high_text = value.replace("%", "").split("-")
    return float(low_text) / 100.0, float(high_text) / 100.0


def _pct_range(low: float, high: float) -> str:
    return f"{low:.0%}-{high:.0%}"


def _profile_text(profile: str, allocation: dict[str, str], posture: str, focus_assets: list[dict[str, Any]]) -> str:
    focus_text = _focus_text(focus_assets)
    return (
        f"{profile}: {posture} 参考区间为权益 {allocation['equity']}、"
        f"固收 {allocation['fixed_income']}、现金类 {allocation['cash']}。"
        f" 近期优先关注：{focus_text}。"
        " 加仓条件是预测置信度和预期收益同步改善；减仓条件是下行风险扩大或回测评分走弱。"
    )


def _rank_predictions(predictions: list[Any], preferred_horizon: int = 20) -> list[dict[str, Any]]:
    latest_by_asset: dict[int, Any] = {}
    for row in predictions:
        if int(row["horizon_days"]) != preferred_horizon:
            continue
        latest_by_asset[int(row["asset_id"])] = row
    if not latest_by_asset:
        latest_by_asset = {int(row["asset_id"]): row for row in predictions}

    ranked = []
    for row in latest_by_asset.values():
        expected_return = float(row["expected_return"] or 0.0)
        confidence = float(row["confidence"] or 0.0)
        downside_risk = float(row["downside_risk"] or 0.0)
        up_probability = float(row["up_probability"] or 0.0)
        score = expected_return * 0.5 + up_probability * 0.2 + confidence * 0.2 + downside_risk * 0.1
        ranked.append(
            {
                "asset_id": int(row["asset_id"]),
                "code": row["asset_code"] if "asset_code" in row.keys() else None,
                "name": row["asset_name"] if "asset_name" in row.keys() else None,
                "asset_type": row["asset_type"] if "asset_type" in row.keys() else None,
                "horizon_days": int(row["horizon_days"]),
                "expected_return": expected_return,
                "up_probability": up_probability,
                "downside_risk": downside_risk,
                "confidence": confidence,
                "score": score,
            }
        )
    return sorted(ranked, key=lambda item: item["score"], reverse=True)


def _preference_payload(user_preference: Any | None) -> dict[str, Any] | None:
    if not user_preference:
        return None
    return {
        "id": int(user_preference["id"]),
        "profile_name": user_preference["profile_name"],
        "risk_profile": user_preference["risk_profile"],
        "investment_horizon_days": int(user_preference["investment_horizon_days"]),
        "max_equity_pct": float(user_preference["max_equity_pct"]),
        "min_cash_pct": float(user_preference["min_cash_pct"]),
    }


def _risk_profile_label(value: str) -> str:
    return {"aggressive": "激进", "balanced": "中等", "conservative": "保守"}.get(value, value)


def _focus_text(focus_assets: list[dict[str, Any]]) -> str:
    if not focus_assets:
        return "暂无足够标的证据，先补齐数据和回测"
    return "、".join(
        f"{item.get('name') or item.get('code') or '资产ID ' + str(item['asset_id'])}"
        f"({item['horizon_days']}日预期{item['expected_return']:.2%}, 置信度{item['confidence']:.0%})"
        for item in focus_assets
    )


def _overall_from_metrics(metrics_json: str | None) -> float | None:
    if not metrics_json:
        return None
    metrics = json.loads(metrics_json)
    value = metrics.get("mean_overall_score")
    return float(value) if value is not None else None


def _fmt_pct(value: Any) -> str:
    return "暂无" if value is None else f"{float(value):.2%}"


def _fmt_num(value: Any) -> str:
    return "暂无" if value is None else f"{float(value):.2f}"


def _date_text(value: str | None) -> str:
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    if value:
        return value
    return date.today().isoformat()
