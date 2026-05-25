from __future__ import annotations

from pathlib import Path
from typing import Any

from investment_forecasting.db import connect, init_db, upsert_capital_flow_observation
from investment_forecasting.providers.akshare_provider import AkshareProvider, ProviderDataError


class CapitalFlowIngestionError(RuntimeError):
    """Raised when capital flow ingestion cannot be completed safely."""


def ingest_capital_flow(
    db_path: str | Path,
    provider: Any | None = None,
    scope: str = "stock",
    asset_codes: tuple[str, ...] = (),
    max_days: int = 20,
) -> dict[str, int]:
    init_db(db_path)
    provider = provider or AkshareProvider()
    if max_days <= 0:
        raise CapitalFlowIngestionError("max_days must be positive")
    if scope not in {"market", "stock"}:
        raise CapitalFlowIngestionError("capital flow ingestion currently supports market or stock scope")

    with connect(db_path) as conn:
        if scope == "market":
            rows = list(provider.market_capital_flow())
            return {"market": _persist_rows(conn, rows[-max_days:])}

        assets = _stock_assets(conn, asset_codes)
        if not assets:
            raise CapitalFlowIngestionError("No tracked stock assets found for capital flow ingestion")
        summary = {}
        for asset in assets:
            try:
                rows = list(provider.stock_capital_flow(asset["code"]))
            except ProviderDataError:
                raise
            except Exception as exc:
                raise CapitalFlowIngestionError(f"Capital flow provider failed for stock:{asset['code']}: {exc}") from exc
            for row in rows:
                row["asset_id"] = int(asset["id"])
                row["subject_code"] = asset["code"]
                row["subject_name"] = asset["name"]
            summary[asset["code"]] = _persist_rows(conn, rows[-max_days:])
        return summary


def _stock_assets(conn: Any, asset_codes: tuple[str, ...]) -> list[Any]:
    if asset_codes:
        normalized = tuple(str(code).zfill(6) for code in asset_codes)
        placeholders = ",".join("?" for _ in normalized)
        return conn.execute(
            f"""
            SELECT id, code, name
            FROM assets
            WHERE asset_type = 'stock'
              AND code IN ({placeholders})
            ORDER BY code
            """,
            normalized,
        ).fetchall()
    return conn.execute(
        """
        SELECT id, code, name
        FROM assets
        WHERE asset_type = 'stock'
          AND status = 'active'
        ORDER BY code
        LIMIT 20
        """
    ).fetchall()


def _persist_rows(conn: Any, rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        upsert_capital_flow_observation(
            conn,
            {
                "asset_id": None,
                **row,
                "source": row.get("source") or getattr(row.get("provider"), "source", None) or "akshare",
            },
        )
        count += 1
    return count
