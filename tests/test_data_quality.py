from __future__ import annotations

import json

from investment_forecasting.data.quality import build_quality_report, validate_price_records


def test_validate_price_records_reports_duplicates_and_gaps():
    warnings = validate_price_records(
        [
            {"trade_date": "2026-01-01"},
            {"trade_date": "2026-01-01"},
            {"trade_date": "2026-01-20"},
        ],
        asset_key="index:TEST",
    )

    assert "index:TEST: duplicate trade_date 2026-01-01" in warnings
    assert "index:TEST: large date gap 2026-01-01 to 2026-01-20" in warnings


def test_build_quality_report_serializes_metadata():
    report = build_quality_report(
        report_date="2026-05-23",
        scope="ingest:index:TEST",
        warnings=["warning"],
        metadata={"row_count": 3},
    )

    assert report["status"] == "warning"
    assert json.loads(report["warnings_json"]) == ["warning"]
    assert json.loads(report["metadata_json"]) == {"row_count": 3}

