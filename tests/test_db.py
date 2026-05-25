from __future__ import annotations

import sqlite3

from investment_forecasting.db import active_user_preference, connect, get_asset, init_db, upsert_asset, upsert_user_preference


REQUIRED_TABLES = {
    "assets",
    "price_daily",
    "fund_info",
    "news_items",
    "news_item_links",
    "news_item_tags",
    "news_feature_daily",
    "features_daily",
    "model_predictions",
    "model_prediction_reliability",
    "backtest_runs",
    "backtest_results",
    "daily_advice",
    "task_logs",
    "agent_runs",
    "agent_tool_calls",
    "scheduler_jobs",
    "scheduler_runs",
    "scheduler_watermarks",
    "provider_rate_limits",
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
    "ai_analysis_records",
    "jarvis_daily_briefs",
    "model_monitoring_reports",
    "communication_recipients",
    "communication_adapter_configs",
    "outbound_messages",
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


def test_init_db_adds_missing_advice_benchmark_identity_columns_to_legacy_database(tmp_path):
    db_path = tmp_path / "legacy_advice_scores.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE advice_outcome_scores (
              id INTEGER PRIMARY KEY,
              advice_id INTEGER NOT NULL,
              horizon_days INTEGER NOT NULL,
              outcome_date TEXT NOT NULL,
              portfolio_return REAL,
              benchmark_return REAL,
              benchmark_excess REAL,
              drawdown_control REAL,
              prediction_score REAL,
              risk_score REAL,
              advice_score REAL,
              overall_score REAL,
              details_json TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now')),
              UNIQUE (advice_id, horizon_days)
            )
            """
        )

    init_db(db_path)

    with connect(db_path) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(advice_outcome_scores)").fetchall()}

    assert {"benchmark_identity", "benchmark_source"}.issubset(columns)


def test_init_db_adds_prediction_reliability_table_to_legacy_database(tmp_path):
    db_path = tmp_path / "legacy_prediction_reliability.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE model_predictions (
              id INTEGER PRIMARY KEY,
              asset_id INTEGER,
              prediction_date TEXT NOT NULL,
              horizon_days INTEGER NOT NULL,
              model_version TEXT NOT NULL,
              target TEXT NOT NULL,
              up_probability REAL,
              expected_return REAL,
              expected_return_low REAL,
              expected_return_high REAL,
              downside_risk REAL,
              confidence REAL,
              input_window_start TEXT,
              input_window_end TEXT,
              assumptions TEXT,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              UNIQUE (asset_id, prediction_date, horizon_days, model_version, target)
            )
            """
        )

    init_db(db_path)

    with connect(db_path) as conn:
        assert "model_prediction_reliability" in table_names(conn)
        assert "model_replay_runs" in table_names(conn)
        assert "model_replay_predictions" in table_names(conn)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(model_prediction_reliability)").fetchall()}
        replay_columns = {row["name"] for row in conn.execute("PRAGMA table_info(model_replay_predictions)").fetchall()}

    assert {"prediction_id", "rank_score", "same_category_rank", "risk_adjusted_score", "validation_status"}.issubset(columns)
    assert {"replay_run_id", "score_status", "actual_return", "overall_score"}.issubset(replay_columns)


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
