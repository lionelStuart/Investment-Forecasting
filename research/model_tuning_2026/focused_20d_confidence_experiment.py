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

from explore_model_tuning import direction, latest_replay_run_id, pearson, ranks


DEFAULT_SOURCE_DB = Path("data/investment_forecasting.sqlite3")
DEFAULT_OUTPUT_DB = Path("research/model_tuning_2026/model_tuning_research.sqlite3")
DEFAULT_REPORT = Path("research/model_tuning_2026/EXPERIMENT_20D_CONFIDENCE_FOCUS_REPORT.md")
HORIZON = 20
HOLDOUT_START = "2026-04-01"
MODELS = ("baseline_mean_v1", "momentum_reversal_v1", "risk_adjusted_factor_v1")

STRATEGIES = {
    "fixed_baseline": {"type": "fixed", "weights": {"baseline_mean_v1": 1.0}},
    "fixed_momentum": {"type": "fixed", "weights": {"momentum_reversal_v1": 1.0}},
    "fixed_risk_adjusted": {"type": "fixed", "weights": {"risk_adjusted_factor_v1": 1.0}},
    "router_no_floor_cap10": {"type": "router", "baseline_floor": 0.0, "monthly_cap": 0.10},
    "router_floor70_cap10": {"type": "router", "baseline_floor": 0.70, "monthly_cap": 0.10},
    "router_floor80_cap10": {"type": "router", "baseline_floor": 0.80, "monthly_cap": 0.10},
    "router_floor90_cap10": {"type": "router", "baseline_floor": 0.90, "monthly_cap": 0.10},
    "router_floor70_cap05": {"type": "router", "baseline_floor": 0.70, "monthly_cap": 0.05},
}

