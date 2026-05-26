from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from explore_model_tuning import direction, latest_replay_run_id, pearson, ranks


DEFAULT_SOURCE_DB = Path("data/investment_forecasting.sqlite3")
DEFAULT_OUTPUT_DB = Path("research/model_tuning_2026/model_tuning_research.sqlite3")
DEFAULT_REPORT = Path("research/model_tuning_2026/EXPERIMENT_WALK_FORWARD_CONTROLS_REPORT.md")

MODELS = ("baseline_mean_v1", "momentum_reversal_v1", "risk_adjusted_factor_v1")
HORIZONS = (5, 20, 60)
HOLDOUT_START = "2026-04-01"

FIXED_STRATEGIES = {
    "fixed_baseline": {5: {"baseline_mean_v1": 1.0}, 20: {"baseline_mean_v1": 1.0}, 60: {"baseline_mean_v1": 1.0}},
    "fixed_prior_route": {5: {"baseline_mean_v1": 1.0}, 20: {"momentum_reversal_v1": 1.0}, 60: {"baseline_mean_v1": 1.0}},
    "fixed_risk60_route": {5: {"baseline_mean_v1": 1.0}, 20: {"momentum_reversal_v1": 1.0}, 60: {"risk_adjusted_factor_v1": 1.0}},
    "fixed_60_ensemble": {
        5: {"baseline_mean_v1": 1.0},
        20: {"momentum_reversal_v1": 1.0},
        60: {"baseline_mean_v1": 0.5, "risk_adjusted_factor_v1": 0.5},
    },
}

