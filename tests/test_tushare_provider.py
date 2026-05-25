from __future__ import annotations

import os

import pytest

from investment_forecasting.cli import main
from investment_forecasting.data.ingestion import MVP_UNIVERSE, ingest_mvp_universe
from investment_forecasting.db import connect
from investment_forecasting.providers.akshare_provider import ProviderDataError
from investment_forecasting.providers.tushare_provider import TushareProvider


class FakeTusharePro:
    def index_daily(self, **kwargs):
        return [
            {"trade_date": "20260521", "open": 3900, "high": 3910, "low": 3890, "close": 3905, "pct_chg": 0.2, "vol": 10, "amount": 20},
            {"trade_date": "20260520", "open": 3880, "high": 3900, "low": 3870, "close": 3897, "pct_chg": 0.1, "vol": 11, "amount": 21},
        ]

    def fund_nav(self, **kwargs):
        return [
            {"nav_date": "20260521", "unit_nav": "1.234", "accum_nav": "1.888", "pct_chg": "0.3"},
        ]

    def stock_basic(self, **kwargs):
        return [{"ts_code": "600000.SH", "symbol": "600000", "name": "浦发银行"}]

    def fund_basic(self, **kwargs):
        return [
            {"ts_code": "510300.SH", "symbol": "510300", "name": "沪深300ETF", "fund_type": "ETF"},
            {"ts_code": "000001.OF", "symbol": "000001", "name": "华夏成长混合", "fund_type": "混合型"},
        ]

    def moneyflow(self, **kwargs):
        return [
            {
                "ts_code": "600519.SH",
                "trade_date": "20260522",
                "buy_sm_amount": 227.69,
                "sell_sm_amount": 684.87,
                "buy_md_amount": 343879.74,
                "sell_md_amount": 315076.86,
                "buy_lg_amount": 162104.86,
                "sell_lg_amount": 208117.70,
                "buy_elg_amount": 131026.65,
                "sell_elg_amount": 113359.51,
                "net_mf_amount": -129787.48,
            }
        ]

    def moneyflow_ths(self, **kwargs):
        return [
            {
                "trade_date": "20260522",
                "ts_code": "600519.SH",
                "name": "贵州茅台",
                "pct_change": -1.59,
                "latest": 1290.2,
                "net_amount": -129787.63,
                "buy_lg_amount": -146694.18,
                "buy_lg_amount_rate": -23.02,
                "buy_md_amount": 16939.24,
                "buy_md_amount_rate": 2.66,
                "buy_sm_amount": -32.69,
                "buy_sm_amount_rate": -0.01,
            }
        ]

    def moneyflow_hsgt(self, **kwargs):
        return [
            {
                "trade_date": "20260522",
                "hgt": 148079.68,
                "sgt": 184497.33,
                "north_money": 332577.01,
                "south_money": 53757.58,
            }
        ]

    def moneyflow_mkt_dc(self, **kwargs):
        return [
            {
                "trade_date": "20260522",
                "close_sh": 4112.90,
                "pct_change_sh": 0.87,
                "net_amount": 38840230000.0,
                "net_amount_rate": 1.34,
                "buy_elg_amount": 37362840000.0,
                "buy_elg_amount_rate": 1.29,
                "buy_lg_amount": 1477386000.0,
                "buy_lg_amount_rate": 0.05,
                "buy_md_amount": -39721730000.0,
                "buy_md_amount_rate": -1.37,
                "buy_sm_amount": 881496100.0,
                "buy_sm_amount_rate": 0.03,
            }
        ]

    def news(self, **kwargs):
        return [
            {
                "datetime": "20260523 09:30:00",
                "title": "贵州茅台盘中异动",
                "content": "白酒板块成交活跃，市场关注消费修复。",
                "url": "https://example.test/news/1",
                "channels": "财经,市场",
            }
        ]


class FakeTushareModule:
    def __init__(self):
        self.token = None
        self.pro = FakeTusharePro()
        self.pro_bar_calls = []

    def pro_api(self, token):
        self.token = token
        return self.pro

    def pro_bar(self, **kwargs):
        self.pro_bar_calls.append(kwargs)
        return [
            {"trade_date": "20260521", "open": 10, "high": 11, "low": 9, "close": 10.5, "pct_chg": 1.2, "vol": 100, "amount": 200},
        ]


class RateLimitedMoneyflowPro(FakeTusharePro):
    def moneyflow(self, **kwargs):
        raise RuntimeError("frequency limited")


class RateLimitedMoneyflowModule(FakeTushareModule):
    def __init__(self):
        super().__init__()
        self.pro = RateLimitedMoneyflowPro()


