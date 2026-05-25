from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from investment_forecasting.data.classification import classify_asset_theme
from investment_forecasting.db import upsert_model_prediction_reliability


def refresh_prediction_reliability(
    conn: Any,
    *,
    prediction_date: str,
    model_version: str,
    horizons: tuple[int, ...],
    target: str = "return",
) -> dict[int, int]:
    summary: dict[int, int] = {}
    monitoring = _latest_monitoring_by_model(conn)

    for horizon in horizons:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT p.id, p.asset_id, p.prediction_date, p.horizon_days,
                       p.model_version, p.target, p.expected_return,
                       p.downside_risk, p.confidence,
                       a.code, a.name, a.asset_type,
                       i.fund_type
                FROM model_predictions p
                LEFT JOIN assets a ON a.id = p.asset_id
                LEFT JOIN fund_info i ON i.asset_id = p.asset_id
                WHERE p.prediction_date = ?
                  AND p.model_version = ?
                  AND p.horizon_days = ?
                  AND p.target = ?
                ORDER BY p.id
                """,
                (prediction_date, model_version, horizon, target),
            ).fetchall()
        ]
        if not rows:
            summary[horizon] = 0
            continue

        global_ranks = _rank_positions(rows, _expected_return_score)
        risk_ranks = _rank_positions(rows, _risk_adjusted_metric)
        category_ranks: dict[int, tuple[str, int, int]] = {}
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[_category_key(row)].append(row)
        for category_key, category_rows in grouped.items():
            for prediction_id, position, count in _rank_positions(category_rows, _expected_return_score).values():
                category_ranks[prediction_id] = (category_key, position, count)

        backtest = _latest_backtest_summary(conn, model_version=model_version, horizon_days=horizon)
        backtest_run_ids = backtest["run_ids"]
        model_monitoring = monitoring.get(model_version)
        validation_status, degraded_reason = _validation_state(model_monitoring, backtest["metrics"])
        written = 0
        for row in rows:
            prediction_id = int(row["id"])
            _, rank_position, rank_count = global_ranks[prediction_id]
            _, risk_position, risk_count = risk_ranks[prediction_id]
            category_key, same_rank, same_count = category_ranks[prediction_id]
            evidence = {
                "prediction_id": prediction_id,
                "backtest_run_ids": backtest_run_ids,
                "model_monitoring_report_id": int(model_monitoring["id"]) if model_monitoring else None,
                "scoring": "rank_score uses expected_return percentile; risk_adjusted_score uses expected_return minus downside-risk penalty percentile",
            }
            upsert_model_prediction_reliability(
                conn,
                {
                    "prediction_id": prediction_id,
                    "rank_score": _percentile_score(rank_position, rank_count),
                    "rank_position": rank_position,
                    "rank_count": rank_count,
                    "same_category_key": category_key,
                    "same_category_rank": same_rank,
                    "same_category_count": same_count,
                    "risk_adjusted_score": _percentile_score(risk_position, risk_count),
                    "validation_status": validation_status,
                    "recent_rank_ic": backtest["metrics"].get("rank_ic"),
                    "bucket_spread": backtest["metrics"].get("bucket_spread"),
                    "degraded_reason": degraded_reason,
                    "evidence_json": json.dumps(evidence, ensure_ascii=False),
                },
            )
            written += 1
        summary[horizon] = written
    return summary


def _rank_positions(rows: list[dict[str, Any]], score_fn: Any) -> dict[int, tuple[int, int, int]]:
    ranked = sorted(rows, key=lambda row: (score_fn(row), int(row["id"])), reverse=True)
    count = len(ranked)
    return {int(row["id"]): (int(row["id"]), index, count) for index, row in enumerate(ranked, start=1)}


def _percentile_score(position: int, count: int) -> float | None:
    if count <= 0:
        return None
    if count == 1:
        return 1.0
    return max(0.0, min(1.0, 1.0 - ((position - 1) / (count - 1))))


def _expected_return_score(row: dict[str, Any]) -> float:
    return float(row.get("expected_return") or 0.0)


def _risk_adjusted_metric(row: dict[str, Any]) -> float:
    expected_return = float(row.get("expected_return") or 0.0)
    downside_risk = min(0.0, float(row.get("downside_risk") or 0.0))
    confidence = float(row.get("confidence") or 0.0)
    return (expected_return - abs(downside_risk) * 0.5) * max(0.0, min(1.0, confidence))


def _category_key(row: dict[str, Any]) -> str:
    theme = classify_asset_theme(
        code=row.get("code"),
        name=row.get("name"),
        asset_type=row.get("asset_type"),
        fund_type=row.get("fund_type"),
    )
    return f"{row.get('asset_type') or 'asset'}:{theme['key']}"


def _latest_backtest_summary(conn: Any, *, model_version: str, horizon_days: int) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT id, metrics_json
        FROM backtest_runs
        WHERE model_version = ? AND horizon_days = ?
        ORDER BY end_date DESC, created_at DESC, id DESC
        LIMIT 3
        """,
        (model_version, horizon_days),
    ).fetchall()
    metrics: dict[str, Any] = {}
    if rows:
        try:
            metrics = json.loads(rows[0]["metrics_json"] or "{}")
        except json.JSONDecodeError:
            metrics = {}
    return {"run_ids": [int(row["id"]) for row in rows], "metrics": metrics}


def _latest_monitoring_by_model(conn: Any) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM model_monitoring_reports
        WHERE report_date = (SELECT MAX(report_date) FROM model_monitoring_reports)
        ORDER BY model_version
        """
    ).fetchall()
    return {row["model_version"]: dict(row) for row in rows}


def _validation_state(monitoring: dict[str, Any] | None, backtest_metrics: dict[str, Any]) -> tuple[str, str | None]:
    if monitoring:
        status = str(monitoring.get("status") or "unvalidated")
        if status == "degraded":
            return "degraded", _warning_summary(monitoring)
        if status == "warning":
            return "warning", _warning_summary(monitoring)
        if status == "ok":
            return "validated", None
    backtest_status = str(backtest_metrics.get("validation_status") or "")
    if backtest_status:
        if backtest_status == "insufficient_sample":
            return "insufficient_sample", "回测样本不足，排名可靠性仅作观察"
        if backtest_status == "degraded":
            return "degraded", "Rank IC 或 bucket spread 为负"
        return backtest_status, None
    return "unvalidated", "缺少回测或监控证据，排名仅为结构化观察值"


def _warning_summary(monitoring: dict[str, Any]) -> str | None:
    try:
        warnings = json.loads(monitoring.get("warnings_json") or "[]")
    except json.JSONDecodeError:
        warnings = []
    codes = [str(item.get("code")) for item in warnings if item.get("code")]
    return "、".join(codes) if codes else str(monitoring.get("status") or "")
