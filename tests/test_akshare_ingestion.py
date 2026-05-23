from __future__ import annotations

import pytest

from investment_forecasting.data.ingestion import (
    MVP_UNIVERSE,
    RESEARCH_UNIVERSE,
    discover_akshare_universe,
    ingest_mvp_universe,
)
from investment_forecasting.db import connect
from investment_forecasting.providers.akshare_provider import (
    ProviderDataError,
    RetryConfig,
    normalize_fund_info,
    normalize_price_rows,
)
from investment_forecasting.providers.akshare_provider import AkshareProvider


class FakeProvider:
    def history(self, asset, start_date: str, end_date: str):
        return [
            {
                "trade_date": "2026-05-21",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 1000.0,
                "amount": 10500.0,
                "pct_change": 1.2,
                "adjusted_close": 10.5,
                "nav": 10.5 if asset.asset_type == "fund" else None,
                "accumulated_nav": 12.0 if asset.asset_type == "fund" else None,
                "raw_payload": None,
            }
        ]


class FakeProviderWithFundInfo(FakeProvider):
    def fund_info(self, asset):
        return {
            "fund_type": "混合型-偏股",
            "fund_company": "华夏基金管理有限公司",
            "manager": "测试经理",
            "custodian": "测试托管行",
            "management_fee": None,
            "custody_fee": None,
            "purchase_fee": 0.15,
            "scale": 26.44,
            "inception_date": "2001-12-18",
            "benchmark": "测试基准",
            "strategy": "测试策略",
            "objective": "测试目标",
            "stage_returns_json": "{}",
            "raw_payload": "{}",
        }


class FakeDiscoveryProvider:
    def asset_universe(self, asset_types=("stock", "etf", "fund")):
        rows = []
        if "stock" in asset_types:
            rows.append({"code": "600000", "name": "浦发银行", "asset_type": "stock", "market": "CN", "provider_symbol": "sh600000"})
        if "etf" in asset_types:
            rows.append({"code": "510050", "name": "上证50ETF", "asset_type": "etf", "market": "CN", "provider_symbol": "sh510050"})
        if "fund" in asset_types:
            rows.append({"code": "000001", "name": "华夏成长混合", "asset_type": "fund", "market": "CN"})
        return rows


class FailingProvider:
    def history(self, asset, start_date: str, end_date: str):
        raise ProviderDataError("changed columns")


class FakeAkModule:
    def fund_open_fund_info_em(self, symbol: str, indicator: str):
        return [
            {"净值日期": "2026-05-19", "单位净值": "1.0"},
            {"净值日期": "2026-05-20", "单位净值": "1.1"},
            {"净值日期": "2026-05-21", "单位净值": "1.2"},
            {"净值日期": "2026-05-22", "单位净值": "1.3"},
        ]


class FakeAkModuleWithEtfFallback:
    def fund_etf_hist_em(self, **kwargs):
        raise RuntimeError("eastmoney unavailable")

    def fund_etf_hist_sina(self, symbol: str):
        return [
            {"date": "2026-05-20", "open": 1, "high": 2, "low": 0.9, "close": 1.5, "volume": 100},
            {"date": "2026-05-22", "open": 1.5, "high": 2.1, "low": 1.4, "close": 1.8, "volume": 120},
        ]


class FakeAkModuleWithStockFallback:
    def stock_zh_a_hist(self, **kwargs):
        raise RuntimeError("eastmoney unavailable")

    def stock_zh_a_daily(self, **kwargs):
        return [
            {"date": "2026-05-20", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100},
            {"date": "2026-05-22", "open": 10.5, "high": 11.2, "low": 10.2, "close": 11.0, "volume": 120},
        ]


class FlakyAkModule:
    def __init__(self):
        self.calls = 0

    def fund_open_fund_info_em(self, symbol: str, indicator: str):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary")
        return [{"净值日期": "2026-05-20", "单位净值": "1.0"}]


class FakeAkModuleWithUniverse:
    def stock_zh_a_spot_em(self):
        return [{"代码": "600000", "名称": "浦发银行"}]

    def fund_etf_spot_em(self):
        return [{"代码": "510050", "名称": "上证50ETF"}]

    def fund_open_fund_rank_em(self, symbol: str):
        return [{"基金代码": "000001", "基金简称": "华夏成长混合"}]


