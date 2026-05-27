from __future__ import annotations

import pytest

from investment_forecasting.db import connect, init_db, upsert_asset, upsert_price_daily
from investment_forecasting.cli import main as cli_main
from investment_forecasting.experts.roster import DEFAULT_ACTIVE_EXPERT_COUNT
from investment_forecasting.experts.roster import initialize_default_experts
from investment_forecasting.portfolio.accounting import (
    DEFAULT_EXPERT_INITIAL_CAPITAL,
    create_virtual_portfolio,
    ensure_expert_portfolios,
    record_virtual_order,
    value_virtual_portfolio,
)


def test_each_active_expert_receives_virtual_portfolio(tmp_path):
    db_path = tmp_path / "portfolio.sqlite3"
    initialize_default_experts(db_path)

    portfolios = ensure_expert_portfolios(db_path)
    repeated = ensure_expert_portfolios(db_path)

    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM virtual_portfolios").fetchone()["count"]

    assert len(portfolios) == DEFAULT_ACTIVE_EXPERT_COUNT
    assert len(repeated) == DEFAULT_ACTIVE_EXPERT_COUNT
    assert count == DEFAULT_ACTIVE_EXPERT_COUNT
    assert all(row["owner_type"] == "expert" for row in portfolios)
    assert all(row["initial_capital"] == DEFAULT_EXPERT_INITIAL_CAPITAL for row in portfolios)
    assert all(row["cash"] == DEFAULT_EXPERT_INITIAL_CAPITAL for row in portfolios)


def test_buy_sell_and_daily_valuation_use_stored_prices(tmp_path):
    db_path, asset_id = seed_price_asset(tmp_path)

    with connect(db_path) as conn:
        portfolio_id = create_virtual_portfolio(
            conn,
            owner_type="user",
            owner_id=1,
            name="测试组合",
            initial_capital=10_000,
        )
        buy = record_virtual_order(
            conn,
            portfolio_id=portfolio_id,
            trade_date="2026-05-20",
            side="buy",
            asset_id=asset_id,
            quantity=10,
            fee=1,
        )
        sell = record_virtual_order(
            conn,
            portfolio_id=portfolio_id,
            trade_date="2026-05-21",
            side="sell",
            asset_id=asset_id,
            quantity=4,
            fee=1,
        )
        valuation = value_virtual_portfolio(conn, portfolio_id=portfolio_id, valuation_date="2026-05-21")
        position = conn.execute("SELECT * FROM virtual_positions WHERE portfolio_id = ?", (portfolio_id,)).fetchone()
        portfolio = conn.execute("SELECT * FROM virtual_portfolios WHERE id = ?", (portfolio_id,)).fetchone()
        cash_rows = conn.execute("SELECT COUNT(*) AS count FROM virtual_cash_ledger WHERE portfolio_id = ?", (portfolio_id,)).fetchone()["count"]

    assert buy["status"] == "filled"
    assert buy["price"] == 100
    assert buy["cost_basis"] == 1001
    assert buy["realized_pnl"] == 0
    assert sell["status"] == "filled"
    assert sell["price"] == 110
    assert sell["cost_basis"] == pytest.approx(400.4)
    assert sell["realized_pnl"] == pytest.approx(38.6)
    assert position["quantity"] == 6
    assert portfolio["cash"] == 10_000 - 1_001 + 439
    assert valuation["positions_value"] == 660
    assert valuation["total_value"] == portfolio["cash"] + 660
    assert round((valuation["total_value"] / 10_000) - 1, 6) == 0.0098
    assert valuation["missing_prices"] == []
    detail = valuation["details"][0]
    assert detail["asset_id"] == asset_id
    assert detail["asset_code"] == "000300"
    assert detail["asset_name"] == "沪深300"
    assert detail["quantity"] == 6
    assert detail["average_cost"] == pytest.approx(100.1)
    assert detail["cost_basis"] == pytest.approx(600.6)
    assert detail["price"] == 110
    assert detail["price_date"] == "2026-05-21"
    assert detail["value"] == pytest.approx(660)
    assert detail["unrealized_pnl"] == pytest.approx(59.4)
    assert detail["position_return"] == pytest.approx((110 / 100.1) - 1)
    assert cash_rows == 3


