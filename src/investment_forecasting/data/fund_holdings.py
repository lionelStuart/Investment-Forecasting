from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from investment_forecasting.db import connect, init_db, upsert_fund_holding
from investment_forecasting.providers.akshare_provider import AkshareProvider, ProviderDataError


class FundHoldingIngestionError(RuntimeError):
    """Raised when fund holding ingestion cannot be completed safely."""


def ingest_fund_holdings(
    db_path: str | Path,
    provider: Any | None = None,
    fund_codes: tuple[str, ...] = (),
    year: str | None = None,
) -> dict[str, int]:
    init_db(db_path)
    provider = provider or AkshareProvider()
    provider_source = str(getattr(provider, "source", "akshare"))
    target_year = str(year or date.today().year)
    with connect(db_path) as conn:
        funds = _fund_assets(conn, fund_codes)
        if not funds:
            raise FundHoldingIngestionError("No tracked fund assets found for fund holding ingestion")
        summary = {}
        for fund in funds:
            try:
                rows = list(provider.fund_stock_holdings(fund["code"], target_year))
            except ProviderDataError:
                raise
            except Exception as exc:
                raise FundHoldingIngestionError(f"Fund holding provider failed for fund:{fund['code']}: {exc}") from exc
            count = 0
            for row in rows:
                holding_asset_id = _holding_asset_id(conn, row["holding_code"])
                upsert_fund_holding(
                    conn,
                    {
                        **row,
                        "fund_asset_id": int(fund["id"]),
                        "holding_asset_id": holding_asset_id,
                        "source": row.get("source") or provider_source,
                    },
                )
                count += 1
            summary[fund["code"]] = count
        return summary


def _fund_assets(conn: Any, fund_codes: tuple[str, ...]) -> list[Any]:
    if fund_codes:
        normalized = tuple(str(code).zfill(6) for code in fund_codes)
        placeholders = ",".join("?" for _ in normalized)
        return conn.execute(
            f"""
            SELECT id, code, name
            FROM assets
            WHERE asset_type = 'fund'
              AND code IN ({placeholders})
            ORDER BY code
            """,
            normalized,
        ).fetchall()
    return conn.execute(
        """
        SELECT id, code, name
        FROM assets
        WHERE asset_type = 'fund'
          AND status = 'active'
        ORDER BY code
        LIMIT 20
        """
    ).fetchall()


def _holding_asset_id(conn: Any, holding_code: str) -> int | None:
    row = conn.execute(
        """
        SELECT id
        FROM assets
        WHERE asset_type = 'stock'
          AND code = ?
        ORDER BY id
        LIMIT 1
        """,
        (holding_code,),
    ).fetchone()
    return int(row["id"]) if row else None
