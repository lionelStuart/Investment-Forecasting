from __future__ import annotations

import json
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from investment_forecasting.db import (
    connect,
    init_db,
    list_assets,
    list_price_history,
    update_backtest_metrics,
    upsert_backtest_result,
    upsert_backtest_run,
    upsert_model_prediction,
)
from investment_forecasting.quant.features import PricePoint


MODEL_VERSION = "baseline_mean_v1"
DEFAULT_HORIZONS = (5, 20, 60)
DEFAULT_LOOKBACK = 60


class BacktestError(RuntimeError):
    """Raised when a forecast or backtest cannot be run safely."""


@dataclass(frozen=True)
class Forecast:
    asset_id: int
    prediction_date: str
    horizon_days: int
    expected_return: float
    expected_return_low: float
    expected_return_high: float
    up_probability: float
    downside_risk: float
    confidence: float
    input_window_start: str
    input_window_end: str


def run_latest_forecasts(db_path: str | Path, horizons: tuple[int, ...] = DEFAULT_HORIZONS) -> dict[int, int]:
    init_db(db_path)
    summary: dict[int, int] = {}

    with connect(db_path) as conn:
        for asset in list_assets(conn):
            prices = _load_prices(conn, int(asset["id"]))
            written = 0
            for horizon in horizons:
                if len(prices) < 2:
                    continue
                forecast = forecast_from_history(prices, horizon_days=horizon)
                upsert_model_prediction(conn, _forecast_record(forecast))
                written += 1
            summary[int(asset["id"])] = written

    return summary


def run_backtest(
    db_path: str | Path,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    lookback_days: int = DEFAULT_LOOKBACK,
) -> dict[str, Any]:
    init_db(db_path)
    metrics_by_horizon: dict[int, dict[str, Any]] = {}

    with connect(db_path) as conn:
        asset_histories = {int(asset["id"]): _load_prices(conn, int(asset["id"])) for asset in list_assets(conn)}
        asset_codes = {int(asset["id"]): asset["code"] for asset in list_assets(conn)}
        benchmark_prices = _benchmark_prices(conn)
        all_prices = [price for prices in asset_histories.values() for price in prices]
        sample_start = min((price.trade_date for price in all_prices), default="")
        sample_end = max((price.trade_date for price in all_prices), default="")

        for horizon in horizons:
            run_id = upsert_backtest_run(
                conn,
                {
                    "model_version": MODEL_VERSION,
                    "asset_scope": "all",
                    "start_date": sample_start,
                    "end_date": sample_end,
                    "horizon_days": horizon,
                    "parameters_json": json.dumps({"lookback_days": lookback_days}, ensure_ascii=False),
                    "metrics_json": None,
                },
            )
            results = []
            for asset_id, prices in asset_histories.items():
                for split in rolling_splits(prices, horizon_days=horizon, lookback_days=lookback_days):
                    history = prices[split["history_start_index"] : split["prediction_index"] + 1]
                    forecast = forecast_from_history(history, horizon_days=horizon)
                    actual_return = (prices[split["outcome_index"]].value / prices[split["prediction_index"]].value) - 1.0
                    benchmark_return = _aligned_return(
                        benchmark_prices,
                        prices[split["prediction_index"]].trade_date,
                        prices[split["outcome_index"]].trade_date,
                    )
                    if asset_codes.get(asset_id) == "000300":
                        benchmark_return = actual_return
                    result = score_forecast(
                        forecast.expected_return,
                        actual_return,
                        forecast.downside_risk,
                        benchmark_return=benchmark_return,
                    )
                    upsert_backtest_result(
                        conn,
                        {
                            "run_id": run_id,
                            "asset_id": asset_id,
                            "prediction_date": prices[split["prediction_index"]].trade_date,
                            "horizon_days": horizon,
                            "predicted_return": forecast.expected_return,
                            "actual_return": actual_return,
                            "predicted_direction": _direction(forecast.expected_return),
                            "actual_direction": _direction(actual_return),
                            "prediction_score": result["prediction_score"],
                            "risk_score": result["risk_score"],
                            "advice_score": result["advice_score"],
                            "overall_score": result["overall_score"],
                            "details_json": json.dumps(
                                {
                                    **result,
                                    "input_window_start": history[0].trade_date,
                                    "input_window_end": history[-1].trade_date,
                                    "outcome_date": prices[split["outcome_index"]].trade_date,
                                    "benchmark_return": benchmark_return,
                                    "model_version": MODEL_VERSION,
                                },
                                ensure_ascii=False,
                            ),
                        },
                    )
                    results.append(result | {"actual_return": actual_return, "predicted_return": forecast.expected_return})

            metrics = aggregate_scores(results)
            metrics_by_horizon[horizon] = metrics
            update_backtest_metrics(conn, run_id, json.dumps(metrics, ensure_ascii=False))

    return {"model_version": MODEL_VERSION, "horizons": metrics_by_horizon}


