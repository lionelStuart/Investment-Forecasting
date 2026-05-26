from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import median, mean
from typing import Any

from investment_forecasting.data.classification import classify_asset_theme
from investment_forecasting.db import (
    connect,
    init_db,
    list_assets,
    list_model_applicability_profiles,
    list_model_governance_reviews,
    list_model_health_metrics,
    list_model_shadow_routes,
    list_price_history,
    upsert_model_applicability_profile,
    upsert_model_governance_review,
    upsert_model_health_metric,
    upsert_model_shadow_route,
)
from investment_forecasting.quant.backtest import aggregate_scores, forecast_from_history, score_forecast
from investment_forecasting.quant.benchmarks import select_asset_benchmark
from investment_forecasting.quant.features import PricePoint
from investment_forecasting.quant.forecast import MODEL_STATES, MODEL_VERSIONS


DEFAULT_HORIZONS = (5, 20, 60)
DEFAULT_MODEL_VERSIONS = MODEL_VERSIONS
DEFAULT_LOOKBACK_DAYS = 60
PRIMARY_MODEL_VERSION = "baseline_mean_v1"
SHADOW_ROUTE_NAME = "router_floor70_cap05"
SHADOW_ROUTE_HORIZON = 20
SHADOW_ROUTE_MODELS = ("baseline_mean_v1", "momentum_reversal_v1", "risk_adjusted_factor_v1")
SHADOW_BASELINE_FLOOR = 0.70
SHADOW_MONTHLY_TURNOVER_CAP = 0.05
SHADOW_INITIAL_WEIGHTS = {
    "baseline_mean_v1": 0.90,
    "momentum_reversal_v1": 0.05,
    "risk_adjusted_factor_v1": 0.05,
}


class ModelValidationError(RuntimeError):
    """Raised when replay validation cannot be completed safely."""


def replay_ytd_predictions(
    db_path: str | Path,
    *,
    year: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    model_versions: tuple[str, ...] = DEFAULT_MODEL_VERSIONS,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    asset_scope: str = "all",
) -> dict[str, Any]:
    init_db(db_path)
    target_year = int(year or date.today().year)
    start = _date_text(start_date) if start_date else f"{target_year}-01-01"
    end = _date_text(end_date) if end_date else date.today().isoformat()
    _validate_model_versions(model_versions)
    if lookback_days < 2:
        raise ModelValidationError("lookback_days must be at least 2")

    run_key = _run_key(target_year, start, end, horizons, model_versions, lookback_days, asset_scope)
    with connect(db_path) as conn:
        run_id = _upsert_replay_run(
            conn,
            {
                "run_key": run_key,
                "year": target_year,
                "start_date": start,
                "end_date": end,
                "horizons_json": json.dumps(list(horizons)),
                "model_versions_json": json.dumps(list(model_versions)),
                "lookback_days": lookback_days,
                "asset_scope": asset_scope,
                "status": "running",
                "metrics_json": None,
                "tuning_recommendations_json": None,
                "error": None,
            },
        )
        try:
            assets = [dict(row) for row in list_assets(conn)]
            if asset_scope != "all":
                assets = [asset for asset in assets if asset["asset_type"] == asset_scope]
            if not assets:
                raise ModelValidationError(f"No assets found for replay scope: {asset_scope}")

            written = {"matured": 0, "pending": 0, "skipped": 0}
            for asset in assets:
                prices = _load_prices(conn, int(asset["id"]))
                if len(prices) < 2:
                    written["skipped"] += _persist_skipped_placeholders(
                        conn, run_id, asset, start, horizons, model_versions, "insufficient_price_history"
                    )
                    continue
                price_dates = [point.trade_date for point in prices]
                date_to_index = {point.trade_date: index for index, point in enumerate(prices)}
                replay_dates = [value for value in price_dates if start <= value <= end]
                for prediction_date in replay_dates:
                    prediction_index = date_to_index[prediction_date]
                    history = prices[: prediction_index + 1]
                    for model_version in model_versions:
                        for horizon in horizons:
                            if len(history) < 2:
                                status = _upsert_replay_prediction(
                                    conn,
                                    _skipped_prediction(run_id, asset, prediction_date, horizon, model_version, "insufficient_history"),
                                )
                                written[status] += 1
                                continue
                            forecast = forecast_from_history(
                                history,
                                horizon_days=horizon,
                                lookback_days=lookback_days,
                                model_version=model_version,
                            )
                            outcome_index = prediction_index + horizon
                            record = _replay_record(run_id, asset, forecast, model_version)
                            if outcome_index < len(prices):
                                outcome = prices[outcome_index]
                                actual_return = (outcome.value / prices[prediction_index].value) - 1.0
                                benchmark = select_asset_benchmark(conn, int(asset["id"]), prediction_date, outcome.trade_date)
                                score = score_forecast(
                                    forecast.expected_return,
                                    actual_return,
                                    forecast.downside_risk,
                                    benchmark_return=benchmark.benchmark_return,
                                )
                                record.update(
                                    {
                                        "outcome_date": outcome.trade_date,
                                        "actual_return": actual_return,
                                        "benchmark_return": benchmark.benchmark_return,
                                        "benchmark_identity": benchmark.identity,
                                        "benchmark_source": benchmark.source,
                                        "prediction_score": score["prediction_score"],
                                        "risk_score": score["risk_score"],
                                        "advice_score": score["advice_score"],
                                        "overall_score": score["overall_score"],
                                        "score_status": "matured",
                                        "skip_reason": None,
                                        "details_json": json.dumps(
                                            {
                                                **score,
                                                **benchmark.details(),
                                                "asset_type": asset["asset_type"],
                                                "same_category_key": _asset_category_key(asset),
                                                "model_state": MODEL_STATES[model_version],
                                                "point_in_time": {
                                                    "history_ended_at": forecast.input_window_end,
                                                    "prediction_date": prediction_date,
                                                },
                                            },
                                            ensure_ascii=False,
                                        ),
                                    }
                                )
                            else:
                                record.update(
                                    {
                                        "outcome_date": None,
                                        "actual_return": None,
                                        "benchmark_return": None,
                                        "benchmark_identity": None,
                                        "benchmark_source": None,
                                        "prediction_score": None,
                                        "risk_score": None,
                                        "advice_score": None,
                                        "overall_score": None,
                                        "score_status": "pending",
                                        "skip_reason": "outcome_not_available",
                                        "details_json": json.dumps(
                                            {
                                                "asset_type": asset["asset_type"],
                                                "same_category_key": _asset_category_key(asset),
                                                "model_state": MODEL_STATES[model_version],
                                                "point_in_time": {
                                                    "history_ended_at": forecast.input_window_end,
                                                    "prediction_date": prediction_date,
                                                },
                                            },
                                            ensure_ascii=False,
                                        ),
                                    }
                                )
                            status = _upsert_replay_prediction(conn, record)
                            written[status] += 1

            metrics = build_replay_report(conn, run_id=run_id)
            _finish_replay_run(conn, run_id, status="success", metrics=metrics, error=None)
        except Exception as exc:
            _finish_replay_run(conn, run_id, status="failed", metrics=None, error=str(exc))
            raise

    return {"run_id": run_id, "run_key": run_key, "year": target_year, "start_date": start, "end_date": end, "written": written, "metrics": metrics}


def build_replay_report(db_or_conn: str | Path | Any, *, run_id: int | None = None) -> dict[str, Any]:
    close_after = False
    if hasattr(db_or_conn, "execute"):
        conn = db_or_conn
    else:
        init_db(db_or_conn)
        conn = connect(db_or_conn)
        close_after = True
    try:
        resolved_run_id = run_id or _latest_replay_run_id(conn)
        if resolved_run_id is None:
            raise ModelValidationError("No model replay run found")
        rows = [dict(row) for row in _replay_rows(conn, resolved_run_id)]
        metrics = _aggregate_replay_metrics(rows)
        conn.execute(
            "UPDATE model_replay_runs SET metrics_json = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(metrics, ensure_ascii=False), resolved_run_id),
        )
        return {"run_id": resolved_run_id, **metrics}
    finally:
        if close_after:
            conn.commit()
            conn.close()


