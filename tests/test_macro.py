from __future__ import annotations

import json

from investment_forecasting.data import macro
from investment_forecasting.db import connect
from investment_forecasting.providers.fred_provider import FredObservation
from investment_forecasting.quant.features import calculate_features_for_db
from investment_forecasting.quant.market import calculate_market_snapshot
from tests.test_features import seed_asset_with_prices


def test_ingest_fred_macro_persists_observations(tmp_path, monkeypatch):
    db_path = tmp_path / "macro.sqlite3"

    def fake_fetch(series_id: str, start_date: str, end_date: str) -> list[FredObservation]:
        assert start_date == "20260101"
        assert end_date == "20260131"
        return [
            FredObservation(
                series_id=series_id,
                observation_date="2026-01-02",
                value=4.1,
                raw_payload=json.dumps({"observation_date": "2026-01-02", series_id: "4.1"}),
            )
        ]

    monkeypatch.setattr(macro, "fetch_fred_series", fake_fetch)

    summary = macro.ingest_fred_macro(db_path, "20260101", "20260131", series_ids=("DGS10", "T10YIE"))
    repeat = macro.ingest_fred_macro(db_path, "20260101", "20260131", series_ids=("DGS10", "T10YIE"))

    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM macro_observations").fetchone()["count"]
        rows = conn.execute("SELECT * FROM macro_observations ORDER BY series_id").fetchall()

    assert summary == {"DGS10": 1, "T10YIE": 1}
    assert repeat == summary
    assert count == 2
    assert [row["series_id"] for row in rows] == ["DGS10", "T10YIE"]
    assert rows[0]["value"] == 4.1


def test_market_snapshot_includes_latest_macro_observations(tmp_path, monkeypatch):
    db_path = tmp_path / "macro-market.sqlite3"
    seed_asset_with_prices(db_path, [100 + i for i in range(30)])
    calculate_features_for_db(db_path)

    monkeypatch.setattr(
        macro,
        "fetch_fred_series",
        lambda series_id, start_date, end_date: [
            FredObservation(series_id, "2026-01-15", 4.2, "{}"),
            FredObservation(series_id, "2026-01-29", 4.4, "{}"),
        ],
    )
    macro.ingest_fred_macro(db_path, "20260101", "20260131", series_ids=("DGS10",))

    snapshot = calculate_market_snapshot(db_path, snapshot_date="20260130")
    details = json.loads(snapshot["details_json"])

    assert details["macro"]["DGS10"]["observation_date"] == "2026-01-29"
    assert details["macro"]["DGS10"]["value"] == 4.4
