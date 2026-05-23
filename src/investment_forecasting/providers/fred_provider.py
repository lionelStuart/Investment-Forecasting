from __future__ import annotations

import csv
import json
import ssl
from dataclasses import dataclass
from io import StringIO
from urllib.error import URLError
from urllib.request import urlopen

import certifi


FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"


class FredDataError(RuntimeError):
    """Raised when FRED macro data cannot be downloaded or normalized."""


@dataclass(frozen=True)
class FredObservation:
    series_id: str
    observation_date: str
    value: float | None
    raw_payload: str


def fetch_fred_series(series_id: str, start_date: str, end_date: str, timeout: int = 20) -> list[FredObservation]:
    normalized_start = _date_text(start_date)
    normalized_end = _date_text(end_date)
    url = FRED_CSV_URL.format(series_id=series_id)
    try:
        with urlopen(url, timeout=timeout, context=ssl.create_default_context(cafile=certifi.where())) as response:
            payload = response.read().decode("utf-8")
    except (OSError, URLError) as exc:
        raise FredDataError(
            f"Failed to download FRED series {series_id}. "
            "If network access is blocked, retry with proxy env: "
            "export https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890 "
            "all_proxy=socks5://127.0.0.1:7890"
        ) from exc

    reader = csv.DictReader(StringIO(payload))
    observations: list[FredObservation] = []
    for row in reader:
        observation_date = row.get("observation_date") or row.get("DATE")
        raw_value = row.get(series_id)
        if not observation_date or observation_date < normalized_start or observation_date > normalized_end:
            continue
        observations.append(
            FredObservation(
                series_id=series_id,
                observation_date=observation_date,
                value=_float_or_none(raw_value),
                raw_payload=json.dumps(row, ensure_ascii=False),
            )
        )
    if not observations:
        raise FredDataError(f"FRED series {series_id} returned no observations from {normalized_start} to {normalized_end}")
    return observations


def _date_text(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def _float_or_none(value: str | None) -> float | None:
    if value in {None, "", "."}:
        return None
    try:
        return float(value)
    except ValueError:
        return None