def forecast_from_history(prices: list[PricePoint], horizon_days: int, lookback_days: int = DEFAULT_LOOKBACK) -> Forecast:
    if len(prices) < 2:
        raise BacktestError("At least two historical prices are required")

    history = prices[-lookback_days:]
    returns = [(history[index].value / history[index - 1].value) - 1.0 for index in range(1, len(history))]
    avg_return = mean(returns)
    volatility = stdev(returns) if len(returns) >= 2 else 0.0
    expected_return = avg_return * horizon_days
    interval = volatility * sqrt(horizon_days)
    up_probability = sum(1 for value in returns if value > 0) / len(returns)
    downside_risk = min(0.0, expected_return - interval)
    confidence = min(1.0, len(returns) / lookback_days)

    return Forecast(
        asset_id=history[-1].asset_id,
        prediction_date=history[-1].trade_date,
        horizon_days=horizon_days,
        expected_return=expected_return,
        expected_return_low=expected_return - interval,
        expected_return_high=expected_return + interval,
        up_probability=up_probability,
        downside_risk=downside_risk,
        confidence=confidence,
        input_window_start=history[0].trade_date,
        input_window_end=history[-1].trade_date,
    )


def rolling_splits(prices: list[PricePoint], horizon_days: int, lookback_days: int) -> list[dict[str, int]]:
    if lookback_days < 2:
        raise BacktestError("lookback_days must be at least 2")
    splits = []
    for prediction_index in range(lookback_days - 1, len(prices) - horizon_days):
        splits.append(
            {
                "history_start_index": prediction_index - lookback_days + 1,
                "prediction_index": prediction_index,
                "outcome_index": prediction_index + horizon_days,
            }
        )
    return splits


def score_forecast(
    predicted_return: float,
    actual_return: float,
    downside_risk: float,
    benchmark_return: float | None = None,
) -> dict[str, float]:
    direction_hit = _direction(predicted_return) == _direction(actual_return)
    return_error = abs(predicted_return - actual_return)
    prediction_score = max(0.0, 100.0 - return_error * 1000.0)
    if direction_hit:
        prediction_score = min(100.0, prediction_score + 10.0)

    risk_hit = actual_return >= downside_risk
    risk_score = 100.0 if risk_hit else max(0.0, 100.0 - abs(actual_return - downside_risk) * 1000.0)
    benchmark_excess = actual_return - benchmark_return if benchmark_return is not None else 0.0
    benchmark_score = max(0.0, min(100.0, 50.0 + benchmark_excess * 1000.0))
    advice_score = (prediction_score * 0.45) + (risk_score * 0.35) + (benchmark_score * 0.20)
    overall_score = (prediction_score + risk_score + advice_score) / 3.0
    return {
        "direction_hit": 1.0 if direction_hit else 0.0,
        "return_error": return_error,
        "risk_hit": 1.0 if risk_hit else 0.0,
        "benchmark_excess": benchmark_excess,
        "drawdown_control": 1.0 if risk_hit else 0.0,
        "prediction_score": prediction_score,
        "risk_score": risk_score,
        "advice_score": advice_score,
        "overall_score": overall_score,
    }


def aggregate_scores(results: list[dict[str, float]]) -> dict[str, float | int | None]:
    if not results:
        return {
            "count": 0,
            "direction_accuracy": None,
            "mean_return_error": None,
            "risk_hit_rate": None,
            "mean_benchmark_excess": None,
            "mean_drawdown_control": None,
            "mean_prediction_score": None,
            "mean_risk_score": None,
            "mean_advice_score": None,
            "mean_overall_score": None,
        }
    return {
        "count": len(results),
        "direction_accuracy": mean(item["direction_hit"] for item in results),
        "mean_return_error": mean(item["return_error"] for item in results),
        "risk_hit_rate": mean(item["risk_hit"] for item in results),
        "mean_benchmark_excess": mean(item["benchmark_excess"] for item in results),
        "mean_drawdown_control": mean(item["drawdown_control"] for item in results),
        "mean_prediction_score": mean(item["prediction_score"] for item in results),
        "mean_risk_score": mean(item["risk_score"] for item in results),
        "mean_advice_score": mean(item["advice_score"] for item in results),
        "mean_overall_score": mean(item["overall_score"] for item in results),
    }


def _load_prices(conn: Any, asset_id: int) -> list[PricePoint]:
    return [
        PricePoint(asset_id=int(row["asset_id"]), trade_date=row["trade_date"], value=float(row["price_value"]))
        for row in list_price_history(conn, asset_id)
    ]


def _benchmark_prices(conn: Any) -> list[PricePoint]:
    row = conn.execute("SELECT id FROM assets WHERE code = '000300' AND asset_type = 'index' ORDER BY id LIMIT 1").fetchone()
    return _load_prices(conn, int(row["id"])) if row else []


def _aligned_return(prices: list[PricePoint], start_date: str, end_date: str) -> float | None:
    by_date = {price.trade_date: price.value for price in prices}
    if start_date not in by_date or end_date not in by_date:
        return None
    return (by_date[end_date] / by_date[start_date]) - 1.0


def _forecast_record(forecast: Forecast) -> dict[str, Any]:
    return {
        "asset_id": forecast.asset_id,
        "prediction_date": forecast.prediction_date,
        "horizon_days": forecast.horizon_days,
        "model_version": MODEL_VERSION,
        "target": "return",
        "up_probability": forecast.up_probability,
        "expected_return": forecast.expected_return,
        "expected_return_low": forecast.expected_return_low,
        "expected_return_high": forecast.expected_return_high,
        "downside_risk": forecast.downside_risk,
        "confidence": forecast.confidence,
        "input_window_start": forecast.input_window_start,
        "input_window_end": forecast.input_window_end,
        "assumptions": "Baseline forecast uses only historical returns available through the prediction date.",
    }


def _direction(value: float) -> str:
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"
