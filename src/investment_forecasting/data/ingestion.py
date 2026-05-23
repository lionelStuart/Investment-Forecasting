from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from investment_forecasting.db import (
    complete_task_log,
    connect,
    init_db,
    start_task_log,
    upsert_asset,
    upsert_data_quality_report,
    upsert_fund_info,
    upsert_price_daily,
)
from investment_forecasting.data.quality import build_quality_report, validate_price_records
from investment_forecasting.providers.akshare_provider import AkshareProvider


@dataclass(frozen=True)
class UniverseAsset:
    code: str
    name: str
    asset_type: str
    market: str
    source: str = "akshare"
    provider_symbol: str | None = None


MVP_UNIVERSE = [
    UniverseAsset(code="000300", name="沪深300", asset_type="index", market="CN", provider_symbol="sh000300"),
    UniverseAsset(code="000905", name="中证500", asset_type="index", market="CN", provider_symbol="sh000905"),
    UniverseAsset(code="399006", name="创业板指", asset_type="index", market="CN", provider_symbol="sz399006"),
    UniverseAsset(code="000001", name="上证指数", asset_type="index", market="CN", provider_symbol="sh000001"),
    UniverseAsset(code="510300", name="沪深300ETF", asset_type="etf", market="CN", provider_symbol="sh510300"),
    UniverseAsset(code="512480", name="半导体ETF", asset_type="etf", market="CN", provider_symbol="sh512480"),
    UniverseAsset(code="511010", name="国债ETF", asset_type="etf", market="CN", provider_symbol="sh511010"),
    UniverseAsset(code="000001", name="华夏成长混合", asset_type="fund", market="CN"),
    UniverseAsset(code="110022", name="易方达消费行业股票", asset_type="fund", market="CN"),
    UniverseAsset(code="600519", name="贵州茅台", asset_type="stock", market="CN", provider_symbol="sh600519"),
]


RESEARCH_UNIVERSE = [
    *MVP_UNIVERSE,
    UniverseAsset(code="000016", name="上证50", asset_type="index", market="CN", provider_symbol="sh000016"),
    UniverseAsset(code="000852", name="中证1000", asset_type="index", market="CN", provider_symbol="sh000852"),
    UniverseAsset(code="588000", name="科创50ETF", asset_type="etf", market="CN", provider_symbol="sh588000"),
    UniverseAsset(code="159915", name="创业板ETF", asset_type="etf", market="CN", provider_symbol="sz159915"),
    UniverseAsset(code="512880", name="证券ETF", asset_type="etf", market="CN", provider_symbol="sh512880"),
    UniverseAsset(code="515790", name="光伏ETF", asset_type="etf", market="CN", provider_symbol="sh515790"),
    UniverseAsset(code="512010", name="医药ETF", asset_type="etf", market="CN", provider_symbol="sh512010"),
    UniverseAsset(code="511880", name="银华日利ETF", asset_type="etf", market="CN", provider_symbol="sh511880"),
    UniverseAsset(code="110011", name="易方达中小盘混合", asset_type="fund", market="CN"),
    UniverseAsset(code="161725", name="招商中证白酒指数", asset_type="fund", market="CN"),
    UniverseAsset(code="163406", name="兴全合润混合", asset_type="fund", market="CN"),
    UniverseAsset(code="002001", name="华夏回报混合", asset_type="fund", market="CN"),
    UniverseAsset(code="600036", name="招商银行", asset_type="stock", market="CN", provider_symbol="sh600036"),
    UniverseAsset(code="000858", name="五粮液", asset_type="stock", market="CN", provider_symbol="sz000858"),
    UniverseAsset(code="300750", name="宁德时代", asset_type="stock", market="CN", provider_symbol="sz300750"),
    UniverseAsset(code="000333", name="美的集团", asset_type="stock", market="CN", provider_symbol="sz000333"),
    UniverseAsset(code="601318", name="中国平安", asset_type="stock", market="CN", provider_symbol="sh601318"),
]


