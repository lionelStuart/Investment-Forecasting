from __future__ import annotations

from pathlib import Path

from investment_forecasting.db import connect, init_db, upsert_macro_observation
from investment_forecasting.providers.fred_provider import fetch_fred_series


DEFAULT_FRED_SERIES = ("DGS10", "T10YIE", "DTWEXBGS")


def ingest_fred_macro(
    db_path: str | Path,
    start_date: str,
    end_date: str,
    series_ids: tuple[str, ...] = DEFAULT_FRED_SERIES,
) -> dict[str, int]:
    init_db(db_path)
    summary: dict[str, int] = {}
    with connect(db_path) as conn:
        for series_id in series_ids:
            observations = fetch_fred_series(series_id, start_date=start_date, end_date=end_date)
            count = 0
            for observation in observations:
                upsert_macro_observation(
                    conn,
                    {
                        "series_id": observation.series_id,
                        "observation_date": observation.observation_date,
                        "value": observation.value,
                        "source": "fred",
                        "raw_payload": observation.raw_payload,
                    },
                )
                count += 1
            summary[series_id] = count
    return summary
