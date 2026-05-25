from __future__ import annotations

from investment_forecasting.data.capital_flow import ingest_capital_flow
from investment_forecasting.db import connect
from investment_forecasting.providers.akshare_provider import AkshareProvider, ProviderAccessPolicy, RetryConfig, normalize_capital_flow_rows
from tests.test_web_app import seed_typed_asset


class FakeCapitalFlowProvider:
    source = "fake"

    def stock_capital_flow(self, code: str) -> list[dict]:
        return [
            {
                "flow_date": "2026-05-22",
                "scope": "stock",
                "subject_code": code,
                "subject_name": code,
                "asset_id": None,
                "close": 12.3,
                "pct_change": 0.012,
                "main_net_inflow": 12000000.0,
                "main_net_inflow_pct": 0.06,
                "super_large_net_inflow": 3000000.0,
                "super_large_net_inflow_pct": 0.015,
                "large_net_inflow": 9000000.0,
                "large_net_inflow_pct": 0.045,
                "medium_net_inflow": -1000000.0,
                "medium_net_inflow_pct": -0.005,
                "small_net_inflow": -11000000.0,
                "small_net_inflow_pct": -0.055,
                "raw_payload": "{}",
                "source": self.source,
            }
        ]

    def market_capital_flow(self) -> list[dict]:
        return [
            {
                "flow_date": "2026-05-22",
                "scope": "market",
                "subject_code": "CN_A",
                "subject_name": "A股市场",
                "asset_id": None,
                "close": None,
                "pct_change": None,
                "main_net_inflow": -2300000000.0,
                "main_net_inflow_pct": None,
                "super_large_net_inflow": None,
                "super_large_net_inflow_pct": None,
                "large_net_inflow": None,
                "large_net_inflow_pct": None,
                "medium_net_inflow": None,
                "medium_net_inflow_pct": None,
                "small_net_inflow": None,
                "small_net_inflow_pct": None,
                "raw_payload": "{}",
                "source": self.source,
            }
        ]


class FailingAkshareCapitalFlowModule:
    def stock_individual_fund_flow(self, stock: str, market: str):
        raise RuntimeError("proxy refused")

    def stock_market_fund_flow(self):
        raise RuntimeError("proxy refused")


def test_normalize_capital_flow_rows_from_akshare_columns():
    rows = normalize_capital_flow_rows(
        [
            {
                "日期": "20260522",
                "收盘价": "12.30",
                "涨跌幅": "1.2",
                "主力净流入-净额": "1200",
                "主力净流入-净占比": "6.5",
                "超大单净流入-净额": "300",
                "小单净流入-净占比": "-5.5",
            }
        ],
        scope="stock",
        subject_code="1",
        subject_name="测试股票",
    )

    assert rows[0]["flow_date"] == "2026-05-22"
    assert rows[0]["subject_code"] == "000001"
    assert rows[0]["pct_change"] == 0.012
    assert rows[0]["main_net_inflow_pct"] == 0.065
    assert rows[0]["small_net_inflow_pct"] == -0.055


def test_ingest_capital_flow_persists_stock_and_market_rows(tmp_path):
    db_path = tmp_path / "capital-flow.sqlite3"
    seed_typed_asset(db_path, "600519", "贵州茅台", "stock", [100, 101, 102])

    provider = FakeCapitalFlowProvider()
    stock_summary = ingest_capital_flow(db_path, provider=provider, scope="stock", asset_codes=("600519",), max_days=5)
    market_summary = ingest_capital_flow(db_path, provider=provider, scope="market", max_days=5)
    repeat_summary = ingest_capital_flow(db_path, provider=provider, scope="stock", asset_codes=("600519",), max_days=5)

    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM capital_flow_observations ORDER BY scope, subject_code").fetchall()

    assert stock_summary == {"600519": 1}
    assert repeat_summary == stock_summary
    assert market_summary == {"market": 1}
    assert len(rows) == 2
    assert rows[0]["scope"] == "market"
    assert rows[1]["asset_id"] is not None
    assert rows[1]["subject_name"] == "贵州茅台"


def test_akshare_provider_uses_eastmoney_curl_fallback_for_capital_flow():
    payload = {
        "rc": 0,
        "data": {
            "klines": [
                "2026-05-22,-1201537024.0,-421681.0,1201958688.0,-623090752.0,-578446272.0,-18.86,-0.01,18.86,-9.78,-9.08,1290.20,-1.59,0.00,0.00"
            ]
        },
    }
    requested_urls = []

    def fake_curl(url: str) -> dict:
        requested_urls.append(url)
        return payload

    provider = AkshareProvider(
        ak_module=FailingAkshareCapitalFlowModule(),
        retry_config=RetryConfig(attempts=1, fallback_to_direct=False, fallback_to_local_proxy=False),
        access_policy=ProviderAccessPolicy(min_delay_seconds=0, jitter_seconds=0),
        curl_runner=fake_curl,
    )

    stock_rows = provider.stock_capital_flow("600519")
    market_rows = provider.market_capital_flow()

    assert stock_rows[0]["flow_date"] == "2026-05-22"
    assert stock_rows[0]["subject_code"] == "600519"
    assert stock_rows[0]["close"] == 1290.2
    assert stock_rows[0]["pct_change"] == -0.0159
    assert stock_rows[0]["main_net_inflow"] == -1201537024.0
    assert stock_rows[0]["small_net_inflow"] == -421681.0
    assert stock_rows[0]["small_net_inflow_pct"] == -0.01
    assert market_rows[0]["scope"] == "market"
    assert market_rows[0]["main_net_inflow_pct"] == -0.1886
    assert any("secid=1.600519" in url for url in requested_urls)
    assert any("secid2=0.399001" in url for url in requested_urls)
