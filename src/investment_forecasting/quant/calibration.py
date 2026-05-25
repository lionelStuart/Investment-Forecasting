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
from investment_forecasting.quant.forecast import MODEL_STATES, MODEL_VERSIONS, forecast_expected_return


CANDIDATE_VERSIONS = MODEL_VERSIONS
MODEL_GOVERNANCE_STATES = ("baseline", "candidate", "contextual", "promoted", "degraded", "retired")


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
        governance = build_model_governance_summary(metrics)
        metrics["governance"] = governance
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
                            | {
                                "predicted_return": predicted_return,
                                "actual_return": actual_return,
                                "up_probability": None,
                                "asset_type": "unknown",
                                "same_category_key": "unknown",
                            }
                        )
            metrics = aggregate_scores(results)
            metrics["model_state"] = MODEL_STATES[version]
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
            "mean_rank_ic": _avg(scores, "rank_ic"),
            "mean_bucket_spread": _avg(scores, "bucket_spread"),
            "model_state": MODEL_STATES[version],
            "stability": _stability([score["mean_overall_score"] for score in scores if score["mean_overall_score"] is not None]),
        }
    return {"aggregate": aggregate, "windows": window_summaries}


def candidate_prediction(version: str, history: list[PricePoint], horizon: int) -> float:
    try:
        return forecast_expected_return(version, history, horizon)
    except ValueError as exc:
        raise CalibrationError(str(exc)) from exc


def choose_promoted_version(metrics: dict[str, Any]) -> tuple[str | None, str]:
    governance = metrics.get("governance") or build_model_governance_summary(metrics)
    primary = governance["primary_decision"]
    return primary["primary_model_version"], primary["rationale"]


def build_model_governance_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    aggregate = metrics["aggregate"]
    viable = {
        version: values
        for version, values in aggregate.items()
        if values["windows"] > 0 and values["mean_overall_score"] is not None
    }
    baseline = viable.get("baseline_mean_v1")
    models = {}
    for version, values in aggregate.items():
        gates = _promotion_gate_results(version, values, baseline)
        state = _governance_state(version, values, gates)
        models[version] = {
            "model_version": version,
            "configured_state": MODEL_STATES.get(version, "candidate"),
            "governance_state": state,
            "promotion_gates": gates,
            "demotion_gates": _demotion_gate_results(values),
            "can_influence_jarvis_primary": state in {"baseline", "promoted"},
            "requires_product_review": version != "baseline_mean_v1" and all(gate["passed"] for gate in gates),
        }
    eligible_candidates = [
        version
        for version, summary in models.items()
        if version != "baseline_mean_v1" and summary["requires_product_review"]
    ]
    rationale = "baseline_mean_v1 remains the primary model; no candidate passed all promotion gates."
    if eligible_candidates:
        rationale = (
            f"{','.join(eligible_candidates)} passed quantitative gates, but product review is required before primary promotion."
        )
    if not viable:
        rationale = "No model produced enough out-of-sample validation evidence; no promotion is allowed."
    return {
        "states": list(MODEL_GOVERNANCE_STATES),
        "models": models,
        "primary_decision": {
            "primary_model_version": "baseline_mean_v1" if baseline else None,
            "decision": "hold_primary" if baseline else "no_primary_change",
            "rationale": rationale,
            "product_review_required_for_candidate_promotion": bool(eligible_candidates),
            "eligible_candidates": eligible_candidates,
        },
    }


def _promotion_gate_results(
    version: str,
    values: dict[str, Any],
    baseline: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    improvement = None
    if baseline and values.get("mean_overall_score") is not None and baseline.get("mean_overall_score") is not None:
        improvement = float(values["mean_overall_score"]) - float(baseline["mean_overall_score"])
    risk_delta = None
    if baseline and values.get("mean_risk_hit_rate") is not None and baseline.get("mean_risk_hit_rate") is not None:
        risk_delta = float(values["mean_risk_hit_rate"]) - float(baseline["mean_risk_hit_rate"])
    drawdown_delta = None
    if baseline and values.get("mean_drawdown_control") is not None and baseline.get("mean_drawdown_control") is not None:
        drawdown_delta = float(values["mean_drawdown_control"]) - float(baseline["mean_drawdown_control"])
    gates = [
        _gate("stored_validation_evidence", (values.get("windows") or 0) >= 2, values.get("windows")),
        _gate("beats_baseline_overall", version == "baseline_mean_v1" or (improvement is not None and improvement >= 2.0), improvement),
        _gate("positive_rank_ic", values.get("mean_rank_ic") is not None and float(values["mean_rank_ic"]) > 0, values.get("mean_rank_ic")),
        _gate("positive_bucket_spread", values.get("mean_bucket_spread") is not None and float(values["mean_bucket_spread"]) > 0, values.get("mean_bucket_spread")),
        _gate("risk_not_worse_than_baseline", version == "baseline_mean_v1" or (risk_delta is not None and risk_delta >= -0.03), risk_delta),
        _gate("drawdown_not_worse_than_baseline", version == "baseline_mean_v1" or (drawdown_delta is not None and drawdown_delta >= -0.03), drawdown_delta),
        _gate("stable_across_windows", values.get("stability") is not None and float(values["stability"]) >= 80, values.get("stability")),
    ]
    return gates


def _demotion_gate_results(values: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _gate("negative_rank_ic", values.get("mean_rank_ic") is not None and float(values["mean_rank_ic"]) < 0, values.get("mean_rank_ic")),
        _gate("negative_bucket_spread", values.get("mean_bucket_spread") is not None and float(values["mean_bucket_spread"]) < 0, values.get("mean_bucket_spread")),
        _gate("low_risk_hit_rate", values.get("mean_risk_hit_rate") is not None and float(values["mean_risk_hit_rate"]) < 0.55, values.get("mean_risk_hit_rate")),
        _gate("insufficient_windows", (values.get("windows") or 0) < 2, values.get("windows")),
    ]


def _governance_state(version: str, values: dict[str, Any], promotion_gates: list[dict[str, Any]]) -> str:
    if version == "baseline_mean_v1":
        return "baseline"
    if not values.get("windows"):
        return "candidate"
    if values.get("mean_rank_ic") is not None and float(values["mean_rank_ic"]) < 0:
        return "degraded"
    if values.get("mean_bucket_spread") is not None and float(values["mean_bucket_spread"]) < 0:
        return "degraded"
    if all(gate["passed"] for gate in promotion_gates):
        return "contextual"
    return "contextual"


def _gate(name: str, passed: bool, value: Any) -> dict[str, Any]:
    return {"gate": name, "passed": bool(passed), "value": value}


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
