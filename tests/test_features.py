from __future__ import annotations

import pytest

from investment_forecasting.db import connect, init_db, upsert_asset, upsert_price_daily
from investment_forecasting.quant.features import (
    FEATURE_VERSION,
    FeatureCalculationError,
    PricePoint,
    calculate_asset_features,
    calculate_features_for_db,
)


def points(values: list[float], start_day: int = 1) -> list[PricePoint]:
    return [
        PricePoint(asset_id=1, trade_date=f"2026-01-{day:02d}", value=value)
        for day, value in enumerate(values, start=start_day)
    ]


def seed_asset_with_prices(db_path, values: list[float]) -> int:
    init_db(db_path)
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": "TEST",
                "name": "Test Asset",
                "asset_type": "index",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "test",
            },
        )
        for point in points(values):
            upsert_price_daily(
                conn,
                asset_id=asset_id,
                source="test",
                price={
                    "trade_date": point.trade_date,
                    "open": point.value,
                    "high": point.value,
                    "low": point.value,
                    "close": point.value,
                    "volume": None,
                    "amount": None,
                    "pct_change": None,
                    "adjusted_close": point.value,
                    "nav": None,
                    "accumulated_nav": None,
                    "raw_payload": None,
                },
            )
    return asset_id


def test_calculate_asset_features_known_returns_and_risk_metrics():
    features = calculate_asset_features(points([100, 110, 105, 120, 132, 118]))

    last = features[-1]
    assert last["feature_date"] == "2026-01-06"
    assert last["return_1d"] == pytest.approx((118 / 132) - 1)
    assert last["return_5d"] == pytest.approx(0.18)
    assert last["return_20d"] is None
    assert last["max_drawdown_60d"] == pytest.approx((118 / 132) - 1)
    assert last["win_rate_60d"] == pytest.approx(3 / 5)
    assert last["market_state"] == "insufficient_history"
    assert last["source"] == FEATURE_VERSION


def test_calculate_asset_features_rejects_large_date_gap():
    prices = [
        PricePoint(asset_id=1, trade_date="2026-01-01", value=100),
        PricePoint(asset_id=1, trade_date="2026-01-20", value=101),
    ]

    with pytest.raises(FeatureCalculationError, match="Large date gap"):
        calculate_asset_features(prices)


def test_calculate_features_for_db_is_idempotent(tmp_path):
    db_path = tmp_path / "features.sqlite3"
    asset_id = seed_asset_with_prices(db_path, [100, 101, 102, 103])

    first = calculate_features_for_db(db_path)
    second = calculate_features_for_db(db_path)

    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM features_daily").fetchone()["count"]
        row = conn.execute(
            """
            SELECT asset_id, feature_date, return_1d, source
            FROM features_daily
            ORDER BY feature_date DESC
            LIMIT 1
            """
        ).fetchone()
        logs = conn.execute("SELECT COUNT(*) AS count FROM task_logs WHERE status = 'success'").fetchone()["count"]

    assert first == {asset_id: 3}
    assert second == first
    assert count == 3
    assert row["asset_id"] == asset_id
    assert row["feature_date"] == "2026-01-04"
    assert row["return_1d"] == pytest.approx((103 / 102) - 1)
    assert row["source"] == FEATURE_VERSION
    assert logs == 2


def test_calculate_features_for_db_records_missing_data_failure(tmp_path):
    db_path = tmp_path / "features.sqlite3"
    init_db(db_path)
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": "GAP",
                "name": "Gap Asset",
                "asset_type": "index",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "test",
            },
        )
        for trade_date, value in [("2026-01-01", 100), ("2026-01-20", 101)]:
            upsert_price_daily(
                conn,
                asset_id=asset_id,
                source="test",
                price={
                    "trade_date": trade_date,
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

    with pytest.raises(FeatureCalculationError, match="Large date gap"):
        calculate_features_for_db(db_path)

    with connect(db_path) as conn:
        log = conn.execute("SELECT status, error FROM task_logs").fetchone()

    assert log["status"] == "failed"
    assert "Large date gap" in log["error"]

