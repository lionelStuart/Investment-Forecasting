from __future__ import annotations

import json
from datetime import date
from statistics import mean
from pathlib import Path
from typing import Any

from investment_forecasting.db import (
    complete_task_log,
    connect,
    init_db,
    start_task_log,
    upsert_model_monitoring_report,
)
from investment_forecasting.quant.forecast import MODEL_STATES


class ModelMonitoringError(RuntimeError):
    """Raised when model monitoring cannot be produced from stored evidence."""


def run_model_monitoring_report(db_path: str | Path, report_date: str | None = None) -> dict[str, Any]:
    init_db(db_path)
    target_date = _date_text(report_date) if report_date else date.today().isoformat()
    with connect(db_path) as conn:
        log_id = start_task_log(
            conn,
            task_name="model_monitoring",
            run_date=target_date,
            message=f"Generating model monitoring report for {target_date}",
        )
        try:
            reports = build_model_monitoring_reports(conn, target_date)
            if not reports:
                raise ModelMonitoringError("Cannot monitor models without backtest_runs evidence")
            report_ids = []
            for report in reports:
                report_ids.append(upsert_model_monitoring_report(conn, report))
            complete_task_log(
                conn,
                log_id,
                status="success",
                message=json.dumps({"report_ids": report_ids, "count": len(report_ids)}, ensure_ascii=False),
            )
            return {"report_date": target_date, "count": len(report_ids), "reports": reports, "report_ids": report_ids}
        except Exception as exc:
            complete_task_log(conn, log_id, status="failed", error=str(exc))
            conn.commit()
            raise


def build_model_monitoring_reports(conn: Any, report_date: str) -> list[dict[str, Any]]:
    versions = [
        row["model_version"]
        for row in conn.execute(
            """
            SELECT DISTINCT model_version
            FROM backtest_runs
            ORDER BY model_version
            """
        ).fetchall()
    ]
    return [_model_report(conn, report_date, version) for version in versions]


def _model_report(conn: Any, report_date: str, model_version: str) -> dict[str, Any]:
    runs = [
        dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM backtest_runs
            WHERE model_version = ?
            ORDER BY end_date DESC, created_at DESC, id DESC
            """,
            (model_version,),
        ).fetchall()
    ]
    latest_runs = _latest_run_per_horizon(runs)
    previous_runs = runs[len(latest_runs) : len(latest_runs) * 2] if latest_runs else []
    latest_metrics = [_metrics(row) for row in latest_runs]
    previous_metrics = [_metrics(row) for row in previous_runs]
    latest_prediction_date = _latest_prediction_date(conn, model_version)
    latest_backtest_end_date = max((row["end_date"] for row in latest_runs if row.get("end_date")), default=None)
    prediction_staleness_days = _days_between(latest_prediction_date, report_date)
    backtest_staleness_days = _days_between(latest_backtest_end_date, report_date)

    mean_prediction_score = _avg(latest_metrics, "mean_prediction_score")
    mean_risk_score = _avg(latest_metrics, "mean_risk_score")
    mean_benchmark_excess = _avg(latest_metrics, "mean_benchmark_excess")
    mean_overall_score = _avg(latest_metrics, "mean_overall_score")
    mean_rank_ic = _avg(latest_metrics, "rank_ic")
    mean_bucket_spread = _avg(latest_metrics, "bucket_spread")
    previous_overall = _avg(previous_metrics, "mean_overall_score")
    score_drift = (mean_overall_score - previous_overall) if mean_overall_score is not None and previous_overall is not None else None
    warnings = _warnings(
        prediction_staleness_days=prediction_staleness_days,
        backtest_staleness_days=backtest_staleness_days,
        mean_prediction_score=mean_prediction_score,
        mean_risk_score=mean_risk_score,
        mean_benchmark_excess=mean_benchmark_excess,
        mean_overall_score=mean_overall_score,
        mean_rank_ic=mean_rank_ic,
        mean_bucket_spread=mean_bucket_spread,
        score_drift=score_drift,
        latest_metrics=latest_metrics,
    )
    status = _status(warnings)
    metrics = {
        "latest_run_ids": [int(row["id"]) for row in latest_runs],
        "latest_horizons": [int(row["horizon_days"]) for row in latest_runs],
        "sample_count": sum(int(metric.get("count") or 0) for metric in latest_metrics),
        "mean_rank_ic": mean_rank_ic,
        "mean_bucket_spread": mean_bucket_spread,
        "validation_statuses": [metric.get("validation_status") for metric in latest_metrics if metric.get("validation_status")],
        "validation_policies": [metric.get("validation_policy") for metric in latest_metrics if metric.get("validation_policy")],
        "previous_overall_score": previous_overall,
        "warnings": warnings,
    }
    metrics["governance"] = _monitoring_governance_state(
        model_version=model_version,
        status=status,
        warnings=warnings,
        latest_metrics=latest_metrics,
    )
    return {
        "report_date": report_date,
        "model_version": model_version,
        "status": status,
        "latest_prediction_date": latest_prediction_date,
        "latest_backtest_end_date": latest_backtest_end_date,
        "prediction_staleness_days": prediction_staleness_days,
        "backtest_staleness_days": backtest_staleness_days,
        "mean_prediction_score": mean_prediction_score,
        "mean_risk_score": mean_risk_score,
        "mean_benchmark_excess": mean_benchmark_excess,
        "mean_overall_score": mean_overall_score,
        "score_drift": score_drift,
        "metrics_json": json.dumps(metrics, ensure_ascii=False),
        "warnings_json": json.dumps(warnings, ensure_ascii=False),
    }


def _latest_run_per_horizon(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[int, dict[str, Any]] = {}
    for row in runs:
        horizon = int(row["horizon_days"])
        if horizon not in latest:
            latest[horizon] = row
    return list(latest.values())


def _metrics(row: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(row.get("metrics_json") or "{}")
    except json.JSONDecodeError:
        return {}


def _latest_prediction_date(conn: Any, model_version: str) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(prediction_date) AS prediction_date
        FROM model_predictions
        WHERE model_version = ?
        """,
        (model_version,),
    ).fetchone()
    return row["prediction_date"] if row else None