def build_tuning_plan(db_path: str | Path, *, run_id: int | None = None) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        resolved_run_id = run_id or _latest_replay_run_id(conn)
        if resolved_run_id is None:
            raise ModelValidationError("No model replay run found")
        row = conn.execute("SELECT metrics_json FROM model_replay_runs WHERE id = ?", (resolved_run_id,)).fetchone()
        metrics = json.loads(row["metrics_json"]) if row and row["metrics_json"] else build_replay_report(conn, run_id=resolved_run_id)
        recommendations = _recommendations_from_metrics(metrics)
        conn.execute(
            "UPDATE model_replay_runs SET tuning_recommendations_json = ?, updated_at = datetime('now') WHERE id = ?",
            (json.dumps(recommendations, ensure_ascii=False), resolved_run_id),
        )
    return {"run_id": resolved_run_id, "recommendations": recommendations}


def generate_model_health_metrics(db_or_conn: str | Path | Any, *, run_id: int | None = None) -> dict[str, Any]:
    close_after = False
    if hasattr(db_or_conn, "execute"):
        conn = db_or_conn
    else:
        init_db(db_or_conn)
        conn = connect(db_or_conn)
        close_after = True
    try:
        resolved_run_id = run_id or _latest_replay_run_id(conn)
        if resolved_run_id is None:
            raise ModelValidationError("No model replay run found")
        rows = [dict(row) for row in _replay_rows(conn, resolved_run_id)]
        matured = [row for row in rows if row["score_status"] == "matured"]
        facts = _model_health_facts(resolved_run_id, matured, total_replay_rows=len(rows))
        metric_ids = [upsert_model_health_metric(conn, fact) for fact in facts]
        return {
            "run_id": resolved_run_id,
            "written": len(metric_ids),
            "matured_rows": len(matured),
            "pending_rows": sum(1 for row in rows if row["score_status"] == "pending"),
            "skipped_rows": sum(1 for row in rows if row["score_status"] == "skipped"),
        }
    finally:
        if close_after:
            conn.commit()
            conn.close()


def build_model_health_report(db_path: str | Path, *, run_id: int | None = None) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        resolved_run_id = run_id or _latest_replay_run_id(conn)
        if resolved_run_id is None:
            raise ModelValidationError("No model replay run found")
        rows = [dict(row) for row in list_model_health_metrics(conn, resolved_run_id)]
        if not rows:
            generate_model_health_metrics(conn, run_id=resolved_run_id)
            rows = [dict(row) for row in list_model_health_metrics(conn, resolved_run_id)]
    by_status: dict[str, int] = defaultdict(int)
    by_scope: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_status[str(row["status"])] += 1
        key = f"{row['model_version']}|{row['horizon_days']}|{row['asset_type']}|{row['same_category_key']}|{row['prediction_month']}|{row['evaluation_window']}"
        by_scope[key] = {
            "sample_count": row["sample_count"],
            "direction_accuracy": row["direction_accuracy"],
            "rank_ic": row["rank_ic"],
            "bucket_spread": row["bucket_spread"],
            "top_bottom_decile_spread": row["top_bottom_decile_spread"],
            "mae": row["mae"],
            "median_abs_error": row["median_abs_error"],
            "raw_high_conf_wrong_rate": row["raw_high_conf_wrong_rate"],
            "coverage_rate": row["coverage_rate"],
            "status": row["status"],
            "output_role": row["output_role"],
            "promotion_status": row["promotion_status"],
            "degradation_reason": row["degradation_reason"],
            "minimum_sample_met": bool(row["minimum_sample_met"]),
            "consumer_display_level": row["consumer_display_level"],
            "confidence_label": row["confidence_label"],
            "confidence_rationale": json.loads(row["confidence_rationale_json"] or "{}"),
        }
    return {
        "run_id": resolved_run_id,
        "count": len(rows),
        "by_status": dict(sorted(by_status.items())),
        "by_scope": by_scope,
    }


def generate_applicability_profiles(db_or_conn: str | Path | Any, *, run_id: int | None = None) -> dict[str, Any]:
    close_after = False
    if hasattr(db_or_conn, "execute"):
        conn = db_or_conn
    else:
        init_db(db_or_conn)
        conn = connect(db_or_conn)
        close_after = True
    try:
        resolved_run_id = run_id or _latest_replay_run_id(conn)
        if resolved_run_id is None:
            raise ModelValidationError("No model replay run found")
        metrics = [dict(row) for row in list_model_health_metrics(conn, resolved_run_id)]
        if not metrics:
            generate_model_health_metrics(conn, run_id=resolved_run_id)
            metrics = [dict(row) for row in list_model_health_metrics(conn, resolved_run_id)]
        profiles = [_applicability_profile_from_metric(metric) for metric in metrics]
        profile_ids = [upsert_model_applicability_profile(conn, profile) for profile in profiles]
        by_role: dict[str, int] = defaultdict(int)
        disabled = 0
        for profile in profiles:
            by_role[str(profile["output_role"])] += 1
            disabled += int(profile["ranking_disabled"])
        return {
            "run_id": resolved_run_id,
            "written": len(profile_ids),
            "by_role": dict(sorted(by_role.items())),
            "ranking_disabled": disabled,
        }
    finally:
        if close_after:
            conn.commit()
            conn.close()


def build_applicability_report(db_path: str | Path, *, run_id: int | None = None) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        resolved_run_id = run_id or _latest_replay_run_id(conn)
        if resolved_run_id is None:
            raise ModelValidationError("No model replay run found")
        rows = [dict(row) for row in list_model_applicability_profiles(conn, resolved_run_id)]
        if not rows:
            generate_applicability_profiles(conn, run_id=resolved_run_id)
            rows = [dict(row) for row in list_model_applicability_profiles(conn, resolved_run_id)]
    by_role: dict[str, int] = defaultdict(int)
    by_scope: dict[str, dict[str, Any]] = {}
    disabled = 0
    for row in rows:
        by_role[str(row["output_role"])] += 1
        disabled += int(row["ranking_disabled"])
        key = f"{row['model_version']}|{row['horizon_days']}|{row['asset_type']}|{row['same_category_key']}|{row['prediction_month']}|{row['evaluation_window']}"
        by_scope[key] = {
            "source_metric_id": row["source_metric_id"],
            "output_role": row["output_role"],
            "ranking_disabled": bool(row["ranking_disabled"]),
            "ranking_disable_reason": row["ranking_disable_reason"],
            "promotion_status": row["promotion_status"],
            "degradation_reason": row["degradation_reason"],
            "minimum_sample_met": bool(row["minimum_sample_met"]),
            "consumer_display_level": row["consumer_display_level"],
            "confidence_label": row["confidence_label"],
            "confidence_rationale": json.loads(row["confidence_rationale_json"] or "{}"),
            "rationale": json.loads(row["rationale_json"] or "{}"),
        }
    return {
        "run_id": resolved_run_id,
        "count": len(rows),
        "by_role": dict(sorted(by_role.items())),
        "ranking_disabled": disabled,
        "by_scope": by_scope,
    }


