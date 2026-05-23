from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from investment_forecasting.db import connect, init_db, list_assets, list_price_history, upsert_calibration_report
from investment_forecasting.data.ingestion import ingest_mvp_universe
from investment_forecasting.quant.backtest import aggregate_scores, score_forecast
from investment_forecasting.quant.features import calculate_features_for_db
from investment_forecasting.quant.features import PricePoint


CANDIDATE_VERSIONS = ("baseline_mean_v1", "momentum_last_return_v1")


class CalibrationError(RuntimeError):
    """Raised when model calibration cannot be evaluated."""


@dataclass(frozen=True)
class CalibrationWindow:
    name: str
    start_index: int
    end_index: int
    start_date: str
    end_date: str


def run_calibration_report(
    db_path: str | Path,
    report_date: str | None = None,
    horizons: tuple[int, ...] = (5, 20, 60),
    lookback_days: int = 60,
) -> dict[str, Any]:
    init_db(db_path)
    target_date = _date_text(report_date) if report_date else date.today().isoformat()
    with connect(db_path) as conn:
        histories = {
            int(asset["id"]): [
                PricePoint(asset_id=int(row["asset_id"]), trade_date=row["trade_date"], value=float(row["price_value"]))
                for row in list_price_history(conn, int(asset["id"]))
            ]
            for asset in list_assets(conn)
        }
        histories = {asset_id: prices for asset_id, prices in histories.items() if len(prices) >= lookback_days + min(horizons) + 1}
        if not histories:
            raise CalibrationError("Not enough stored price history for calibration")

        reference_history = max(histories.values(), key=len)
        windows = build_calibration_windows(len(reference_history), min_required=lookback_days + max(horizons) + 1)
        windows = [
            CalibrationWindow(
                name=window.name,
                start_index=window.start_index,
                end_index=window.end_index,
                start_date=reference_history[window.start_index].trade_date,
                end_date=reference_history[window.end_index].trade_date,
            )
            for window in windows
        ]
        metrics = evaluate_candidates(histories, windows, horizons=horizons, lookback_days=lookback_days)
        promoted_version, rationale = choose_promoted_version(metrics)
        report = {
            "report_date": target_date,
            "candidate_versions": ",".join(CANDIDATE_VERSIONS),
            "promoted_version": promoted_version,
            "windows_json": json.dumps([window.__dict__ for window in windows], ensure_ascii=False),
            "metrics_json": json.dumps(metrics, ensure_ascii=False),
            "rationale": rationale,
        }
        report_id = upsert_calibration_report(conn, report)

    return {"report_id": report_id, **report}


def run_historical_calibration_corpus(
    db_path: str | Path,
    start_date: str,
    end_date: str,
    report_date: str | None = None,
    horizons: tuple[int, ...] = (5, 20, 60),
    lookback_days: int = 60,
    skip_ingest: bool = False,
) -> dict[str, Any]:
    ingest_summary = {"skipped": True} if skip_ingest else ingest_mvp_universe(db_path, start_date=start_date, end_date=end_date)
    feature_summary = calculate_features_for_db(db_path, start_date=start_date, end_date=end_date)
    report = run_calibration_report(
        db_path,
        report_date=report_date or _date_text(end_date),
        horizons=horizons,
        lookback_days=lookback_days,
    )
    return {"ingest": ingest_summary, "features": feature_summary, "calibration": report}


def build_calibration_windows(length: int, min_required: int) -> list[CalibrationWindow]:
    if length < min_required:
        raise CalibrationError("Not enough observations for one calibration window")
    if length >= min_required * 3:
        chunk = length // 3
        ranges = [(0, chunk - 1), (chunk, chunk * 2 - 1), (chunk * 2, length - 1)]
    elif length >= min_required * 2:
        chunk = length // 2
        ranges = [(0, chunk - 1), (chunk, length - 1)]
    else:
        ranges = [(0, length - 1)]
    return [
        CalibrationWindow(name=f"sample_{index + 1}", start_index=start, end_index=end, start_date="", end_date="")
        for index, (start, end) in enumerate(ranges)
    ]


