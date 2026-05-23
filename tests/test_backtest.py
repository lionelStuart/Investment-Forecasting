from __future__ import annotations

import json

import pytest

from investment_forecasting.db import connect
from investment_forecasting.quant.backtest import (
    MODEL_VERSION,
    aggregate_scores,
    forecast_from_history,
    rolling_splits,
    run_backtest,
    run_latest_forecasts,
)
from investment_forecasting.quant.features import PricePoint
from tests.test_features import seed_asset_with_prices


def prices(values: list[float]) -> list[PricePoint]:
    return [
        PricePoint(asset_id=1, trade_date=f"2026-01-{day:02d}", value=value)
        for day, value in enumerate(values, start=1)
    ]


def test_rolling_splits_do_not_include_future_rows():
    series = prices([100, 101, 102, 103, 104, 105])

    splits = rolling_splits(series, horizon_days=2, lookback_days=3)

    assert splits == [
        {"history_start_index": 0, "prediction_index": 2, "outcome_index": 4},
        {"history_start_index": 1, "prediction_index": 3, "outcome_index": 5},
    ]
    for split in splits:
        history = series[split["history_start_index"] : split["prediction_index"] + 1]
        assert history[-1].trade_date == series[split["prediction_index"]].trade_date
        assert series[split["outcome_index"]].trade_date > history[-1].trade_date


def test_forecast_from_history_uses_only_given_history():
    full_series = prices([100, 102, 104, 106, 80])
    truncated = full_series[:4]

    forecast = forecast_from_history(truncated, horizon_days=2, lookback_days=4)

    assert forecast.prediction_date == "2026-01-04"
    assert forecast.input_window_end == "2026-01-04"
    assert forecast.expected_return > 0


def test_run_latest_forecasts_is_idempotent(tmp_path):
    db_path = tmp_path / "forecast.sqlite3"
    asset_id = seed_asset_with_prices(db_path, [100, 101, 102, 103, 104])

    first = run_latest_forecasts(db_path, horizons=(5, 20, 60))
    second = run_latest_forecasts(db_path, horizons=(5, 20, 60))

    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM model_predictions").fetchone()["count"]
        row = conn.execute("SELECT * FROM model_predictions WHERE horizon_days = 5").fetchone()

    assert first == {asset_id: 3}
    assert second == first
    assert count == 3
    assert row["model_version"] == MODEL_VERSION
    assert row["input_window_end"] == "2026-01-05"
    assert "historical returns" in row["assumptions"]


def test_run_backtest_persists_scores_and_metrics(tmp_path):
    db_path = tmp_path / "backtest.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])

    result = run_backtest(db_path, horizons=(2,), lookback_days=3)
    repeat = run_backtest(db_path, horizons=(2,), lookback_days=3)

    with connect(db_path) as conn:
        runs = conn.execute("SELECT COUNT(*) AS count FROM backtest_runs").fetchone()["count"]
        rows = conn.execute("SELECT COUNT(*) AS count FROM backtest_results").fetchone()["count"]
        run = conn.execute("SELECT * FROM backtest_runs").fetchone()
        details = conn.execute("SELECT details_json FROM backtest_results ORDER BY prediction_date LIMIT 1").fetchone()

    assert result == repeat
    assert result["model_version"] == MODEL_VERSION
    assert result["horizons"][2]["count"] == 3
    assert runs == 1
    assert rows == 3
    assert run["start_date"] == "2026-01-01"
    assert run["end_date"] == "2026-01-07"
    assert json.loads(run["metrics_json"])["count"] == 3
    assert json.loads(details["details_json"])["input_window_end"] == "2026-01-03"


def test_aggregate_scores_handles_empty_results():
    metrics = aggregate_scores([])

    assert metrics["count"] == 0
    assert metrics["direction_accuracy"] is None
    assert metrics["mean_benchmark_excess"] is None


def test_score_forecast_uses_real_benchmark_excess():
    from investment_forecasting.quant.backtest import score_forecast

    result = score_forecast(
        predicted_return=0.03,
        actual_return=0.04,
        downside_risk=-0.02,
        benchmark_return=0.01,
    )

    assert result["benchmark_excess"] == pytest.approx(0.03)
    assert result["advice_score"] > 0