def _warnings(
    *,
    prediction_staleness_days: int | None,
    backtest_staleness_days: int | None,
    mean_prediction_score: float | None,
    mean_risk_score: float | None,
    mean_benchmark_excess: float | None,
    mean_overall_score: float | None,
    mean_rank_ic: float | None,
    mean_bucket_spread: float | None,
    score_drift: float | None,
    latest_metrics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if prediction_staleness_days is None or prediction_staleness_days > 5:
        warnings.append({"severity": "warning", "code": "stale_predictions", "value": prediction_staleness_days})
    if backtest_staleness_days is None or backtest_staleness_days > 30:
        warnings.append({"severity": "warning", "code": "stale_backtests", "value": backtest_staleness_days})
    if mean_overall_score is not None and mean_overall_score < 55:
        warnings.append({"severity": "degraded", "code": "low_overall_score", "value": mean_overall_score})
    if mean_prediction_score is not None and mean_prediction_score < 55:
        warnings.append({"severity": "degraded", "code": "low_prediction_score", "value": mean_prediction_score})
    if mean_risk_score is not None and mean_risk_score < 55:
        warnings.append({"severity": "degraded", "code": "low_risk_score", "value": mean_risk_score})
    if mean_benchmark_excess is not None and mean_benchmark_excess < -0.02:
        warnings.append({"severity": "warning", "code": "negative_benchmark_excess", "value": mean_benchmark_excess})
    if score_drift is not None and score_drift < -5:
        warnings.append({"severity": "warning", "code": "score_drift", "value": score_drift})
    if any(metric.get("validation_status") == "insufficient_sample" for metric in latest_metrics):
        warnings.append({"severity": "warning", "code": "insufficient_validation_sample", "value": None})
    if mean_rank_ic is not None and mean_rank_ic < 0:
        warnings.append({"severity": "degraded", "code": "negative_rank_ic", "value": mean_rank_ic})
    if mean_bucket_spread is not None and mean_bucket_spread < 0:
        warnings.append({"severity": "degraded", "code": "negative_bucket_spread", "value": mean_bucket_spread})
    return warnings


def _status(warnings: list[dict[str, Any]]) -> str:
    if any(item["severity"] == "degraded" for item in warnings):
        return "degraded"
    if warnings:
        return "warning"
    return "ok"


def _monitoring_governance_state(
    *,
    model_version: str,
    status: str,
    warnings: list[dict[str, Any]],
    latest_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    warning_codes = {item["code"] for item in warnings}
    configured = MODEL_STATES.get(model_version, "candidate")
    if model_version == "baseline_mean_v1":
        state = "baseline"
    elif status == "degraded" or {"negative_rank_ic", "negative_bucket_spread"} & warning_codes:
        state = "degraded"
    elif not latest_metrics:
        state = "candidate"
    else:
        state = "contextual"
    promotion_blockers = sorted(
        code
        for code in warning_codes
        if code
        in {
            "stale_predictions",
            "stale_backtests",
            "low_overall_score",
            "low_prediction_score",
            "negative_rank_ic",
            "negative_bucket_spread",
            "insufficient_validation_sample",
        }
    )
    return {
        "model_version": model_version,
        "configured_state": configured,
        "governance_state": state,
        "promotion_allowed": state == "promoted",
        "jarvis_primary_allowed": state in {"baseline", "promoted"},
        "promotion_blockers": promotion_blockers,
        "demotion_reasons": promotion_blockers if state == "degraded" else [],
        "product_review_required_for_promotion": configured != "baseline",
    }


def summarize_model_governance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    models = {}
    for row in rows:
        metrics = row.get("metrics")
        if metrics is None:
            try:
                metrics = json.loads(row.get("metrics_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                metrics = {}
        governance = metrics.get("governance") or {}
        if governance:
            models[row["model_version"]] = governance
    primary = "baseline_mean_v1" if "baseline_mean_v1" in models else None
    return {
        "primary_model_version": primary,
        "models": models,
        "decision": "hold_primary" if primary else "no_primary_available",
        "rationale": "baseline_mean_v1 remains primary until a candidate passes promotion gates and product review.",
    }


def _avg(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return mean(values) if values else None


def _days_between(start: str | None, end: str) -> int | None:
    if not start:
        return None
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _date_text(value: str | None) -> str:
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value or date.today().isoformat()
