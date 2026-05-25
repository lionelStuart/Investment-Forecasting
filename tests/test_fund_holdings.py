from __future__ import annotations

import pytest

from investment_forecasting.data.fund_holdings import ingest_fund_holdings
from investment_forecasting.db import connect
from investment_forecasting.providers.akshare_provider import normalize_fund_stock_holding_rows
from tests.test_web_app import seed_typed_asset


class FakeFundHoldingProvider:
    source = "fake"

    def fund_stock_holdings(self, code: str, year: str) -> list[dict]:
        assert year == "2024"
        return [
            {
                "fund_code": code,
                "report_period": "2024年4季度股票投资明细",
                "holding_type": "stock",
                "holding_code": "600519",
                "holding_name": "贵州茅台",
                "holding_asset_id": None,
                "weight_pct": 0.082,
                "shares": 120000.0,
                "market_value": 18000000.0,
                "rank": 1,
                "raw_payload": "{}",
                "source": self.source,
            }
        ]


def test_normalize_fund_stock_holding_rows_from_akshare_columns():
    rows = normalize_fund_stock_holding_rows(
        [
            {
                "序号": 1,
                "股票代码": "600519",
                "股票名称": "贵州茅台",
                "占净值比例": "8.2",
                "持股数": "12",
                "持仓市值": "1800",
                "季度": "2024年4季度股票投资明细",
            }
        ],
        fund_code="1",
    )

    assert rows[0]["fund_code"] == "000001"
    assert rows[0]["holding_code"] == "600519"
    assert rows[0]["weight_pct"] == pytest.approx(0.082)
    assert rows[0]["shares"] == 120000
    assert rows[0]["market_value"] == 18000000
    assert rows[0]["rank"] == 1


def test_ingest_fund_holdings_persists_and_links_stock_assets(tmp_path):
    db_path = tmp_path / "fund-holdings.sqlite3"
    seed_typed_asset(db_path, "000001", "华夏成长混合", "fund", [1.0, 1.01, 1.02])
    stock_id = seed_typed_asset(db_path, "600519", "贵州茅台", "stock", [100, 101, 102])

    provider = FakeFundHoldingProvider()
    summary = ingest_fund_holdings(db_path, provider=provider, fund_codes=("000001",), year="2024")
    repeat = ingest_fund_holdings(db_path, provider=provider, fund_codes=("000001",), year="2024")

    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM fund_holdings").fetchall()

    assert summary == {"000001": 1}
    assert repeat == summary
    assert len(rows) == 1
    assert rows[0]["holding_asset_id"] == stock_id
    assert rows[0]["holding_name"] == "贵州茅台"