def run_shadow_router_floor70(db_or_conn: str | Path | Any, *, run_id: int | None = None) -> dict[str, Any]:
    close_after = False
    if hasattr(db_or_conn, "execute"):
        conn = db_or_conn
    else:
        init_db(db_or_conn)
        conn = connect(db_or_conn)
        close_after = True
    try:
        resolved_run_id = run_id or _latest_replay_run_id(conn)
        if resolved_run_id is None:
            raise ModelValidationError("No model replay run found")
        rows = _shadow_candidate_rows(conn, resolved_run_id)
        months = sorted({str(row["month"]) for row in rows if row["score_status"] == "matured"})
        if not months:
            raise ModelValidationError("No matured 20-day replay rows found for shadow routing")
        weights = dict(SHADOW_INITIAL_WEIGHTS)
        route_ids = []
        for month in months:
            training_cutoff = f"{month}-01"
            train_rows = [
                row
                for row in rows
                if row["score_status"] == "matured"
                and row["outcome_date"] is not None
                and str(row["outcome_date"]) < training_cutoff
            ]
            target_weights = _shadow_target_weights(train_rows)
            weights, turnover = _apply_turnover_cap(weights, target_weights, SHADOW_MONTHLY_TURNOVER_CAP)
            holdout_rows = [row for row in rows if row["score_status"] == "matured" and row["month"] == month]
            shadow_metrics, baseline_metrics, comparison = _shadow_month_metrics(holdout_rows, weights)
            if not shadow_metrics["count"]:
                continue
            route_ids.append(
                upsert_model_shadow_route(
                    conn,
                    {
                        "replay_run_id": resolved_run_id,
                        "route_name": SHADOW_ROUTE_NAME,
                        "horizon_days": SHADOW_ROUTE_HORIZON,
                        "prediction_month": month,
                        "status": "shadow_only",
                        "training_cutoff": training_cutoff,
                        "baseline_floor": SHADOW_BASELINE_FLOOR,
                        "monthly_turnover_cap": SHADOW_MONTHLY_TURNOVER_CAP,
                        "realized_turnover": turnover,
                        "weights_json": json.dumps(weights, ensure_ascii=False),
                        "shadow_metrics_json": json.dumps(shadow_metrics, ensure_ascii=False),
                        "baseline_metrics_json": json.dumps(baseline_metrics, ensure_ascii=False),
                        "comparison_json": json.dumps(comparison, ensure_ascii=False),
                    },
                )
            )
        return {
            "run_id": resolved_run_id,
            "route_name": SHADOW_ROUTE_NAME,
            "horizon_days": SHADOW_ROUTE_HORIZON,
            "written": len(route_ids),
            "status": "shadow_only",
        }
    finally:
        if close_after:
            conn.commit()
            conn.close()


def build_shadow_router_report(db_path: str | Path, *, run_id: int | None = None) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        resolved_run_id = run_id or _latest_replay_run_id(conn)
        if resolved_run_id is None:
            raise ModelValidationError("No model replay run found")
        rows = [dict(row) for row in list_model_shadow_routes(conn, resolved_run_id, SHADOW_ROUTE_NAME)]
        if not rows:
            run_shadow_router_floor70(conn, run_id=resolved_run_id)
            rows = [dict(row) for row in list_model_shadow_routes(conn, resolved_run_id, SHADOW_ROUTE_NAME)]
    monthly = {}
    for row in rows:
        monthly[row["prediction_month"]] = {
            "status": row["status"],
            "training_cutoff": row["training_cutoff"],
            "baseline_floor": row["baseline_floor"],
            "monthly_turnover_cap": row["monthly_turnover_cap"],
            "realized_turnover": row["realized_turnover"],
            "weights": json.loads(row["weights_json"] or "{}"),
            "shadow_metrics": json.loads(row["shadow_metrics_json"] or "{}"),
            "baseline_metrics": json.loads(row["baseline_metrics_json"] or "{}"),
            "comparison": json.loads(row["comparison_json"] or "{}"),
        }
    return {
        "run_id": resolved_run_id,
        "route_name": SHADOW_ROUTE_NAME,
        "horizon_days": SHADOW_ROUTE_HORIZON,
        "count": len(rows),
        "status": "shadow_only",
        "monthly": monthly,
    }


