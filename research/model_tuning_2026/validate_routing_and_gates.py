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

from explore_model_tuning import direction, latest_replay_run_id, load_matured_rows, pearson, ranks


DEFAULT_SOURCE_DB = Path("data/investment_forecasting.sqlite3")
DEFAULT_OUTPUT_DB = Path("research/model_tuning_2026/model_tuning_research.sqlite3")
DEFAULT_REPORT = Path("research/model_tuning_2026/EXPERIMENT_ROUTING_GATES_REPORT.md")
TRAIN_END = "2026-03-31"
HOLDOUT_START = "2026-04-01"

ROUTES = {
    "baseline_all": {5: ("baseline_mean_v1",), 20: ("baseline_mean_v1",), 60: ("baseline_mean_v1",)},
    "direction_route": {5: ("baseline_mean_v1",), 20: ("baseline_mean_v1",), 60: ("baseline_mean_v1",)},
    "ranking_route": {5: ("baseline_mean_v1",), 20: ("momentum_reversal_v1",), 60: ("baseline_mean_v1",)},
    "risk_60_route": {5: ("baseline_mean_v1",), 20: ("momentum_reversal_v1",), 60: ("risk_adjusted_factor_v1",)},
    "ensemble_60_route": {5: ("baseline_mean_v1",), 20: ("momentum_reversal_v1",), 60: ("baseline_mean_v1", "risk_adjusted_factor_v1")},
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate model routing and gates without mutating the source DB.")
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
        rows = load_matured_rows(source, replay_run_id)

    train_rows = [row for row in rows if row["prediction_date"] <= TRAIN_END]
    holdout_rows = [row for row in rows if row["prediction_date"] >= HOLDOUT_START]
    gate_decisions = build_gate_decisions(train_rows)
    confidence_factors = build_confidence_factors(train_rows)

    args.output_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.output_db) as out:
        create_schema(out)
        experiment_id = insert_experiment_run(out, args.source_db, replay_run_id, source_run, rows, train_rows, holdout_rows)
        write_gate_decisions(out, experiment_id, gate_decisions)
        write_confidence_factors(out, experiment_id, confidence_factors)
        metrics = []
        deciles = []
        for split, split_rows in (("train", train_rows), ("holdout", holdout_rows), ("full", rows)):
            for strategy_name in list(ROUTES) + ["gated_ranking_route"]:
                selected = select_strategy_rows(split_rows, strategy_name, gate_decisions, confidence_factors)
                for horizon in (5, 20, 60):
                    horizon_rows = [row for row in selected if row["horizon_days"] == horizon]
                    if not horizon_rows:
                        continue
                    metric = strategy_metric(horizon_rows)
                    metric.update({"split": split, "strategy": strategy_name, "horizon_days": horizon})
                    metrics.append(metric)
                    deciles.extend(strategy_deciles(split, strategy_name, horizon, horizon_rows))
        write_strategy_metrics(out, experiment_id, metrics)
        write_strategy_deciles(out, experiment_id, deciles)
        out.commit()

    write_report(args.report, args.source_db, args.output_db, replay_run_id, experiment_id, rows, train_rows, holdout_rows, metrics, gate_decisions)
    print(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "source_db": str(args.source_db),
                "output_db": str(args.output_db),
                "report": str(args.report),
                "replay_run_id": replay_run_id,
                "matured_rows": len(rows),
                "train_rows": len(train_rows),
                "holdout_rows": len(holdout_rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS experiment_runs (
          id INTEGER PRIMARY KEY,
          created_at TEXT NOT NULL,
          experiment_name TEXT NOT NULL,
          source_db TEXT NOT NULL,
          replay_run_id INTEGER NOT NULL,
          source_run_json TEXT NOT NULL,
          config_json TEXT NOT NULL,
          matured_rows INTEGER NOT NULL,
          train_rows INTEGER NOT NULL,
          holdout_rows INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS slice_gate_decisions (
          experiment_id INTEGER NOT NULL,
          model_version TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          train_sample_count INTEGER NOT NULL,
          train_direction_accuracy REAL,
          train_rank_ic REAL,
          train_bucket_spread REAL,
          gate_enabled INTEGER NOT NULL,
          reason TEXT NOT NULL,
          PRIMARY KEY (experiment_id, model_version, horizon_days)
        );
        CREATE TABLE IF NOT EXISTS confidence_cooling_factors (
          experiment_id INTEGER NOT NULL,
          model_version TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          train_direction_accuracy REAL,
          train_high_conf_wrong_rate REAL,
          cooling_factor REAL NOT NULL,
          PRIMARY KEY (experiment_id, model_version, horizon_days)
        );
        CREATE TABLE IF NOT EXISTS strategy_metrics (
          experiment_id INTEGER NOT NULL,
          split TEXT NOT NULL,
          strategy TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          sample_count INTEGER NOT NULL,
          direction_accuracy REAL,
          mean_abs_error REAL,
          rank_ic REAL,
          bucket_spread REAL,
          top_decile_return REAL,
          bottom_decile_return REAL,
          top_bottom_decile_spread REAL,
          original_high_conf_count INTEGER NOT NULL,
          original_high_conf_wrong_rate REAL,
          cooled_high_conf_count INTEGER NOT NULL,
          cooled_high_conf_wrong_rate REAL,
          PRIMARY KEY (experiment_id, split, strategy, horizon_days)
        );
        CREATE TABLE IF NOT EXISTS strategy_deciles (
          experiment_id INTEGER NOT NULL,
          split TEXT NOT NULL,
          strategy TEXT NOT NULL,
          horizon_days INTEGER NOT NULL,
          decile INTEGER NOT NULL,
          sample_count INTEGER NOT NULL,
          mean_score REAL,
          mean_actual_return REAL,
          direction_accuracy REAL,
          PRIMARY KEY (experiment_id, split, strategy, horizon_days, decile)
        );
        """
    )


def insert_experiment_run(
    conn: sqlite3.Connection,
    source_db: Path,
    replay_run_id: int,
    source_run: dict[str, Any],
    rows: list[dict[str, Any]],
    train_rows: list[dict[str, Any]],
    holdout_rows: list[dict[str, Any]],
) -> int:
    config = {
        "experiment": "routing_and_gates_v1",
        "train_end": TRAIN_END,
        "holdout_start": HOLDOUT_START,
        "routes": ROUTES,
        "gate_rule": "enable model/horizon slice when train Rank IC >= 0 and train bucket spread >= 0",
        "confidence_rule": "cool confidence to train direction accuracy capped at 0.85 for each model/horizon",
    }
    cursor = conn.execute(
        """
        INSERT INTO experiment_runs(
          created_at, experiment_name, source_db, replay_run_id, source_run_json,
          config_json, matured_rows, train_rows, holdout_rows
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            "routing_and_gates_v1",
            str(source_db),
            replay_run_id,
            json.dumps(source_run, ensure_ascii=False, default=str),
            json.dumps(config, ensure_ascii=False),
            len(rows),
            len(train_rows),
            len(holdout_rows),
        ),
    )
    return int(cursor.lastrowid)


def build_gate_decisions(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    decisions = {}
    for (model, horizon), items in group_by_tuple(rows, ("model_version", "horizon_days")).items():
        metric = raw_metric(items, score_key="expected_return")
        rank_ic = metric["rank_ic"]
        spread = metric["bucket_spread"]
        enabled = rank_ic is not None and spread is not None and rank_ic >= 0 and spread >= 0
        decisions[(str(model), int(horizon))] = {
            "model_version": str(model),
            "horizon_days": int(horizon),
            "train_sample_count": len(items),
            "train_direction_accuracy": metric["direction_accuracy"],
            "train_rank_ic": rank_ic,
            "train_bucket_spread": spread,
            "gate_enabled": enabled,
            "reason": "positive train ranking signal" if enabled else "negative train Rank IC or bucket spread",
        }
    return decisions


def build_confidence_factors(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    factors = {}
    for (model, horizon), items in group_by_tuple(rows, ("model_version", "horizon_days")).items():
        correct = [1.0 if direction(row["expected_return"]) == direction(row["actual_return"]) else 0.0 for row in items]
        high_conf = [row for row in items if float(row.get("confidence") or 0) >= 0.8]
        high_conf_wrong = None
        if high_conf:
            high_conf_wrong = mean(1.0 if direction(row["expected_return"]) != direction(row["actual_return"]) else 0.0 for row in high_conf)
        accuracy = mean(correct) if correct else None
        factors[(str(model), int(horizon))] = {
            "model_version": str(model),
            "horizon_days": int(horizon),
            "train_direction_accuracy": accuracy,
            "train_high_conf_wrong_rate": high_conf_wrong,
            "cooling_factor": min(0.85, max(0.0, accuracy or 0.0)),
        }
    return factors


def select_strategy_rows(
    rows: list[dict[str, Any]],
    strategy_name: str,
    gate_decisions: dict[tuple[str, int], dict[str, Any]],
    confidence_factors: dict[tuple[str, int], dict[str, Any]],
) -> list[dict[str, Any]]:
    route = ROUTES["ranking_route"] if strategy_name == "gated_ranking_route" else ROUTES[strategy_name]
    selected = []
    for (date, horizon, asset_id), candidates in group_by_tuple(rows, ("prediction_date", "horizon_days", "asset_id")).items():
        models = route.get(int(horizon), ())
        routed = [row for row in candidates if row["model_version"] in models]
        if strategy_name == "gated_ranking_route":
            routed = [
                row
                for row in routed
                if gate_decisions.get((row["model_version"], int(row["horizon_days"])), {}).get("gate_enabled")
            ]
        if not routed:
            continue
        selected.append(merge_rows(routed, confidence_factors))
    return selected


def merge_rows(rows: list[dict[str, Any]], confidence_factors: dict[tuple[str, int], dict[str, Any]]) -> dict[str, Any]:
    if len(rows) == 1:
        row = dict(rows[0])
        row["strategy_score"] = float(row["expected_return"])
    else:
        row = dict(rows[0])
        row["model_version"] = "+".join(sorted(str(item["model_version"]) for item in rows))
        row["expected_return"] = mean(float(item["expected_return"]) for item in rows)
        row["strategy_score"] = mean(float(item["expected_return"]) for item in rows)
        row["confidence"] = mean(float(item.get("confidence") or 0) for item in rows)
    cooling_values = [
        confidence_factors.get((item["model_version"], int(item["horizon_days"])), {}).get("cooling_factor", 0.0)
        for item in rows
    ]
    row["cooled_confidence"] = min(float(row.get("confidence") or 0), mean(cooling_values) if cooling_values else 0.0)
    return row


def strategy_metric(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metric = raw_metric(rows, score_key="strategy_score")
    top_decile, bottom_decile = edge_deciles(rows)
    original_high_conf = [row for row in rows if float(row.get("confidence") or 0) >= 0.8]
    cooled_high_conf = [row for row in rows if float(row.get("cooled_confidence") or 0) >= 0.7]
    return {
        **metric,
        "top_decile_return": mean(float(row["actual_return"]) for row in top_decile) if top_decile else None,
        "bottom_decile_return": mean(float(row["actual_return"]) for row in bottom_decile) if bottom_decile else None,
        "top_bottom_decile_spread": (
            mean(float(row["actual_return"]) for row in top_decile) - mean(float(row["actual_return"]) for row in bottom_decile)
            if top_decile and bottom_decile
            else None
        ),
        "original_high_conf_count": len(original_high_conf),
        "original_high_conf_wrong_rate": wrong_rate(original_high_conf),
        "cooled_high_conf_count": len(cooled_high_conf),
        "cooled_high_conf_wrong_rate": wrong_rate(cooled_high_conf),
    }


def raw_metric(rows: list[dict[str, Any]], score_key: str) -> dict[str, Any]:
    return {
        "sample_count": len(rows),
        "direction_accuracy": mean(1.0 if direction(row[score_key]) == direction(row["actual_return"]) else 0.0 for row in rows),
        "mean_abs_error": mean(abs(float(row[score_key]) - float(row["actual_return"])) for row in rows),
        "rank_ic": pearson(ranks([float(row[score_key]) for row in rows]), ranks([float(row["actual_return"]) for row in rows])),
        "bucket_spread": bucket_spread(rows, score_key, fraction=0.2),
    }


def strategy_deciles(split: str, strategy_name: str, horizon: int, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) < 10:
        return []
    ordered = sorted(rows, key=lambda row: float(row["strategy_score"]), reverse=True)
    output = []
    for decile in range(1, 11):
        start = int((decile - 1) * len(ordered) / 10)
        end = int(decile * len(ordered) / 10)
        bucket = ordered[start:end]
        output.append(
            {
                "split": split,
                "strategy": strategy_name,
                "horizon_days": horizon,
                "decile": decile,
                "sample_count": len(bucket),
                "mean_score": mean(float(row["strategy_score"]) for row in bucket),
                "mean_actual_return": mean(float(row["actual_return"]) for row in bucket),
                "direction_accuracy": mean(1.0 if direction(row["strategy_score"]) == direction(row["actual_return"]) else 0.0 for row in bucket),
            }
        )
    return output


def edge_deciles(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(rows) < 10:
        return [], []
    ordered = sorted(rows, key=lambda row: float(row["strategy_score"]), reverse=True)
    size = max(1, int(len(ordered) * 0.1))
    return ordered[:size], ordered[-size:]


def bucket_spread(rows: list[dict[str, Any]], score_key: str, fraction: float = 0.2) -> float | None:
    if len(rows) < 5:
        return None
    ordered = sorted(rows, key=lambda row: float(row[score_key]), reverse=True)
    size = max(1, int(len(ordered) * fraction))
    top = ordered[:size]
    bottom = ordered[-size:]
    return mean(float(row["actual_return"]) for row in top) - mean(float(row["actual_return"]) for row in bottom)


def wrong_rate(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return mean(1.0 if direction(row["strategy_score"]) != direction(row["actual_return"]) else 0.0 for row in rows)


def group_by_tuple(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    return dict(groups)


def write_gate_decisions(conn: sqlite3.Connection, experiment_id: int, decisions: dict[tuple[str, int], dict[str, Any]]) -> None:
    for decision in decisions.values():
        conn.execute(
            """
            INSERT INTO slice_gate_decisions(
              experiment_id, model_version, horizon_days, train_sample_count,
              train_direction_accuracy, train_rank_ic, train_bucket_spread,
              gate_enabled, reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment_id,
                decision["model_version"],
                decision["horizon_days"],
                decision["train_sample_count"],
                decision["train_direction_accuracy"],
                decision["train_rank_ic"],
                decision["train_bucket_spread"],
                1 if decision["gate_enabled"] else 0,
                decision["reason"],
            ),
        )


def write_confidence_factors(conn: sqlite3.Connection, experiment_id: int, factors: dict[tuple[str, int], dict[str, Any]]) -> None:
    for factor in factors.values():
        conn.execute(
            """
            INSERT INTO confidence_cooling_factors(
              experiment_id, model_version, horizon_days, train_direction_accuracy,
              train_high_conf_wrong_rate, cooling_factor
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                experiment_id,
                factor["model_version"],
                factor["horizon_days"],
                factor["train_direction_accuracy"],
                factor["train_high_conf_wrong_rate"],
                factor["cooling_factor"],
            ),
        )


def write_strategy_metrics(conn: sqlite3.Connection, experiment_id: int, metrics: list[dict[str, Any]]) -> None:
    for metric in metrics:
        conn.execute(
            """
            INSERT INTO strategy_metrics(
              experiment_id, split, strategy, horizon_days, sample_count,
              direction_accuracy, mean_abs_error, rank_ic, bucket_spread,
              top_decile_return, bottom_decile_return, top_bottom_decile_spread,
              original_high_conf_count, original_high_conf_wrong_rate,
              cooled_high_conf_count, cooled_high_conf_wrong_rate
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment_id,
                metric["split"],
                metric["strategy"],
                metric["horizon_days"],
                metric["sample_count"],
                metric["direction_accuracy"],
                metric["mean_abs_error"],
                metric["rank_ic"],
                metric["bucket_spread"],
                metric["top_decile_return"],
                metric["bottom_decile_return"],
                metric["top_bottom_decile_spread"],
                metric["original_high_conf_count"],
                metric["original_high_conf_wrong_rate"],
                metric["cooled_high_conf_count"],
                metric["cooled_high_conf_wrong_rate"],
            ),
        )


def write_strategy_deciles(conn: sqlite3.Connection, experiment_id: int, deciles: list[dict[str, Any]]) -> None:
    for bucket in deciles:
        conn.execute(
            """
            INSERT INTO strategy_deciles(
              experiment_id, split, strategy, horizon_days, decile,
              sample_count, mean_score, mean_actual_return, direction_accuracy
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment_id,
                bucket["split"],
                bucket["strategy"],
                bucket["horizon_days"],
                bucket["decile"],
                bucket["sample_count"],
                bucket["mean_score"],
                bucket["mean_actual_return"],
                bucket["direction_accuracy"],
            ),
        )


def write_report(
    report_path: Path,
    source_db: Path,
    output_db: Path,
    replay_run_id: int,
    experiment_id: int,
    rows: list[dict[str, Any]],
    train_rows: list[dict[str, Any]],
    holdout_rows: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    gate_decisions: dict[tuple[str, int], dict[str, Any]],
) -> None:
    holdout = [metric for metric in metrics if metric["split"] == "holdout"]
    full = [metric for metric in metrics if metric["split"] == "full"]
    key_rows = [
        metric
        for metric in holdout
        if metric["strategy"] in {"baseline_all", "ranking_route", "risk_60_route", "ensemble_60_route", "gated_ranking_route"}
    ]
    key_rows.sort(key=lambda item: (item["horizon_days"], item["strategy"]))
    lines = [
        "# Routing and Gate Validation Experiment",
        "",
        f"Generated: {datetime.now().date().isoformat()}",
        "",
        "This is an isolated research artifact. The source database was opened read-only and all experiment outputs were written to the research database.",
        "",
        "## Scope",
        "",
        f"- Source DB: `{source_db}`",
        f"- Output DB: `{output_db}`",
        f"- Replay run: `{replay_run_id}`",
        f"- Experiment ID: `{experiment_id}`",
        f"- Matured samples: {len(rows):,}",
        f"- Train split: prediction_date <= `{TRAIN_END}`, rows {len(train_rows):,}",
        f"- Holdout split: prediction_date >= `{HOLDOUT_START}`, rows {len(holdout_rows):,}",
        "",
        "## Holdout Metrics",
        "",
        "| strategy | horizon | n | direction | MAE | Rank IC | bucket | top-bottom decile | high-conf wrong | cooled high-conf wrong |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for metric in key_rows:
        lines.append(
            "| {strategy} | {horizon_days} | {sample_count:,} | {direction_accuracy:.3f} | {mean_abs_error:.3f} | {rank_ic:.3f} | {bucket_spread:.3f} | {top_bottom_decile_spread:.3f} | {ohcw} | {chcw} |".format(
                **metric,
                ohcw=format_optional(metric["original_high_conf_wrong_rate"]),
                chcw=format_optional(metric["cooled_high_conf_wrong_rate"]),
            )
        )
    lines.extend(
        [
            "",
            "## Full-Sample 60-Day Metrics",
            "",
            "The 60-day horizon has no April/May holdout rows because those predictions had not matured yet.",
            "",
            "| strategy | horizon | n | direction | MAE | Rank IC | bucket | top-bottom decile |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for metric in sorted([item for item in full if item["horizon_days"] == 60], key=lambda item: item["strategy"]):
        lines.append(
            "| {strategy} | {horizon_days} | {sample_count:,} | {direction_accuracy:.3f} | {mean_abs_error:.3f} | {rank_ic:.3f} | {bucket_spread:.3f} | {top_bottom_decile_spread:.3f} |".format(
                **metric
            )
        )
    lines.extend(
        [
            "",
            "## Gate Decisions From Train Split",
            "",
            "| model | horizon | n | train direction | train Rank IC | train bucket | enabled |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for decision in sorted(gate_decisions.values(), key=lambda item: (item["horizon_days"], item["model_version"])):
        lines.append(
            "| {model_version} | {horizon_days} | {train_sample_count:,} | {train_direction_accuracy:.3f} | {train_rank_ic:.3f} | {train_bucket_spread:.3f} | {enabled} |".format(
                **decision,
                enabled="yes" if decision["gate_enabled"] else "no",
            )
        )
    lines.extend(
        [
            "",
            "## Readout",
            "",
            "- 5-day: `baseline_mean_v1` is still the best short-horizon default in the April/May holdout, but the January/March train split was negative. Do not use a static old-period gate to disable this horizon.",
            "- 20-day: the earlier full-sample preference for `momentum_reversal_v1` is not stable in the April/May holdout. Baseline wins on direction, Rank IC, and bucket spread in holdout, while momentum has lower MAE. This needs rolling, recency-weighted gating rather than a single global route.",
            "- 60-day: no independent April/May holdout is available yet. Full-sample evidence still supports `baseline_mean_v1` and `risk_adjusted_factor_v1` as ranking candidates, with baseline slightly stronger.",
            "- Train-derived hard gates are too brittle for 5-day and 20-day because regime changed after March. Use rolling monthly diagnostics as a weight/cooling input, not a binary production switch.",
            "- Confidence cooling reduces qualifying high-confidence rows to zero at the 0.70 threshold for holdout 5-day/20-day, which confirms raw confidence is not safe as product-facing certainty.",
            "",
            "## Reproduce",
            "",
            "```bash",
            "python3 research/model_tuning_2026/validate_routing_and_gates.py \\",
            "  --source-db data/investment_forecasting.sqlite3 \\",
            "  --output-db research/model_tuning_2026/model_tuning_research.sqlite3 \\",
            "  --replay-run-id 1",
            "```",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def format_optional(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return f"{value:.3f}"


if __name__ == "__main__":
    raise SystemExit(main())
