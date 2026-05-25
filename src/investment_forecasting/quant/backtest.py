from __future__ import annotations

import json
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from investment_forecasting.data.classification import classify_asset_theme
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
from investment_forecasting.quant.benchmarks import BenchmarkSelection, select_asset_benchmark
from investment_forecasting.quant.features import PricePoint
from investment_forecasting.quant.forecast import (
    MODEL_STATES,
    MODEL_VERSIONS,
    PRIMARY_MODEL_VERSION,
    daily_returns,
    forecast_expected_return,
)
from investment_forecasting.quant.reliability import refresh_prediction_reliability


MODEL_VERSION = PRIMARY_MODEL_VERSION
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


def run_latest_forecasts(
    db_path: str | Path,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    model_versions: tuple[str, ...] = (MODEL_VERSION,),
) -> dict[int, int]:
    init_db(db_path)
    _validate_model_versions(model_versions)
    summary: dict[int, int] = {}

    with connect(db_path) as conn:
        for asset in list_assets(conn):
            prices = _load_prices(conn, int(asset["id"]))
            written = 0
            if len(prices) >= 2:
                for model_version in model_versions:
                    for horizon in horizons:
                        forecast = forecast_from_history(prices, horizon_days=horizon, model_version=model_version)
                        upsert_model_prediction(conn, _forecast_record(forecast, model_version=model_version))
                        written += 1
            summary[int(asset["id"])] = written
        for model_version in model_versions:
            latest_prediction_date = conn.execute(
                "SELECT MAX(prediction_date) AS prediction_date FROM model_predictions WHERE model_version = ?",
                (model_version,),
            ).fetchone()["prediction_date"]
            if latest_prediction_date:
                refresh_prediction_reliability(
                    conn,
                    prediction_date=latest_prediction_date,
                    model_version=model_version,
                    horizons=horizons,
                )

    return summary


def run_backtest(
    db_path: str | Path,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    lookback_days: int = DEFAULT_LOOKBACK,
    embargo_days: int = 0,
    model_versions: tuple[str, ...] = (MODEL_VERSION,),
) -> dict[str, Any]:
    init_db(db_path)
    _validate_model_versions(model_versions)
    metrics_by_model: dict[str, dict[int, dict[str, Any]]] = {}

    with connect(db_path) as conn:
        assets = list_assets(conn)
        asset_histories = {int(asset["id"]): _load_prices(conn, int(asset["id"])) for asset in assets}
        all_prices = [price for prices in asset_histories.values() for price in prices]
        sample_start = min((price.trade_date for price in all_prices), default="")
        sample_end = max((price.trade_date for price in all_prices), default="")
        benchmark_cache: dict[tuple[int, str, str], BenchmarkSelection] = {}

        for model_version in model_versions:
            metrics_by_horizon: dict[int, dict[str, Any]] = {}
            for horizon in horizons:
                run_id = upsert_backtest_run(
                    conn,
                    {
                        "model_version": model_version,
                        "asset_scope": "all",
                        "start_date": sample_start,
                        "end_date": sample_end,
                        "horizon_days": horizon,
                        "parameters_json": json.dumps(
                            {
                                "lookback_days": lookback_days,
                                "model_state": MODEL_STATES[model_version],
                                "validation_policy": {
                                    "split": "rolling_time_series",
                                    "gap_days": 0,
                                    "embargo_days": embargo_days,
                                    "label_horizon_days": horizon,
                                },
                            },
                            ensure_ascii=False,
                        ),
                        "metrics_json": None,
                    },
                )
                results = []
                for asset in assets:
                    asset_id = int(asset["id"])
                    prices = asset_histories[asset_id]
                    asset_category_key = _asset_category_key(asset)
                    for split in rolling_splits(prices, horizon_days=horizon, lookback_days=lookback_days, embargo_days=embargo_days):
                        history = prices[split["history_start_index"] : split["prediction_index"] + 1]
                        forecast = forecast_from_history(history, horizon_days=horizon, model_version=model_version)
                        actual_return = (prices[split["outcome_index"]].value / prices[split["prediction_index"]].value) - 1.0
                        start_date = prices[split["prediction_index"]].trade_date
                        outcome_date = prices[split["outcome_index"]].trade_date
                        cache_key = (asset_id, start_date, outcome_date)
                        if cache_key not in benchmark_cache:
                            benchmark_cache[cache_key] = select_asset_benchmark(conn, asset_id, start_date, outcome_date)
                        benchmark = benchmark_cache[cache_key]
                        result = score_forecast(
                            forecast.expected_return,
                            actual_return,
                            forecast.downside_risk,
                            benchmark_return=benchmark.benchmark_return,
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
                                        "outcome_date": outcome_date,
                                        **benchmark.details(),
                                        "model_version": model_version,
                                        "model_state": MODEL_STATES[model_version],
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        )
                        results.append(
                            result
                            | {
                                "actual_return": actual_return,
                                "predicted_return": forecast.expected_return,
                                "up_probability": forecast.up_probability,
                                "asset_type": asset["asset_type"],
                                "same_category_key": asset_category_key,
                            }
                        )

                metrics = aggregate_scores(
                    results,
                    validation_policy={
                        "split": "rolling_time_series",
                        "gap_days": 0,
                        "embargo_days": embargo_days,
                        "label_horizon_days": horizon,
                    },
                )
                metrics["model_state"] = MODEL_STATES[model_version]
                metrics_by_horizon[horizon] = metrics
                update_backtest_metrics(conn, run_id, json.dumps(metrics, ensure_ascii=False))
            metrics_by_model[model_version] = metrics_by_horizon

    result: dict[str, Any] = {"model_versions": list(model_versions), "models": metrics_by_model}
    if len(model_versions) == 1:
        result["model_version"] = model_versions[0]
        result["horizons"] = metrics_by_model[model_versions[0]]
    return result


