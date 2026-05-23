from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from investment_forecasting.db import connect, init_db, list_experts


DEFAULT_EXPERT_INITIAL_CAPITAL = 500_000.0


class PortfolioError(ValueError):
    pass


def ensure_expert_portfolios(
    db_path: str | Path,
    initial_capital: float = DEFAULT_EXPERT_INITIAL_CAPITAL,
) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        experts = list_experts(conn, lifecycle_state="active")
        portfolios = [
            dict(
                _get_portfolio(
                    conn,
                    create_virtual_portfolio(
                        conn,
                        owner_type="expert",
                        owner_id=expert["id"],
                        name=f"{expert['name']}虚拟组合",
                        initial_capital=initial_capital,
                    ),
                )
            )
            for expert in experts
        ]
    return portfolios


def create_virtual_portfolio(
    conn,
    *,
    owner_type: str,
    owner_id: int | None,
    name: str,
    initial_capital: float = DEFAULT_EXPERT_INITIAL_CAPITAL,
    currency: str = "CNY",
) -> int:
    if initial_capital < 0:
        raise PortfolioError("initial_capital must be non-negative")
    cursor = conn.execute(
        """
        INSERT INTO virtual_portfolios(owner_type, owner_id, name, initial_capital, cash, currency)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(owner_type, owner_id) DO UPDATE SET
            name = excluded.name,
            initial_capital = excluded.initial_capital,
            currency = excluded.currency,
            updated_at = datetime('now')
        RETURNING id
        """,
        (owner_type, owner_id, name, initial_capital, initial_capital, currency),
    )
    portfolio_id = int(cursor.fetchone()["id"])
    _ensure_initial_cash_ledger(conn, portfolio_id, initial_capital)
    return portfolio_id


def record_virtual_order(
    conn,
    *,
    portfolio_id: int,
    trade_date: str,
    side: str,
    asset_id: int | None = None,
    quantity: float = 0.0,
    fee: float = 0.0,
    reason: str | None = None,
) -> dict[str, Any]:
    side = side.lower()
    if side in {"hold", "no_trade"}:
        transaction_id = _insert_transaction(
            conn,
            portfolio_id=portfolio_id,
            asset_id=asset_id,
            trade_date=trade_date,
            side="no_trade",
            quantity=0.0,
            price=None,
            price_date=None,
            gross_amount=0.0,
            fee=0.0,
            cash_delta=0.0,
            status="no_trade",
            reason=reason or "No trade requested.",
        )
        return dict(_get_transaction(conn, transaction_id))

    if side not in {"buy", "sell"}:
        raise PortfolioError(f"unsupported side: {side}")
    if asset_id is None:
        raise PortfolioError("asset_id is required for buy/sell orders")
    if quantity <= 0:
        raise PortfolioError("quantity must be positive for buy/sell orders")
    if fee < 0:
        raise PortfolioError("fee must be non-negative")

    price = _latest_price(conn, asset_id, trade_date)
    if price is None:
        transaction_id = _insert_transaction(
            conn,
            portfolio_id=portfolio_id,
            asset_id=asset_id,
            trade_date=trade_date,
            side="unfilled",
            quantity=quantity,
            price=None,
            price_date=None,
            gross_amount=0.0,
            fee=0.0,
            cash_delta=0.0,
            status="unfilled",
            reason="Missing stored close/nav price for or before trade date.",
        )
        return dict(_get_transaction(conn, transaction_id))

    gross_amount = quantity * float(price["price_value"])
    if side == "buy":
        return _record_buy(conn, portfolio_id, asset_id, trade_date, quantity, price, gross_amount, fee, reason)
    return _record_sell(conn, portfolio_id, asset_id, trade_date, quantity, price, gross_amount, fee, reason)