def generate_confidence_labels(db_or_conn: str | Path | Any, *, run_id: int | None = None) -> dict[str, Any]:
    close_after = False
    if hasattr(db_or_conn, "execute"):
        conn = db_or_conn
    else:
        init_db(db_or_conn)
        conn = connect(db_or_conn)
        close_after = True
    try:
        resolved_run_id = run_id or _latest_replay_run_id(conn)
        if resolved_run_id is None:
            raise ModelValidationError("No model replay run found")
        metrics = [dict(row) for row in list_model_health_metrics(conn, resolved_run_id)]
        if not metrics:
            generate_model_health_metrics(conn, run_id=resolved_run_id)
            metrics = [dict(row) for row in list_model_health_metrics(conn, resolved_run_id)]
        if not list_model_applicability_profiles(conn, resolved_run_id):
            generate_applicability_profiles(conn, run_id=resolved_run_id)
        monthly_passes = _monthly_confidence_pass_counts(metrics)
        by_label: dict[str, int] = defaultdict(int)
        for metric in metrics:
            label, rationale = _confidence_label_for_metric(metric, monthly_passes)
            rationale_json = json.dumps(rationale, ensure_ascii=False)
            conn.execute(
                """
                UPDATE model_health_metrics
                SET confidence_label = ?,
                    confidence_rationale_json = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (label, rationale_json, metric["id"]),
            )
            conn.execute(
                """
                UPDATE model_applicability_profiles
                SET confidence_label = ?,
                    confidence_rationale_json = ?,
                    updated_at = datetime('now')
                WHERE source_metric_id = ?
                """,
                (label, rationale_json, metric["id"]),
            )
            by_label[label] += 1
        return {"run_id": resolved_run_id, "written": len(metrics), "by_label": dict(sorted(by_label.items()))}
    finally:
        if close_after:
            conn.commit()
            conn.close()


def build_confidence_label_report(db_path: str | Path, *, run_id: int | None = None) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        resolved_run_id = run_id or _latest_replay_run_id(conn)
        if resolved_run_id is None:
            raise ModelValidationError("No model replay run found")
        rows = [dict(row) for row in list_model_applicability_profiles(conn, resolved_run_id)]
        if not rows or not any(row.get("confidence_rationale_json") and row["confidence_rationale_json"] != "{}" for row in rows):
            generate_confidence_labels(conn, run_id=resolved_run_id)
            rows = [dict(row) for row in list_model_applicability_profiles(conn, resolved_run_id)]
    by_label: dict[str, int] = defaultdict(int)
    by_scope = {}
    for row in rows:
        by_label[str(row["confidence_label"])] += 1
        key = f"{row['model_version']}|{row['horizon_days']}|{row['asset_type']}|{row['same_category_key']}|{row['prediction_month']}|{row['evaluation_window']}"
        by_scope[key] = {
            "confidence_label": row["confidence_label"],
            "confidence_rationale": json.loads(row["confidence_rationale_json"] or "{}"),
            "output_role": row["output_role"],
            "ranking_disabled": bool(row["ranking_disabled"]),
        }
    return {"run_id": resolved_run_id, "count": len(rows), "by_label": dict(sorted(by_label.items())), "by_scope": by_scope}


def generate_model_governance_summary(
    db_or_conn: str | Path | Any,
    *,
    run_id: int | None = None,
    review_month: str | None = None,
) -> dict[str, Any]:
    close_after = False
    if hasattr(db_or_conn, "execute"):
        conn = db_or_conn
    else:
        init_db(db_or_conn)
        conn = connect(db_or_conn)
        close_after = True
    try:
        resolved_run_id = run_id or _latest_replay_run_id(conn)
        if resolved_run_id is None:
            raise ModelValidationError("No model replay run found")
        if not list_model_applicability_profiles(conn, resolved_run_id):
            generate_applicability_profiles(conn, run_id=resolved_run_id)
        profiles = [dict(row) for row in list_model_applicability_profiles(conn, resolved_run_id)]
        if not profiles or not any(row.get("confidence_rationale_json") and row["confidence_rationale_json"] != "{}" for row in profiles):
            generate_confidence_labels(conn, run_id=resolved_run_id)
            profiles = [dict(row) for row in list_model_applicability_profiles(conn, resolved_run_id)]
        shadows = [dict(row) for row in list_model_shadow_routes(conn, resolved_run_id, SHADOW_ROUTE_NAME)]
        if not shadows:
            try:
                run_shadow_router_floor70(conn, run_id=resolved_run_id)
                shadows = [dict(row) for row in list_model_shadow_routes(conn, resolved_run_id, SHADOW_ROUTE_NAME)]
            except ModelValidationError:
                shadows = []
        target_month = review_month or _latest_review_month(profiles, shadows)
        report = _governance_report(resolved_run_id, target_month, profiles, shadows)
        summary = _governance_summary_text(report)
        review_id = upsert_model_governance_review(
            conn,
            {
                "replay_run_id": resolved_run_id,
                "review_month": target_month,
                "status": "review_only",
                "summary_text": summary,
                "report_json": json.dumps(report, ensure_ascii=False),
                "production_defaults_changed": 0,
                "promotion_review_eligible": int(bool(report["promotion_review_eligible"])),
            },
        )
        return {"run_id": resolved_run_id, "review_id": review_id, "review_month": target_month, **report, "summary_text": summary}
    finally:
        if close_after:
            conn.commit()
            conn.close()


def build_model_governance_report(db_path: str | Path, *, run_id: int | None = None) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        resolved_run_id = run_id or _latest_replay_run_id(conn)
        if resolved_run_id is None:
            raise ModelValidationError("No model replay run found")
        rows = [dict(row) for row in list_model_governance_reviews(conn, resolved_run_id)]
        if not rows:
            return generate_model_governance_summary(conn, run_id=resolved_run_id)
        latest = rows[0]
        return {
            "run_id": resolved_run_id,
            "review_id": latest["id"],
            "review_month": latest["review_month"],
            "status": latest["status"],
            "summary_text": latest["summary_text"],
            "production_defaults_changed": bool(latest["production_defaults_changed"]),
            "promotion_review_eligible": bool(latest["promotion_review_eligible"]),
            "report": json.loads(latest["report_json"] or "{}"),
        }


def _aggregate_replay_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = {
        "total": len(rows),
        "matured": sum(1 for row in rows if row["score_status"] == "matured"),
        "pending": sum(1 for row in rows if row["score_status"] == "pending"),
        "skipped": sum(1 for row in rows if row["score_status"] == "skipped"),
    }
    matured = [row for row in rows if row["score_status"] == "matured"]
    by_model_horizon = _slice_metrics(matured, ("model_version", "horizon_days"))
    return {
        "coverage": coverage,
        "by_model_horizon": by_model_horizon,
        "by_month": _slice_metrics(matured, ("model_version", "horizon_days", "month")),
        "by_asset_type": _slice_metrics(matured, ("model_version", "horizon_days", "asset_type")),
        "by_category": _slice_metrics(matured, ("model_version", "horizon_days", "same_category_key")),
        "diagnostics": _diagnostics(matured, by_model_horizon),
    }


def _slice_metrics(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, Any]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(key) for key in keys)].append(row)
    output = {}
    for group_key, items in sorted(grouped.items(), key=lambda item: tuple(str(value) for value in item[0])):
        label = "|".join(str(value) for value in group_key)
        output[label] = _scored_metrics(items)
    return output


def _scored_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    results = []
    for row in rows:
        details = json.loads(row["details_json"] or "{}")
        results.append(
            {
                "direction_hit": 1.0 if (row["expected_return"] or 0) * (row["actual_return"] or 0) >= 0 else 0.0,
                "return_error": abs(float(row["expected_return"] or 0) - float(row["actual_return"] or 0)),
                "risk_hit": 1.0 if row.get("downside_risk") is None or float(row["actual_return"] or 0) >= float(row["downside_risk"] or 0) else 0.0,
                "benchmark_excess": float(row["actual_return"] or 0) - float(row["benchmark_return"] or 0),
                "drawdown_control": 1.0 if row.get("downside_risk") is None or float(row["actual_return"] or 0) >= float(row["downside_risk"] or 0) else 0.0,
                "prediction_score": float(row["prediction_score"] or 0),
                "risk_score": float(row["risk_score"] or 0),
                "advice_score": float(row["advice_score"] or 0),
                "overall_score": float(row["overall_score"] or 0),
                "predicted_return": float(row["expected_return"] or 0),
                "actual_return": float(row["actual_return"] or 0),
                "up_probability": row.get("up_probability"),
                "asset_type": row.get("asset_type") or details.get("asset_type") or "unknown",
                "same_category_key": row.get("same_category_key") or details.get("same_category_key") or "unknown",
            }
        )
    metrics = aggregate_scores(results)
    metrics["high_confidence_wrong_direction_count"] = sum(
        1 for row in rows if float(row.get("confidence") or 0) >= 0.8 and _direction(row.get("expected_return")) != _direction(row.get("actual_return"))
    )
    metrics["downside_risk_miss_count"] = sum(
        1 for row in rows if row.get("downside_risk") is not None and float(row["actual_return"] or 0) < float(row["downside_risk"] or 0)
    )
    metrics["mean_confidence"] = mean(float(row.get("confidence") or 0) for row in rows) if rows else None
    return metrics


def _model_health_facts(run_id: int, matured: list[dict[str, Any]], *, total_replay_rows: int) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in matured:
        model_version = str(row["model_version"])
        horizon_days = int(row["horizon_days"])
        asset_type = str(row.get("asset_type") or "unknown")
        category = str(row.get("same_category_key") or "unknown")
        month = str(row.get("month") or str(row["prediction_date"])[:7])
        groups[(model_version, horizon_days, asset_type, category, month, "monthly")].append(row)
        groups[(model_version, horizon_days, asset_type, "all", month, "monthly")].append(row)
        groups[(model_version, horizon_days, asset_type, category, "all", "all_history")].append(row)
        groups[(model_version, horizon_days, asset_type, "all", "all", "all_history")].append(row)

    return [
        _model_health_fact(run_id, key, rows, total_replay_rows=total_replay_rows)
        for key, rows in sorted(groups.items(), key=lambda item: tuple(str(value) for value in item[0]))
    ]


def _latest_review_month(profiles: list[dict[str, Any]], shadows: list[dict[str, Any]]) -> str:
    months = [str(row["prediction_month"]) for row in profiles if row["prediction_month"] != "all"]
    months.extend(str(row["prediction_month"]) for row in shadows)
    return max(months) if months else date.today().strftime("%Y-%m")


def _governance_report(run_id: int, review_month: str, profiles: list[dict[str, Any]], shadows: list[dict[str, Any]]) -> dict[str, Any]:
    month_profiles = [row for row in profiles if row["prediction_month"] in {review_month, "all"}]
    safe_defaults = [
        _profile_ref(row)
        for row in month_profiles
        if row["output_role"] == "primary_forecast" and row["confidence_label"] in {"谨慎观察", "相对稳健"}
    ]
    shadow_continue = [
        {
            "route_name": row["route_name"],
            "horizon_days": row["horizon_days"],
            "prediction_month": row["prediction_month"],
            "status": row["status"],
            "realized_turnover": row["realized_turnover"],
            "comparison": json.loads(row["comparison_json"] or "{}"),
        }
        for row in shadows
        if row["status"] == "shadow_only" and row["prediction_month"] <= review_month
    ]
    downgraded = [
        _profile_ref(row)
        for row in month_profiles
        if row["output_role"] in {"observation_only", "risk_reference"} or row["ranking_disabled"] or row["confidence_label"] == "暂不强调"
    ][:100]
    promotion_candidates = [
        _profile_ref(row)
        for row in month_profiles
        if row["output_role"] in {"primary_forecast", "allocation_bias", "ranking_signal"}
        and row["confidence_label"] == "相对稳健"
        and not row["ranking_disabled"]
    ]
    eligible = _promotion_review_eligible(promotion_candidates, shadow_continue)
    return {
        "run_id": run_id,
        "review_month": review_month,
        "status": "review_only",
        "questions": {
            "safe_as_default": safe_defaults,
            "continue_shadow_mode": shadow_continue,
            "downgrade_or_disable": downgraded,
            "promotion_review": {
                "eligible": eligible,
                "candidates": promotion_candidates if eligible else [],
                "blockers": [] if eligible else _promotion_blockers(month_profiles, shadow_continue),
                "review_only": True,
            },
        },
        "guardrails": {
            "production_defaults_changed": False,
            "operational_model_predictions_updated": False,
            "automatic_promotion": False,
            "expert_jarvis_advice_phone_portfolio_impact": "none",
            "stop_conditions": [
                "do not promote without future product review",
                "do not use shadow router for same-type ranking",
                "keep raw confidence as evidence-quality label only",
            ],
        },
        "promotion_review_eligible": eligible,
    }


def _profile_ref(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_version": row["model_version"],
        "horizon_days": row["horizon_days"],
        "asset_type": row["asset_type"],
        "same_category_key": row["same_category_key"],
        "prediction_month": row["prediction_month"],
        "evaluation_window": row["evaluation_window"],
        "output_role": row["output_role"],
        "confidence_label": row["confidence_label"],
        "ranking_disabled": bool(row["ranking_disabled"]),
        "degradation_reason": row["degradation_reason"],
    }


def _promotion_review_eligible(candidates: list[dict[str, Any]], shadows: list[dict[str, Any]]) -> bool:
    if not candidates:
        return False
    for row in shadows:
        comparison = row.get("comparison") or {}
        if comparison.get("rank_ic_delta") is not None and comparison["rank_ic_delta"] < 0:
            return False
        if comparison.get("bucket_spread_delta") is not None and comparison["bucket_spread_delta"] < 0:
            return False
        if comparison.get("direction_accuracy_delta") is not None and comparison["direction_accuracy_delta"] < 0:
            return False
        if float(row.get("realized_turnover") or 0) > SHADOW_MONTHLY_TURNOVER_CAP:
            return False
    return True


def _promotion_blockers(profiles: list[dict[str, Any]], shadows: list[dict[str, Any]]) -> list[str]:
    blockers = []
    if not any(row["confidence_label"] == "相对稳健" for row in profiles):
        blockers.append("no scope has 相对稳健 confidence label")
    if any(row["ranking_disabled"] for row in profiles):
        blockers.append("some same-type ranking scopes are disabled")
    if any(_negative_delta((row.get("comparison") or {}).get("rank_ic_delta")) for row in shadows):
        blockers.append("shadow router has negative Rank IC delta in at least one month")
    if any(_negative_delta((row.get("comparison") or {}).get("bucket_spread_delta")) for row in shadows):
        blockers.append("shadow router has negative bucket-spread delta in at least one month")
    return blockers or ["future product review required before promotion"]


def _negative_delta(value: Any) -> bool:
    return value is not None and float(value) < 0


def _governance_summary_text(report: dict[str, Any]) -> str:
    questions = report["questions"]
    return (
        f"{report['review_month']} 模型治理总结："
        f"默认安全范围 {len(questions['safe_as_default'])} 个，"
        f"shadow 继续观察 {len(questions['continue_shadow_mode'])} 个，"
        f"降级/禁用 {len(questions['downgrade_or_disable'])} 个样本范围；"
        "生产默认保持不变，任何 promotion 仅进入未来评审。"
    )


def _monthly_confidence_pass_counts(metrics: list[dict[str, Any]]) -> dict[tuple[str, int, str, str], int]:
    counts: dict[tuple[str, int, str, str], int] = defaultdict(int)
    for metric in metrics:
        if metric["evaluation_window"] != "monthly":
            continue
        if _confidence_base_pass(metric):
            key = (
                str(metric["model_version"]),
                int(metric["horizon_days"]),
                str(metric["asset_type"]),
                str(metric["same_category_key"]),
            )
            counts[key] += 1
    return counts


def _confidence_label_for_metric(metric: dict[str, Any], monthly_passes: dict[tuple[str, int, str, str], int]) -> tuple[str, dict[str, Any]]:
    max_calibration_error = _max_calibration_error(metric)
    high_conf_wrong_rate = metric["raw_high_conf_wrong_rate"]
    base_pass = _confidence_base_pass(metric)
    key = (
        str(metric["model_version"]),
        int(metric["horizon_days"]),
        str(metric["asset_type"]),
        str(metric["same_category_key"]),
    )
    stable_windows = monthly_passes.get(key, 0)
    rationale = {
        "minimum_sample_met": bool(metric["minimum_sample_met"]),
        "status": metric["status"],
        "rank_ic": metric["rank_ic"],
        "bucket_spread": metric["bucket_spread"],
        "max_calibration_error": max_calibration_error,
        "raw_high_conf_wrong_rate": high_conf_wrong_rate,
        "stable_monthly_windows": stable_windows,
        "evaluation_window": metric["evaluation_window"],
        "no_probability_guarantee": True,
    }
    if not metric["minimum_sample_met"]:
        return "暂不强调", {**rationale, "reason": "minimum sample gate not met"}
    if metric["rank_ic"] is None or float(metric["rank_ic"]) <= 0:
        return "暂不强调", {**rationale, "reason": "rank evidence is non-positive"}
    if metric["bucket_spread"] is None or float(metric["bucket_spread"]) <= 0:
        return "暂不强调", {**rationale, "reason": "bucket spread is non-positive"}
    if high_conf_wrong_rate is not None and float(high_conf_wrong_rate) >= 0.30:
        return "暂不强调", {**rationale, "reason": "high-confidence wrong rate is elevated"}
    if max_calibration_error is not None and max_calibration_error >= 0.15:
        return "暂不强调", {**rationale, "reason": "probability calibration error is elevated"}
    if base_pass and metric["evaluation_window"] == "all_history" and stable_windows >= 2:
        return "相对稳健", {**rationale, "reason": "multiple matured monthly windows show positive separation"}
    return "谨慎观察", {**rationale, "reason": "watchable evidence but not enough stable windows for strong label"}


def _confidence_base_pass(metric: dict[str, Any]) -> bool:
    if not metric["minimum_sample_met"]:
        return False
    if metric["rank_ic"] is None or float(metric["rank_ic"]) <= 0:
        return False
    if metric["bucket_spread"] is None or float(metric["bucket_spread"]) <= 0:
        return False
    high_conf_wrong_rate = metric["raw_high_conf_wrong_rate"]
    if high_conf_wrong_rate is not None and float(high_conf_wrong_rate) > 0.20:
        return False
    max_calibration_error = _max_calibration_error(metric)
    if max_calibration_error is not None and max_calibration_error > 0.10:
        return False
    return True


def _max_calibration_error(metric: dict[str, Any]) -> float | None:
    payload = json.loads(metric.get("metrics_json") or "{}")
    calibration = payload.get("probability_calibration") or []
    errors = [float(item.get("calibration_error") or 0) for item in calibration]
    return max(errors) if errors else None


def _shadow_candidate_rows(conn: Any, run_id: int) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in SHADOW_ROUTE_MODELS)
    return [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT r.*, a.code, a.name, a.asset_type,
                   substr(r.prediction_date, 1, 7) AS month,
                   json_extract(r.details_json, '$.same_category_key') AS same_category_key
            FROM model_replay_predictions r
            LEFT JOIN assets a ON a.id = r.asset_id
            WHERE r.replay_run_id = ?
              AND r.horizon_days = ?
              AND r.model_version IN ({placeholders})
            """,
            (run_id, SHADOW_ROUTE_HORIZON, *SHADOW_ROUTE_MODELS),
        ).fetchall()
    ]