CONFIDENCE_TIERS = (
    ("low", 0.0, 0.50),
    ("watch", 0.50, 0.58),
    ("constructive", 0.58, 1.01),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Focused 20-day router and confidence-tier experiment.")
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--output-db", type=Path, default=DEFAULT_OUTPUT_DB)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--replay-run-id", type=int)
    args = parser.parse_args()

    source_uri = f"file:{args.source_db.resolve()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source:
        source.row_factory = sqlite3.Row
        replay_run_id = args.replay_run_id or latest_replay_run_id(source)
        if replay_run_id is None:
            raise SystemExit("No replay run found in source DB")
        source_run = dict(source.execute("SELECT * FROM model_replay_runs WHERE id = ?", (replay_run_id,)).fetchone())
        rows = load_rows(source, replay_run_id)

    predictions, weights = simulate(rows)
    strategy_metrics = build_strategy_metrics(predictions)
    month_metrics = build_month_metrics(predictions)
    asset_metrics = build_asset_metrics(predictions)
    tier_metrics = build_tier_metrics(predictions)
    decomposition_metrics = build_decomposition_metrics(predictions)
    weight_metrics = build_weight_metrics(weights)

    args.output_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.output_db) as out:
        create_schema(out)
        experiment_id = insert_run(out, args.source_db, replay_run_id, source_run, rows)
        write_strategy_metrics(out, experiment_id, strategy_metrics)
        write_month_metrics(out, experiment_id, month_metrics)
        write_asset_metrics(out, experiment_id, asset_metrics)
        write_tier_metrics(out, experiment_id, tier_metrics)
        write_decomposition_metrics(out, experiment_id, decomposition_metrics)
        write_weights(out, experiment_id, weights)
        write_weight_metrics(out, experiment_id, weight_metrics)
        out.commit()

    write_report(
        args.report,
        args.source_db,
        args.output_db,
        replay_run_id,
        experiment_id,
        rows,
        strategy_metrics,
        month_metrics,
        asset_metrics,
        tier_metrics,
        decomposition_metrics,
        weight_metrics,
    )
    print(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "source_db": str(args.source_db),
                "output_db": str(args.output_db),
                "report": str(args.report),
                "replay_run_id": replay_run_id,
                "rows": len(rows),
                "predictions": len(predictions),
                "monthly_weights": len(weights),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def load_rows(conn: sqlite3.Connection, replay_run_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT
              p.asset_id,
              a.code,
              a.name,
              a.asset_type,
              p.prediction_date,
              substr(p.prediction_date, 1, 7) AS month,
              p.horizon_days,
              p.model_version,
              p.expected_return,
              p.confidence,
              p.outcome_date,
              p.actual_return,
              json_extract(p.details_json, '$.same_category_key') AS same_category_key
            FROM model_replay_predictions p
            LEFT JOIN assets a ON a.id = p.asset_id
            WHERE p.replay_run_id = ?
              AND p.score_status = 'matured'
              AND p.horizon_days = ?
              AND p.expected_return IS NOT NULL
              AND p.actual_return IS NOT NULL
              AND p.outcome_date IS NOT NULL
            """,
            (replay_run_id, HORIZON),
        )
    ]


def simulate(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_key = group_by_tuple(rows, ("prediction_date", "asset_id"))
    keys_by_month: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for key in by_key:
        keys_by_month[str(key[0])[:7]].append(key)
    months = sorted(keys_by_month)
    predictions = []
    weight_rows = []
    previous_weights = {
        strategy: {"baseline_mean_v1": 1.0, "momentum_reversal_v1": 0.0, "risk_adjusted_factor_v1": 0.0}
        for strategy, config in STRATEGIES.items()
        if config["type"] == "router"
    }

    for month in months:
        month_start = f"{month}-01"
        model_metrics = build_model_metrics([row for row in rows if row["outcome_date"] < month_start])
        for strategy, config in STRATEGIES.items():
            if config["type"] == "fixed":
                strategy_weights = complete_weights(config["weights"])
            else:
                target = router_target_weights(model_metrics, float(config["baseline_floor"]))
                strategy_weights = smooth_weights(previous_weights[strategy], target, float(config["monthly_cap"]))
                previous_weights[strategy] = strategy_weights
                weight_rows.append({"month": month, "strategy": strategy, "weights": strategy_weights, "model_metrics": model_metrics})
            for key in keys_by_month[month]:
                candidates = {row["model_version"]: row for row in by_key[key]}
                usable = {model: weight for model, weight in strategy_weights.items() if model in candidates and weight > 0}
                if not usable:
                    continue
                usable = renormalize(usable)
                source = next(iter(candidates.values()))
                expected = sum(float(candidates[model]["expected_return"]) * weight for model, weight in usable.items())
                raw_confidence = sum(float(candidates[model].get("confidence") or 0) * weight for model, weight in usable.items())
                confidence_score = calibrated_confidence_score(usable, model_metrics)
                predictions.append(
                    {
                        "strategy": strategy,
                        "prediction_date": source["prediction_date"],
                        "month": source["month"],
                        "asset_id": source["asset_id"],
                        "asset_type": source["asset_type"] or "unknown",
                        "expected_return": expected,
                        "actual_return": float(source["actual_return"]),
                        "raw_confidence": raw_confidence,
                        "calibrated_confidence": confidence_score,
                        "confidence_tier": confidence_tier(confidence_score),
                        "primary_model": max(usable.items(), key=lambda item: item[1])[0],
                        "weights": usable,
                    }
                )
    return predictions, weight_rows


def build_model_metrics(history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output = {}
    for model in MODELS:
        model_rows = [row for row in history if row["model_version"] == model]
        if len(model_rows) < 300:
            output[model] = {"sample_count": len(model_rows), "direction_accuracy": None, "rank_ic": None, "bucket_spread": None, "mae": None, "score": -1.0}
            continue
        metric = prediction_metric(model_rows, score_key="expected_return")
        score = reliability_score(metric)
        output[model] = {**metric, "score": score}
    return output


def router_target_weights(model_metrics: dict[str, dict[str, Any]], baseline_floor: float) -> dict[str, float]:
    if max(metric["score"] for metric in model_metrics.values()) <= -0.5:
        return complete_weights({"baseline_mean_v1": 1.0})
    exp_scores = {model: math.exp(max(-2.0, min(2.0, metric["score"])) * 2.0) for model, metric in model_metrics.items()}
    target = renormalize(exp_scores)
    if baseline_floor > 0:
        target["baseline_mean_v1"] = max(target["baseline_mean_v1"], baseline_floor)
        residual = 1.0 - target["baseline_mean_v1"]
        non_base = {model: target[model] for model in MODELS if model != "baseline_mean_v1"}
        non_base_total = sum(non_base.values())
        for model in non_base:
            target[model] = residual * (non_base[model] / non_base_total) if non_base_total else 0.0
    return renormalize(target)


def reliability_score(metric: dict[str, Any]) -> float:
    rank_ic = metric["rank_ic"] or 0.0
    spread = metric["bucket_spread"] or 0.0
    direction_accuracy = metric["direction_accuracy"] if metric["direction_accuracy"] is not None else 0.5
    high_conf_wrong = metric["raw_high_conf_wrong_rate"] if metric["raw_high_conf_wrong_rate"] is not None else 0.35
    return (
        0.40 * math.tanh(rank_ic * 5.0)
        + 0.25 * math.tanh(spread * 12.0)
        + 0.25 * ((direction_accuracy - 0.5) * 2.0)
        - 0.10 * max(0.0, high_conf_wrong - 0.25) * 2.0
    )


def smooth_weights(previous: dict[str, float], target: dict[str, float], cap: float) -> dict[str, float]:
    updated = {}
    for model in MODELS:
        delta = target.get(model, 0.0) - previous.get(model, 0.0)
        updated[model] = max(0.0, previous.get(model, 0.0) + max(-cap, min(cap, delta)))
    return renormalize(updated)


def calibrated_confidence_score(weights: dict[str, float], model_metrics: dict[str, dict[str, Any]]) -> float:
    score = 0.0
    for model, weight in weights.items():
        metric = model_metrics.get(model) or {}
        if not metric or metric.get("direction_accuracy") is None:
            model_conf = 0.50
        else:
            direction_accuracy = metric["direction_accuracy"]
            rank_ic = metric["rank_ic"] or 0.0
            spread = metric["bucket_spread"] or 0.0
            wrong = metric["raw_high_conf_wrong_rate"] if metric["raw_high_conf_wrong_rate"] is not None else 0.35
            model_conf = 0.50 + (direction_accuracy - 0.5) * 0.35 + math.tanh(rank_ic * 4.0) * 0.08 + math.tanh(spread * 8.0) * 0.05
            model_conf -= max(0.0, wrong - 0.30) * 0.12
        score += weight * model_conf
    return max(0.0, min(1.0, score))


def confidence_tier(score: float) -> str:
    for tier, low, high in CONFIDENCE_TIERS:
        if low <= score < high:
            return tier
    return CONFIDENCE_TIERS[-1][0]


def build_strategy_metrics(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for (split, strategy), items in split_groups(predictions).items():
        output.append({"split": split, "strategy": strategy, **prediction_metric(items)})
    return output


def build_month_metrics(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for (strategy, month), items in group_by_tuple(predictions, ("strategy", "month")).items():
        output.append({"strategy": strategy, "month": month, **prediction_metric(items)})
    return output


def build_asset_metrics(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for (split, strategy, asset_type), items in split_asset_groups(predictions).items():
        if len(items) < 100:
            continue
        output.append({"split": split, "strategy": strategy, "asset_type": asset_type, **prediction_metric(items)})
    return output


def build_tier_metrics(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for (split, strategy, tier), items in split_tier_groups(predictions).items():
        output.append({"split": split, "strategy": strategy, "confidence_tier": tier, **prediction_metric(items)})
    return output


def build_decomposition_metrics(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for (split, strategy), items in split_groups(predictions).items():
        asset_type_rows = []
        for (date, asset_type), bucket in group_by_tuple(items, ("prediction_date", "asset_type")).items():
            asset_type_rows.append(
                {
                    "expected_return": mean(float(row["expected_return"]) for row in bucket),
                    "actual_return": mean(float(row["actual_return"]) for row in bucket),
                    "raw_confidence": mean(float(row["raw_confidence"]) for row in bucket),
                    "calibrated_confidence": mean(float(row["calibrated_confidence"]) for row in bucket),
                    "asset_type": asset_type,
                    "prediction_date": date,
                }
            )
        within_metrics = [prediction_metric(bucket) for (_, bucket) in group_by_tuple(items, ("asset_type",)).items() if len(bucket) >= 100]
        output.append({"split": split, "strategy": strategy, "component": "asset_type_allocation", **prediction_metric(asset_type_rows)})
        output.append({"split": split, "strategy": strategy, "component": "within_asset_type_weighted", **weighted_metric(within_metrics)})
    return output


def weighted_metric(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(metric["sample_count"] for metric in metrics)
    if not total:
        return {
            "sample_count": 0,
            "direction_accuracy": None,
            "mae": None,
            "rank_ic": None,
            "bucket_spread": None,
            "top_bottom_decile_spread": None,
            "raw_high_conf_wrong_rate": None,
            "mean_calibrated_confidence": None,
        }
    output = {"sample_count": total}
    for key in (
        "direction_accuracy",
        "mae",
        "rank_ic",
        "bucket_spread",
        "top_bottom_decile_spread",
        "raw_high_conf_wrong_rate",
        "mean_calibrated_confidence",
    ):
        values = [(metric[key], metric["sample_count"]) for metric in metrics if metric[key] is not None]
        output[key] = sum(value * weight for value, weight in values) / sum(weight for _, weight in values) if values else None
    return output


def build_weight_metrics(weights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for strategy, items in group_by_tuple(weights, ("strategy",)).items():
        ordered = sorted(items, key=lambda row: row["month"])
        changes = []
        for index in range(1, len(ordered)):
            changes.append(sum(abs(ordered[index]["weights"][model] - ordered[index - 1]["weights"][model]) for model in MODELS) / 2.0)
        output.append(
            {
                "strategy": strategy[0],
                "months": len(ordered),
                "mean_turnover": mean(changes) if changes else 0.0,
                "max_turnover": max(changes) if changes else 0.0,
                "mean_baseline_weight": mean(row["weights"]["baseline_mean_v1"] for row in ordered),
                "mean_momentum_weight": mean(row["weights"]["momentum_reversal_v1"] for row in ordered),
                "mean_risk_weight": mean(row["weights"]["risk_adjusted_factor_v1"] for row in ordered),
            }
        )
    return output


def prediction_metric(rows: list[dict[str, Any]], score_key: str = "expected_return") -> dict[str, Any]:
    high_conf = [row for row in rows if float(row.get("raw_confidence") or 0) >= 0.8]
    top, bottom = edge_deciles(rows, score_key)
    return {
        "sample_count": len(rows),
        "direction_accuracy": mean(1.0 if direction(row[score_key]) == direction(row["actual_return"]) else 0.0 for row in rows),
        "mae": mean(abs(float(row[score_key]) - float(row["actual_return"])) for row in rows),
        "rank_ic": pearson(ranks([float(row[score_key]) for row in rows]), ranks([float(row["actual_return"]) for row in rows])),
        "bucket_spread": bucket_spread(rows, score_key, 0.2),
        "top_bottom_decile_spread": mean(float(row["actual_return"]) for row in top) - mean(float(row["actual_return"]) for row in bottom) if top and bottom else None,
        "raw_high_conf_wrong_rate": wrong_rate(high_conf),
        "mean_calibrated_confidence": mean(float(row.get("calibrated_confidence") or 0) for row in rows),
    }


def split_groups(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups = defaultdict(list)
    for row in rows:
        groups[("full", row["strategy"])].append(row)
        groups[("holdout" if row["prediction_date"] >= HOLDOUT_START else "pre_holdout", row["strategy"])].append(row)
    return dict(groups)


def split_asset_groups(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    groups = defaultdict(list)
    for row in rows:
        groups[("full", row["strategy"], row["asset_type"])].append(row)
        groups[("holdout" if row["prediction_date"] >= HOLDOUT_START else "pre_holdout", row["strategy"], row["asset_type"])].append(row)
    return dict(groups)


def split_tier_groups(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    groups = defaultdict(list)
    for row in rows:
        groups[("full", row["strategy"], row["confidence_tier"])].append(row)
        groups[("holdout" if row["prediction_date"] >= HOLDOUT_START else "pre_holdout", row["strategy"], row["confidence_tier"])].append(row)
    return dict(groups)


def bucket_spread(rows: list[dict[str, Any]], score_key: str, fraction: float) -> float | None:
    if len(rows) < 5:
        return None
    ordered = sorted(rows, key=lambda row: float(row[score_key]), reverse=True)
    size = max(1, int(len(ordered) * fraction))
    return mean(float(row["actual_return"]) for row in ordered[:size]) - mean(float(row["actual_return"]) for row in ordered[-size:])


def edge_deciles(rows: list[dict[str, Any]], score_key: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(rows) < 10:
        return [], []
    ordered = sorted(rows, key=lambda row: float(row[score_key]), reverse=True)
    size = max(1, int(len(ordered) * 0.1))
    return ordered[:size], ordered[-size:]


def wrong_rate(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return mean(1.0 if direction(row["expected_return"]) != direction(row["actual_return"]) else 0.0 for row in rows)


def complete_weights(weights: dict[str, float]) -> dict[str, float]:
    return renormalize({model: weights.get(model, 0.0) for model in MODELS})


def renormalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in weights.values())
    if not total:
        return {"baseline_mean_v1": 1.0, "momentum_reversal_v1": 0.0, "risk_adjusted_factor_v1": 0.0}
    return {model: max(0.0, weights.get(model, 0.0)) / total for model in MODELS}


def group_by_tuple(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    return dict(groups)


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS focused_20d_experiment_runs (
          id INTEGER PRIMARY KEY,
          created_at TEXT NOT NULL,
          experiment_name TEXT NOT NULL,
          source_db TEXT NOT NULL,
          replay_run_id INTEGER NOT NULL,
          source_run_json TEXT NOT NULL,
          config_json TEXT NOT NULL,
          rows INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS focused_20d_strategy_metrics (
          experiment_id INTEGER NOT NULL,
          split TEXT NOT NULL,
          strategy TEXT NOT NULL,
          sample_count INTEGER NOT NULL,
          direction_accuracy REAL,
          mae REAL,
          rank_ic REAL,
          bucket_spread REAL,
          top_bottom_decile_spread REAL,
          raw_high_conf_wrong_rate REAL,
          mean_calibrated_confidence REAL,
          PRIMARY KEY (experiment_id, split, strategy)
        );
        CREATE TABLE IF NOT EXISTS focused_20d_month_metrics (
          experiment_id INTEGER NOT NULL,
          strategy TEXT NOT NULL,
          month TEXT NOT NULL,
          sample_count INTEGER NOT NULL,
          direction_accuracy REAL,
          mae REAL,
          rank_ic REAL,
          bucket_spread REAL,
          top_bottom_decile_spread REAL,
          raw_high_conf_wrong_rate REAL,
          mean_calibrated_confidence REAL,
          PRIMARY KEY (experiment_id, strategy, month)
        );
        CREATE TABLE IF NOT EXISTS focused_20d_asset_metrics (
          experiment_id INTEGER NOT NULL,
          split TEXT NOT NULL,
          strategy TEXT NOT NULL,
          asset_type TEXT NOT NULL,
          sample_count INTEGER NOT NULL,
          direction_accuracy REAL,
          mae REAL,
          rank_ic REAL,
          bucket_spread REAL,
          top_bottom_decile_spread REAL,
          raw_high_conf_wrong_rate REAL,
          mean_calibrated_confidence REAL,
          PRIMARY KEY (experiment_id, split, strategy, asset_type)
        );
        CREATE TABLE IF NOT EXISTS focused_20d_tier_metrics (
          experiment_id INTEGER NOT NULL,
          split TEXT NOT NULL,
          strategy TEXT NOT NULL,
          confidence_tier TEXT NOT NULL,
          sample_count INTEGER NOT NULL,
          direction_accuracy REAL,
          mae REAL,
          rank_ic REAL,
          bucket_spread REAL,
          top_bottom_decile_spread REAL,
          raw_high_conf_wrong_rate REAL,
          mean_calibrated_confidence REAL,
          PRIMARY KEY (experiment_id, split, strategy, confidence_tier)
        );
        CREATE TABLE IF NOT EXISTS focused_20d_decomposition_metrics (
          experiment_id INTEGER NOT NULL,
          split TEXT NOT NULL,
          strategy TEXT NOT NULL,
          component TEXT NOT NULL,
          sample_count INTEGER NOT NULL,
          direction_accuracy REAL,
          mae REAL,
          rank_ic REAL,
          bucket_spread REAL,
          top_bottom_decile_spread REAL,
          raw_high_conf_wrong_rate REAL,
          mean_calibrated_confidence REAL,
          PRIMARY KEY (experiment_id, split, strategy, component)
        );
        CREATE TABLE IF NOT EXISTS focused_20d_monthly_weights (
          experiment_id INTEGER NOT NULL,
          strategy TEXT NOT NULL,
          month TEXT NOT NULL,
          baseline_weight REAL NOT NULL,
          momentum_weight REAL NOT NULL,
          risk_adjusted_weight REAL NOT NULL,
          model_metrics_json TEXT NOT NULL,
          PRIMARY KEY (experiment_id, strategy, month)
        );
        CREATE TABLE IF NOT EXISTS focused_20d_weight_metrics (
          experiment_id INTEGER NOT NULL,
          strategy TEXT NOT NULL,
          months INTEGER NOT NULL,
          mean_turnover REAL,
          max_turnover REAL,
          mean_baseline_weight REAL,
          mean_momentum_weight REAL,
          mean_risk_weight REAL,
          PRIMARY KEY (experiment_id, strategy)
        );
        """
    )


def insert_run(conn: sqlite3.Connection, source_db: Path, replay_run_id: int, source_run: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO focused_20d_experiment_runs(
          created_at, experiment_name, source_db, replay_run_id, source_run_json, config_json, rows
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            "focused_20d_confidence_v1",
            str(source_db),
            replay_run_id,
            json.dumps(source_run, ensure_ascii=False, default=str),
            json.dumps({"strategies": STRATEGIES, "confidence_tiers": CONFIDENCE_TIERS, "holdout_start": HOLDOUT_START}, ensure_ascii=False),
            len(rows),
        ),
    )
    return int(cursor.lastrowid)


def write_strategy_metrics(conn: sqlite3.Connection, experiment_id: int, rows: list[dict[str, Any]]) -> None:
    write_metric_rows(conn, "focused_20d_strategy_metrics", experiment_id, rows, ("split", "strategy"))


def write_month_metrics(conn: sqlite3.Connection, experiment_id: int, rows: list[dict[str, Any]]) -> None:
    write_metric_rows(conn, "focused_20d_month_metrics", experiment_id, rows, ("strategy", "month"))


def write_asset_metrics(conn: sqlite3.Connection, experiment_id: int, rows: list[dict[str, Any]]) -> None:
    write_metric_rows(conn, "focused_20d_asset_metrics", experiment_id, rows, ("split", "strategy", "asset_type"))


def write_tier_metrics(conn: sqlite3.Connection, experiment_id: int, rows: list[dict[str, Any]]) -> None:
    write_metric_rows(conn, "focused_20d_tier_metrics", experiment_id, rows, ("split", "strategy", "confidence_tier"))


def write_decomposition_metrics(conn: sqlite3.Connection, experiment_id: int, rows: list[dict[str, Any]]) -> None:
    write_metric_rows(conn, "focused_20d_decomposition_metrics", experiment_id, rows, ("split", "strategy", "component"))


def write_metric_rows(conn: sqlite3.Connection, table: str, experiment_id: int, rows: list[dict[str, Any]], keys: tuple[str, ...]) -> None:
    metric_columns = (
        "sample_count",
        "direction_accuracy",
        "mae",
        "rank_ic",
        "bucket_spread",
        "top_bottom_decile_spread",
        "raw_high_conf_wrong_rate",
        "mean_calibrated_confidence",
    )
    columns = ("experiment_id",) + keys + metric_columns
    placeholders = ",".join("?" for _ in columns)
    conn.executemany(
        f"INSERT INTO {table}({','.join(columns)}) VALUES ({placeholders})",
        [tuple([experiment_id] + [row[key] for key in keys] + [row[column] for column in metric_columns]) for row in rows],
    )


def write_weights(conn: sqlite3.Connection, experiment_id: int, rows: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO focused_20d_monthly_weights(
          experiment_id, strategy, month, baseline_weight, momentum_weight,
          risk_adjusted_weight, model_metrics_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                experiment_id,
                row["strategy"],
                row["month"],
                row["weights"]["baseline_mean_v1"],
                row["weights"]["momentum_reversal_v1"],
                row["weights"]["risk_adjusted_factor_v1"],
                json.dumps(row["model_metrics"], ensure_ascii=False),
            )
            for row in rows
        ],
    )


