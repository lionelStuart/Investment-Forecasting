from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import sqrt
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from investment_forecasting.db import (
    complete_task_log,
    connect,
    init_db,
    list_assets,
    list_price_history,
    start_task_log,
    upsert_feature_daily,
)


FEATURE_VERSION = "features_v1"
MAX_CALENDAR_GAP_DAYS = 15


class FeatureCalculationError(RuntimeError):
    """Raised when stored price history is not safe to transform into features."""


@dataclass(frozen=True)
class PricePoint:
    asset_id: int
    trade_date: str
    value: float


def calculate_features_for_db(db_path: str | Path, start_date: str | None = None, end_date: str | None = None) -> dict[int, int]:
    init_db(db_path)
    summary: dict[int, int] = {}

    with connect(db_path) as conn:
        log_id = start_task_log(
            conn,
            task_name="feature_calculation",
            run_date=date.today().isoformat(),
            message="Calculating daily features and risk metrics",
        )
        try:
            for asset in list_assets(conn):
                prices = [
                    PricePoint(
                        asset_id=int(row["asset_id"]),
                        trade_date=row["trade_date"],
                        value=float(row["price_value"]),
                    )
                    for row in list_price_history(conn, asset_id=int(asset["id"]))
                ]
                features = calculate_asset_features(prices)
                written = 0
                for feature in features:
                    if start_date and feature["feature_date"] < _date_text(start_date):
                        continue
                    if end_date and feature["feature_date"] > _date_text(end_date):
                        continue
                    upsert_feature_daily(conn, feature)
                    written += 1
                summary[int(asset["id"])] = written
            complete_task_log(conn, log_id, status="success", message=f"Calculated {sum(summary.values())} feature rows")
        except Exception as exc:
            complete_task_log(conn, log_id, status="failed", error=str(exc))
            conn.commit()
            raise

    return summary


def calculate_asset_features(prices: list[PricePoint]) -> list[dict[str, Any]]:
    if not prices:
        return []

    _validate_price_history(prices)
    values = [point.value for point in prices]
    daily_returns = _daily_returns(values)
    features = []

    for index, point in enumerate(prices):
        if index == 0:
            continue

        return_1d = daily_returns[index - 1]
        return_5d = _period_return(values, index, 5)
        return_20d = _period_return(values, index, 20)
        return_60d = _period_return(values, index, 60)
        returns_20d = _trailing(daily_returns, index - 1, 20)
        returns_60d = _trailing(daily_returns, index - 1, 60)
        prices_60d = _trailing(values, index, 61)

        max_drawdown_60d = _max_drawdown(prices_60d) if len(prices_60d) >= 2 else None
        volatility_20d = stdev(returns_20d) if len(returns_20d) >= 2 else None
        sharpe_60d = _sharpe(returns_60d)
        calmar_60d = _calmar(return_60d, max_drawdown_60d)
        win_rate_60d = _win_rate(returns_60d)

        features.append(
            {
                "asset_id": point.asset_id,
                "feature_date": point.trade_date,
                "return_1d": return_1d,
                "return_5d": return_5d,
                "return_20d": return_20d,
                "return_60d": return_60d,
                "volatility_20d": volatility_20d,
                "max_drawdown_60d": max_drawdown_60d,
                "sharpe_60d": sharpe_60d,
                "calmar_60d": calmar_60d,
                "win_rate_60d": win_rate_60d,
                "momentum_20d": return_20d,
                "market_state": _market_state(return_20d, max_drawdown_60d),
                "source": FEATURE_VERSION,
            }
        )

    return features


def _validate_price_history(prices: list[PricePoint]) -> None:
    seen_dates: set[str] = set()
    previous: date | None = None
    for point in prices:
        if point.value <= 0:
            raise FeatureCalculationError(f"Non-positive price for asset {point.asset_id} on {point.trade_date}")
        current = date.fromisoformat(point.trade_date)
        if point.trade_date in seen_dates:
            raise FeatureCalculationError(f"Duplicate price date for asset {point.asset_id}: {point.trade_date}")
        if previous and current <= previous:
            raise FeatureCalculationError(f"Non-monotonic price dates for asset {point.asset_id}")
        if previous and (current - previous).days > MAX_CALENDAR_GAP_DAYS:
            raise FeatureCalculationError(
                f"Large date gap for asset {point.asset_id}: {previous.isoformat()} to {current.isoformat()}"
            )
        seen_dates.add(point.trade_date)
        previous = current


def _daily_returns(values: list[float]) -> list[float]:
    return [(values[index] / values[index - 1]) - 1.0 for index in range(1, len(values))]


def _period_return(values: list[float], index: int, window: int) -> float | None:
    if index < window:
        return None
    return (values[index] / values[index - window]) - 1.0


def _trailing(values: list[float], end_index: int, window: int) -> list[float]:
    start = max(0, end_index - window + 1)
    return values[start : end_index + 1]


def _max_drawdown(values: list[float]) -> float:
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = (value / peak) - 1.0
        max_drawdown = min(max_drawdown, drawdown)
    return max_drawdown


def _sharpe(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    sigma = stdev(returns)
    if sigma == 0:
        return None
    return mean(returns) / sigma * sqrt(252)


def _calmar(return_60d: float | None, max_drawdown_60d: float | None) -> float | None:
    if return_60d is None or max_drawdown_60d is None or max_drawdown_60d == 0:
        return None
    annualized_return = (1.0 + return_60d) ** (252 / 60) - 1.0
    return annualized_return / abs(max_drawdown_60d)


def _win_rate(returns: list[float]) -> float | None:
    if not returns:
        return None
    return sum(1 for value in returns if value > 0) / len(returns)


def _market_state(return_20d: float | None, max_drawdown_60d: float | None) -> str:
    if return_20d is None:
        return "insufficient_history"
    if max_drawdown_60d is not None and max_drawdown_60d <= -0.1:
        return "high_risk"
    if return_20d > 0.03:
        return "risk_on"
    if return_20d < -0.03:
        return "risk_off"
    return "neutral"


def _date_text(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value
