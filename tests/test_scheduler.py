from __future__ import annotations

import json
from datetime import datetime

from investment_forecasting.cli import main as cli_main
from investment_forecasting.db import connect, init_db, upsert_asset, upsert_feature_daily, upsert_price_daily
from investment_forecasting.scheduler import initialize_scheduler, record_provider_failure, run_due_jobs, run_scheduler_job, scheduler_status


def test_scheduler_initializes_fixed_incremental_sync_jobs(tmp_path):
    db_path = init_db(tmp_path / "scheduler.sqlite3")

    jobs = initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))

    job_by_key = {job["job_key"]: job for job in jobs}
    assert job_by_key["news_hourly_incremental"]["time_window"]["fixed_minute"] == 5
    assert job_by_key["market_context_intraday"]["time_window"]["fixed_times"] == ["09:45", "10:45", "11:45", "13:45", "14:45", "15:20"]
    assert job_by_key["price_nav_post_close"]["time_window"]["fixed_time"] == "17:30"
    assert job_by_key["expert_t_day_agents"]["enabled"] is False
    assert job_by_key["jarvis_t_plus_one"]["enabled"] is False


def test_scheduler_run_due_records_runs_watermarks_and_task_logs(tmp_path):
    db_path = init_db(tmp_path / "scheduler-run.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))

    result = run_due_jobs(db_path, now=datetime.fromisoformat("2026-05-25T10:00:00"))

    assert result["ok"] is True
    assert result["due_count"] == 2
    assert {run["job_key"] for run in result["runs"]} == {"news_hourly_incremental", "market_context_intraday"}
    with connect(db_path) as conn:
        run_count = conn.execute("SELECT COUNT(*) AS count FROM scheduler_runs WHERE status = 'success'").fetchone()["count"]
        watermark_count = conn.execute("SELECT COUNT(*) AS count FROM scheduler_watermarks").fetchone()["count"]
        task_log = conn.execute("SELECT status, message FROM task_logs WHERE task_name = 'scheduler_job' ORDER BY id DESC LIMIT 1").fetchone()
    assert run_count == 2
    assert watermark_count == 2
    assert task_log["status"] == "success"
    assert "incremental" in task_log["message"]


def test_scheduler_status_and_cli_commands_are_json(tmp_path, capsys):
    db_path = init_db(tmp_path / "scheduler-cli.sqlite3")

    assert cli_main(["scheduler", "list-jobs", "--db", str(db_path), "--now", "2026-05-25T08:00:00"]) == 0
    output = capsys.readouterr().out
    assert "news_hourly_incremental" in output

    run = run_scheduler_job(db_path, "news_hourly_incremental", now=datetime.fromisoformat("2026-05-25T10:00:00"))
    status = scheduler_status(db_path)

    assert run["status"] == "success"
    assert status["latest_runs"]["news_hourly_incremental"]["status"] == "success"
    assert status["watermarks"]

    assert cli_main(["scheduler", "status", "--db", str(db_path)]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["latest_runs"]["news_hourly_incremental"]["status"] == "success"


def test_scheduler_provider_backoff_defers_due_job(tmp_path):
    db_path = init_db(tmp_path / "scheduler-backoff.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO provider_rate_limits(provider_key, backoff_until, failure_count, last_failure_reason)
            VALUES ('news', '2026-05-25T11:00:00', 1, 'likely throttled')
            """
        )

    run = run_scheduler_job(db_path, "news_hourly_incremental", now=datetime.fromisoformat("2026-05-25T10:00:00"))

    assert run["status"] == "deferred"
    assert "backoff active" in run["deferred_reason"]
    assert run["provider_request_counts"] == {"news": 0}


def test_news_hourly_incremental_uses_source_watermark_and_bounded_window(tmp_path):
    db_path = init_db(tmp_path / "scheduler-news.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO scheduler_watermarks(job_key, provider_key, source_key, scope_key, last_success_cursor, last_attempted_cursor, metadata_json)
            VALUES ('news_hourly_incremental', 'news', 'sina', 'news', '2026-05-25T09:05:00', '2026-05-25T09:05:00', '{}')
            """
        )

    run = run_scheduler_job(db_path, "news_hourly_incremental", now=datetime.fromisoformat("2026-05-25T10:05:00"))

    planned = run["metadata"]["planned_windows"][0]
    assert run["status"] == "success"
    assert planned["source"] == "sina"
    assert planned["start"] == "2026-05-25T09:05:00"
    assert planned["end"] == "2026-05-25T10:05:00"
    assert run["provider_request_counts"] == {"news": 1}
    assert run["metadata"]["bounded_window"] is True
    assert run["metadata"]["real_provider_calls"] is False


def test_price_and_feature_jobs_skip_current_assets_and_plan_affected_ranges(tmp_path):
    db_path = init_db(tmp_path / "scheduler-price-features.sqlite3")
    with connect(db_path) as conn:
        current_asset_id = _seed_asset(conn, "CUR", "Current", "2026-05-25")
        stale_asset_id = _seed_asset(conn, "OLD", "Stale", "2026-05-23")
        upsert_feature_daily(
            conn,
            {
                "asset_id": current_asset_id,
                "feature_date": "2026-05-25",
                "return_1d": None,
                "return_5d": None,
                "return_20d": None,
                "return_60d": None,
                "volatility_20d": None,
                "max_drawdown_60d": None,
                "sharpe_60d": None,
                "calmar_60d": None,
                "win_rate_60d": None,
                "momentum_20d": None,
                "market_state": "neutral",
                "source": "features_v1",
            },
        )
        upsert_feature_daily(
            conn,
            {
                "asset_id": stale_asset_id,
                "feature_date": "2026-05-22",
                "return_1d": None,
                "return_5d": None,
                "return_20d": None,
                "return_60d": None,
                "volatility_20d": None,
                "max_drawdown_60d": None,
                "sharpe_60d": None,
                "calmar_60d": None,
                "win_rate_60d": None,
                "momentum_20d": None,
                "market_state": "neutral",
                "source": "features_v1",
            },
        )
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))

    price_run = run_scheduler_job(db_path, "price_nav_post_close", now=datetime.fromisoformat("2026-05-25T17:30:00"))
    feature_run = run_scheduler_job(db_path, "features_post_close", now=datetime.fromisoformat("2026-05-25T18:10:00"))

    assert price_run["updated_counts"]["planned_assets"] == 1
    assert price_run["updated_counts"]["current_assets"] == 1
    assert price_run["metadata"]["planned_assets"][0]["code"] == "OLD"
    assert feature_run["updated_counts"]["affected_assets"] == 1
    assert feature_run["metadata"]["affected_ranges"][0]["code"] == "OLD"