def _shadow_target_weights(training_rows: list[dict[str, Any]]) -> dict[str, float]:
    weights = dict(SHADOW_INITIAL_WEIGHTS)
    grouped = {
        model: [row for row in training_rows if row["model_version"] == model]
        for model in SHADOW_ROUTE_MODELS
    }
    if not grouped[PRIMARY_MODEL_VERSION]:
        return weights
    metrics = {
        model: _scored_metrics(rows) if rows else {"mean_overall_score": None, "rank_ic": None, "bucket_spread": None}
        for model, rows in grouped.items()
    }
    baseline = metrics[PRIMARY_MODEL_VERSION]
    candidate_scores = {}
    for model in SHADOW_ROUTE_MODELS:
        if model == PRIMARY_MODEL_VERSION:
            continue
        values = metrics[model]
        if not values.get("count"):
            candidate_scores[model] = 0.0
            continue
        rank_ic = float(values.get("rank_ic") or 0)
        bucket_spread = float(values.get("bucket_spread") or 0)
        score_delta = float(values.get("mean_overall_score") or 0) - float(baseline.get("mean_overall_score") or 0)
        candidate_scores[model] = max(0.0, score_delta / 100.0) + max(0.0, rank_ic) + max(0.0, bucket_spread)
    total = sum(candidate_scores.values())
    if total <= 0:
        return weights
    available = 1.0 - SHADOW_BASELINE_FLOOR
    weights = {PRIMARY_MODEL_VERSION: SHADOW_BASELINE_FLOOR}
    for model, score in candidate_scores.items():
        weights[model] = available * (score / total)
    return _normalize_weights(weights)


