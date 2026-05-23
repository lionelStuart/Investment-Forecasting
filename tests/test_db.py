from __future__ import annotations

import sqlite3

from investment_forecasting.db import active_user_preference, connect, get_asset, init_db, upsert_asset, upsert_user_preference


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
    "user_preferences",
    "experts",
    "virtual_portfolios",
    "virtual_positions",
    "virtual_transactions",
    "virtual_cash_ledger",
    "virtual_valuations",
    "expert_plans",
    "expert_plan_items",
    "expert_scorecards",
    "expert_reviews",
    "expert_lessons",
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


def test_init_db_adds_missing_fund_info_columns_to_legacy_database(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE fund_info (
              id INTEGER PRIMARY KEY,
              asset_id INTEGER NOT NULL,
              fund_type TEXT,
              manager TEXT,
              management_fee REAL,
              custody_fee REAL,
              scale REAL,
              inception_date TEXT,
              source TEXT NOT NULL,
              raw_payload TEXT,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now')),
              UNIQUE (asset_id, source)
            )
            """
        )

    init_db(db_path)

    with connect(db_path) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(fund_info)").fetchall()}

    assert {"fund_company", "custodian", "purchase_fee", "benchmark", "strategy", "objective", "stage_returns_json"}.issubset(columns)


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


def test_user_preference_upsert_tracks_single_active_profile(tmp_path):
    db_path = init_db(tmp_path / "test.sqlite3")

    with connect(db_path) as conn:
        first_id = upsert_user_preference(
            conn,
            {
                "profile_name": "稳健账户",
                "risk_profile": "conservative",
                "investment_horizon_days": 60,
                "max_equity_pct": 0.3,
                "min_cash_pct": 0.25,
                "notes": "低波动优先",
                "is_active": 1,
            },
        )
        second_id = upsert_user_preference(
            conn,
            {
                "profile_name": "成长账户",
                "risk_profile": "aggressive",
                "investment_horizon_days": 20,
                "max_equity_pct": 0.75,
                "min_cash_pct": 0.05,
                "notes": "可接受较大波动",
                "is_active": 1,
            },
        )
        active = active_user_preference(conn)
        active_count = conn.execute("SELECT COUNT(*) AS count FROM user_preferences WHERE is_active = 1").fetchone()["count"]

    assert first_id != second_id
    assert active["profile_name"] == "成长账户"
    assert active["risk_profile"] == "aggressive"
    assert active_count == 1
