from __future__ import annotations

import json

from investment_forecasting.db import connect, init_db, upsert_asset, upsert_price_daily
from investment_forecasting.quant.model_validation import build_replay_report, build_tuning_plan, replay_ytd_predictions


def seed_prices(db_path, values: list[float], code: str = "600000", asset_type: str = "stock") -> int:
    init_db(db_path)
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": code,
                "name": code,
                "asset_type": asset_type,
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "test",
            },
        )
        for index, value in enumerate(values, start=1):
            upsert_price_daily(
                conn,
                asset_id=asset_id,
                source="test",
                price={
                    "trade_date": f"2026-01-{index:02d}",
                    "open": value,
                    "high": value,
                    "low": value,
                    "close": value,
                    "volume": None,
                    "amount": None,
                    "pct_change": None,
                    "adjusted_close": value,
                    "nav": None,
                    "accumulated_nav": None,
                    "raw_payload": None,
                },
            )
    return asset_id


def test_replay_ytd_uses_point_in_time_inputs_and_separate_tables(tmp_path):
    db_path = tmp_path / "replay.sqlite3"
    seed_prices(db_path, [100, 101, 102, 103, 104, 105, 106, 107])

    result = replay_ytd_predictions(
        db_path,
        year=2026,
        start_date="20260103",
        end_date="20260106",
        horizons=(2,),
        model_versions=("baseline_mean_v1",),
        lookback_days=3,
    )

    with connect(db_path) as conn:
        operational = conn.execute("SELECT COUNT(*) AS count FROM model_predictions").fetchone()["count"]
        rows = conn.execute("SELECT * FROM model_replay_predictions ORDER BY prediction_date").fetchall()

    assert result["written"]["matured"] == 4
    assert operational == 0
    assert rows[0]["prediction_date"] == "2026-01-03"
    assert rows[0]["input_window_end"] == "2026-01-03"
    assert rows[0]["outcome_date"] == "2026-01-05"


def test_replay_report_scores_only_matured_rows_and_counts_pending(tmp_path):
    db_path = tmp_path / "replay_report.sqlite3"
    seed_prices(db_path, [100, 101, 102, 103, 104])

    replay = replay_ytd_predictions(
        db_path,
        year=2026,
        start_date="20260103",
        end_date="20260105",
        horizons=(2,),
        model_versions=("baseline_mean_v1",),
        lookback_days=3,
    )
    report = build_replay_report(db_path, run_id=replay["run_id"])

    assert report["coverage"]["matured"] == 1
    assert report["coverage"]["pending"] == 2
    key = "baseline_mean_v1|2"
    assert report["by_model_horizon"][key]["count"] == 1


def test_tuning_plan_has_evidence_backed_recommendations(tmp_path):
    db_path = tmp_path / "tuning.sqlite3"
    seed_prices(db_path, [100, 102, 101, 103, 99, 104, 98, 105, 97, 106])

    replay = replay_ytd_predictions(
        db_path,
        year=2026,
        start_date="20260103",
        end_date="20260108",
        horizons=(1,),
        model_versions=("baseline_mean_v1",),
        lookback_days=3,
    )
    plan = build_tuning_plan(db_path, run_id=replay["run_id"])

    assert plan["recommendations"]
    assert {"priority", "title", "verification_metric", "stop_condition"}.issubset(plan["recommendations"][0])
    with connect(db_path) as conn:
        row = conn.execute("SELECT tuning_recommendations_json FROM model_replay_runs WHERE id = ?", (replay["run_id"],)).fetchone()
    assert json.loads(row["tuning_recommendations_json"])