def evaluate_candidates(
    histories: dict[int, list[PricePoint]],
    windows: list[CalibrationWindow],
    horizons: tuple[int, ...],
    lookback_days: int,
) -> dict[str, Any]:
    candidate_scores: dict[str, list[dict[str, float]]] = {version: [] for version in CANDIDATE_VERSIONS}
    benchmark_by_date = _benchmark_by_date(histories)
    window_summaries = []

    for window in windows:
        window_metrics: dict[str, Any] = {"name": window.name, "candidates": {}}
        for version in CANDIDATE_VERSIONS:
            results = []
            for prices in histories.values():
                bounded = prices[window.start_index : min(window.end_index + 1, len(prices))]
                if len(bounded) < lookback_days + min(horizons) + 1:
                    continue
                for horizon in horizons:
                    for prediction_index in range(lookback_days - 1, len(bounded) - horizon):
                        history = bounded[prediction_index - lookback_days + 1 : prediction_index + 1]
                        predicted_return = candidate_prediction(version, history, horizon)
                        actual_return = (bounded[prediction_index + horizon].value / bounded[prediction_index].value) - 1.0
                        start_date = bounded[prediction_index].trade_date
                        end_date = bounded[prediction_index + horizon].trade_date
                        benchmark_return = _aligned_benchmark_return(benchmark_by_date, start_date, end_date)
                        results.append(
                            score_forecast(
                                predicted_return,
                                actual_return,
                                min(0.0, predicted_return),
                                benchmark_return=benchmark_return,
                            )
                        )
            metrics = aggregate_scores(results)
            window_metrics["candidates"][version] = metrics
            if metrics["count"]:
                candidate_scores[version].append(metrics)
        window_summaries.append(window_metrics)

    aggregate = {}
    for version, scores in candidate_scores.items():
        aggregate[version] = {
            "windows": len(scores),
            "mean_overall_score": _avg(scores, "mean_overall_score"),
            "mean_direction_accuracy": _avg(scores, "direction_accuracy"),
            "mean_return_error": _avg(scores, "mean_return_error"),
            "mean_risk_hit_rate": _avg(scores, "risk_hit_rate"),
            "mean_benchmark_excess": _avg(scores, "mean_benchmark_excess"),
            "mean_drawdown_control": _avg(scores, "mean_drawdown_control"),
            "stability": _stability([score["mean_overall_score"] for score in scores if score["mean_overall_score"] is not None]),
        }
    return {"aggregate": aggregate, "windows": window_summaries}


def candidate_prediction(version: str, history: list[PricePoint], horizon: int) -> float:
    returns = [(history[index].value / history[index - 1].value) - 1.0 for index in range(1, len(history))]
    if version == "baseline_mean_v1":
        return mean(returns) * horizon
    if version == "momentum_last_return_v1":
        return returns[-1] * horizon
    raise CalibrationError(f"Unknown candidate model: {version}")


def choose_promoted_version(metrics: dict[str, Any]) -> tuple[str | None, str]:
    aggregate = metrics["aggregate"]
    viable = {
        version: values
        for version, values in aggregate.items()
        if values["windows"] > 0 and values["mean_overall_score"] is not None
    }
    if not viable:
        return None, "No candidate produced enough out-of-sample backtest results."
    ranked = sorted(
        viable.items(),
        key=lambda item: (
            item[1]["mean_overall_score"] or 0,
            item[1]["mean_risk_hit_rate"] or 0,
            item[1]["stability"] or 0,
        ),
        reverse=True,
    )
    winner, values = ranked[0]
    baseline = viable.get("baseline_mean_v1")
    if winner != "baseline_mean_v1" and baseline:
        improvement = (values["mean_overall_score"] or 0) - (baseline["mean_overall_score"] or 0)
        if improvement < 2.0:
            return "baseline_mean_v1", "Candidate improvement was below the 2 point promotion threshold, so the baseline remains promoted."
    return winner, f"{winner} had the strongest combined overall score, risk hit rate, and stability across available windows."


def _avg(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return mean(values) if values else None


def _stability(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return 100.0
    return max(0.0, 100.0 - stdev(values))


def _benchmark_by_date(histories: dict[int, list[PricePoint]]) -> dict[str, float]:
    for prices in histories.values():
        if prices and prices[0].asset_id:
            # Prefer the first history whose asset code is unavailable here but
            # whose dates can still serve as a conservative market proxy in
            # fixture tests. Live reports include 沪深300 as the first indexed
            # universe asset.
            return {price.trade_date: price.value for price in prices}
    return {}


def _aligned_benchmark_return(benchmark_by_date: dict[str, float], start_date: str, end_date: str) -> float | None:
    if start_date not in benchmark_by_date or end_date not in benchmark_by_date:
        return None
    return (benchmark_by_date[end_date] / benchmark_by_date[start_date]) - 1.0


def _date_text(value: str | None) -> str:
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value or date.today().isoformat()
