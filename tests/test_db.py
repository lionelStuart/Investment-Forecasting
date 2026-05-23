from __future__ import annotations

import sqlite3

from investment_forecasting.db import connect, get_asset, init_db, upsert_asset


REQUIRED_TABLES = {
    "assets",
    "price_daily",
    "fund_info",
    "features_daily",
    "model_predictions",
    "backtest_runs",
    "backtest_results",
    "daily_advice",
    "task_logs",
}


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row["name"] for row in rows}


def test_init_db_creates_required_tables(tmp_path):
    db_path = init_db(tmp_path / "test.sqlite3")

    with connect(db_path) as conn:
        assert REQUIRED_TABLES.issubset(table_names(conn))
        migration = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = '001_init'"
        ).fetchone()
        assert migration is not None


def test_asset_upsert_is_idempotent(tmp_path):
    db_path = init_db(tmp_path / "test.sqlite3")
    asset = {
        "code": "000300",
        "name": "沪深300",
        "asset_type": "index",
        "market": "CN",
        "currency": "CNY",
        "status": "active",
        "source": "manual",
    }

    with connect(db_path) as conn:
        first_id = upsert_asset(conn, asset)
        second_id = upsert_asset(conn, {**asset, "name": "沪深300指数"})
        row = get_asset(conn, "000300", "CN")
        count = conn.execute("SELECT COUNT(*) AS count FROM assets").fetchone()["count"]

    assert first_id == second_id
    assert row is not None
    assert row["name"] == "沪深300指数"
    assert count == 1