def test_normalize_index_rows_from_akshare_columns():
    rows = normalize_price_rows(
        [
            {
                "日期": "2026-05-21",
                "开盘": "3880.1",
                "收盘": "3900.2",
                "最高": "3910.0",
                "最低": "3860.0",
                "成交量": "123456",
                "成交额": "987654321",
                "涨跌幅": "0.52",
            }
        ],
        asset_type="index",
    )

    assert rows == [
        {
            "trade_date": "2026-05-21",
            "open": 3880.1,
            "high": 3910.0,
            "low": 3860.0,
            "close": 3900.2,
            "volume": 123456.0,
            "amount": 987654321.0,
            "pct_change": 0.52,
            "adjusted_close": 3900.2,
            "nav": None,
            "accumulated_nav": None,
            "raw_payload": None,
        }
    ]


def test_normalize_fund_rows_from_akshare_columns():
    rows = normalize_price_rows(
        [{"净值日期": "2026-05-21", "单位净值": "1.2345", "累计净值": "2.3456", "日增长率": "0.12%"}],
        asset_type="fund",
    )

    assert rows[0]["trade_date"] == "2026-05-21"
    assert rows[0]["close"] == 1.2345
    assert rows[0]["nav"] == 1.2345
    assert rows[0]["accumulated_nav"] == 2.3456
    assert rows[0]["pct_change"] == 0.12


def test_normalize_fund_info_from_basic_and_rank_rows():
    info = normalize_fund_info(
        [
            {"item": "基金代码", "value": "000001"},
            {"item": "基金类型", "value": "混合型-偏股"},
            {"item": "基金公司", "value": "华夏基金管理有限公司"},
            {"item": "基金经理", "value": "刘睿聪"},
            {"item": "托管银行", "value": "中国建设银行"},
            {"item": "成立时间", "value": "2001-12-18"},
            {"item": "最新规模", "value": "26.44亿"},
            {"item": "业绩比较基准", "value": "本基金暂不设业绩比较基准"},
            {"item": "投资策略", "value": "成长股策略"},
            {"item": "投资目标", "value": "长期资本增值"},
        ],
        [{"基金代码": "000001", "日期": "2026-05-22", "近1月": "1.23", "近1年": "4.56", "手续费": "0.15%"}],
        code="000001",
    )

    assert info["fund_type"] == "混合型-偏股"
    assert info["manager"] == "刘睿聪"
    assert info["scale"] == 26.44
    assert info["purchase_fee"] == 0.15
    assert '"return_1m": 1.23' in info["stage_returns_json"]


def test_normalize_rejects_missing_date_column():
    with pytest.raises(ProviderDataError, match="date column"):
        normalize_price_rows([{"收盘": "3900.2"}], asset_type="index")


def test_ingest_mvp_universe_upserts_prices_without_duplicates(tmp_path):
    db_path = tmp_path / "ingest.sqlite3"

    first = ingest_mvp_universe(db_path, "20260520", "20260521", provider=FakeProvider())
    second = ingest_mvp_universe(db_path, "20260520", "20260521", provider=FakeProvider())

    with connect(db_path) as conn:
        assets = conn.execute("SELECT COUNT(*) AS count FROM assets").fetchone()["count"]
        prices = conn.execute("SELECT COUNT(*) AS count FROM price_daily").fetchone()["count"]
        reports = conn.execute("SELECT COUNT(*) AS count FROM data_quality_reports").fetchone()["count"]
        logs = conn.execute("SELECT COUNT(*) AS count FROM task_logs WHERE status = 'success'").fetchone()["count"]

    assert first == {f"{asset.asset_type}:{asset.code}": 1 for asset in MVP_UNIVERSE}
    assert second == first
    assert assets == len(MVP_UNIVERSE)
    assert prices == len(MVP_UNIVERSE)
    assert reports == len(MVP_UNIVERSE)
    assert logs == 2


def test_ingest_mvp_universe_writes_fund_info_when_provider_supports_it(tmp_path):
    db_path = tmp_path / "ingest.sqlite3"

    ingest_mvp_universe(db_path, "20260520", "20260521", provider=FakeProviderWithFundInfo())

    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM fund_info").fetchone()["count"]
        row = conn.execute("SELECT fund_type, manager, scale, purchase_fee FROM fund_info LIMIT 1").fetchone()

    expected_funds = sum(1 for asset in MVP_UNIVERSE if asset.asset_type == "fund")
    assert count == expected_funds
    assert row["fund_type"] == "混合型-偏股"
    assert row["manager"] == "测试经理"
    assert row["scale"] == 26.44
    assert row["purchase_fee"] == 0.15


