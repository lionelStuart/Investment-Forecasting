from __future__ import annotations

import json

import pytest

from investment_forecasting.db import connect
from investment_forecasting.db import init_db, upsert_asset, upsert_fund_info, upsert_price_daily
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


def seed_typed_asset_with_prices(db_path, code: str, asset_type: str, values: list[float], fund_type: str | None = None) -> int:
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
        for point in [
            PricePoint(asset_id=asset_id, trade_date=f"2026-01-{day:02d}", value=value)
            for day, value in enumerate(values, start=1)
        ]:
            upsert_price_daily(
                conn,
                asset_id=asset_id,
                source="test",
                price={
                    "trade_date": point.trade_date,
                    "open": point.value,
                    "high": point.value,
                    "low": point.value,
                    "close": point.value if asset_type != "fund" else None,
                    "volume": None,
                    "amount": None,
                    "pct_change": None,
                    "adjusted_close": point.value if asset_type != "fund" else None,
                    "nav": point.value if asset_type == "fund" else None,
                    "accumulated_nav": None,
                    "raw_payload": None,
                },
            )
        if fund_type:
            upsert_fund_info(conn, asset_id, "test", fund_info_payload(fund_type))
    return asset_id


def fund_info_payload(fund_type: str) -> dict[str, object]:
    return {
        "fund_type": fund_type,
        "fund_company": None,
        "manager": None,
        "custodian": None,
        "management_fee": None,
        "custody_fee": None,
        "purchase_fee": None,
        "scale": None,
        "inception_date": None,
        "benchmark": None,
        "strategy": None,
        "objective": None,
        "stage_returns_json": None,
        "raw_payload": None,
    }


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


def test_rolling_splits_can_embargo_overlapping_labels():
    series = prices([100, 101, 102, 103, 104, 105, 106, 107])

    splits = rolling_splits(series, horizon_days=2, lookback_days=3, embargo_days=2)

    assert splits == [
        {"history_start_index": 0, "prediction_index": 2, "outcome_index": 4},
        {"history_start_index": 3, "prediction_index": 5, "outcome_index": 7},
    ]
    assert splits[1]["prediction_index"] > splits[0]["outcome_index"]


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