def forecast_from_history(
    prices: list[PricePoint],
    horizon_days: int,
    lookback_days: int = DEFAULT_LOOKBACK,
    model_version: str = MODEL_VERSION,
) -> Forecast:
    if len(prices) < 2:
        raise BacktestError("At least two historical prices are required")

    history = prices[-lookback_days:]
    returns = daily_returns(history)
    volatility = stdev(returns) if len(returns) >= 2 else 0.0
    expected_return = forecast_expected_return(model_version, history, horizon_days)
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


def rolling_splits(prices: list[PricePoint], horizon_days: int, lookback_days: int, embargo_days: int = 0) -> list[dict[str, int]]:
    if lookback_days < 2:
        raise BacktestError("lookback_days must be at least 2")
    if embargo_days < 0:
        raise BacktestError("embargo_days must be non-negative")
    splits = []
    step = max(1, embargo_days + 1)
    for prediction_index in range(lookback_days - 1, len(prices) - horizon_days, step):
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


def aggregate_scores(
    results: list[dict[str, Any]],
    validation_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = validation_policy or {"split": "rolling_time_series", "gap_days": 0, "embargo_days": 0}
    if not results:
        return {
            "count": 0,
            "validation_status": "insufficient_sample",
            "validation_policy": policy,
            "direction_accuracy": None,
            "mean_return_error": None,
            "risk_hit_rate": None,
            "mean_benchmark_excess": None,
            "mean_drawdown_control": None,
            "mean_prediction_score": None,
            "mean_risk_score": None,
            "mean_advice_score": None,
            "mean_overall_score": None,
            "information_coefficient": None,
            "rank_ic": None,
            "bucket_spread": None,
            "asset_type_performance": {},
            "same_category_performance": {},
            "probability_calibration": [],
        }
    rank_ic = _rank_ic(results)
    bucket_spread = _bucket_spread(results)
    validation_status = _validation_status(len(results), rank_ic, bucket_spread)
    return {
        "count": len(results),
        "validation_status": validation_status,
        "validation_policy": policy,
        "direction_accuracy": mean(item["direction_hit"] for item in results),
        "mean_return_error": mean(item["return_error"] for item in results),
        "risk_hit_rate": mean(item["risk_hit"] for item in results),
        "mean_benchmark_excess": mean(item["benchmark_excess"] for item in results),
        "mean_drawdown_control": mean(item["drawdown_control"] for item in results),
        "mean_prediction_score": mean(item["prediction_score"] for item in results),
        "mean_risk_score": mean(item["risk_score"] for item in results),
        "mean_advice_score": mean(item["advice_score"] for item in results),
        "mean_overall_score": mean(item["overall_score"] for item in results),
        "information_coefficient": _pearson(
            [item["predicted_return"] for item in results],
            [item["actual_return"] for item in results],
        ),
        "rank_ic": rank_ic,
        "bucket_spread": bucket_spread,
        "asset_type_performance": _group_performance(results, "asset_type"),
        "same_category_performance": _group_performance(results, "same_category_key"),
        "probability_calibration": _probability_calibration(results),
    }


def _load_prices(conn: Any, asset_id: int) -> list[PricePoint]:
    return [
        PricePoint(asset_id=int(row["asset_id"]), trade_date=row["trade_date"], value=float(row["price_value"]))
        for row in list_price_history(conn, asset_id)
    ]


def _forecast_record(forecast: Forecast, model_version: str = MODEL_VERSION) -> dict[str, Any]:
    return {
        "asset_id": forecast.asset_id,
        "prediction_date": forecast.prediction_date,
        "horizon_days": forecast.horizon_days,
        "model_version": model_version,
        "target": "return",
        "up_probability": forecast.up_probability,
        "expected_return": forecast.expected_return,
        "expected_return_low": forecast.expected_return_low,
        "expected_return_high": forecast.expected_return_high,
        "downside_risk": forecast.downside_risk,
        "confidence": forecast.confidence,
        "input_window_start": forecast.input_window_start,
        "input_window_end": forecast.input_window_end,
        "assumptions": _model_assumptions(model_version),
    }


def _validate_model_versions(model_versions: tuple[str, ...]) -> None:
    unknown = [version for version in model_versions if version not in MODEL_VERSIONS]
    if unknown:
        raise BacktestError(f"Unknown model versions: {', '.join(unknown)}")


def _model_assumptions(model_version: str) -> str:
    assumptions = {
        MODEL_VERSION: "Baseline forecast uses only historical returns available through the prediction date.",
        "momentum_reversal_v1": "Candidate forecast blends short-term momentum with medium-term reversal; contextual evidence only.",
        "risk_adjusted_factor_v1": "Candidate forecast uses return, volatility penalty, and win-rate adjustment; contextual evidence only.",
    }
    return assumptions[model_version]


def _asset_category_key(asset: Any) -> str:
    theme = classify_asset_theme(
        code=asset["code"],
        name=asset["name"],
        asset_type=asset["asset_type"],
        fund_type=None,
    )
    return f"{asset['asset_type']}:{theme['key']}"


def _validation_status(count: int, rank_ic: float | None, bucket_spread: float | None) -> str:
    if count < 20:
        return "insufficient_sample"
    if rank_ic is None or bucket_spread is None:
        return "unvalidated"
    if rank_ic < 0 or bucket_spread < 0:
        return "degraded"
    return "validated"


def _rank_ic(results: list[dict[str, Any]]) -> float | None:
    predicted = [float(item["predicted_return"]) for item in results]
    actual = [float(item["actual_return"]) for item in results]
    return _pearson(_ranks(predicted), _ranks(actual))


def _bucket_spread(results: list[dict[str, Any]], bucket_fraction: float = 0.2) -> float | None:
    if len(results) < 5:
        return None
    ordered = sorted(results, key=lambda item: float(item["predicted_return"]), reverse=True)
    bucket_size = max(1, int(len(ordered) * bucket_fraction))
    top = ordered[:bucket_size]
    bottom = ordered[-bucket_size:]
    return mean(float(item["actual_return"]) for item in top) - mean(float(item["actual_return"]) for item in bottom)


def _group_performance(results: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        group_key = str(item.get(key) or "unknown")
        grouped.setdefault(group_key, []).append(item)
    return {
        group_key: {
            "count": len(items),
            "direction_accuracy": mean(item["direction_hit"] for item in items),
            "mean_return_error": mean(item["return_error"] for item in items),
            "rank_ic": _rank_ic(items),
            "bucket_spread": _bucket_spread(items),
        }
        for group_key, items in sorted(grouped.items())
    }


def _probability_calibration(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bins = [(0.0, 0.4), (0.4, 0.6), (0.6, 1.01)]
    output = []
    for low, high in bins:
        items = [item for item in results if item.get("up_probability") is not None and low <= float(item["up_probability"]) < high]
        if not items:
            continue
        predicted = mean(float(item["up_probability"]) for item in items)
        actual = mean(1.0 if float(item["actual_return"]) > 0 else 0.0 for item in items)
        output.append(
            {
                "bin": f"{low:.1f}-{min(high, 1.0):.1f}",
                "count": len(items),
                "mean_predicted_probability": predicted,
                "actual_positive_rate": actual,
                "calibration_error": abs(predicted - actual),
            }
        )
    return output


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_var = sum((x - left_mean) ** 2 for x in left)
    right_var = sum((y - right_mean) ** 2 for y in right)
    denominator = sqrt(left_var * right_var)
    if denominator == 0:
        return None
    return numerator / denominator


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        next_index = index + 1
        while next_index < len(ordered) and ordered[next_index][1] == ordered[index][1]:
            next_index += 1
        average_rank = (index + 1 + next_index) / 2
        for original_index, _ in ordered[index:next_index]:
            ranks[original_index] = average_rank
        index = next_index
    return ranks


def _direction(value: float) -> str:
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"