def test_provider_failure_records_backoff_and_budget_defers_later_job(tmp_path):
    db_path = init_db(tmp_path / "scheduler-provider-policy.sqlite3")
    failure = record_provider_failure(
        db_path,
        "akshare",
        "HTTP 429 rate limit",
        now=datetime.fromisoformat("2026-05-25T10:00:00"),
        backoff_minutes=10,
    )
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T10:00:00"))

    backoff_run = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T10:05:00"))

    assert failure["likely_throttled"] is True
    assert failure["backoff_until"] == "2026-05-25T10:20:00"
    assert backoff_run["status"] == "deferred"
    assert "backoff active" in backoff_run["deferred_reason"]


def test_scheduler_health_exposes_agent_gates_without_enabling_codex_automation(tmp_path):
    db_path = init_db(tmp_path / "scheduler-health.sqlite3")
    jobs = initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    status = scheduler_status(db_path)

    expert = next(job for job in jobs if job["job_key"] == "expert_t_day_agents")
    jarvis = next(job for job in jobs if job["job_key"] == "jarvis_t_plus_one")
    assert expert["enabled"] is False
    assert jarvis["enabled"] is False
    assert "scheduler_jobs" not in status
    assert status["jobs"]
    assert status["latest_runs"]["expert_t_day_agents"] is None


def _seed_asset(conn, code: str, name: str, trade_date: str) -> int:
    asset_id = upsert_asset(
        conn,
        {
            "code": code,
            "name": name,
            "asset_type": "stock",
            "market": "CN",
            "currency": "CNY",
            "status": "active",
            "source": "akshare",
        },
    )
    upsert_price_daily(
        conn,
        asset_id=asset_id,
        source="akshare",
        price={
            "trade_date": trade_date,
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": None,
            "amount": None,
            "pct_change": None,
            "adjusted_close": 1.0,
            "nav": None,
            "accumulated_nav": None,
            "raw_payload": None,
        },
    )
    return asset_id
