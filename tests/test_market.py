from __future__ import annotations

import json

import pytest

from investment_forecasting.db import connect
from investment_forecasting.quant.features import calculate_features_for_db
from investment_forecasting.quant.market import MarketSnapshotError, calculate_market_snapshot
from tests.test_features import seed_asset_with_prices


def test_calculate_market_snapshot_from_stored_features(tmp_path):
    db_path = tmp_path / "market.sqlite3"
    seed_asset_with_prices(db_path, [100 + i for i in range(30)])
    calculate_features_for_db(db_path)

    snapshot = calculate_market_snapshot(db_path, snapshot_date="20260130")
    repeat = calculate_market_snapshot(db_path, snapshot_date="20260130")

    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM market_snapshots").fetchone()["count"]
        row = conn.execute("SELECT * FROM market_snapshots").fetchone()

    details = json.loads(row["details_json"])
    assert repeat["snapshot_id"] == snapshot["snapshot_id"]
    assert count == 1
    assert row["snapshot_date"] == "2026-01-30"
    assert row["sentiment"] in {"risk_on", "risk_off", "neutral"}
    assert row["breadth"] == pytest.approx(1.0)
    assert details["components"]["breadth"]


def test_market_snapshot_requires_features(tmp_path):
    db_path = tmp_path / "market.sqlite3"

    with pytest.raises(MarketSnapshotError, match="features_daily"):
        calculate_market_snapshot(db_path, snapshot_date="20260130")

