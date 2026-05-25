from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

from investment_forecasting.data.classification import classify_asset_theme
from investment_forecasting.db import connect, init_db, list_assets, list_price_history
from investment_forecasting.quant.backtest import aggregate_scores, forecast_from_history, score_forecast
from investment_forecasting.quant.benchmarks import select_asset_benchmark
from investment_forecasting.quant.features import PricePoint
from investment_forecasting.quant.forecast import MODEL_STATES, MODEL_VERSIONS


DEFAULT_HORIZONS = (5, 20, 60)
DEFAULT_MODEL_VERSIONS = MODEL_VERSIONS
DEFAULT_LOOKBACK_DAYS = 60


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
