from __future__ import annotations

import json
from datetime import date
from typing import Any


MAX_INGEST_GAP_DAYS = 15


def validate_price_records(records: list[dict[str, Any]], asset_key: str) -> list[str]:
    warnings: list[str] = []
    if not records:
        return [f"{asset_key}: no price records returned"]

    seen: set[str] = set()
    previous: date | None = None
    for record in sorted(records, key=lambda row: row.get("trade_date") or ""):
        trade_date = record.get("trade_date")
        if not trade_date:
            warnings.append(f"{asset_key}: missing trade_date")
            continue
        if trade_date in seen:
            warnings.append(f"{asset_key}: duplicate trade_date {trade_date}")
        seen.add(trade_date)
        try:
            current = date.fromisoformat(str(trade_date))
        except ValueError:
            warnings.append(f"{asset_key}: invalid trade_date {trade_date}")
            continue
        if previous and (current - previous).days > MAX_INGEST_GAP_DAYS:
            warnings.append(f"{asset_key}: large date gap {previous.isoformat()} to {current.isoformat()}")
        previous = current
    return warnings


def build_quality_report(
    report_date: str,
    scope: str,
    warnings: list[str],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "report_date": report_date,
        "scope": scope,
        "status": "warning" if warnings else "ok",
        "warnings_json": json.dumps(warnings, ensure_ascii=False),
        "metadata_json": json.dumps(metadata, ensure_ascii=False, default=str),
    }