def test_partial_sell_after_multiple_buys_uses_average_cost(tmp_path):
    db_path = init_db(tmp_path / "portfolio-multi-buy.sqlite3")
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": "510300",
                "name": "沪深300ETF",
                "asset_type": "etf",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "test",
            },
        )
        for trade_date, close in [("2026-05-20", 100), ("2026-05-21", 120), ("2026-05-22", 150)]:
            upsert_price_daily(
                conn,
                asset_id,
                "test",
                {
                    "trade_date": trade_date,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": None,
                    "amount": None,
                    "pct_change": None,
                    "adjusted_close": None,
                    "nav": None,
                    "accumulated_nav": None,
                    "raw_payload": "{}",
                },
            )
        portfolio_id = create_virtual_portfolio(
            conn,
            owner_type="user",
            owner_id=1,
            name="测试组合",
            initial_capital=10_000,
        )

        first_buy = record_virtual_order(conn, portfolio_id=portfolio_id, trade_date="2026-05-20", side="buy", asset_id=asset_id, quantity=10, fee=0)
        second_buy = record_virtual_order(conn, portfolio_id=portfolio_id, trade_date="2026-05-21", side="buy", asset_id=asset_id, quantity=10, fee=0)
        sell = record_virtual_order(conn, portfolio_id=portfolio_id, trade_date="2026-05-22", side="sell", asset_id=asset_id, quantity=5, fee=0)
        valuation = value_virtual_portfolio(conn, portfolio_id=portfolio_id, valuation_date="2026-05-22")
        position = conn.execute("SELECT * FROM virtual_positions WHERE portfolio_id = ? AND asset_id = ?", (portfolio_id, asset_id)).fetchone()

    assert first_buy["cost_basis"] == 1000
    assert second_buy["cost_basis"] == 1200
    assert position["quantity"] == 15
    assert position["average_cost"] == pytest.approx(110)
    assert sell["cost_basis"] == pytest.approx(550)
    assert sell["realized_pnl"] == pytest.approx(200)
    assert valuation["details"][0]["cost_basis"] == pytest.approx(1650)
    assert valuation["details"][0]["unrealized_pnl"] == pytest.approx(600)
    assert valuation["total_value"] == pytest.approx(10_000 + 800)


def test_hold_no_trade_records_decision_without_cash_change(tmp_path):
    db_path = init_db(tmp_path / "portfolio.sqlite3")

    with connect(db_path) as conn:
        portfolio_id = create_virtual_portfolio(
            conn,
            owner_type="user",
            owner_id=1,
            name="测试组合",
            initial_capital=10_000,
        )
        hold = record_virtual_order(
            conn,
            portfolio_id=portfolio_id,
            trade_date="2026-05-20",
            side="hold",
            reason="市场证据不足，保持观察。",
        )
        portfolio = conn.execute("SELECT * FROM virtual_portfolios WHERE id = ?", (portfolio_id,)).fetchone()

    assert hold["status"] == "no_trade"
    assert hold["side"] == "no_trade"
    assert hold["cash_delta"] == 0
    assert portfolio["cash"] == 10_000


def test_missing_price_records_unfilled_order_and_valuation_exception(tmp_path):
    db_path = init_db(tmp_path / "portfolio.sqlite3")
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": "NO_PRICE",
                "name": "缺价资产",
                "asset_type": "fund",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "test",
            },
        )
        portfolio_id = create_virtual_portfolio(
            conn,
            owner_type="user",
            owner_id=1,
            name="测试组合",
            initial_capital=10_000,
        )
        unfilled = record_virtual_order(
            conn,
            portfolio_id=portfolio_id,
            trade_date="2026-05-20",
            side="buy",
            asset_id=asset_id,
            quantity=10,
        )
        conn.execute(
            """
            INSERT INTO virtual_positions(portfolio_id, asset_id, quantity, average_cost)
            VALUES (?, ?, ?, ?)
            """,
            (portfolio_id, asset_id, 3, 100),
        )
        valuation = value_virtual_portfolio(conn, portfolio_id=portfolio_id, valuation_date="2026-05-20")

    assert unfilled["status"] == "unfilled"
    assert "Missing stored" in unfilled["reason"]
    assert valuation["positions_value"] == 0
    assert valuation["missing_prices"] == [{"asset_id": asset_id, "asset_code": "NO_PRICE"}]
    assert valuation["details"][0]["price"] is None


def test_portfolio_cli_create_trade_value_and_list(tmp_path, capsys):
    db_path, asset_id = seed_price_asset(tmp_path)

    assert cli_main(["portfolio", "create", "--db", str(db_path), "--name", "用户组合", "--initial-capital", "10000"]) == 0
    create_output = capsys.readouterr().out
    assert '"portfolio_id": 1' in create_output

    assert cli_main([
        "portfolio",
        "trade",
        "--db",
        str(db_path),
        "--portfolio-id",
        "1",
        "--date",
        "2026-05-20",
        "--side",
        "buy",
        "--asset-id",
        str(asset_id),
        "--quantity",
        "5",
        "--fee",
        "1",
    ]) == 0
    trade_output = capsys.readouterr().out
    assert '"status": "filled"' in trade_output

    assert cli_main(["portfolio", "value", "--db", str(db_path), "--portfolio-id", "1", "--date", "2026-05-21"]) == 0
    value_output = capsys.readouterr().out
    assert '"total_value"' in value_output

    assert cli_main(["portfolio", "list", "--db", str(db_path)]) == 0
    list_output = capsys.readouterr().out
    assert '"count": 1' in list_output
    assert "用户组合" in list_output


def seed_price_asset(tmp_path):
    db_path = init_db(tmp_path / "portfolio.sqlite3")
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": "000300",
                "name": "沪深300",
                "asset_type": "index",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "test",
            },
        )
        for trade_date, close in [("2026-05-20", 100), ("2026-05-21", 110)]:
            upsert_price_daily(
                conn,
                asset_id,
                "test",
                {
                    "trade_date": trade_date,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": None,
                    "amount": None,
                    "pct_change": None,
                    "adjusted_close": None,
                    "nav": None,
                    "accumulated_nav": None,
                    "raw_payload": "{}",
                },
            )
    return db_path, asset_id