def test_run_latest_forecasts_persists_prediction_reliability(tmp_path):
    db_path = tmp_path / "forecast_reliability.sqlite3"
    strong_id = seed_typed_asset_with_prices(db_path, "STRONG", "etf", [100, 101, 103, 106, 110])
    weak_id = seed_typed_asset_with_prices(db_path, "WEAK", "etf", [100, 99, 98, 97, 96])

    run_latest_forecasts(db_path, horizons=(5,))

    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT p.asset_id, r.rank_score, r.rank_position, r.rank_count,
                   r.same_category_rank, r.same_category_count,
                   r.risk_adjusted_score, r.validation_status, r.evidence_json
            FROM model_predictions p
            JOIN model_prediction_reliability r ON r.prediction_id = p.id
            WHERE p.horizon_days = 5
            ORDER BY r.rank_position
            """
        ).fetchall()

    assert len(rows) == 2
    assert rows[0]["asset_id"] == strong_id
    assert rows[0]["rank_score"] == 1.0
    assert rows[0]["rank_count"] == 2
    assert rows[0]["same_category_rank"] == 1
    assert rows[0]["same_category_count"] == 2
    assert rows[0]["risk_adjusted_score"] >= rows[1]["risk_adjusted_score"]
    assert rows[0]["validation_status"] == "unvalidated"
    assert json.loads(rows[0]["evidence_json"])["prediction_id"]
    assert rows[1]["asset_id"] == weak_id


def test_candidate_forecasts_and_backtests_are_contextual(tmp_path):
    db_path = tmp_path / "candidate_models.sqlite3"
    seed_typed_asset_with_prices(db_path, "STRONG", "etf", [100, 101, 102, 104, 107, 111, 116, 122])
    seed_typed_asset_with_prices(db_path, "WEAK", "stock", [100, 100, 99, 98, 97, 95, 94, 92])

    forecast_summary = run_latest_forecasts(
        db_path,
        horizons=(2,),
        model_versions=("baseline_mean_v1", "momentum_reversal_v1", "risk_adjusted_factor_v1"),
    )
    backtest = run_backtest(
        db_path,
        horizons=(2,),
        lookback_days=3,
        model_versions=("baseline_mean_v1", "momentum_reversal_v1", "risk_adjusted_factor_v1"),
    )

    with connect(db_path) as conn:
        prediction_versions = {
            row["model_version"]
            for row in conn.execute("SELECT DISTINCT model_version FROM model_predictions").fetchall()
        }
        reliability_versions = {
            row["model_version"]
            for row in conn.execute(
                """
                SELECT DISTINCT p.model_version
                FROM model_prediction_reliability r
                JOIN model_predictions p ON p.id = r.prediction_id
                """
            ).fetchall()
        }
        run_rows = conn.execute("SELECT model_version, parameters_json, metrics_json FROM backtest_runs").fetchall()

    assert forecast_summary == {1: 3, 2: 3}
    assert prediction_versions == {"baseline_mean_v1", "momentum_reversal_v1", "risk_adjusted_factor_v1"}
    assert reliability_versions == prediction_versions
    assert set(backtest["models"]) == prediction_versions
    for version, horizons in backtest["models"].items():
        assert horizons[2]["model_state"] in {"baseline", "candidate"}
        assert "rank_ic" in horizons[2]
    assert any(json.loads(row["parameters_json"])["model_state"] == "candidate" for row in run_rows)
    assert all(json.loads(row["metrics_json"])["model_state"] in {"baseline", "candidate"} for row in run_rows)


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


def test_run_backtest_persists_financial_validation_metrics(tmp_path):
    db_path = tmp_path / "financial_validation.sqlite3"
    seed_typed_asset_with_prices(db_path, "STRONG_A", "etf", [100, 101, 102, 103, 104, 108, 112, 116])
    seed_typed_asset_with_prices(db_path, "STRONG_B", "etf", [100, 101, 102, 104, 106, 110, 115, 120])
    seed_typed_asset_with_prices(db_path, "MID_A", "stock", [100, 100, 101, 101, 102, 103, 103, 104])
    seed_typed_asset_with_prices(db_path, "WEAK_A", "stock", [100, 99, 98, 97, 96, 95, 94, 93])
    seed_typed_asset_with_prices(db_path, "WEAK_B", "fund", [100, 99, 98, 96, 94, 92, 90, 88], "偏股混合型")

    result = run_backtest(db_path, horizons=(2,), lookback_days=3, embargo_days=1)

    metrics = result["horizons"][2]
    assert metrics["validation_policy"]["embargo_days"] == 1
    assert metrics["validation_status"] in {"validated", "degraded", "insufficient_sample", "unvalidated"}
    assert metrics["information_coefficient"] is not None
    assert metrics["rank_ic"] is not None
    assert metrics["bucket_spread"] is not None
    assert "etf" in metrics["asset_type_performance"]
    assert any(key.startswith("etf:") for key in metrics["same_category_performance"])
    assert metrics["probability_calibration"]

    with connect(db_path) as conn:
        run = conn.execute("SELECT * FROM backtest_runs WHERE horizon_days = 2").fetchone()
    stored = json.loads(run["metrics_json"])
    params = json.loads(run["parameters_json"])
    assert stored["rank_ic"] == pytest.approx(metrics["rank_ic"])
    assert params["validation_policy"]["embargo_days"] == 1


def test_fund_backtest_uses_peer_benchmark_when_available(tmp_path):
    db_path = tmp_path / "fund_peer_backtest.sqlite3"
    target_id = seed_typed_asset_with_prices(db_path, "FUND_TARGET", "fund", [100, 100, 100, 105, 110, 115], "混合型-偏股")
    seed_typed_asset_with_prices(db_path, "FUND_PEER_A", "fund", [100, 100, 100, 102, 104, 106], "偏股混合型")
    seed_typed_asset_with_prices(db_path, "FUND_PEER_B", "fund", [100, 100, 100, 103, 106, 109], "股票型")
    seed_typed_asset_with_prices(db_path, "000300", "index", [100, 100, 100, 100, 100, 100])

    run_backtest(db_path, horizons=(2,), lookback_days=3)

    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT details_json
            FROM backtest_results
            WHERE asset_id = ? AND prediction_date = '2026-01-03'
            """,
            (target_id,),
        ).fetchone()
    details = json.loads(row["details_json"])

    assert details["benchmark_source"] == "fund_peer_average"
    assert details["benchmark_identity"] == "fund_peer:equity_fund:n=2"
    assert details["benchmark_peer_count"] == 2
    assert details["benchmark_return"] == pytest.approx(0.05)


def test_aggregate_scores_handles_empty_results():
    metrics = aggregate_scores([])

    assert metrics["count"] == 0
    assert metrics["validation_status"] == "insufficient_sample"
    assert metrics["validation_policy"]["split"] == "rolling_time_series"
    assert metrics["direction_accuracy"] is None
    assert metrics["mean_benchmark_excess"] is None
    assert metrics["rank_ic"] is None


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