def test_research_universe_extends_mvp_coverage():
    assert len(RESEARCH_UNIVERSE) > len(MVP_UNIVERSE)
    assert {asset.asset_type for asset in RESEARCH_UNIVERSE} >= {"index", "etf", "fund", "stock"}


def test_discover_akshare_universe_keeps_core_indices_and_dynamic_assets():
    universe = discover_akshare_universe(provider=FakeDiscoveryProvider(), asset_types=("stock", "etf"), max_assets=2)

    assert any(asset.code == "000300" and asset.asset_type == "index" for asset in universe)
    assert any(asset.code == "600000" and asset.provider_symbol == "sh600000" for asset in universe)
    assert any(asset.code == "510050" and asset.asset_type == "etf" for asset in universe)


def test_ingest_failure_writes_task_log(tmp_path):
    db_path = tmp_path / "ingest.sqlite3"

    with pytest.raises(ProviderDataError, match="changed columns"):
        ingest_mvp_universe(db_path, "20260520", "20260521", provider=FailingProvider())

    with connect(db_path) as conn:
        log = conn.execute("SELECT status, error FROM task_logs").fetchone()

    assert log["status"] == "failed"
    assert log["error"] == "changed columns"


def test_provider_filters_fund_history_to_requested_dates():
    provider = AkshareProvider(ak_module=FakeAkModule())
    asset = next(asset for asset in MVP_UNIVERSE if asset.asset_type == "fund")

    rows = provider.history(asset, start_date="20260520", end_date="20260521")

    assert [row["trade_date"] for row in rows] == ["2026-05-20", "2026-05-21"]


def test_provider_falls_back_to_sina_for_etf_history():
    provider = AkshareProvider(ak_module=FakeAkModuleWithEtfFallback())
    asset = next(asset for asset in MVP_UNIVERSE if asset.asset_type == "etf")

    rows = provider.history(asset, start_date="20260520", end_date="20260521")

    assert len(rows) == 1
    assert rows[0]["trade_date"] == "2026-05-20"
    assert rows[0]["close"] == 1.5


def test_provider_falls_back_for_stock_history():
    provider = AkshareProvider(ak_module=FakeAkModuleWithStockFallback())
    asset = next(asset for asset in MVP_UNIVERSE if asset.asset_type == "stock")

    rows = provider.history(asset, start_date="20260520", end_date="20260521")

    assert len(rows) == 1
    assert rows[0]["trade_date"] == "2026-05-20"
    assert rows[0]["close"] == 10.5


def test_provider_discovers_stock_etf_and_fund_universe():
    provider = AkshareProvider(ak_module=FakeAkModuleWithUniverse())

    rows = provider.asset_universe(asset_types=("stock", "etf", "fund"))

    assert rows == [
        {"code": "600000", "name": "浦发银行", "asset_type": "stock", "market": "CN", "provider_symbol": "sh600000"},
        {"code": "510050", "name": "上证50ETF", "asset_type": "etf", "market": "CN", "provider_symbol": "sh510050"},
        {"code": "000001", "name": "华夏成长混合", "asset_type": "fund", "market": "CN", "provider_symbol": None},
    ]


def test_provider_retries_transient_failures():
    ak_module = FlakyAkModule()
    provider = AkshareProvider(ak_module=ak_module, retry_config=RetryConfig(attempts=2))
    asset = next(asset for asset in MVP_UNIVERSE if asset.asset_type == "fund")

    rows = provider.history(asset, start_date="20260520", end_date="20260520")

    assert ak_module.calls == 2
    assert rows[0]["trade_date"] == "2026-05-20"


def test_mvp_universe_has_representative_assets():
    by_type = {}
    for asset in MVP_UNIVERSE:
        by_type.setdefault(asset.asset_type, []).append(asset.code)

    assert {"000300", "000905", "399006", "000001"}.issubset(set(by_type["index"]))
    assert len(by_type["etf"]) >= 3
    assert len(by_type["fund"]) >= 2
    assert "600519" in by_type["stock"]


def test_normalize_stock_rows_from_akshare_columns():
    rows = normalize_price_rows(
        [
            {
                "日期": "2026-05-21",
                "开盘": "1670.1",
                "收盘": "1688.2",
                "最高": "1690.0",
                "最低": "1660.0",
                "成交量": "12345",
                "成交额": "2080000000",
                "涨跌幅": "1.02",
            }
        ],
        asset_type="stock",
    )

    assert rows[0]["trade_date"] == "2026-05-21"
    assert rows[0]["close"] == 1688.2
    assert rows[0]["adjusted_close"] == 1688.2