def value_virtual_portfolio(conn, *, portfolio_id: int, valuation_date: str) -> dict[str, Any]:
    portfolio = _get_portfolio(conn, portfolio_id)
    positions = conn.execute(
        """
        SELECT p.*, a.code AS asset_code, a.name AS asset_name
        FROM virtual_positions p
        JOIN assets a ON a.id = p.asset_id
        WHERE p.portfolio_id = ? AND p.quantity > 0
        ORDER BY a.code
        """,
        (portfolio_id,),
    ).fetchall()
    details = []
    missing_prices = []
    positions_value = 0.0
    for position in positions:
        price = _latest_price(conn, position["asset_id"], valuation_date)
        if price is None:
            missing_prices.append({"asset_id": position["asset_id"], "asset_code": position["asset_code"]})
            value = 0.0
            price_value = None
            price_date = None
        else:
            price_value = float(price["price_value"])
            price_date = price["trade_date"]
            value = float(position["quantity"]) * price_value
            positions_value += value
        details.append(
            {
                "asset_id": position["asset_id"],
                "asset_code": position["asset_code"],
                "asset_name": position["asset_name"],
                "quantity": position["quantity"],
                "average_cost": position["average_cost"],
                "price": price_value,
                "price_date": price_date,
                "value": value,
            }
        )
    total_value = float(portfolio["cash"]) + positions_value
    cursor = conn.execute(
        """
        INSERT INTO virtual_valuations(
            portfolio_id, valuation_date, cash, positions_value, total_value,
            missing_prices_json, details_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(portfolio_id, valuation_date) DO UPDATE SET
            cash = excluded.cash,
            positions_value = excluded.positions_value,
            total_value = excluded.total_value,
            missing_prices_json = excluded.missing_prices_json,
            details_json = excluded.details_json,
            updated_at = datetime('now')
        RETURNING *
        """,
        (
            portfolio_id,
            valuation_date,
            portfolio["cash"],
            positions_value,
            total_value,
            json.dumps(missing_prices, ensure_ascii=False),
            json.dumps(details, ensure_ascii=False),
        ),
    )
    row = dict(cursor.fetchone())
    row["missing_prices"] = json.loads(row.pop("missing_prices_json"))
    row["details"] = json.loads(row.pop("details_json"))
    return row


def _record_buy(conn, portfolio_id, asset_id, trade_date, quantity, price, gross_amount, fee, reason):
    portfolio = _get_portfolio(conn, portfolio_id)
    cash_delta = -(gross_amount + fee)
    if float(portfolio["cash"]) + cash_delta < -1e-9:
        transaction_id = _insert_transaction(
            conn,
            portfolio_id=portfolio_id,
            asset_id=asset_id,
            trade_date=trade_date,
            side="unfilled",
            quantity=quantity,
            price=price["price_value"],
            price_date=price["trade_date"],
            gross_amount=gross_amount,
            fee=fee,
            cash_delta=0.0,
            status="unfilled",
            reason="Insufficient virtual cash.",
        )
        return dict(_get_transaction(conn, transaction_id))

    position = _get_position(conn, portfolio_id, asset_id)
    old_quantity = float(position["quantity"]) if position else 0.0
    old_cost = float(position["average_cost"]) if position else 0.0
    new_quantity = old_quantity + quantity
    new_average_cost = ((old_quantity * old_cost) + gross_amount + fee) / new_quantity
    _upsert_position(conn, portfolio_id, asset_id, new_quantity, new_average_cost)
    _update_cash(conn, portfolio_id, cash_delta)
    transaction_id = _insert_transaction(
        conn,
        portfolio_id=portfolio_id,
        asset_id=asset_id,
        trade_date=trade_date,
        side="buy",
        quantity=quantity,
        price=price["price_value"],
        price_date=price["trade_date"],
        gross_amount=gross_amount,
        fee=fee,
        cash_delta=cash_delta,
        status="filled",
        reason=reason,
    )
    _insert_cash_ledger(conn, portfolio_id, transaction_id, trade_date, cash_delta, reason or "buy")
    return dict(_get_transaction(conn, transaction_id))


def _record_sell(conn, portfolio_id, asset_id, trade_date, quantity, price, gross_amount, fee, reason):
    position = _get_position(conn, portfolio_id, asset_id)
    if position is None or float(position["quantity"]) + 1e-9 < quantity:
        transaction_id = _insert_transaction(
            conn,
            portfolio_id=portfolio_id,
            asset_id=asset_id,
            trade_date=trade_date,
            side="unfilled",
            quantity=quantity,
            price=price["price_value"],
            price_date=price["trade_date"],
            gross_amount=gross_amount,
            fee=fee,
            cash_delta=0.0,
            status="unfilled",
            reason="Insufficient virtual position.",
        )
        return dict(_get_transaction(conn, transaction_id))

    new_quantity = float(position["quantity"]) - quantity
    _upsert_position(conn, portfolio_id, asset_id, new_quantity, float(position["average_cost"]))
    cash_delta = gross_amount - fee
    _update_cash(conn, portfolio_id, cash_delta)
    transaction_id = _insert_transaction(
        conn,
        portfolio_id=portfolio_id,
        asset_id=asset_id,
        trade_date=trade_date,
        side="sell",
        quantity=quantity,
        price=price["price_value"],
        price_date=price["trade_date"],
        gross_amount=gross_amount,
        fee=fee,
        cash_delta=cash_delta,
        status="filled",
        reason=reason,
    )
    _insert_cash_ledger(conn, portfolio_id, transaction_id, trade_date, cash_delta, reason or "sell")
    return dict(_get_transaction(conn, transaction_id))


