from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any


DEFAULT_SOURCE_DB = Path("data/investment_forecasting.sqlite3")
DEFAULT_OUTPUT_DB = Path("research/model_tuning_2026/model_tuning_research.sqlite3")


def main() -> int:
    parser = argparse.ArgumentParser(description="Explore model tuning ideas from replay predictions without mutating the source DB.")
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--output-db", type=Path, default=DEFAULT_OUTPUT_DB)
    parser.add_argument("--replay-run-id", type=int)
    parser.add_argument("--top-n", type=int, default=80)
    args = parser.parse_args()

    source_uri = f"file:{args.source_db.resolve()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source:
        source.row_factory = sqlite3.Row
        replay_run_id = args.replay_run_id or latest_replay_run_id(source)
        if replay_run_id is None:
            raise SystemExit("No replay run found in source DB")
        run = dict(source.execute("SELECT * FROM model_replay_runs WHERE id = ?", (replay_run_id,)).fetchone())
        rows = load_matured_rows(source, replay_run_id)
        coverage = {
            row["score_status"]: row["count"]
            for row in source.execute(
                """
                SELECT score_status, COUNT(*) AS count
                FROM model_replay_predictions
                WHERE replay_run_id = ?
                GROUP BY score_status
                """,
                (replay_run_id,),
            )
        }

    args.output_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.output_db) as out:
        create_output_schema(out)
        analysis_id = insert_analysis_run(out, args.source_db, replay_run_id, run, coverage, len(rows))
        write_group_metrics(out, analysis_id, rows, ("model_version", "horizon_days"), "model_horizon")
        write_group_metrics(out, analysis_id, rows, ("model_version", "horizon_days", "asset_type"), "asset_type")
        write_group_metrics(out, analysis_id, rows, ("model_version", "horizon_days", "same_category_key"), "category")
        write_group_metrics(out, analysis_id, rows, ("model_version", "horizon_days", "month"), "month")
        write_probability_bins(out, analysis_id, rows)
        write_confidence_bins(out, analysis_id, rows)
        write_amplitude_experiments(out, analysis_id, rows)
        write_top_errors(out, analysis_id, rows, limit=args.top_n)
        recommendations = build_recommendations(rows)
        write_recommendations(out, analysis_id, recommendations)
        out.commit()

    summary = {
        "analysis_id": analysis_id,
        "source_db": str(args.source_db),
        "output_db": str(args.output_db),
        "replay_run_id": replay_run_id,
        "coverage": coverage,
        "matured_rows_loaded": len(rows),
        "recommendations": recommendations[:10],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def latest_replay_run_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT id FROM model_replay_runs ORDER BY updated_at DESC, id DESC LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def load_matured_rows(conn: sqlite3.Connection, replay_run_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT
              p.id,
              p.asset_id,
              a.code,
              a.name,
              a.asset_type,
              p.prediction_date,
              substr(p.prediction_date, 1, 7) AS month,
              p.horizon_days,
              p.model_version,
              p.up_probability,
              p.expected_return,
              p.downside_risk,
              p.confidence,
              p.actual_return,
              p.benchmark_return,
              p.prediction_score,
              p.risk_score,
              p.overall_score,
              json_extract(p.details_json, '$.same_category_key') AS same_category_key
            FROM model_replay_predictions p
            LEFT JOIN assets a ON a.id = p.asset_id
            WHERE p.replay_run_id = ?
              AND p.score_status = 'matured'
              AND p.expected_return IS NOT NULL
              AND p.actual_return IS NOT NULL
            """,
            (replay_run_id,),
        )
    ]


def create_output_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS analysis_runs (
          id INTEGER PRIMARY KEY,
          created_at TEXT NOT NULL,
          source_db TEXT NOT NULL,
          replay_run_id INTEGER NOT NULL,
          source_run_json TEXT NOT NULL,
          coverage_json TEXT NOT NULL,
          matured_rows INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS group_metrics (
          analysis_id INTEGER NOT NULL,
          slice_type TEXT NOT NULL,
          group_key TEXT NOT NULL,
          sample_count INTEGER NOT NULL,
          direction_accuracy REAL,
          mean_return_error REAL,
          median_abs_error REAL,
          mean_actual_return REAL,
          mean_predicted_return REAL,
          mean_overall_score REAL,
          rank_ic REAL,
          bucket_spread REAL,
          high_conf_wrong_rate REAL,
          downside_miss_rate REAL,
          PRIMARY KEY (analysis_id, slice_type, group_key)
        );
        CREATE TABLE IF NOT EXISTS calibration_bins (
          analysis_id INTEGER NOT NULL,
          bin_type TEXT NOT NULL,
          group_key TEXT NOT NULL,
          bin_label TEXT NOT NULL,
          sample_count INTEGER NOT NULL,
          mean_predicted REAL,
          actual_positive_rate REAL,
          calibration_error REAL,
          PRIMARY KEY (analysis_id, bin_type, group_key, bin_label)
        );
        CREATE TABLE IF NOT EXISTS amplitude_experiments (
          analysis_id INTEGER NOT NULL,
          group_key TEXT NOT NULL,
          sample_count INTEGER NOT NULL,
          base_mae REAL,
          optimal_scale REAL,
          scaled_mae REAL,
          mae_improvement REAL,
          slope REAL,
          intercept REAL,
          PRIMARY KEY (analysis_id, group_key)
        );
        CREATE TABLE IF NOT EXISTS top_errors (
          analysis_id INTEGER NOT NULL,
          rank INTEGER NOT NULL,
          replay_prediction_id INTEGER NOT NULL,
          model_version TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          code TEXT,
          name TEXT,
          asset_type TEXT,
          prediction_date TEXT NOT NULL,
          expected_return REAL,
          actual_return REAL,
          abs_error REAL,
          confidence REAL,
          same_category_key TEXT,
          PRIMARY KEY (analysis_id, rank)
        );
        CREATE TABLE IF NOT EXISTS recommendations (
          analysis_id INTEGER NOT NULL,
          priority INTEGER NOT NULL,
          title TEXT NOT NULL,
          affected_scope TEXT NOT NULL,
          evidence_json TEXT NOT NULL,
          experiment TEXT NOT NULL,
          verification_metric TEXT NOT NULL,
          stop_condition TEXT NOT NULL,
          PRIMARY KEY (analysis_id, priority)
        );
        """
    )


def insert_analysis_run(
    conn: sqlite3.Connection,
    source_db: Path,
    replay_run_id: int,
    run: dict[str, Any],
    coverage: dict[str, int],
    matured_rows: int,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO analysis_runs(created_at, source_db, replay_run_id, source_run_json, coverage_json, matured_rows)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            str(source_db),
            replay_run_id,
            json.dumps(run, ensure_ascii=False, default=str),
            json.dumps(coverage, ensure_ascii=False),
            matured_rows,
        ),
    )
    return int(cursor.lastrowid)