def test_tushare_provider_requires_explicit_token(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TS_TOKEN", raising=False)

    with pytest.raises(ProviderDataError, match="TUSHARE_TOKEN"):
        TushareProvider(ts_module=FakeTushareModule())


def test_tushare_provider_normalizes_index_stock_and_fund_history():
    module = FakeTushareModule()
    provider = TushareProvider(ts_module=module, token="test-token")

    index_rows = provider.history(MVP_UNIVERSE[0], "20260520", "20260521")
    stock_rows = provider.history(MVP_UNIVERSE[-1], "20260520", "20260521")
    fund = next(asset for asset in MVP_UNIVERSE if asset.asset_type == "fund")
    fund_rows = provider.history(fund, "20260520", "20260521")

    assert module.token == "test-token"
    assert index_rows[0]["trade_date"] == "2026-05-20"
    assert index_rows[-1]["close"] == 3905.0
    assert module.pro_bar_calls[0]["ts_code"] == "600519.SH"
    assert stock_rows[0]["adjusted_close"] == 10.5
    assert fund_rows[0]["nav"] == 1.234
    assert fund_rows[0]["accumulated_nav"] == 1.888


def test_tushare_provider_discovers_stock_etf_and_fund_universe():
    provider = TushareProvider(ts_module=FakeTushareModule(), token="test-token")

    rows = provider.asset_universe(asset_types=("stock", "etf", "fund"))

    assert {"code": "600000", "name": "浦发银行", "asset_type": "stock", "market": "CN", "provider_symbol": "600000.SH"} in rows
    assert {"code": "510300", "name": "沪深300ETF", "asset_type": "etf", "market": "CN", "provider_symbol": "510300.SH"} in rows
    assert {"code": "000001", "name": "华夏成长混合", "asset_type": "fund", "market": "CN", "provider_symbol": "000001.OF"} in rows


def test_tushare_provider_normalizes_capital_flow_rows():
    provider = TushareProvider(ts_module=FakeTushareModule(), token="test-token")

    stock_rows = provider.stock_capital_flow("600519")
    market_rows = provider.market_capital_flow()

    assert stock_rows[0]["flow_date"] == "2026-05-22"
    assert stock_rows[0]["subject_name"] == "贵州茅台"
    assert stock_rows[0]["close"] == 1290.2
    assert stock_rows[0]["pct_change"] == -0.0159
    assert stock_rows[0]["main_net_inflow"] == -1297874800.0
    assert stock_rows[0]["super_large_net_inflow"] == 176671400.0
    assert stock_rows[0]["large_net_inflow_pct"] == -0.2302
    assert market_rows[0]["subject_code"] == "CN_A"
    assert market_rows[0]["main_net_inflow"] == 38840230000.0
    assert market_rows[0]["large_net_inflow"] == 1477386000.0
    assert market_rows[0]["main_net_inflow_pct"] == 0.0134


def test_tushare_provider_falls_back_to_ths_capital_flow_when_moneyflow_is_limited():
    provider = TushareProvider(ts_module=RateLimitedMoneyflowModule(), token="test-token")

    rows = provider.stock_capital_flow("600519")

    assert rows[0]["subject_name"] == "贵州茅台"
    assert rows[0]["main_net_inflow"] == -1297876300.0
    assert rows[0]["super_large_net_inflow"] is None
    assert rows[0]["large_net_inflow"] == -1466941800.0


def test_tushare_provider_fetches_news_with_bounded_datetime_params():
    provider = TushareProvider(ts_module=FakeTushareModule(), token="test-token")

    rows = provider.news(source="sina", start_datetime="20260523 09:00:00", end_datetime="20260523 10:00:00")

    assert rows[0]["title"] == "贵州茅台盘中异动"


def test_ingestion_with_tushare_provider_records_provider_source(tmp_path):
    db_path = tmp_path / "tushare.sqlite3"
    provider = TushareProvider(ts_module=FakeTushareModule(), token="test-token")

    summary = ingest_mvp_universe(db_path, "20260520", "20260521", provider=provider, universe=[MVP_UNIVERSE[0]])

    with connect(db_path) as conn:
        asset = conn.execute("SELECT source FROM assets WHERE code = '000300'").fetchone()
        price = conn.execute("SELECT source FROM price_daily LIMIT 1").fetchone()
        log = conn.execute("SELECT message FROM task_logs ORDER BY id DESC LIMIT 1").fetchone()

    assert summary == {"index:000300": 2}
    assert asset["source"] == "tushare"
    assert price["source"] == "tushare"
    assert '"provider": "TushareProvider"' in log["message"]


def test_ingest_cli_provider_selection_is_explicit(capsys):
    with pytest.raises(SystemExit):
        main(["ingest", "mvp", "--help"])
    output = capsys.readouterr().out

    assert "--provider {akshare,tushare}" in output
    assert "--tushare-token" in output


def test_capital_flow_cli_provider_selection_is_explicit(capsys):
    with pytest.raises(SystemExit):
        main(["ingest", "capital-flow", "--help"])
    output = capsys.readouterr().out

    assert "--provider {akshare,tushare}" in output
    assert "--tushare-token" in output
    assert "--tushare-lookback-days" in output