def _ensure_initial_cash_ledger(conn, portfolio_id: int, initial_capital: float) -> None:
    existing = conn.execute(
        "SELECT id FROM virtual_cash_ledger WHERE portfolio_id = ? AND transaction_id IS NULL",
        (portfolio_id,),
    ).fetchone()
    if existing is None:
        _insert_cash_ledger(conn, portfolio_id, None, _today(conn), initial_capital, "initial_capital")


def _latest_price(conn, asset_id: int, valuation_date: str):
    return conn.execute(
        """
        SELECT trade_date, COALESCE(close, nav, adjusted_close) AS price_value
        FROM price_daily
        WHERE asset_id = ?
          AND trade_date <= ?
          AND COALESCE(close, nav, adjusted_close) IS NOT NULL
        ORDER BY trade_date DESC
        LIMIT 1
        """,
        (asset_id, valuation_date),
    ).fetchone()


def _get_portfolio(conn, portfolio_id: int):
    row = conn.execute("SELECT * FROM virtual_portfolios WHERE id = ?", (portfolio_id,)).fetchone()
    if row is None:
        raise PortfolioError(f"portfolio not found: {portfolio_id}")
    return row


def _get_position(conn, portfolio_id: int, asset_id: int):
    return conn.execute(
        "SELECT * FROM virtual_positions WHERE portfolio_id = ? AND asset_id = ?",
        (portfolio_id, asset_id),
    ).fetchone()


def _upsert_position(conn, portfolio_id: int, asset_id: int, quantity: float, average_cost: float) -> None:
    conn.execute(
        """
        INSERT INTO virtual_positions(portfolio_id, asset_id, quantity, average_cost)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(portfolio_id, asset_id) DO UPDATE SET
            quantity = excluded.quantity,
            average_cost = excluded.average_cost,
            updated_at = datetime('now')
        """,
        (portfolio_id, asset_id, quantity, average_cost),
    )


def _update_cash(conn, portfolio_id: int, cash_delta: float) -> None:
    conn.execute(
        "UPDATE virtual_portfolios SET cash = cash + ?, updated_at = datetime('now') WHERE id = ?",
        (cash_delta, portfolio_id),
    )


def _insert_transaction(
    conn,
    *,
    portfolio_id: int,
    asset_id: int | None,
    trade_date: str,
    side: str,
    quantity: float,
    price: float | None,
    price_date: str | None,
    gross_amount: float,
    fee: float,
    cash_delta: float,
    status: str,
    reason: str | None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO virtual_transactions(
            portfolio_id, asset_id, trade_date, side, quantity, price, price_date,
            gross_amount, fee, cash_delta, status, reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            portfolio_id,
            asset_id,
            trade_date,
            side,
            quantity,
            price,
            price_date,
            gross_amount,
            fee,
            cash_delta,
            status,
            reason,
        ),
    )
    return int(cursor.fetchone()["id"])


def _get_transaction(conn, transaction_id: int):
    return conn.execute("SELECT * FROM virtual_transactions WHERE id = ?", (transaction_id,)).fetchone()


def _insert_cash_ledger(
    conn,
    portfolio_id: int,
    transaction_id: int | None,
    ledger_date: str,
    amount: float,
    reason: str,
) -> None:
    balance_after = _get_portfolio(conn, portfolio_id)["cash"]
    conn.execute(
        """
        INSERT INTO virtual_cash_ledger(portfolio_id, transaction_id, ledger_date, amount, balance_after, reason)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (portfolio_id, transaction_id, ledger_date, amount, balance_after, reason),
    )


def _today(conn) -> str:
    return conn.execute("SELECT date('now') AS today").fetchone()["today"]