def write_group_metrics(conn: sqlite3.Connection, analysis_id: int, rows: list[dict[str, Any]], keys: tuple[str, ...], slice_type: str) -> None:
    for group_key, items in group_by(rows, keys).items():
        metric = group_metric(items)
        conn.execute(
            """
            INSERT INTO group_metrics(
              analysis_id, slice_type, group_key, sample_count, direction_accuracy,
              mean_return_error, median_abs_error, mean_actual_return,
              mean_predicted_return, mean_overall_score, rank_ic, bucket_spread,
              high_conf_wrong_rate, downside_miss_rate
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                slice_type,
                group_key,
                metric["sample_count"],
                metric["direction_accuracy"],
                metric["mean_return_error"],
                metric["median_abs_error"],
                metric["mean_actual_return"],
                metric["mean_predicted_return"],
                metric["mean_overall_score"],
                metric["rank_ic"],
                metric["bucket_spread"],
                metric["high_conf_wrong_rate"],
                metric["downside_miss_rate"],
            ),
        )


def write_probability_bins(conn: sqlite3.Connection, analysis_id: int, rows: list[dict[str, Any]]) -> None:
    bins = [(0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 1.01)]
    for group_key, items in group_by(rows, ("model_version", "horizon_days")).items():
        for low, high in bins:
            bucket = [row for row in items if row["up_probability"] is not None and low <= float(row["up_probability"]) < high]
            if not bucket:
                continue
            predicted = mean(float(row["up_probability"]) for row in bucket)
            actual = mean(1.0 if float(row["actual_return"]) > 0 else 0.0 for row in bucket)
            insert_bin(conn, analysis_id, "probability", group_key, f"{low:.1f}-{min(high, 1.0):.1f}", len(bucket), predicted, actual)


def write_confidence_bins(conn: sqlite3.Connection, analysis_id: int, rows: list[dict[str, Any]]) -> None:
    bins = [(0, 0.6), (0.6, 0.8), (0.8, 0.95), (0.95, 1.01)]
    for group_key, items in group_by(rows, ("model_version", "horizon_days")).items():
        for low, high in bins:
            bucket = [row for row in items if row["confidence"] is not None and low <= float(row["confidence"]) < high]
            if not bucket:
                continue
            predicted = mean(float(row["confidence"]) for row in bucket)
            actual = mean(1.0 if direction(row["expected_return"]) == direction(row["actual_return"]) else 0.0 for row in bucket)
            insert_bin(conn, analysis_id, "confidence", group_key, f"{low:.2f}-{min(high, 1.0):.2f}", len(bucket), predicted, actual)


def insert_bin(
    conn: sqlite3.Connection,
    analysis_id: int,
    bin_type: str,
    group_key: str,
    label: str,
    count: int,
    predicted: float,
    actual: float,
) -> None:
    conn.execute(
        """
        INSERT INTO calibration_bins(
          analysis_id, bin_type, group_key, bin_label, sample_count,
          mean_predicted, actual_positive_rate, calibration_error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (analysis_id, bin_type, group_key, label, count, predicted, actual, abs(predicted - actual)),
    )


def write_amplitude_experiments(conn: sqlite3.Connection, analysis_id: int, rows: list[dict[str, Any]]) -> None:
    for group_key, items in group_by(rows, ("model_version", "horizon_days")).items():
        preds = [float(row["expected_return"]) for row in items]
        actuals = [float(row["actual_return"]) for row in items]
        base_mae = mean(abs(pred - actual) for pred, actual in zip(preds, actuals))
        slope, intercept = linear_fit(preds, actuals)
        candidates = [0.0, 0.15, 0.25, 0.35, 0.5, 0.65, 0.8, 1.0, 1.25, 1.5]
        scored = [(scale, mean(abs((pred * scale) - actual) for pred, actual in zip(preds, actuals))) for scale in candidates]
        optimal_scale, scaled_mae = min(scored, key=lambda item: item[1])
        conn.execute(
            """
            INSERT INTO amplitude_experiments(
              analysis_id, group_key, sample_count, base_mae, optimal_scale,
              scaled_mae, mae_improvement, slope, intercept
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (analysis_id, group_key, len(items), base_mae, optimal_scale, scaled_mae, base_mae - scaled_mae, slope, intercept),
        )


def write_top_errors(conn: sqlite3.Connection, analysis_id: int, rows: list[dict[str, Any]], limit: int) -> None:
    ordered = sorted(rows, key=lambda row: abs(float(row["expected_return"]) - float(row["actual_return"])), reverse=True)[:limit]
    for index, row in enumerate(ordered, start=1):
        conn.execute(
            """
            INSERT INTO top_errors(
              analysis_id, rank, replay_prediction_id, model_version, horizon_days,
              code, name, asset_type, prediction_date, expected_return,
              actual_return, abs_error, confidence, same_category_key
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                index,
                row["id"],
                row["model_version"],
                row["horizon_days"],
                row["code"],
                row["name"],
                row["asset_type"],
                row["prediction_date"],
                row["expected_return"],
                row["actual_return"],
                abs(float(row["expected_return"]) - float(row["actual_return"])),
                row["confidence"],
                row["same_category_key"],
            ),
        )


def write_recommendations(conn: sqlite3.Connection, analysis_id: int, recommendations: list[dict[str, Any]]) -> None:
    for priority, rec in enumerate(recommendations, start=1):
        conn.execute(
            """
            INSERT INTO recommendations(
              analysis_id, priority, title, affected_scope, evidence_json,
              experiment, verification_metric, stop_condition
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                priority,
                rec["title"],
                rec["affected_scope"],
                json.dumps(rec["evidence"], ensure_ascii=False),
                rec["experiment"],
                rec["verification_metric"],
                rec["stop_condition"],
            ),
        )


def build_recommendations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    metrics = {key: group_metric(items) for key, items in group_by(rows, ("model_version", "horizon_days")).items()}
    experiments = {key: amplitude_summary(items) for key, items in group_by(rows, ("model_version", "horizon_days")).items()}
    for key, metric in metrics.items():
        amp = experiments[key]
        if metric["rank_ic"] is not None and metric["rank_ic"] < 0:
            recs.append(
                recommendation(
                    "排序信号为负，先降权或加 rank gate",
                    key,
                    {**metric, **amp},
                    "将该切片从资产排序主信号中移除或降低权重；只保留方向/风险参考。",
                    "下一次独立 replay 的 Rank IC >= 0 且 bucket_spread >= 0。",
                    "连续两次 replay 仍为负则停止该切片参与排序。",
                )
            )
        if metric["bucket_spread"] is not None and metric["bucket_spread"] < 0:
            recs.append(
                recommendation(
                    "Top/Bottom 分桶倒挂，降低 alpha 强度",
                    key,
                    {**metric, **amp},
                    "将 expected_return 乘以收缩系数并加入同类资产中性排序。",
                    "bucket_spread > 0 且 scaled MAE 不高于原 MAE。",
                    "收缩后 bucket_spread 仍为负则只做观测模型。",
                )
            )
        if amp["mae_improvement"] > max(0.002, metric["mean_return_error"] * 0.05):
            recs.append(
                recommendation(
                    "收益幅度过激，做预测振幅收缩",
                    key,
                    {**metric, **amp},
                    f"先验证 scale={amp['optimal_scale']:.2f} 的后处理收益率收缩。",
                    "MAE 至少改善 5%，方向准确率不下降超过 1pct。",
                    "若改善只来自极端样本且分桶排序恶化，则停止上线。",
                )
            )
        if metric["high_conf_wrong_rate"] > 0.2:
            recs.append(
                recommendation(
                    "高置信错误偏多，做 confidence cooling",
                    key,
                    metric,
                    "将 confidence 与近期 Rank IC、bucket spread、方向命中率绑定，负验证时自动降温。",
                    "高置信错误率 < 15%。",
                    "降温后仍不能区分正确/错误样本，则移除高置信文案。",
                )
            )
    recs.sort(key=lambda rec: severity(rec), reverse=True)
    return recs


def recommendation(title: str, scope: str, evidence: dict[str, Any], experiment: str, verification: str, stop: str) -> dict[str, Any]:
    return {
        "title": title,
        "affected_scope": scope,
        "evidence": evidence,
        "experiment": experiment,
        "verification_metric": verification,
        "stop_condition": stop,
    }


def severity(rec: dict[str, Any]) -> float:
    ev = rec["evidence"]
    return abs(float(ev.get("rank_ic") or 0)) + abs(float(ev.get("bucket_spread") or 0)) + float(ev.get("mae_improvement") or 0) * 10 + float(ev.get("high_conf_wrong_rate") or 0)


def group_by(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups["|".join(str(row.get(key)) for key in keys)].append(row)
    return dict(groups)


def group_metric(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors = sorted(abs(float(row["expected_return"]) - float(row["actual_return"])) for row in rows)
    count = len(rows)
    return {
        "sample_count": count,
        "direction_accuracy": mean(1.0 if direction(row["expected_return"]) == direction(row["actual_return"]) else 0.0 for row in rows),
        "mean_return_error": mean(errors),
        "median_abs_error": percentile(errors, 0.5),
        "mean_actual_return": mean(float(row["actual_return"]) for row in rows),
        "mean_predicted_return": mean(float(row["expected_return"]) for row in rows),
        "mean_overall_score": mean(float(row["overall_score"] or 0) for row in rows),
        "rank_ic": pearson(ranks([float(row["expected_return"]) for row in rows]), ranks([float(row["actual_return"]) for row in rows])),
        "bucket_spread": bucket_spread(rows),
        "high_conf_wrong_rate": mean(
            1.0 if float(row.get("confidence") or 0) >= 0.8 and direction(row["expected_return"]) != direction(row["actual_return"]) else 0.0
            for row in rows
        ),
        "downside_miss_rate": mean(
            1.0 if row.get("downside_risk") is not None and float(row["actual_return"]) < float(row["downside_risk"]) else 0.0
            for row in rows
        ),
    }


def amplitude_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    preds = [float(row["expected_return"]) for row in rows]
    actuals = [float(row["actual_return"]) for row in rows]
    base_mae = mean(abs(pred - actual) for pred, actual in zip(preds, actuals))
    candidates = [0.0, 0.15, 0.25, 0.35, 0.5, 0.65, 0.8, 1.0, 1.25, 1.5]
    optimal_scale, scaled_mae = min(
        ((scale, mean(abs((pred * scale) - actual) for pred, actual in zip(preds, actuals))) for scale in candidates),
        key=lambda item: item[1],
    )
    return {"base_mae": base_mae, "optimal_scale": optimal_scale, "scaled_mae": scaled_mae, "mae_improvement": base_mae - scaled_mae}


def direction(value: Any) -> str:
    return "up" if float(value or 0) >= 0 else "down"


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * p))))
    return values[index]


def ranks(values: list[float]) -> list[float]:
    ordered = sorted((value, index) for index, value in enumerate(values))
    output = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][0] == ordered[index][0]:
            end += 1
        rank = (index + end + 2) / 2
        for _, original in ordered[index : end + 1]:
            output[original] = rank
        index = end + 1
    return output


def pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_var = sum((a - left_mean) ** 2 for a in left)
    right_var = sum((b - right_mean) ** 2 for b in right)
    denom = math.sqrt(left_var * right_var)
    return numerator / denom if denom else None


def bucket_spread(rows: list[dict[str, Any]], fraction: float = 0.2) -> float | None:
    if len(rows) < 5:
        return None
    ordered = sorted(rows, key=lambda row: float(row["expected_return"]), reverse=True)
    size = max(1, int(len(ordered) * fraction))
    top = ordered[:size]
    bottom = ordered[-size:]
    return mean(float(row["actual_return"]) for row in top) - mean(float(row["actual_return"]) for row in bottom)


def linear_fit(x_values: list[float], y_values: list[float]) -> tuple[float | None, float | None]:
    if len(x_values) < 2:
        return None, None
    x_mean = mean(x_values)
    y_mean = mean(y_values)
    denom = sum((x - x_mean) ** 2 for x in x_values)
    if not denom:
        return None, y_mean
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)) / denom
    return slope, y_mean - slope * x_mean


if __name__ == "__main__":
    raise SystemExit(main())
