from __future__ import annotations

from math import sqrt
from statistics import mean, median
from typing import Any


TRADING_DAYS_PER_YEAR = 252
DEFAULT_TARGET_VOLATILITY = {
    "conservative": 0.08,
    "balanced": 0.12,
    "aggressive": 0.18,
}


def build_target_volatility_proposal(
    conn: Any,
    *,
    target_date: str,
    user_preference: Any | None,
) -> dict[str, Any]:
    """Build a bounded target-volatility allocation proposal from stored features."""
    features = _latest_feature_rows(conn, target_date)
    max_equity = float(user_preference["max_equity_pct"]) if user_preference else 0.6
    min_cash = float(user_preference["min_cash_pct"]) if user_preference else 0.1
    risk_profile = str(user_preference["risk_profile"]) if user_preference else "balanced"
    target_volatility = DEFAULT_TARGET_VOLATILITY.get(risk_profile, DEFAULT_TARGET_VOLATILITY["balanced"])

    constraints = {
        "risk_profile": risk_profile,
        "max_equity_pct": max_equity,
        "min_cash_pct": min_cash,
        "target_annual_volatility": target_volatility,
    }
    usable = [row for row in features if row["volatility_20d"] is not None]
    if not usable:
        return {
            "status": "insufficient_risk_metrics",
            "constraints": constraints,
            "proposed_weights": {
                "equity": 0.0,
                "fixed_income": max(0.0, 1.0 - min_cash),
                "cash": min_cash,
            },
            "evidence": {"feature_ids": [], "feature_date": None, "asset_count": 0},
            "notes": ["缺少已入库波动率指标，暂不提高权益风险预算。"],
        }

    equity_rows = [row for row in usable if _asset_bucket(row) == "equity"]
    defensive_rows = [row for row in usable if _asset_bucket(row) in {"fixed_income", "cash"}]
    risk_rows = equity_rows or usable
    annual_vols = [_annualized_vol(row) for row in risk_rows if _annualized_vol(row) is not None]
    estimated_equity_volatility = median(annual_vols) if annual_vols else None
    raw_equity = _raw_equity_weight(target_volatility, estimated_equity_volatility)
    drawdown_penalty = _drawdown_penalty(risk_rows)
    equity = min(max_equity, raw_equity * drawdown_penalty)
    equity = min(equity, max(0.0, 1.0 - min_cash))
    equity = max(0.0, equity)
    cash = max(min_cash, 0.1 if drawdown_penalty < 1.0 else min_cash)
    cash = min(cash, 1.0 - equity)
    fixed_income = max(0.0, 1.0 - equity - cash)

    selected_assets = _selected_assets(equity_rows[:], defensive_rows[:])
    latest_feature_date = max(row["feature_date"] for row in usable)
    notes = [
        f"目标年化波动率 {target_volatility:.0%}，以入库 20 日波动率年化估算。",
        "权益权重受用户权益上限和现金下限约束。",
    ]
    if drawdown_penalty < 1.0:
        notes.append("近期最大回撤偏大，已降低权益风险预算。")
    if not equity_rows:
        notes.append("未识别到权益类风险指标，使用全体可用资产估算风险。")

    return {
        "status": "ready",
        "constraints": constraints,
        "estimated_equity_annual_volatility": estimated_equity_volatility,
        "drawdown_penalty": drawdown_penalty,
        "proposed_weights": {
            "equity": round(equity, 4),
            "fixed_income": round(fixed_income, 4),
            "cash": round(cash, 4),
        },
        "selected_assets": selected_assets,
        "evidence": {
            "feature_ids": [int(row["id"]) for row in usable],
            "feature_date": latest_feature_date,
            "asset_count": len(usable),
        },
        "notes": notes,
    }