def _apply_turnover_cap(
    previous: dict[str, float],
    target: dict[str, float],
    cap: float,
) -> tuple[dict[str, float], float]:
    previous = _normalize_weights(previous)
    target = _normalize_weights(target)
    turnover = 0.5 * sum(abs(target.get(model, 0.0) - previous.get(model, 0.0)) for model in SHADOW_ROUTE_MODELS)
    if turnover <= cap or turnover == 0:
        return target, turnover
    ratio = cap / turnover
    blended = {
        model: previous.get(model, 0.0) + (target.get(model, 0.0) - previous.get(model, 0.0)) * ratio
        for model in SHADOW_ROUTE_MODELS
    }
    blended = _normalize_weights(blended)
    realized = 0.5 * sum(abs(blended.get(model, 0.0) - previous.get(model, 0.0)) for model in SHADOW_ROUTE_MODELS)
    return blended, min(realized, cap)


def _shadow_month_metrics(
    holdout_rows: list[dict[str, Any]],
    weights: dict[str, float],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    grouped: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in holdout_rows:
        key = (row["asset_id"], row["prediction_date"], row["target"])
        grouped[key][str(row["model_version"])] = row
    shadow_results = []
    baseline_rows = []
    for variants in grouped.values():
        if not all(model in variants for model in SHADOW_ROUTE_MODELS):
            continue
        baseline = variants[PRIMARY_MODEL_VERSION]
        weighted_return = sum(float(variants[model].get("expected_return") or 0) * weights.get(model, 0.0) for model in SHADOW_ROUTE_MODELS)
        weighted_confidence = sum(float(variants[model].get("confidence") or 0) * weights.get(model, 0.0) for model in SHADOW_ROUTE_MODELS)
        weighted_probability = sum(float(variants[model].get("up_probability") or 0.5) * weights.get(model, 0.0) for model in SHADOW_ROUTE_MODELS)
        shadow_row = {**baseline, "expected_return": weighted_return, "confidence": weighted_confidence, "up_probability": weighted_probability}
        shadow_results.append(shadow_row)
        baseline_rows.append(baseline)
    shadow_metrics = _scored_metrics(shadow_results) if shadow_results else _scored_metrics([])
    baseline_metrics = _scored_metrics(baseline_rows) if baseline_rows else _scored_metrics([])
    comparison = {
        "rank_ic_delta": _delta(shadow_metrics.get("rank_ic"), baseline_metrics.get("rank_ic")),
        "bucket_spread_delta": _delta(shadow_metrics.get("bucket_spread"), baseline_metrics.get("bucket_spread")),
        "direction_accuracy_delta": _delta(shadow_metrics.get("direction_accuracy"), baseline_metrics.get("direction_accuracy")),
        "mae_delta": _delta(shadow_metrics.get("mean_return_error"), baseline_metrics.get("mean_return_error")),
        "high_confidence_wrong_direction_delta": int(shadow_metrics.get("high_confidence_wrong_direction_count") or 0)
        - int(baseline_metrics.get("high_confidence_wrong_direction_count") or 0),
        "operational_impact": "none_shadow_only",
        "same_type_ranking_usage": "disabled",
    }
    return shadow_metrics, baseline_metrics, comparison


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    normalized = {model: max(0.0, float(weights.get(model, 0.0))) for model in SHADOW_ROUTE_MODELS}
    total = sum(normalized.values())
    if total <= 0:
        return dict(SHADOW_INITIAL_WEIGHTS)
    normalized = {model: value / total for model, value in normalized.items()}
    if normalized[PRIMARY_MODEL_VERSION] < SHADOW_BASELINE_FLOOR:
        remainder_total = sum(value for model, value in normalized.items() if model != PRIMARY_MODEL_VERSION)
        available = 1.0 - SHADOW_BASELINE_FLOOR
        adjusted = {PRIMARY_MODEL_VERSION: SHADOW_BASELINE_FLOOR}
        for model in SHADOW_ROUTE_MODELS:
            if model == PRIMARY_MODEL_VERSION:
                continue
            adjusted[model] = available * (normalized[model] / remainder_total) if remainder_total else 0.0
        return adjusted
    return normalized


def _delta(left: Any, right: Any) -> float | None:
    if left is None or right is None:
        return None
    return float(left) - float(right)


def _model_health_fact(
    run_id: int,
    key: tuple[str, int, str, str, str, str],
    rows: list[dict[str, Any]],
    *,
    total_replay_rows: int,
) -> dict[str, Any]:
    model_version, horizon_days, asset_type, category, month, window = key
    metrics = _scored_metrics(rows)
    errors = [abs(float(row["expected_return"] or 0) - float(row["actual_return"] or 0)) for row in rows]
    high_conf_rows = [row for row in rows if float(row.get("confidence") or 0) >= 0.8]
    high_conf_wrong = [
        row
        for row in high_conf_rows
        if _direction(row.get("expected_return")) != _direction(row.get("actual_return"))
    ]
    minimum_sample_met = int((metrics.get("count") or 0) >= 20)
    status = str(metrics.get("validation_status") or "unvalidated")
    degradation_reason = _model_health_degradation_reason(metrics, minimum_sample_met=bool(minimum_sample_met))
    metrics_payload = {
        **metrics,
        "evaluation_scope": {
            "model_version": model_version,
            "horizon_days": horizon_days,
            "asset_type": asset_type,
            "same_category_key": category,
            "prediction_month": month,
            "evaluation_window": window,
        },
    }
    return {
        "replay_run_id": run_id,
        "model_version": model_version,
        "horizon_days": horizon_days,
        "asset_type": asset_type,
        "same_category_key": category,
        "prediction_month": month,
        "evaluation_window": window,
        "sample_count": int(metrics.get("count") or 0),
        "direction_accuracy": metrics.get("direction_accuracy"),
        "rank_ic": metrics.get("rank_ic"),
        "bucket_spread": metrics.get("bucket_spread"),
        "top_bottom_decile_spread": _top_bottom_spread(rows, bucket_fraction=0.1),
        "mae": metrics.get("mean_return_error"),
        "median_abs_error": median(errors) if errors else None,
        "raw_high_conf_wrong_rate": (len(high_conf_wrong) / len(high_conf_rows)) if high_conf_rows else None,
        "coverage_rate": (len(rows) / total_replay_rows) if total_replay_rows else None,
        "status": status,
        "output_role": "observation_only",
        "promotion_status": "not_reviewed",
        "degradation_reason": degradation_reason,
        "minimum_sample_met": minimum_sample_met,
        "consumer_display_level": "internal",
        "confidence_label": "暂不强调",
        "confidence_rationale_json": "{}",
        "last_promoted_at": None,
        "last_demoted_at": None,
        "metrics_json": json.dumps(metrics_payload, ensure_ascii=False),
    }


def _model_health_degradation_reason(metrics: dict[str, Any], *, minimum_sample_met: bool) -> str | None:
    if not minimum_sample_met:
        return "insufficient_sample"
    if metrics.get("rank_ic") is None or metrics.get("bucket_spread") is None:
        return "unvalidated_metric"
    reasons = []
    if float(metrics.get("rank_ic") or 0) < 0:
        reasons.append("negative_rank_ic")
    if float(metrics.get("bucket_spread") or 0) < 0:
        reasons.append("negative_bucket_spread")
    high_conf_wrong = int(metrics.get("high_confidence_wrong_direction_count") or 0)
    count = int(metrics.get("count") or 0)
    if count and high_conf_wrong / count >= 0.2:
        reasons.append("high_confidence_wrong_rate")
    return ",".join(reasons) if reasons else None


def _applicability_profile_from_metric(metric: dict[str, Any]) -> dict[str, Any]:
    ranking_disabled, ranking_reason = _same_type_ranking_disabled(metric)
    role, role_reason = _derive_output_role(metric, ranking_disabled=ranking_disabled)
    promotion_status = "shadow_only" if str(metric["model_version"]).startswith("router_") else "not_reviewed"
    rationale = {
        "source_metric_id": metric["id"],
        "metric_status": metric["status"],
        "sample_count": metric["sample_count"],
        "rank_ic": metric["rank_ic"],
        "bucket_spread": metric["bucket_spread"],
        "degradation_reason": metric["degradation_reason"],
        "role_reason": role_reason,
        "ranking_disable_reason": ranking_reason,
        "guardrails": [
            "profile evidence only; no operational prediction update",
            "no expert, Jarvis, advice, phone, WebUI, or portfolio consumption in TASK-094",
        ],
    }
    return {
        "replay_run_id": metric["replay_run_id"],
        "source_metric_id": metric["id"],
        "model_version": metric["model_version"],
        "horizon_days": metric["horizon_days"],
        "asset_type": metric["asset_type"],
        "same_category_key": metric["same_category_key"],
        "prediction_month": metric["prediction_month"],
        "evaluation_window": metric["evaluation_window"],
        "output_role": role,
        "ranking_disabled": int(ranking_disabled),
        "ranking_disable_reason": ranking_reason,
        "promotion_status": promotion_status,
        "degradation_reason": metric["degradation_reason"],
        "minimum_sample_met": metric["minimum_sample_met"],
        "consumer_display_level": _consumer_display_level(role, ranking_disabled=ranking_disabled),
        "confidence_label": metric["confidence_label"] if "confidence_label" in metric else "暂不强调",
        "confidence_rationale_json": metric["confidence_rationale_json"] if "confidence_rationale_json" in metric else "{}",
        "rationale_json": json.dumps(rationale, ensure_ascii=False),
    }


def _derive_output_role(metric: dict[str, Any], *, ranking_disabled: bool) -> tuple[str, str]:
    model_version = str(metric["model_version"])
    horizon_days = int(metric["horizon_days"])
    same_category_key = str(metric["same_category_key"])
    status = str(metric["status"])
    minimum_sample_met = bool(metric["minimum_sample_met"])

    if not minimum_sample_met or status == "insufficient_sample":
        return "observation_only", "minimum sample gate not met"
    if model_version.startswith("router_"):
        if horizon_days == 20 and same_category_key == "all":
            return "allocation_bias", "router output remains shadow-only broad allocation evidence"
        return "observation_only", "router output cannot become production or same-type role in this task"
    if model_version != PRIMARY_MODEL_VERSION:
        return "observation_only", "candidate model remains research-only before promotion review"
    if same_category_key != "all":
        if ranking_disabled:
            return "observation_only", "same-type ranking disabled by non-positive rank/bucket evidence"
        return "ranking_signal", "same-type evidence passed rank and bucket spread gates"
    if horizon_days in {5, 60}:
        if status == "validated":
            return "primary_forecast", "baseline remains conservative default for validated 5/60 day broad scope"
        return "risk_reference", "baseline broad scope degraded; retain only as model-layer risk reference"
    if horizon_days == 20:
        if status == "validated":
            return "allocation_bias", "20-day baseline can inform broad allocation bias but not same-type selection"
        return "risk_reference", "20-day baseline degraded; keep default evidence cautious and disable ranking elsewhere"
    return "observation_only", "unsupported horizon remains observation-only"


def _same_type_ranking_disabled(metric: dict[str, Any]) -> tuple[bool, str | None]:
    if str(metric["same_category_key"]) == "all":
        return False, None
    reasons = []
    rank_ic = metric["rank_ic"]
    bucket_spread = metric["bucket_spread"]
    if rank_ic is None or float(rank_ic) <= 0:
        reasons.append("non_positive_same_type_rank_ic")
    if bucket_spread is None or float(bucket_spread) <= 0:
        reasons.append("non_positive_same_type_bucket_spread")
    return bool(reasons), ",".join(reasons) if reasons else None


def _consumer_display_level(role: str, *, ranking_disabled: bool) -> str:
    if role == "primary_forecast":
        return "default_evidence"
    if role in {"allocation_bias", "ranking_signal"}:
        return "model_layer_only"
    if role == "risk_reference" or ranking_disabled:
        return "caution"
    return "internal"


def _top_bottom_spread(rows: list[dict[str, Any]], *, bucket_fraction: float) -> float | None:
    if len(rows) < 10:
        return None
    ordered = sorted(rows, key=lambda row: float(row.get("expected_return") or 0), reverse=True)
    bucket_size = max(1, int(len(ordered) * bucket_fraction))
    top = ordered[:bucket_size]
    bottom = ordered[-bucket_size:]
    return mean(float(row.get("actual_return") or 0) for row in top) - mean(float(row.get("actual_return") or 0) for row in bottom)


def _diagnostics(matured: list[dict[str, Any]], by_model_horizon: dict[str, Any]) -> dict[str, Any]:
    return {
        "high_confidence_wrong_direction": [
            _small_row(row)
            for row in matured
            if float(row.get("confidence") or 0) >= 0.8 and _direction(row.get("expected_return")) != _direction(row.get("actual_return"))
        ][:25],
        "negative_rank_slices": {
            key: value
            for key, value in by_model_horizon.items()
            if value.get("rank_ic") is not None and value.get("rank_ic") < 0
        },
        "negative_bucket_spread_slices": {
            key: value
            for key, value in by_model_horizon.items()
            if value.get("bucket_spread") is not None and value.get("bucket_spread") < 0
        },
        "downside_risk_misses": [
            _small_row(row)
            for row in matured
            if row.get("downside_risk") is not None and float(row["actual_return"] or 0) < float(row["downside_risk"] or 0)
        ][:25],
    }


def _recommendations_from_metrics(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    coverage = metrics.get("coverage", {})
    if int(coverage.get("matured") or 0) < 200:
        return [
            {
                "priority": 1,
                "title": "暂不调参，先扩大成熟 replay 样本",
                "affected_scope": "all",
                "triggering_metrics": coverage,
                "proposed_experiment": "继续积累点时 replay 样本，仅更新报告，不改变模型默认参数。",
                "verification_metric": "matured replay rows >= 200",
                "stop_condition": "样本不足时停止任何模型默认值变更。",
                "model_layer_confidence_impact": "降低模型层置信度解释权重。",
            }
        ]
    recs = []
    by_model = metrics.get("by_model_horizon", {})
    for key, values in by_model.items():
        model, horizon = key.split("|", 1)
        if values.get("rank_ic") is not None and values["rank_ic"] < 0:
            recs.append(_rec(len(recs) + 1, "排名信号反向，降低该模型/周期排序权重", model, horizon, values, "在该周期引入 rank gate；若 Rank IC 连续为负，则只保留为观测模型。", "Rank IC >= 0 且 bucket_spread >= 0", "连续两个 replay 报告仍为负则停用该模型/周期排序。", "降低高排名预测的展示置信。"))
        if values.get("bucket_spread") is not None and values["bucket_spread"] < 0:
            recs.append(_rec(len(recs) + 1, "Top/Bottom 分桶收益倒挂，需调弱 alpha 强度", model, horizon, values, "测试缩小 expected_return 振幅或加入行业中性分桶。", "bucket_spread > 0", "分桶差连续为负则不允许进入主推荐。", "将该切片标为 degraded。"))
        calibration = values.get("probability_calibration") or []
        max_error = max((item.get("calibration_error") or 0 for item in calibration), default=0)
        if max_error > 0.12:
            recs.append(_rec(len(recs) + 1, "上涨概率校准偏差偏大", model, horizon, {"max_calibration_error": max_error, "bins": calibration}, "对 up_probability 做分桶校准，先作为后处理层验证。", "max calibration_error <= 0.08", "校准后方向准确率下降超过 2pct 则回滚。", "概率文本降级为区间描述。"))
        if values.get("high_confidence_wrong_direction_count", 0) > max(10, (values.get("count") or 0) * 0.2):
            recs.append(_rec(len(recs) + 1, "高置信错误方向过多，置信度需要降温", model, horizon, values, "将 confidence 与近期 Rank IC、bucket_spread 绑定，负验证期自动降温。", "high_confidence_wrong_direction_count / count < 15%", "降温后错失显著机会过多则只用于风险提示。", "降低模型层高置信输出频率。"))
    if not recs:
        baseline = {key: value for key, value in by_model.items() if key.startswith("baseline_mean_v1|")}
        recs.append(
            {
                "priority": 1,
                "title": "保持 baseline_mean_v1 为主模型，候选模型继续观察",
                "affected_scope": "all",
                "triggering_metrics": baseline,
                "proposed_experiment": "不改默认模型；继续用 replay 报告追踪候选模型是否稳定超过 baseline。",
                "verification_metric": "candidate mean_overall_score and rank_ic both beat baseline for two reports",
                "stop_condition": "候选模型未持续胜出时不提升为主模型。",
                "model_layer_confidence_impact": "维持当前主模型置信描述。",
            }
        )
    return sorted(recs, key=lambda row: row["priority"])


def _rec(priority: int, title: str, model: str, horizon: str, metrics: dict[str, Any], experiment: str, verification: str, stop: str, impact: str) -> dict[str, Any]:
    return {
        "priority": priority,
        "title": title,
        "affected_scope": f"{model}|horizon={horizon}",
        "triggering_metrics": metrics,
        "proposed_experiment": experiment,
        "verification_metric": verification,
        "stop_condition": stop,
        "model_layer_confidence_impact": impact,
    }


def _upsert_replay_run(conn: Any, run: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO model_replay_runs(
            run_key, year, start_date, end_date, horizons_json,
            model_versions_json, lookback_days, asset_scope, status,
            metrics_json, tuning_recommendations_json, error
        )
        VALUES (
            :run_key, :year, :start_date, :end_date, :horizons_json,
            :model_versions_json, :lookback_days, :asset_scope, :status,
            :metrics_json, :tuning_recommendations_json, :error
        )
        ON CONFLICT(run_key) DO UPDATE SET
            year = excluded.year,
            start_date = excluded.start_date,
            end_date = excluded.end_date,
            horizons_json = excluded.horizons_json,
            model_versions_json = excluded.model_versions_json,
            lookback_days = excluded.lookback_days,
            asset_scope = excluded.asset_scope,
            status = excluded.status,
            error = excluded.error,
            updated_at = datetime('now')
        RETURNING id
        """,
        run,
    )
    return int(cursor.fetchone()["id"])


def _finish_replay_run(conn: Any, run_id: int, *, status: str, metrics: dict[str, Any] | None, error: str | None) -> None:
    conn.execute(
        "UPDATE model_replay_runs SET status = ?, metrics_json = ?, error = ?, updated_at = datetime('now') WHERE id = ?",
        (status, json.dumps(metrics, ensure_ascii=False) if metrics is not None else None, error, run_id),
    )


def _upsert_replay_prediction(conn: Any, record: dict[str, Any]) -> str:
    conn.execute(
        """
        INSERT INTO model_replay_predictions(
            replay_run_id, asset_id, prediction_date, horizon_days, model_version, target,
            up_probability, expected_return, expected_return_low, expected_return_high,
            downside_risk, confidence, input_window_start, input_window_end,
            outcome_date, actual_return, benchmark_return, benchmark_identity, benchmark_source,
            prediction_score, risk_score, advice_score, overall_score, score_status,
            skip_reason, details_json
        )
        VALUES (
            :replay_run_id, :asset_id, :prediction_date, :horizon_days, :model_version, :target,
            :up_probability, :expected_return, :expected_return_low, :expected_return_high,
            :downside_risk, :confidence, :input_window_start, :input_window_end,
            :outcome_date, :actual_return, :benchmark_return, :benchmark_identity, :benchmark_source,
            :prediction_score, :risk_score, :advice_score, :overall_score, :score_status,
            :skip_reason, :details_json
        )
        ON CONFLICT(replay_run_id, asset_id, prediction_date, horizon_days, model_version, target) DO UPDATE SET
            up_probability = excluded.up_probability,
            expected_return = excluded.expected_return,
            expected_return_low = excluded.expected_return_low,
            expected_return_high = excluded.expected_return_high,
            downside_risk = excluded.downside_risk,
            confidence = excluded.confidence,
            input_window_start = excluded.input_window_start,
            input_window_end = excluded.input_window_end,
            outcome_date = excluded.outcome_date,
            actual_return = excluded.actual_return,
            benchmark_return = excluded.benchmark_return,
            benchmark_identity = excluded.benchmark_identity,
            benchmark_source = excluded.benchmark_source,
            prediction_score = excluded.prediction_score,
            risk_score = excluded.risk_score,
            advice_score = excluded.advice_score,
            overall_score = excluded.overall_score,
            score_status = excluded.score_status,
            skip_reason = excluded.skip_reason,
            details_json = excluded.details_json,
            updated_at = datetime('now')
        """,
        record,
    )
    return str(record["score_status"])


def _replay_rows(conn: Any, run_id: int) -> list[Any]:
    return conn.execute(
        """
        SELECT r.*, a.code, a.name, a.asset_type,
               substr(r.prediction_date, 1, 7) AS month,
               json_extract(r.details_json, '$.same_category_key') AS same_category_key
        FROM model_replay_predictions r
        LEFT JOIN assets a ON a.id = r.asset_id
        WHERE r.replay_run_id = ?
        """,
        (run_id,),
    ).fetchall()


def _latest_replay_run_id(conn: Any) -> int | None:
    row = conn.execute("SELECT id FROM model_replay_runs ORDER BY updated_at DESC, id DESC LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _load_prices(conn: Any, asset_id: int) -> list[PricePoint]:
    return [
        PricePoint(asset_id=int(row["asset_id"]), trade_date=row["trade_date"], value=float(row["price_value"]))
        for row in list_price_history(conn, asset_id)
    ]


def _replay_record(run_id: int, asset: dict[str, Any], forecast: Any, model_version: str) -> dict[str, Any]:
    return {
        "replay_run_id": run_id,
        "asset_id": int(asset["id"]),
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
    }


def _skipped_prediction(run_id: int, asset: dict[str, Any], prediction_date: str, horizon: int, model_version: str, reason: str) -> dict[str, Any]:
    return {
        "replay_run_id": run_id,
        "asset_id": int(asset["id"]),
        "prediction_date": prediction_date,
        "horizon_days": horizon,
        "model_version": model_version,
        "target": "return",
        "up_probability": None,
        "expected_return": None,
        "expected_return_low": None,
        "expected_return_high": None,
        "downside_risk": None,
        "confidence": None,
        "input_window_start": None,
        "input_window_end": None,
        "outcome_date": None,
        "actual_return": None,
        "benchmark_return": None,
        "benchmark_identity": None,
        "benchmark_source": None,
        "prediction_score": None,
        "risk_score": None,
        "advice_score": None,
        "overall_score": None,
        "score_status": "skipped",
        "skip_reason": reason,
        "details_json": json.dumps({"asset_type": asset["asset_type"], "same_category_key": _asset_category_key(asset)}, ensure_ascii=False),
    }


def _persist_skipped_placeholders(conn: Any, run_id: int, asset: dict[str, Any], prediction_date: str, horizons: tuple[int, ...], model_versions: tuple[str, ...], reason: str) -> int:
    count = 0
    for model_version in model_versions:
        for horizon in horizons:
            _upsert_replay_prediction(conn, _skipped_prediction(run_id, asset, prediction_date, horizon, model_version, reason))
            count += 1
    return count


def _asset_category_key(asset: dict[str, Any]) -> str:
    theme = classify_asset_theme(code=asset["code"], name=asset["name"], asset_type=asset["asset_type"], fund_type=None)
    return f"{asset['asset_type']}:{theme['key']}"


def _small_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": row.get("asset_id"),
        "code": row.get("code"),
        "prediction_date": row.get("prediction_date"),
        "horizon_days": row.get("horizon_days"),
        "model_version": row.get("model_version"),
        "expected_return": row.get("expected_return"),
        "actual_return": row.get("actual_return"),
        "confidence": row.get("confidence"),
    }


def _direction(value: Any) -> str:
    return "up" if float(value or 0) >= 0 else "down"


def _date_text(value: str) -> str:
    text = str(value)
    if "-" in text:
        return text
    if len(text) == 8:
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    raise ModelValidationError(f"Invalid date: {value}")


def _validate_model_versions(model_versions: tuple[str, ...]) -> None:
    unknown = [version for version in model_versions if version not in MODEL_VERSIONS]
    if unknown:
        raise ModelValidationError(f"Unknown model versions: {', '.join(unknown)}")


def _run_key(year: int, start: str, end: str, horizons: tuple[int, ...], versions: tuple[str, ...], lookback: int, scope: str) -> str:
    return f"ytd:{year}:{start}:{end}:h={','.join(map(str, horizons))}:m={','.join(versions)}:l={lookback}:s={scope}"
