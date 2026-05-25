from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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
    provider_source = str(getattr(provider, "source", "akshare"))
    assets = list(universe or MVP_UNIVERSE)
    summary: dict[str, int] = {}
    run_date = datetime.now(timezone.utc).date().isoformat()

    with connect(db_path) as conn:
        log_id = start_task_log(
            conn,
            task_name="akshare_ingest_mvp",
            run_date=run_date,
            message=f"Ingesting {len(assets)} assets from {start_date} to {end_date}",
        )
        ingest_warnings: list[str] = []
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
                        "source": provider_source,
                    },
                )
                asset_key = f"{universe_asset.asset_type}:{universe_asset.code}"
                effective_start_date, incremental_metadata = _incremental_start_date(
                    conn,
                    asset_id=asset_id,
                    source=provider_source,
                    requested_start_date=start_date,
                    requested_end_date=end_date,
                )
                if effective_start_date is None:
                    upsert_data_quality_report(
                        conn,
                        build_quality_report(
                            report_date=run_date,
                            scope=f"ingest:{asset_key}",
                            warnings=[],
                            metadata={
                                "asset": universe_asset.__dict__,
                                "row_count": 0,
                                "requested_start_date": start_date,
                                "requested_end_date": end_date,
                                "provider": provider.__class__.__name__,
                                **incremental_metadata,
                            },
                        ),
                    )
                    summary[asset_key] = 0
                    continue
                try:
                    prices = provider.history(universe_asset, start_date=effective_start_date, end_date=end_date)
                except Exception as exc:
                    provider_warning = _provider_warning(asset_key, exc)
                    ingest_warnings.extend(provider_warning)
                    if not continue_on_error:
                        raise
                    upsert_data_quality_report(
                        conn,
                        build_quality_report(
                            report_date=run_date,
                            scope=f"ingest:{asset_key}",
                            warnings=[f"{asset_key}: provider fetch failed: {exc}", *provider_warning],
                            metadata={
                                "asset": universe_asset.__dict__,
                                "row_count": 0,
                                "requested_start_date": start_date,
                                "requested_end_date": end_date,
                                "effective_start_date": effective_start_date,
                                "provider": provider.__class__.__name__,
                                "error": str(exc),
                                **incremental_metadata,
                            },
                        ),
                    )
                    summary[asset_key] = 0
                    continue
                warnings = validate_price_records(prices, asset_key=asset_key)
                rows = 0
                for price in prices:
                    upsert_price_daily(conn, asset_id=asset_id, source=provider_source, price=price)
                    rows += 1
                if universe_asset.asset_type == "fund" and hasattr(provider, "fund_info"):
                    try:
                        info = provider.fund_info(universe_asset)
                    except Exception as exc:
                        if not continue_on_error:
                            raise
                        warnings.append(f"{asset_key}: fund info fetch failed: {exc}")
                    else:
                        upsert_fund_info(conn, asset_id=asset_id, source=provider_source, info=info)
                upsert_data_quality_report(
                    conn,
                    build_quality_report(
                        report_date=run_date,
                        scope=f"ingest:{asset_key}",
                        warnings=warnings,
                        metadata={
                            "asset": universe_asset.__dict__,
                            "row_count": len(prices),
                            "requested_start_date": start_date,
                            "requested_end_date": end_date,
                            "effective_start_date": effective_start_date,
                            "provider": provider.__class__.__name__,
                            **incremental_metadata,
                        },
                    ),
                )
                summary[asset_key] = rows
            provider_diagnostics = _provider_diagnostics(provider)
            ingest_warnings.extend(provider_diagnostics.get("throttling_warnings", []))
            complete_task_log(
                conn,
                log_id,
                status="success",
                message=json.dumps(
                    {
                        "rows": sum(summary.values()),
                        "assets": len(assets),
                        "requested_start_date": start_date,
                        "requested_end_date": end_date,
                        "provider": provider.__class__.__name__,
                        "provider_diagnostics": provider_diagnostics,
                        "warnings": ingest_warnings,
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            provider_diagnostics = _provider_diagnostics(provider)
            complete_task_log(
                conn,
                log_id,
                status="failed",
                message=json.dumps(
                    {
                        "rows": sum(summary.values()),
                        "assets": len(assets),
                        "requested_start_date": start_date,
                        "requested_end_date": end_date,
                        "provider": provider.__class__.__name__,
                        "provider_diagnostics": provider_diagnostics,
                        "warnings": [*ingest_warnings, *provider_diagnostics.get("throttling_warnings", [])],
                    },
                    ensure_ascii=False,
                ),
                error=str(exc),
            )
            conn.commit()
            raise

    return summary


def discover_akshare_universe(
    provider: AkshareProvider | None = None,
    asset_types: tuple[str, ...] = ("stock", "etf", "fund"),
    max_assets: int | None = None,
    max_assets_per_type: int | None = None,
    offset_per_type: int = 0,
    include_core_indices: bool = True,
) -> list[UniverseAsset]:
    provider = provider or AkshareProvider()
    discovered = []
    per_type_counts: dict[str, int] = {}
    per_type_offsets: dict[str, int] = {}
    for item in provider.asset_universe(asset_types=asset_types):
        asset_type = str(item["asset_type"])
        if offset_per_type and per_type_offsets.get(asset_type, 0) < offset_per_type:
            per_type_offsets[asset_type] = per_type_offsets.get(asset_type, 0) + 1
            continue
        if max_assets_per_type is not None and per_type_counts.get(asset_type, 0) >= max_assets_per_type:
            continue
        discovered.append(
            UniverseAsset(
                code=str(item["code"]),
                name=str(item["name"]),
                asset_type=asset_type,
                market=str(item.get("market") or "CN"),
                provider_symbol=item.get("provider_symbol"),
            )
        )
        per_type_counts[asset_type] = per_type_counts.get(asset_type, 0) + 1
    if max_assets is not None:
        discovered = discovered[:max_assets]
    if include_core_indices:
        return [*CORE_INDEX_UNIVERSE, *discovered]
    return discovered


def filter_existing_universe_assets(db_path: str | Path, universe: list[UniverseAsset]) -> list[UniverseAsset]:
    init_db(db_path)
    with connect(db_path) as conn:
        existing = {
            (row["code"], row["asset_type"], row["market"], row["source"])
            for row in conn.execute("SELECT code, asset_type, market, source FROM assets")
        }
    return [
        asset
        for asset in universe
        if (asset.code, asset.asset_type, asset.market, asset.source) not in existing
    ]


def _incremental_start_date(
    conn,
    asset_id: int,
    source: str,
    requested_start_date: str,
    requested_end_date: str,
) -> tuple[str | None, dict[str, object]]:
    requested_start = _parse_date(requested_start_date)
    requested_end = _parse_date(requested_end_date)
    latest = conn.execute(
        """
        SELECT MAX(trade_date) AS latest_trade_date
        FROM price_daily
        WHERE asset_id = ? AND source = ?
        """,
        (asset_id, source),
    ).fetchone()["latest_trade_date"]
    metadata: dict[str, object] = {
        "incremental": True,
        "latest_local_trade_date": latest,
    }
    if not latest:
        metadata["incremental_action"] = "full_requested_range"
        return _compact_date(requested_start), metadata
    next_date = _parse_date(str(latest)) + timedelta(days=1)
    effective_start = max(requested_start, next_date)
    if effective_start > requested_end:
        metadata["incremental_action"] = "skip_already_current"
        metadata["effective_start_date"] = None
        return None, metadata
    metadata["incremental_action"] = "resume_after_latest_local_date"
    metadata["effective_start_date"] = _compact_date(effective_start)
    return _compact_date(effective_start), metadata


def _provider_diagnostics(provider: object) -> dict[str, object]:
    diagnostics = getattr(provider, "diagnostics", None)
    if callable(diagnostics):
        try:
            value = diagnostics()
        except Exception as exc:
            return {"diagnostics_error": str(exc)}
        if isinstance(value, dict):
            return value
    return {}


def _provider_warning(asset_key: str, exc: Exception) -> list[str]:
    text = str(exc).lower()
    warnings = []
    if "returned no history" in text or "no history" in text or "empty" in text:
        warnings.append(f"{asset_key}: provider returned an empty response; use incremental retry instead of repeated full-history downloads")
    if any(marker in text for marker in ("429", "403", "too many", "rate limit", "captcha", "anti", "访问过于频繁", "限流", "验证码")):
        warnings.append(f"{asset_key}: possible provider throttling or anti-bot response; slow down before retrying")
    return warnings


def _parse_date(value: str) -> date:
    text = str(value)
    fmt = "%Y-%m-%d" if "-" in text else "%Y%m%d"
    return datetime.strptime(text, fmt).date()


def _compact_date(value) -> str:
    return value.strftime("%Y%m%d")