def write_weight_metrics(conn: sqlite3.Connection, experiment_id: int, rows: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO focused_20d_weight_metrics(
          experiment_id, strategy, months, mean_turnover, max_turnover,
          mean_baseline_weight, mean_momentum_weight, mean_risk_weight
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                experiment_id,
                row["strategy"],
                row["months"],
                row["mean_turnover"],
                row["max_turnover"],
                row["mean_baseline_weight"],
                row["mean_momentum_weight"],
                row["mean_risk_weight"],
            )
            for row in rows
        ],
    )


def write_report(
    report_path: Path,
    source_db: Path,
    output_db: Path,
    replay_run_id: int,
    experiment_id: int,
    rows: list[dict[str, Any]],
    strategy_metrics: list[dict[str, Any]],
    month_metrics: list[dict[str, Any]],
    asset_metrics: list[dict[str, Any]],
    tier_metrics: list[dict[str, Any]],
    decomposition_metrics: list[dict[str, Any]],
    weight_metrics: list[dict[str, Any]],
) -> None:
    holdout = [row for row in strategy_metrics if row["split"] == "holdout"]
    key_strategies = {"fixed_baseline", "fixed_momentum", "router_no_floor_cap10", "router_floor70_cap10", "router_floor80_cap10", "router_floor90_cap10"}
    tier_rows = [row for row in tier_metrics if row["split"] == "holdout" and row["strategy"] in {"fixed_baseline", "router_floor80_cap10"}]
    lines = [
        "# Focused 20-Day Router And Confidence Experiment",
        "",
        f"Generated: {datetime.now().date().isoformat()}",
        "",
        "This isolated experiment tests only the 20-day horizon. Monthly router weights use only outcomes already matured before the first day of each prediction month.",
        "",
        "## Scope",
        "",
        f"- Source DB: `{source_db}`",
        f"- Output DB: `{output_db}`",
        f"- Replay run: `{replay_run_id}`",
        f"- Experiment ID: `{experiment_id}`",
        f"- Matured 20-day rows: {len(rows):,}",
        f"- Holdout split: prediction_date >= `{HOLDOUT_START}`",
        "",
        "## Holdout Strategy Metrics",
        "",
        "| strategy | n | direction | MAE | Rank IC | bucket | top-bottom decile | raw high-conf wrong | calibrated conf |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted([item for item in holdout if item["strategy"] in key_strategies], key=lambda item: item["strategy"]):
        lines.append(metric_line(row))
    lines.extend(["", "## Monthly Router Weights", "", "| strategy | months | turnover | max turnover | baseline | momentum | risk-adjusted |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for row in sorted(weight_metrics, key=lambda item: item["strategy"]):
        lines.append(
            f"| {row['strategy']} | {row['months']} | {fmt(row['mean_turnover'])} | {fmt(row['max_turnover'])} | {fmt(row['mean_baseline_weight'])} | {fmt(row['mean_momentum_weight'])} | {fmt(row['mean_risk_weight'])} |"
        )
    lines.extend(["", "## Holdout Confidence Tiers", "", "| strategy | tier | n | direction | Rank IC | bucket | calibrated conf |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"])
    for row in sorted(tier_rows, key=lambda item: (item["strategy"], item["confidence_tier"])):
        lines.append(
            f"| {row['strategy']} | {row['confidence_tier']} | {row['sample_count']:,} | {fmt(row['direction_accuracy'])} | {fmt(row['rank_ic'])} | {fmt(row['bucket_spread'])} | {fmt(row['mean_calibrated_confidence'])} |"
        )
    lines.extend(["", "## Holdout By Asset Type", "", "| strategy | asset type | n | direction | Rank IC | bucket | MAE |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"])
    for row in sorted(
        [item for item in asset_metrics if item["split"] == "holdout" and item["strategy"] in {"fixed_baseline", "router_floor80_cap10"}],
        key=lambda item: (item["strategy"], item["asset_type"]),
    ):
        lines.append(
            f"| {row['strategy']} | {row['asset_type']} | {row['sample_count']:,} | {fmt(row['direction_accuracy'])} | {fmt(row['rank_ic'])} | {fmt(row['bucket_spread'])} | {fmt(row['mae'])} |"
        )
    lines.extend(["", "## Holdout Signal Decomposition", "", "| strategy | component | n | direction | Rank IC | bucket | top-bottom decile |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"])
    for row in sorted(
        [item for item in decomposition_metrics if item["split"] == "holdout" and item["strategy"] in {"fixed_baseline", "router_floor70_cap05", "router_floor80_cap10"}],
        key=lambda item: (item["strategy"], item["component"]),
    ):
        lines.append(
            f"| {row['strategy']} | {row['component']} | {row['sample_count']:,} | {fmt(row['direction_accuracy'])} | {fmt(row['rank_ic'])} | {fmt(row['bucket_spread'])} | {fmt(row['top_bottom_decile_spread'])} |"
        )
    lines.extend(
        [
            "",
            "## Readout",
            "",
            "- The 20-day router should be conservative. Baseline-heavy router variants are the only candidates worth shadowing.",
            "- A baseline floor prevents the router from turning into a momentum chase while still allowing small non-baseline contributions.",
            "- Confidence should be displayed as calibrated tiers only if the tiers show monotonic or at least useful separation in holdout.",
            "- If confidence tiers do not separate holdout quality, use them as caution labels rather than strong-signal labels.",
            "- If asset-type allocation is positive while within-type ranking is weak, use the 20-day layer for broad allocation bias rather than individual asset ranking.",
            "",
            "## Reproduce",
            "",
            "```bash",
            "python3 research/model_tuning_2026/focused_20d_confidence_experiment.py \\",
            "  --source-db data/investment_forecasting.sqlite3 \\",
            "  --output-db research/model_tuning_2026/model_tuning_research.sqlite3 \\",
            "  --replay-run-id 1",
            "```",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def metric_line(row: dict[str, Any]) -> str:
    return (
        f"| {row['strategy']} | {row['sample_count']:,} | {fmt(row['direction_accuracy'])} | {fmt(row['mae'])} | "
        f"{fmt(row['rank_ic'])} | {fmt(row['bucket_spread'])} | {fmt(row['top_bottom_decile_spread'])} | "
        f"{fmt(row['raw_high_conf_wrong_rate'])} | {fmt(row['mean_calibrated_confidence'])} |"
    )


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.3f}"


if __name__ == "__main__":
    raise SystemExit(main())
