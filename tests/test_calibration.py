from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from investment_forecasting.db import connect, init_db, upsert_asset, upsert_price_daily
from investment_forecasting.quant.calibration import (
    CANDIDATE_VERSIONS,
    CalibrationError,
    build_calibration_windows,
    candidate_prediction,
    run_calibration_report,
    run_historical_calibration_corpus,
)
from investment_forecasting.quant.features import PricePoint


def seed_calibration_prices(db_path, values: list[float]) -> None:
    init_db(db_path)
    start = date(2026, 1, 1)
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": "CAL",
                "name": "Calibration Asset",
                "asset_type": "index",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "test",
            },
        )
        for offset, value in enumerate(values):
            upsert_price_daily(
                conn,
                asset_id=asset_id,
                source="test",
                price={
                    "trade_date": (start + timedelta(days=offset)).isoformat(),
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


def test_build_calibration_windows_uses_multiple_samples_when_available():
    windows = build_calibration_windows(length=90, min_required=30)

    assert [window.name for window in windows] == ["sample_1", "sample_2", "sample_3"]
    assert windows[0].start_index == 0
    assert windows[-1].end_index == 89


def test_candidate_prediction_versions_are_distinct():
    history = [
        PricePoint(asset_id=1, trade_date="2026-01-01", value=100),
        PricePoint(asset_id=1, trade_date="2026-01-02", value=101),
        PricePoint(asset_id=1, trade_date="2026-01-03", value=103),
    ]

    baseline = candidate_prediction("baseline_mean_v1", history, horizon=2)
    momentum = candidate_prediction("momentum_last_return_v1", history, horizon=2)

    assert baseline != momentum
    assert momentum == pytest.approx(((103 / 101) - 1) * 2)


def test_run_calibration_report_persists_idempotently(tmp_path):
    db_path = tmp_path / "calibration.sqlite3"
    values = [100 + index + (index % 5) for index in range(75)]
    seed_calibration_prices(db_path, values)

    first = run_calibration_report(db_path, report_date="20260523", horizons=(2,), lookback_days=10)
    second = run_calibration_report(db_path, report_date="20260523", horizons=(2,), lookback_days=10)

    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM model_calibration_reports").fetchone()["count"]
        row = conn.execute("SELECT * FROM model_calibration_reports").fetchone()

    metrics = json.loads(row["metrics_json"])
    windows = json.loads(row["windows_json"])
    assert first["report_id"] == second["report_id"]
    assert count == 1
    assert row["promoted_version"] in CANDIDATE_VERSIONS
    assert len(windows) >= 3
    assert windows[0]["start_date"] == "2026-01-01"
    assert windows[-1]["end_date"] == "2026-03-16"
    assert set(metrics["aggregate"]) == set(CANDIDATE_VERSIONS)
    assert "mean_benchmark_excess" in metrics["aggregate"]["baseline_mean_v1"]
    assert "mean_drawdown_control" in metrics["aggregate"]["baseline_mean_v1"]
    assert row["rationale"]


def test_run_calibration_report_requires_sufficient_history(tmp_path):
    db_path = tmp_path / "calibration.sqlite3"
    seed_calibration_prices(db_path, [100, 101, 102])

    with pytest.raises(CalibrationError, match="Not enough"):
        run_calibration_report(db_path, report_date="20260523", horizons=(2,), lookback_days=10)


def test_run_historical_calibration_corpus_can_use_existing_data(tmp_path):
    db_path = tmp_path / "corpus.sqlite3"
    values = [100 + index + (index % 3) for index in range(75)]
    seed_calibration_prices(db_path, values)

    result = run_historical_calibration_corpus(
        db_path,
        start_date="20260101",
        end_date="20260316",
        report_date="20260523",
        horizons=(2,),
        lookback_days=10,
        skip_ingest=True,
    )

    assert result["ingest"] == {"skipped": True}
    assert result["calibration"]["promoted_version"] in CANDIDATE_VERSIONS