def build_correlation_risk_budget_proposal(
    conn: Any,
    *,
    target_date: str,
    target_volatility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Estimate correlation-aware risk-budget evidence from stored prices."""
    proposal = target_volatility or {}
    selected_assets = proposal.get("selected_assets") or []
    weights = proposal.get("proposed_weights") or {}
    if not selected_assets:
        return {
            "status": "insufficient_risk_assets",
            "risk_budget": {},
            "correlation": {},
            "evidence": {"asset_ids": [], "price_observation_count": 0},
            "notes": ["缺少目标波动率候选资产，暂不能估算相关性风险预算。"],
        }

    series = {
        int(asset["asset_id"]): _asset_return_series(conn, int(asset["asset_id"]), target_date=target_date)
        for asset in selected_assets
    }
    usable_series = {asset_id: returns for asset_id, returns in series.items() if len(returns) >= 2}
    if len(usable_series) < 2:
        return {
            "status": "insufficient_correlation_history",
            "risk_budget": {},
            "correlation": {"pair_count": 0},
            "evidence": {
                "asset_ids": [int(asset["asset_id"]) for asset in selected_assets],
                "price_observation_count": sum(len(returns) for returns in series.values()),
            },
            "notes": ["至少需要两个资产的重叠收益序列才能计算相关性。"],
        }

    correlations = _pairwise_correlations(usable_series)
    avg_abs_correlation = mean(abs(item["correlation"]) for item in correlations) if correlations else 0.0
    max_abs_pair = max(correlations, key=lambda item: abs(item["correlation"])) if correlations else None
    by_asset = {int(asset["asset_id"]): asset for asset in selected_assets}
    asset_risks = []
    bucket_counts = _bucket_counts(selected_assets)
    for asset_id, returns in usable_series.items():
        asset = by_asset[asset_id]
        bucket = asset.get("bucket") or "other"
        bucket_weight = float(weights.get(bucket) or 0.0)
        asset_weight = bucket_weight / max(1, bucket_counts.get(bucket, 1))
        annual_volatility = asset.get("annualized_volatility")
        if annual_volatility is None:
            annual_volatility = _series_annualized_volatility(returns)
        correlation_load = 1.0 + _average_abs_correlation_for_asset(asset_id, correlations)
        asset_risks.append(
            {
                "asset_id": asset_id,
                "code": asset.get("code"),
                "name": asset.get("name"),
                "bucket": bucket,
                "asset_weight": asset_weight,
                "annualized_volatility": annual_volatility,
                "correlation_load": correlation_load,
                "risk_score": max(0.0, asset_weight) * max(0.0, float(annual_volatility or 0.0)) * correlation_load,
            }
        )
    total_risk = sum(item["risk_score"] for item in asset_risks)
    risk_budget = _risk_budget_by_bucket(asset_risks, total_risk)
    notes = [
        f"基于 {len(usable_series)} 个候选资产的重叠收益序列估算相关性。",
        "风险贡献为近似值，用于识别拥挤和分散度，不构成自动调仓。"
    ]
    if avg_abs_correlation >= 0.65:
        notes.append("候选资产平均相关性偏高，分散效果可能有限。")
    elif avg_abs_correlation <= 0.25:
        notes.append("候选资产相关性较低，组合分散度相对更好。")

    return {
        "status": "ready",
        "risk_budget": risk_budget,
        "correlation": {
            "pair_count": len(correlations),
            "average_abs_correlation": round(avg_abs_correlation, 4),
            "max_abs_pair": max_abs_pair,
        },
        "asset_risk": [
            {
                **item,
                "asset_weight": round(item["asset_weight"], 4),
                "annualized_volatility": round(float(item["annualized_volatility"] or 0.0), 6),
                "correlation_load": round(item["correlation_load"], 4),
                "risk_score": round(item["risk_score"], 6),
            }
            for item in sorted(asset_risks, key=lambda item: item["risk_score"], reverse=True)
        ],
        "evidence": {
            "asset_ids": sorted(usable_series),
            "price_observation_count": sum(len(returns) for returns in usable_series.values()),
        },
        "notes": notes,
    }


def _latest_feature_rows(conn: Any, target_date: str) -> list[Any]:
    return conn.execute(
        """
        SELECT fd.*, a.code AS asset_code, a.name AS asset_name,
               a.asset_type, fi.fund_type
        FROM features_daily fd
        JOIN assets a ON a.id = fd.asset_id
        LEFT JOIN fund_info fi ON fi.asset_id = a.id
        WHERE fd.feature_date = (
            SELECT MAX(inner_fd.feature_date)
            FROM features_daily inner_fd
            WHERE inner_fd.asset_id = fd.asset_id
              AND inner_fd.feature_date <= ?
        )
        ORDER BY fd.feature_date DESC, a.asset_type, a.code
        """,
        (target_date,),
    ).fetchall()


def _asset_bucket(row: Any) -> str:
    asset_type = str(row["asset_type"] or "")
    fund_type = str(row["fund_type"] or "")
    name = str(row["asset_name"] or "")
    text = f"{fund_type} {name}"
    if asset_type == "index":
        return "equity"
    if asset_type == "stock":
        return "equity"
    if "货币" in text or "现金" in text:
        return "cash"
    if "债" in text or "固收" in text:
        return "fixed_income"
    if asset_type in {"etf", "fund"}:
        return "equity"
    return "other"


def _annualized_vol(row: Any) -> float | None:
    if row["volatility_20d"] is None:
        return None
    return max(0.0, float(row["volatility_20d"])) * sqrt(TRADING_DAYS_PER_YEAR)


def _raw_equity_weight(target_volatility: float, estimated_equity_volatility: float | None) -> float:
    if estimated_equity_volatility is None or estimated_equity_volatility <= 0:
        return 0.0
    return min(1.0, target_volatility / estimated_equity_volatility)


def _drawdown_penalty(rows: list[Any]) -> float:
    drawdowns = [abs(float(row["max_drawdown_60d"])) for row in rows if row["max_drawdown_60d"] is not None]
    if not drawdowns:
        return 1.0
    typical_drawdown = median(drawdowns)
    if typical_drawdown >= 0.18:
        return 0.65
    if typical_drawdown >= 0.10:
        return 0.8
    return 1.0


def _selected_assets(equity_rows: list[Any], defensive_rows: list[Any]) -> list[dict[str, Any]]:
    ranked_equity = sorted(equity_rows, key=_asset_rank, reverse=True)[:3]
    ranked_defensive = sorted(defensive_rows, key=_asset_rank, reverse=True)[:2]
    result = []
    for row in [*ranked_equity, *ranked_defensive]:
        result.append(
            {
                "asset_id": int(row["asset_id"]),
                "code": row["asset_code"],
                "name": row["asset_name"],
                "bucket": _asset_bucket(row),
                "feature_date": row["feature_date"],
                "volatility_20d": float(row["volatility_20d"]) if row["volatility_20d"] is not None else None,
                "annualized_volatility": _annualized_vol(row),
                "max_drawdown_60d": float(row["max_drawdown_60d"]) if row["max_drawdown_60d"] is not None else None,
                "return_20d": float(row["return_20d"]) if row["return_20d"] is not None else None,
                "sharpe_60d": float(row["sharpe_60d"]) if row["sharpe_60d"] is not None else None,
            }
        )
    return result


def _asset_rank(row: Any) -> float:
    return_20d = float(row["return_20d"] or 0.0)
    sharpe = float(row["sharpe_60d"] or 0.0)
    drawdown = abs(float(row["max_drawdown_60d"] or 0.0))
    annual_vol = _annualized_vol(row) or 0.0
    return return_20d + sharpe * 0.02 - drawdown * 0.5 - annual_vol * 0.1


def _asset_return_series(conn: Any, asset_id: int, *, target_date: str, limit: int = 80) -> list[tuple[str, float]]:
    rows = conn.execute(
        """
        SELECT trade_date, COALESCE(adjusted_close, close, nav) AS value
        FROM price_daily
        WHERE asset_id = ?
          AND trade_date <= ?
          AND COALESCE(adjusted_close, close, nav) IS NOT NULL
        ORDER BY trade_date DESC
        LIMIT ?
        """,
        (asset_id, target_date, limit),
    ).fetchall()
    ordered = list(reversed(rows))
    result = []
    previous = None
    for row in ordered:
        value = float(row["value"])
        if previous and previous > 0:
            result.append((row["trade_date"], value / previous - 1.0))
        previous = value
    return result


def _pairwise_correlations(series: dict[int, list[tuple[str, float]]]) -> list[dict[str, Any]]:
    asset_ids = sorted(series)
    results = []
    for index, left_id in enumerate(asset_ids):
        for right_id in asset_ids[index + 1 :]:
            left = dict(series[left_id])
            right = dict(series[right_id])
            common_dates = sorted(set(left) & set(right))
            if len(common_dates) < 2:
                continue
            left_values = [left[date] for date in common_dates]
            right_values = [right[date] for date in common_dates]
            correlation = _correlation(left_values, right_values)
            if correlation is None:
                continue
            results.append(
                {
                    "left_asset_id": left_id,
                    "right_asset_id": right_id,
                    "correlation": round(correlation, 4),
                    "overlap_days": len(common_dates),
                }
            )
    return results


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    left_diff = [value - left_mean for value in left]
    right_diff = [value - right_mean for value in right]
    numerator = sum(a * b for a, b in zip(left_diff, right_diff))
    left_var = sum(value * value for value in left_diff)
    right_var = sum(value * value for value in right_diff)
    denominator = sqrt(left_var * right_var)
    if denominator == 0:
        return None
    return max(-1.0, min(1.0, numerator / denominator))


def _bucket_counts(assets: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for asset in assets:
        bucket = str(asset.get("bucket") or "other")
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def _average_abs_correlation_for_asset(asset_id: int, correlations: list[dict[str, Any]]) -> float:
    values = [
        abs(item["correlation"])
        for item in correlations
        if item["left_asset_id"] == asset_id or item["right_asset_id"] == asset_id
    ]
    return mean(values) if values else 0.0


def _series_annualized_volatility(returns: list[tuple[str, float]]) -> float:
    values = [value for _, value in returns]
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    return sqrt(variance) * sqrt(TRADING_DAYS_PER_YEAR)


def _risk_budget_by_bucket(asset_risks: list[dict[str, Any]], total_risk: float) -> dict[str, float]:
    budgets = {"equity": 0.0, "fixed_income": 0.0, "cash": 0.0, "other": 0.0}
    if total_risk <= 0:
        return budgets
    for item in asset_risks:
        bucket = item["bucket"] if item["bucket"] in budgets else "other"
        budgets[bucket] += item["risk_score"] / total_risk
    return {key: round(value, 4) for key, value in budgets.items()}