UNIVERSES = {
    "mvp": MVP_UNIVERSE,
    "research": RESEARCH_UNIVERSE,
}

CORE_INDEX_UNIVERSE = [asset for asset in RESEARCH_UNIVERSE if asset.asset_type == "index"]


def ingest_mvp_universe(
    db_path: str | Path,
    start_date: str,
    end_date: str,
    provider: AkshareProvider | None = None,
    universe: list[UniverseAsset] | tuple[UniverseAsset, ...] | None = None,
    continue_on_error: bool = False,
) -> dict[str, int]:
    init_db(db_path)
    provider = provider or AkshareProvider()
    assets = list(universe or MVP_UNIVERSE)
    summary: dict[str, int] = {}
    run_date = datetime.now(UTC).date().isoformat()

    with connect(db_path) as conn:
        log_id = start_task_log(
            conn,
            task_name="akshare_ingest_mvp",
            run_date=run_date,
            message=f"Ingesting {len(assets)} assets from {start_date} to {end_date}",
        )
        try:
            for universe_asset in assets:
                asset_id = upsert_asset(
                    conn,
                    {
                        "code": universe_asset.code,
                        "name": universe_asset.name,
                        "asset_type": universe_asset.asset_type,
                        "market": universe_asset.market,
                        "currency": "CNY",
                        "status": "active",
                        "source": universe_asset.source,
                    },
                )
                asset_key = f"{universe_asset.asset_type}:{universe_asset.code}"
                try:
                    prices = provider.history(universe_asset, start_date=start_date, end_date=end_date)
                except Exception as exc:
                    if not continue_on_error:
                        raise
                    upsert_data_quality_report(
                        conn,
                        build_quality_report(
                            report_date=run_date,
                            scope=f"ingest:{asset_key}",
                            warnings=[f"{asset_key}: provider fetch failed: {exc}"],
                            metadata={
                                "asset": universe_asset.__dict__,
                                "row_count": 0,
                                "start_date": start_date,
                                "end_date": end_date,
                                "provider": provider.__class__.__name__,
                                "error": str(exc),
                            },
                        ),
                    )
                    summary[asset_key] = 0
                    continue
                warnings = validate_price_records(prices, asset_key=asset_key)
                upsert_data_quality_report(
                    conn,
                    build_quality_report(
                        report_date=run_date,
                        scope=f"ingest:{asset_key}",
                        warnings=warnings,
                        metadata={
                            "asset": universe_asset.__dict__,
                            "row_count": len(prices),
                            "start_date": start_date,
                            "end_date": end_date,
                            "provider": provider.__class__.__name__,
                        },
                    ),
                )
                rows = 0
                for price in prices:
                    upsert_price_daily(conn, asset_id=asset_id, source=universe_asset.source, price=price)
                    rows += 1
                if universe_asset.asset_type == "fund" and hasattr(provider, "fund_info"):
                    info = provider.fund_info(universe_asset)
                    upsert_fund_info(conn, asset_id=asset_id, source=universe_asset.source, info=info)
                summary[asset_key] = rows
            complete_task_log(conn, log_id, status="success", message=f"Ingested {sum(summary.values())} rows")
        except Exception as exc:
            complete_task_log(conn, log_id, status="failed", error=str(exc))
            conn.commit()
            raise

    return summary


def discover_akshare_universe(
    provider: AkshareProvider | None = None,
    asset_types: tuple[str, ...] = ("stock", "etf", "fund"),
    max_assets: int | None = None,
    include_core_indices: bool = True,
) -> list[UniverseAsset]:
    provider = provider or AkshareProvider()
    discovered = [
        UniverseAsset(
            code=str(item["code"]),
            name=str(item["name"]),
            asset_type=str(item["asset_type"]),
            market=str(item.get("market") or "CN"),
            provider_symbol=item.get("provider_symbol"),
        )
        for item in provider.asset_universe(asset_types=asset_types)
    ]
    if max_assets is not None:
        discovered = discovered[:max_assets]
    if include_core_indices:
        return [*CORE_INDEX_UNIVERSE, *discovered]
    return discovered