ROUTER_CONFIGS = [
    {"name": "wf_w20_cap10", "windows": (20,), "max_daily_change": 0.10},
    {"name": "wf_w40_cap10", "windows": (40,), "max_daily_change": 0.10},
    {"name": "wf_blend_20_40_60_cap10", "windows": (20, 40, 60), "max_daily_change": 0.10},
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward control-layer experiment using read-only replay data.")
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

    args.output_db.parent.mkdir(parents=True, exist_ok=True)
    predictions, weights = run_walk_forward(rows)
    metrics = build_metrics(predictions)
    weight_metrics = build_weight_metrics(weights)
    cooling = build_confidence_metrics(predictions)
    regime = build_regime_metrics(predictions)

    with sqlite3.connect(args.output_db) as out:
        create_schema(out)
        experiment_id = insert_run(out, args.source_db, replay_run_id, source_run, rows)
        write_weights(out, experiment_id, weights)
        write_metrics(out, experiment_id, metrics)
        write_weight_metrics(out, experiment_id, weight_metrics)
        write_confidence_metrics(out, experiment_id, cooling)
        write_regime_metrics(out, experiment_id, regime)
        out.commit()

    write_report(args.report, args.source_db, args.output_db, replay_run_id, experiment_id, rows, metrics, weight_metrics, cooling, regime)
    print(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "source_db": str(args.source_db),
                "output_db": str(args.output_db),
                "report": str(args.report),
                "replay_run_id": replay_run_id,
                "matured_rows": len(rows),
                "strategy_predictions": len(predictions),
                "daily_weights": len(weights),
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
              p.outcome_date,
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
              AND p.outcome_date IS NOT NULL
            """,
            (replay_run_id,),
        )
    ]


def run_walk_forward(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_key = group_by_tuple(rows, ("prediction_date", "horizon_days", "asset_id"))
    keys_by_month: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for key in by_key:
        keys_by_month[str(key[0])[:7]].append(key)
    months = sorted({row["prediction_date"][:7] for row in rows})
    rows_by_horizon = {horizon: [row for row in rows if int(row["horizon_days"]) == horizon] for horizon in HORIZONS}
    predictions: list[dict[str, Any]] = []
    weights: list[dict[str, Any]] = []

    all_strategy_names = list(FIXED_STRATEGIES) + [config["name"] for config in ROUTER_CONFIGS]
    previous_weights = {
        config["name"]: {horizon: {"baseline_mean_v1": 1.0, "momentum_reversal_v1": 0.0, "risk_adjusted_factor_v1": 0.0} for horizon in HORIZONS}
        for config in ROUTER_CONFIGS
    }

    for month in months:
        prediction_date = f"{month}-01"
        daily_fixed_weights = {(name, horizon): route[horizon] for name, route in FIXED_STRATEGIES.items() for horizon in HORIZONS}
        daily_router_weights: dict[tuple[str, int], dict[str, float]] = {}
        daily_router_diagnostics: dict[tuple[str, int], dict[str, Any]] = {}
        for config in ROUTER_CONFIGS:
            for horizon in HORIZONS:
                target, diagnostics = target_weights(rows_by_horizon[horizon], prediction_date, int(horizon), config["windows"])
                smoothed = smooth_weights(previous_weights[config["name"]][horizon], target, float(config["max_daily_change"]))
                previous_weights[config["name"]][horizon] = smoothed
                daily_router_weights[(config["name"], horizon)] = smoothed
                daily_router_diagnostics[(config["name"], horizon)] = diagnostics
                weights.append(
                    {
                        "prediction_date": prediction_date,
                        "strategy": config["name"],
                        "horizon_days": horizon,
                        "weights": smoothed,
                        **diagnostics,
                    }
                )

        for date, horizon, asset_id in keys_by_month[month]:
            candidates = by_key[(date, horizon, asset_id)]
            candidate_by_model = {row["model_version"]: row for row in candidates}
            for strategy in all_strategy_names:
                if strategy in FIXED_STRATEGIES:
                    model_weights = daily_fixed_weights[(strategy, int(horizon))]
                    diagnostics = {"sample_count": None, "model_scores": {}}
                else:
                    model_weights = daily_router_weights[(strategy, int(horizon))]
                    diagnostics = daily_router_diagnostics[(strategy, int(horizon))]
                available = {model: weight for model, weight in model_weights.items() if model in candidate_by_model and weight > 0}
                if not available:
                    continue
                total = sum(available.values())
                normalized = {model: weight / total for model, weight in available.items()}
                source_rows = [candidate_by_model[model] for model in normalized]
                expected_return = sum(float(candidate_by_model[model]["expected_return"]) * weight for model, weight in normalized.items())
                raw_confidence = sum(float(candidate_by_model[model].get("confidence") or 0) * weight for model, weight in normalized.items())
                reliability_cap = weighted_reliability_cap(normalized, diagnostics.get("model_scores") or {})
                predictions.append(
                    {
                        "strategy": strategy,
                        "prediction_date": date,
                        "horizon_days": int(horizon),
                        "asset_id": int(asset_id),
                        "expected_return": expected_return,
                        "actual_return": float(source_rows[0]["actual_return"]),
                        "raw_confidence": raw_confidence,
                        "cooled_confidence": min(raw_confidence, reliability_cap),
                        "primary_model": max(normalized.items(), key=lambda item: item[1])[0],
                        "weights": normalized,
                        "data_ready_sample_count": diagnostics.get("sample_count"),
                    }
                )
    return predictions, weights


def target_weights(rows: list[dict[str, Any]], prediction_date: str, horizon: int, windows: tuple[int, ...]) -> tuple[dict[str, float], dict[str, Any]]:
    history = [row for row in rows if row["outcome_date"] and row["outcome_date"] < prediction_date]
    if not history:
        return baseline_weight(), {"sample_count": 0, "model_scores": {}, "fallback_reason": "no matured history"}
    weighted_scores = {}
    diagnostics = {}
    for model in MODELS:
        model_rows = [row for row in history if row["model_version"] == model]
        if len(model_rows) < 300:
            weighted_scores[model] = -1.0
            diagnostics[model] = {"sample_count": len(model_rows), "score": -1.0}
            continue
        scores = []
        for window in windows:
            start_date = (parse_date(prediction_date) - timedelta(days=window * 2)).isoformat()
            window_rows = [row for row in model_rows if row["outcome_date"] >= start_date]
            if len(window_rows) < 150:
                window_rows = model_rows[-min(len(model_rows), 2000) :]
            metric = raw_metric(window_rows)
            scores.append(reliability_score(metric))
        score = mean(scores)
        weighted_scores[model] = score
        metric = raw_metric(model_rows[-min(len(model_rows), 3000) :])
        diagnostics[model] = {**metric, "score": score, "sample_count": len(model_rows)}

    if max(weighted_scores.values()) <= -0.5:
        return baseline_weight(), {"sample_count": len(history), "model_scores": diagnostics, "fallback_reason": "insufficient model history"}
    exp_scores = {model: math.exp(max(-2.0, min(2.0, score)) * 2.0) for model, score in weighted_scores.items()}
    total = sum(exp_scores.values())
    weights = {model: value / total for model, value in exp_scores.items()}
    if horizon == 5:
        weights["baseline_mean_v1"] = max(weights["baseline_mean_v1"], 0.45)
        weights = renormalize(weights)
    return weights, {"sample_count": len(history), "model_scores": diagnostics, "fallback_reason": None}


def raw_metric(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    if not rows:
        return {"direction_accuracy": None, "rank_ic": None, "bucket_spread": None, "mean_abs_error": None, "high_conf_wrong_rate": None}
    high_conf = [row for row in rows if float(row.get("confidence") or 0) >= 0.8]
    return {
        "direction_accuracy": mean(1.0 if direction(row["expected_return"]) == direction(row["actual_return"]) else 0.0 for row in rows),
        "rank_ic": pearson(ranks([float(row["expected_return"]) for row in rows]), ranks([float(row["actual_return"]) for row in rows])),
        "bucket_spread": bucket_spread(rows, "expected_return", 0.2),
        "mean_abs_error": mean(abs(float(row["expected_return"]) - float(row["actual_return"])) for row in rows),
        "high_conf_wrong_rate": (
            mean(1.0 if direction(row["expected_return"]) != direction(row["actual_return"]) else 0.0 for row in high_conf) if high_conf else None
        ),
    }


def reliability_score(metric: dict[str, float | None]) -> float:
    rank_ic = metric["rank_ic"] or 0.0
    spread = metric["bucket_spread"] or 0.0
    direction_accuracy = metric["direction_accuracy"] if metric["direction_accuracy"] is not None else 0.5
    high_conf_wrong = metric["high_conf_wrong_rate"] if metric["high_conf_wrong_rate"] is not None else 0.35
    return (
        0.40 * math.tanh(rank_ic * 5.0)
        + 0.25 * math.tanh(spread * 12.0)
        + 0.25 * ((direction_accuracy - 0.5) * 2.0)
        - 0.10 * max(0.0, high_conf_wrong - 0.20) * 2.0
    )


def smooth_weights(previous: dict[str, float], target: dict[str, float], cap: float) -> dict[str, float]:
    updated = {}
    for model in MODELS:
        delta = target.get(model, 0.0) - previous.get(model, 0.0)
        delta = max(-cap, min(cap, delta))
        updated[model] = max(0.0, previous.get(model, 0.0) + delta)
    return renormalize(updated)


def baseline_weight() -> dict[str, float]:
    return {"baseline_mean_v1": 1.0, "momentum_reversal_v1": 0.0, "risk_adjusted_factor_v1": 0.0}


def renormalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in weights.values())
    if not total:
        return baseline_weight()
    return {model: max(0.0, weights.get(model, 0.0)) / total for model in MODELS}


def weighted_reliability_cap(weights: dict[str, float], scores: dict[str, Any]) -> float:
    caps = []
    for model, weight in weights.items():
        model_score = scores.get(model) or {}
        accuracy = model_score.get("direction_accuracy")
        rank_ic = model_score.get("rank_ic") or 0.0
        spread = model_score.get("bucket_spread") or 0.0
        base = accuracy if accuracy is not None else 0.55
        bonus = max(0.0, min(0.10, rank_ic * 0.25 + spread * 0.20))
        caps.append(weight * min(0.85, max(0.35, base + bonus)))
    return sum(caps) if caps else 0.55


def build_metrics(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for (split, strategy, horizon), rows in grouped_metric_rows(predictions).items():
        metric = prediction_metric(rows)
        output.append({"split": split, "strategy": strategy, "horizon_days": horizon, **metric})
    return output


def grouped_metric_rows(predictions: list[dict[str, Any]]) -> dict[tuple[str, str, int], list[dict[str, Any]]]:
    groups = defaultdict(list)
    for row in predictions:
        for split in ("full", "holdout" if row["prediction_date"] >= HOLDOUT_START else "pre_holdout"):
            groups[(split, row["strategy"], row["horizon_days"])].append(row)
    return dict(groups)


def prediction_metric(rows: list[dict[str, Any]]) -> dict[str, Any]:
    top_decile, bottom_decile = edge_deciles(rows)
    return {
        "sample_count": len(rows),
        "direction_accuracy": mean(1.0 if direction(row["expected_return"]) == direction(row["actual_return"]) else 0.0 for row in rows),
        "mean_abs_error": mean(abs(row["expected_return"] - row["actual_return"]) for row in rows),
        "rank_ic": pearson(ranks([row["expected_return"] for row in rows]), ranks([row["actual_return"] for row in rows])),
        "bucket_spread": bucket_spread(rows, "expected_return", 0.2),
        "top_bottom_decile_spread": (
            mean(row["actual_return"] for row in top_decile) - mean(row["actual_return"] for row in bottom_decile) if top_decile and bottom_decile else None
        ),
        "raw_high_conf_count": sum(1 for row in rows if row["raw_confidence"] >= 0.8),
        "raw_high_conf_wrong_rate": wrong_rate([row for row in rows if row["raw_confidence"] >= 0.8]),
        "cooled_high_conf_count": sum(1 for row in rows if row["cooled_confidence"] >= 0.7),
        "cooled_high_conf_wrong_rate": wrong_rate([row for row in rows if row["cooled_confidence"] >= 0.7]),
    }


def build_weight_metrics(weights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for (strategy, horizon), items in group_by_tuple(weights, ("strategy", "horizon_days")).items():
        ordered = sorted(items, key=lambda row: row["prediction_date"])
        changes = []
        baseline_weights = []
        momentum_weights = []
        risk_weights = []
        for index, row in enumerate(ordered):
            current = row["weights"]
            baseline_weights.append(current["baseline_mean_v1"])
            momentum_weights.append(current["momentum_reversal_v1"])
            risk_weights.append(current["risk_adjusted_factor_v1"])
            if index:
                previous = ordered[index - 1]["weights"]
                changes.append(sum(abs(current[model] - previous[model]) for model in MODELS) / 2.0)
        output.append(
            {
                "strategy": strategy,
                "horizon_days": int(horizon),
                "days": len(ordered),
                "mean_daily_turnover": mean(changes) if changes else 0.0,
                "max_daily_turnover": max(changes) if changes else 0.0,
                "mean_baseline_weight": mean(baseline_weights),
                "mean_momentum_weight": mean(momentum_weights),
                "mean_risk_weight": mean(risk_weights),
            }
        )
    return output


def build_confidence_metrics(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    thresholds = (0.60, 0.70, 0.80)
    for (split, strategy, horizon), rows in grouped_metric_rows(predictions).items():
        for confidence_type in ("raw", "cooled"):
            key = "raw_confidence" if confidence_type == "raw" else "cooled_confidence"
            for threshold in thresholds:
                selected = [row for row in rows if row[key] >= threshold]
                output.append(
                    {
                        "split": split,
                        "strategy": strategy,
                        "horizon_days": horizon,
                        "confidence_type": confidence_type,
                        "threshold": threshold,
                        "sample_count": len(selected),
                        "coverage_rate": len(selected) / len(rows) if rows else None,
                        "wrong_rate": wrong_rate(selected),
                    }
                )
    return output


def build_regime_metrics(predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for (strategy, horizon, month), rows in group_by_tuple(predictions, ("strategy", "horizon_days", "month")).items():
        metric = prediction_metric(rows)
        output.append({"strategy": strategy, "horizon_days": int(horizon), "month": month, **metric})
    return output


def edge_deciles(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(rows) < 10:
        return [], []
    ordered = sorted(rows, key=lambda row: row["expected_return"], reverse=True)
    size = max(1, int(len(ordered) * 0.1))
    return ordered[:size], ordered[-size:]


def bucket_spread(rows: list[dict[str, Any]], score_key: str, fraction: float) -> float | None:
    if len(rows) < 5:
        return None
    ordered = sorted(rows, key=lambda row: float(row[score_key]), reverse=True)
    size = max(1, int(len(ordered) * fraction))
    return mean(float(row["actual_return"]) for row in ordered[:size]) - mean(float(row["actual_return"]) for row in ordered[-size:])


def wrong_rate(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return mean(1.0 if direction(row["expected_return"]) != direction(row["actual_return"]) else 0.0 for row in rows)


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS walk_forward_experiment_runs (
          id INTEGER PRIMARY KEY,
          created_at TEXT NOT NULL,
          experiment_name TEXT NOT NULL,
          source_db TEXT NOT NULL,
          replay_run_id INTEGER NOT NULL,
          source_run_json TEXT NOT NULL,
          config_json TEXT NOT NULL,
          matured_rows INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS walk_forward_predictions (
          experiment_id INTEGER NOT NULL,
          strategy TEXT NOT NULL,
          prediction_date TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          asset_id INTEGER NOT NULL,
          primary_model TEXT NOT NULL,
          expected_return REAL NOT NULL,
          actual_return REAL NOT NULL,
          raw_confidence REAL NOT NULL,
          cooled_confidence REAL NOT NULL,
          data_ready_sample_count INTEGER,
          weights_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS walk_forward_daily_weights (
          experiment_id INTEGER NOT NULL,
          prediction_date TEXT NOT NULL,
          strategy TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          baseline_weight REAL NOT NULL,
          momentum_weight REAL NOT NULL,
          risk_adjusted_weight REAL NOT NULL,
          data_ready_sample_count INTEGER NOT NULL,
          diagnostics_json TEXT NOT NULL,
          PRIMARY KEY (experiment_id, prediction_date, strategy, horizon_days)
        );
        CREATE TABLE IF NOT EXISTS walk_forward_metrics (
          experiment_id INTEGER NOT NULL,
          split TEXT NOT NULL,
          strategy TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          sample_count INTEGER NOT NULL,
          direction_accuracy REAL,
          mean_abs_error REAL,
          rank_ic REAL,
          bucket_spread REAL,
          top_bottom_decile_spread REAL,
          raw_high_conf_count INTEGER NOT NULL,
          raw_high_conf_wrong_rate REAL,
          cooled_high_conf_count INTEGER NOT NULL,
          cooled_high_conf_wrong_rate REAL,
          PRIMARY KEY (experiment_id, split, strategy, horizon_days)
        );
        CREATE TABLE IF NOT EXISTS walk_forward_weight_metrics (
          experiment_id INTEGER NOT NULL,
          strategy TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          days INTEGER NOT NULL,
          mean_daily_turnover REAL,
          max_daily_turnover REAL,
          mean_baseline_weight REAL,
          mean_momentum_weight REAL,
          mean_risk_weight REAL,
          PRIMARY KEY (experiment_id, strategy, horizon_days)
        );
        CREATE TABLE IF NOT EXISTS walk_forward_confidence_metrics (
          experiment_id INTEGER NOT NULL,
          split TEXT NOT NULL,
          strategy TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          confidence_type TEXT NOT NULL,
          threshold REAL NOT NULL,
          sample_count INTEGER NOT NULL,
          coverage_rate REAL,
          wrong_rate REAL,
          PRIMARY KEY (experiment_id, split, strategy, horizon_days, confidence_type, threshold)
        );
        CREATE TABLE IF NOT EXISTS walk_forward_regime_metrics (
          experiment_id INTEGER NOT NULL,
          strategy TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          month TEXT NOT NULL,
          sample_count INTEGER NOT NULL,
          direction_accuracy REAL,
          mean_abs_error REAL,
          rank_ic REAL,
          bucket_spread REAL,
          top_bottom_decile_spread REAL,
          raw_high_conf_count INTEGER NOT NULL,
          raw_high_conf_wrong_rate REAL,
          cooled_high_conf_count INTEGER NOT NULL,
          cooled_high_conf_wrong_rate REAL,
          PRIMARY KEY (experiment_id, strategy, horizon_days, month)
        );
        """
    )


def insert_run(conn: sqlite3.Connection, source_db: Path, replay_run_id: int, source_run: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    config = {"fixed_strategies": FIXED_STRATEGIES, "router_configs": ROUTER_CONFIGS, "holdout_start": HOLDOUT_START}
    cursor = conn.execute(
        """
        INSERT INTO walk_forward_experiment_runs(
          created_at, experiment_name, source_db, replay_run_id,
          source_run_json, config_json, matured_rows
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            "walk_forward_control_layers_v1",
            str(source_db),
            replay_run_id,
            json.dumps(source_run, ensure_ascii=False, default=str),
            json.dumps(config, ensure_ascii=False),
            len(rows),
        ),
    )
    return int(cursor.lastrowid)


def write_predictions(conn: sqlite3.Connection, experiment_id: int, predictions: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO walk_forward_predictions(
          experiment_id, strategy, prediction_date, horizon_days, asset_id,
          primary_model, expected_return, actual_return, raw_confidence,
          cooled_confidence, data_ready_sample_count, weights_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                experiment_id,
                row["strategy"],
                row["prediction_date"],
                row["horizon_days"],
                row["asset_id"],
                row["primary_model"],
                row["expected_return"],
                row["actual_return"],
                row["raw_confidence"],
                row["cooled_confidence"],
                row["data_ready_sample_count"],
                json.dumps(row["weights"], ensure_ascii=False),
            )
            for row in predictions
        ],
    )


def write_weights(conn: sqlite3.Connection, experiment_id: int, weights: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO walk_forward_daily_weights(
          experiment_id, prediction_date, strategy, horizon_days, baseline_weight,
          momentum_weight, risk_adjusted_weight, data_ready_sample_count, diagnostics_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                experiment_id,
                row["prediction_date"],
                row["strategy"],
                row["horizon_days"],
                row["weights"]["baseline_mean_v1"],
                row["weights"]["momentum_reversal_v1"],
                row["weights"]["risk_adjusted_factor_v1"],
                row["sample_count"] or 0,
                json.dumps({"model_scores": row.get("model_scores"), "fallback_reason": row.get("fallback_reason")}, ensure_ascii=False),
            )
            for row in weights
        ],
    )


def write_metrics(conn: sqlite3.Connection, experiment_id: int, metrics: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO walk_forward_metrics(
          experiment_id, split, strategy, horizon_days, sample_count,
          direction_accuracy, mean_abs_error, rank_ic, bucket_spread,
          top_bottom_decile_spread, raw_high_conf_count, raw_high_conf_wrong_rate,
          cooled_high_conf_count, cooled_high_conf_wrong_rate
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                experiment_id,
                row["split"],
                row["strategy"],
                row["horizon_days"],
                row["sample_count"],
                row["direction_accuracy"],
                row["mean_abs_error"],
                row["rank_ic"],
                row["bucket_spread"],
                row["top_bottom_decile_spread"],
                row["raw_high_conf_count"],
                row["raw_high_conf_wrong_rate"],
                row["cooled_high_conf_count"],
                row["cooled_high_conf_wrong_rate"],
            )
            for row in metrics
        ],
    )


def write_weight_metrics(conn: sqlite3.Connection, experiment_id: int, rows: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO walk_forward_weight_metrics(
          experiment_id, strategy, horizon_days, days, mean_daily_turnover,
          max_daily_turnover, mean_baseline_weight, mean_momentum_weight, mean_risk_weight
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                experiment_id,
                row["strategy"],
                row["horizon_days"],
                row["days"],
                row["mean_daily_turnover"],
                row["max_daily_turnover"],
                row["mean_baseline_weight"],
                row["mean_momentum_weight"],
                row["mean_risk_weight"],
            )
            for row in rows
        ],
    )


def write_confidence_metrics(conn: sqlite3.Connection, experiment_id: int, rows: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO walk_forward_confidence_metrics(
          experiment_id, split, strategy, horizon_days, confidence_type,
          threshold, sample_count, coverage_rate, wrong_rate
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                experiment_id,
                row["split"],
                row["strategy"],
                row["horizon_days"],
                row["confidence_type"],
                row["threshold"],
                row["sample_count"],
                row["coverage_rate"],
                row["wrong_rate"],
            )
            for row in rows
        ],
    )


def write_regime_metrics(conn: sqlite3.Connection, experiment_id: int, rows: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO walk_forward_regime_metrics(
          experiment_id, strategy, horizon_days, month, sample_count,
          direction_accuracy, mean_abs_error, rank_ic, bucket_spread,
          top_bottom_decile_spread, raw_high_conf_count, raw_high_conf_wrong_rate,
          cooled_high_conf_count, cooled_high_conf_wrong_rate
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                experiment_id,
                row["strategy"],
                row["horizon_days"],
                row["month"],
                row["sample_count"],
                row["direction_accuracy"],
                row["mean_abs_error"],
                row["rank_ic"],
                row["bucket_spread"],
                row["top_bottom_decile_spread"],
                row["raw_high_conf_count"],
                row["raw_high_conf_wrong_rate"],
                row["cooled_high_conf_count"],
                row["cooled_high_conf_wrong_rate"],
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
    metrics: list[dict[str, Any]],
    weight_metrics: list[dict[str, Any]],
    cooling: list[dict[str, Any]],
    regime: list[dict[str, Any]],
) -> None:
    holdout_rows = [row for row in metrics if row["split"] == "holdout" and row["strategy"] in {"fixed_baseline", "fixed_prior_route", "wf_w40_cap10", "wf_blend_20_40_60_cap10"}]
    full_rows = [row for row in metrics if row["split"] == "full" and row["strategy"] in {"fixed_baseline", "fixed_prior_route", "wf_w40_cap10", "wf_blend_20_40_60_cap10"}]
    best_by_horizon = best_metrics(metrics, split="holdout")
    cooling_rows = [
        row
        for row in cooling
        if row["split"] == "holdout" and row["strategy"] in {"fixed_baseline", "wf_blend_20_40_60_cap10"} and row["threshold"] == 0.7
    ]
    lines = [
        "# Walk-Forward Control Layer Experiment",
        "",
        f"Generated: {datetime.now().date().isoformat()}",
        "",
        "This experiment opens the source replay database read-only. It simulates monthly model routing using only outcomes whose `outcome_date` is before the first day of each prediction month.",
        "",
        "## Scope",
        "",
        f"- Source DB: `{source_db}`",
        f"- Output DB: `{output_db}`",
        f"- Replay run: `{replay_run_id}`",
        f"- Experiment ID: `{experiment_id}`",
        f"- Matured samples: {len(rows):,}",
        f"- Holdout split: prediction_date >= `{HOLDOUT_START}`",
        "",
        "## Holdout Metrics",
        "",
        "| strategy | horizon | n | direction | MAE | Rank IC | bucket | top-bottom decile | raw high-conf wrong | cooled high-conf count |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(holdout_rows, key=lambda item: (item["horizon_days"], item["strategy"])):
        lines.append(metric_line(row))
    lines.extend(["", "## Full-Sample Metrics", "", "| strategy | horizon | n | direction | MAE | Rank IC | bucket | top-bottom decile | raw high-conf wrong | cooled high-conf count |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for row in sorted(full_rows, key=lambda item: (item["horizon_days"], item["strategy"])):
        lines.append(metric_line(row))
    lines.extend(["", "## Best Holdout Candidate By Horizon", "", "| horizon | strategy | Rank IC | bucket | direction | MAE |", "| ---: | --- | ---: | ---: | ---: | ---: |"])
    for row in sorted(best_by_horizon, key=lambda item: item["horizon_days"]):
        lines.append(
            f"| {row['horizon_days']} | {row['strategy']} | {fmt(row['rank_ic'])} | {fmt(row['bucket_spread'])} | {fmt(row['direction_accuracy'])} | {fmt(row['mean_abs_error'])} |"
        )
    lines.extend(["", "## Router Turnover", "", "| strategy | horizon | mean monthly turnover | max monthly turnover | mean baseline | mean momentum | mean risk |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for row in sorted([item for item in weight_metrics if item["strategy"] in {"wf_w40_cap10", "wf_blend_20_40_60_cap10"}], key=lambda item: (item["horizon_days"], item["strategy"])):
        lines.append(
            f"| {row['strategy']} | {row['horizon_days']} | {fmt(row['mean_daily_turnover'])} | {fmt(row['max_daily_turnover'])} | {fmt(row['mean_baseline_weight'])} | {fmt(row['mean_momentum_weight'])} | {fmt(row['mean_risk_weight'])} |"
        )
    lines.extend(["", "## Confidence Cooling At 0.70 Threshold", "", "| split | strategy | horizon | type | coverage | wrong rate | count |", "| --- | --- | ---: | --- | ---: | ---: | ---: |"])
    for row in sorted(cooling_rows, key=lambda item: (item["horizon_days"], item["strategy"], item["confidence_type"])):
        lines.append(
            f"| {row['split']} | {row['strategy']} | {row['horizon_days']} | {row['confidence_type']} | {fmt(row['coverage_rate'])} | {fmt(row['wrong_rate'])} | {row['sample_count']:,} |"
        )
    lines.extend(
        [
            "",
            "## Readout",
            "",
            "- Monthly walk-forward routing is safer than a hard global switch, but it is not automatically better than fixed baseline. Treat it as a shadow control layer until it beats baseline on Rank IC/bucket without excessive turnover.",
            "- 20-day remains the main instability zone. The control layer should prefer conservative smoothing and recency confirmation rather than a fast 20-day router.",
            "- Confidence cooling is directionally justified, but the current threshold can become too strict and reduce coverage sharply. A calibrated three-band display is safer than a single high-confidence cutoff.",
            "- 60-day still has limited late-period maturity. Do not promote a 60-day ensemble until more matured April/May outcomes arrive.",
            "",
            "## Reproduce",
            "",
            "```bash",
            "python3 research/model_tuning_2026/walk_forward_control_layer_experiment.py \\",
            "  --source-db data/investment_forecasting.sqlite3 \\",
            "  --output-db research/model_tuning_2026/model_tuning_research.sqlite3 \\",
            "  --replay-run-id 1",
            "```",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def best_metrics(metrics: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    output = []
    for horizon in HORIZONS:
        candidates = [row for row in metrics if row["split"] == split and row["horizon_days"] == horizon]
        if not candidates:
            continue
        output.append(max(candidates, key=lambda row: ((row["rank_ic"] or -99) + (row["bucket_spread"] or -99))))
    return output


def metric_line(row: dict[str, Any]) -> str:
    return (
        f"| {row['strategy']} | {row['horizon_days']} | {row['sample_count']:,} | {fmt(row['direction_accuracy'])} | "
        f"{fmt(row['mean_abs_error'])} | {fmt(row['rank_ic'])} | {fmt(row['bucket_spread'])} | "
        f"{fmt(row['top_bottom_decile_spread'])} | {fmt(row['raw_high_conf_wrong_rate'])} | {row['cooled_high_conf_count']:,} |"
    )


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.3f}"


def group_by_tuple(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        materialized = dict(row)
        materialized.setdefault("month", str(row.get("prediction_date", ""))[:7])
        groups[tuple(materialized[key] for key in keys)].append(materialized)
    return dict(groups)


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


if __name__ == "__main__":
    raise SystemExit(main())
