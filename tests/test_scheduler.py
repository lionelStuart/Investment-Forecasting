from __future__ import annotations

import json
import plistlib
from datetime import datetime

import pytest

from investment_forecasting.cli import main as cli_main
from investment_forecasting.db import connect, init_db, upsert_asset, upsert_feature_daily, upsert_price_daily
from investment_forecasting.scheduler import initialize_scheduler, record_provider_failure, run_due_jobs, run_scheduler_job, scheduler_status, scheduler_today_status


def test_scheduler_initializes_fixed_incremental_sync_jobs(tmp_path):
    db_path = init_db(tmp_path / "scheduler.sqlite3")

    jobs = initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))

    job_by_key = {job["job_key"]: job for job in jobs}
    assert job_by_key["news_hourly_incremental"]["cadence"] == "interval_hours"
    assert job_by_key["news_hourly_incremental"]["time_window"]["interval_hours"] == 2
    assert job_by_key["news_hourly_incremental"]["time_window"]["fixed_minute"] == 5
    assert job_by_key["market_context_intraday"]["cadence"] == "interval_hours"
    assert job_by_key["market_context_intraday"]["time_window"]["interval_hours"] == 2
    assert job_by_key["market_context_intraday"]["time_window"]["fixed_minute"] == 15
    assert job_by_key["price_nav_post_close"]["time_window"]["fixed_time"] == "17:30"
    assert job_by_key["expert_t_day_agents"]["enabled"] is True
    assert job_by_key["jarvis_t_plus_one"]["enabled"] is True


def test_scheduler_run_due_records_runs_watermarks_and_task_logs(tmp_path, monkeypatch):
    _patch_scheduler_providers(monkeypatch)
    db_path = init_db(tmp_path / "scheduler-run.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))

    result = run_due_jobs(db_path, now=datetime.fromisoformat("2026-05-25T10:20:00"))

    assert result["ok"] is True
    assert result["due_count"] == 2
    assert {run["job_key"] for run in result["runs"]} == {"news_hourly_incremental", "market_context_intraday"}
    with connect(db_path) as conn:
        run_count = conn.execute("SELECT COUNT(*) AS count FROM scheduler_runs WHERE status = 'success'").fetchone()["count"]
        watermark_count = conn.execute("SELECT COUNT(*) AS count FROM scheduler_watermarks").fetchone()["count"]
        task_log = conn.execute("SELECT status, message FROM task_logs WHERE task_name = 'scheduler_job' ORDER BY id DESC LIMIT 1").fetchone()
    assert run_count == 2
    assert watermark_count == 4
    assert task_log["status"] == "success"
    assert "incremental" in task_log["message"]


def test_scheduler_status_and_cli_commands_are_json(tmp_path, capsys, monkeypatch):
    _patch_scheduler_providers(monkeypatch)
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
    assert parsed["today"]["items"]

    assert cli_main(["scheduler", "today-status", "--db", str(db_path), "--now", "2026-05-25T10:30:00"]) == 0
    today = json.loads(capsys.readouterr().out)
    assert today["date"] == "2026-05-25"
    assert any(item["job_key"] == "news_hourly_incremental" for item in today["items"])


def test_scheduler_status_explains_failed_deferred_skipped_cursors_and_provider_state(tmp_path):
    db_path = init_db(tmp_path / "scheduler-status-explain.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO scheduler_runs(
                job_key, scheduled_at, started_at, finished_at, status,
                skipped_reason, deferred_reason, error,
                updated_counts_json, provider_request_counts_json, metadata_json
            )
            VALUES
              (
                'news_hourly_incremental', '2026-05-25T10:05:00',
                '2026-05-25 10:05:01', '2026-05-25 10:05:02',
                'failed', NULL, NULL, 'Tushare provider requires TUSHARE_TOKEN',
                '{}', '{"news": 0}', '{"real_provider_calls": true, "failed_stage": "deterministic_job"}'
              ),
              (
                'market_context_intraday', '2026-05-25T10:15:00',
                '2026-05-25 10:15:01', '2026-05-25 10:15:02',
                'deferred', NULL, 'provider backoff active until 2026-05-25T11:00:00', NULL,
                '{}', '{"akshare": 0}', '{"real_provider_calls": false, "job_type": "market_context_incremental"}'
              ),
              (
                'features_post_close', '2026-05-25T18:10:00',
                '2026-05-25 18:10:01', '2026-05-25 18:10:02',
                'skipped', 'no affected assets from price watermarks', NULL, NULL,
                '{"affected_assets": 0}', '{"system": 0}', '{"real_calculation": false, "readiness_gate": true}'
              )
            """
        )
        conn.execute(
            """
            INSERT INTO scheduler_watermarks(
                job_key, provider_key, source_key, scope_key,
                last_success_cursor, last_attempted_cursor, metadata_json
            )
            VALUES (
                'news_hourly_incremental', 'news', 'sina', 'news',
                '2026-05-25T08:05:00', '2026-05-25T10:05:00',
                '{"incremental": true, "bounded_window": true, "summary": {"inserted_count": 0}}'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO provider_rate_limits(
                provider_key, hourly_count, daily_count, backoff_until,
                failure_count, last_failure_reason, metadata_json
            )
            VALUES (
                'news', 0, 3, '2026-05-25T11:00:00', 1,
                'Tushare provider requires TUSHARE_TOKEN',
                '{"last_failure_at": "2026-05-25T10:05:02"}'
            )
            """
        )

    status = scheduler_status(db_path)
    latest = status["latest_runs"]
    watermark = next(row for row in status["watermarks"] if row["job_key"] == "news_hourly_incremental")
    provider = next(row for row in status["provider_rate_limits"] if row["provider_key"] == "news")

    assert latest["news_hourly_incremental"]["status"] == "failed"
    assert latest["news_hourly_incremental"]["error"] == "Tushare provider requires TUSHARE_TOKEN"
    assert latest["news_hourly_incremental"]["execution_mode"] == "real_provider"
    assert latest["market_context_intraday"]["status"] == "deferred"
    assert latest["market_context_intraday"]["deferred_reason"] == "provider backoff active until 2026-05-25T11:00:00"
    assert latest["features_post_close"]["status"] == "skipped"
    assert latest["features_post_close"]["skipped_reason"] == "no affected assets from price watermarks"
    assert watermark["last_success_cursor"] == "2026-05-25T08:05:00"
    assert watermark["last_attempted_cursor"] == "2026-05-25T10:05:00"
    assert watermark["metadata"]["summary"]["inserted_count"] == 0
    assert provider["backoff_until"] == "2026-05-25T11:00:00"
    assert provider["failure_count"] == 1
    assert provider["last_failure_reason"] == "Tushare provider requires TUSHARE_TOKEN"
    assert provider["metadata"]["last_failure_at"] == "2026-05-25T10:05:02"


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


def test_scheduler_provider_recovers_after_backoff_expires(tmp_path, monkeypatch):
    _patch_scheduler_providers(monkeypatch)
    db_path = init_db(tmp_path / "scheduler-backoff-recovery.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO provider_rate_limits(provider_key, backoff_until, failure_count, last_failure_reason)
            VALUES ('news', '2026-05-25T09:00:00', 2, 'rate limit')
            """
        )

    run = run_scheduler_job(db_path, "news_hourly_incremental", now=datetime.fromisoformat("2026-05-25T10:05:00"))

    assert run["status"] == "success"
    assert run["execution_mode"] == "real_provider"
    assert run["updated_counts"]["inserted_news"] == 3
    with connect(db_path) as conn:
        limit = conn.execute("SELECT backoff_until, failure_count, last_failure_reason FROM provider_rate_limits WHERE provider_key = 'news'").fetchone()
    assert limit["backoff_until"] is None
    assert limit["failure_count"] == 0
    assert limit["last_failure_reason"] is None


def test_news_hourly_incremental_uses_source_watermark_and_bounded_window(tmp_path, monkeypatch):
    _patch_scheduler_providers(monkeypatch)
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
    assert run["provider_request_counts"] == {"news": 3}
    assert run["metadata"]["bounded_window"] is True
    assert run["metadata"]["real_provider_calls"] is True
    assert run["updated_counts"]["inserted_news"] == 3


def test_price_and_feature_jobs_skip_current_assets_and_plan_affected_ranges(tmp_path, monkeypatch):
    _patch_scheduler_providers(monkeypatch)
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

    assert price_run["status"] == "success"
    assert price_run["updated_counts"]["planned_assets"] == 1
    assert price_run["updated_counts"]["written_price_rows"] == 1
    assert price_run["updated_counts"]["current_assets"] == 1
    assert price_run["metadata"]["planned_assets"][0]["code"] == "OLD"
    assert feature_run["updated_counts"]["affected_assets"] == 1
    assert feature_run["updated_counts"]["written_feature_rows"] >= 1
    assert feature_run["metadata"]["affected_ranges"][0]["code"] == "OLD"


def test_provider_symbol_uses_shanghai_prefix_only_for_shanghai_stock_or_index():
    import investment_forecasting.scheduler.service as service

    assert service._provider_symbol("stock", "000518") == "sz000518"
    assert service._provider_symbol("stock", "600519") == "sh600519"
    assert service._provider_symbol("index", "000300") == "sh000300"
    assert service._provider_symbol("etf", "510300") == "sh510300"


def test_provider_failure_records_backoff_and_budget_defers_later_job(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-provider-policy.sqlite3")
    failure = record_provider_failure(
        db_path,
        "akshare",
        "HTTP 429 rate limit",
        now=datetime.fromisoformat("2026-05-25T10:00:00"),
        backoff_minutes=10,
    )
    monkeypatch.setattr(service, "_market_context_has_fallback_provider", lambda: False)
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T10:00:00"))

    backoff_run = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T10:05:00"))

    assert failure["likely_throttled"] is True
    assert failure["backoff_until"] == "2026-05-25T10:20:00"
    assert backoff_run["status"] == "deferred"
    assert "backoff active" in backoff_run["deferred_reason"]


def test_provider_budget_counts_reset_by_time_window(tmp_path, monkeypatch):
    _patch_scheduler_providers(monkeypatch)
    db_path = init_db(tmp_path / "scheduler-provider-budget.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO provider_rate_limits(provider_key, hourly_count, daily_count, metadata_json)
            VALUES ('akshare', 550, 100, ?)
            """,
            ('{"last_success_at": "2026-05-24T17:30:00"}',),
        )

    run = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T10:15:00"))

    assert run["status"] == "success"
    with connect(db_path) as conn:
        row = conn.execute("SELECT hourly_count, daily_count FROM provider_rate_limits WHERE provider_key = 'akshare'").fetchone()
    assert row["hourly_count"] <= 40
    assert row["daily_count"] <= 40


def test_provider_failure_preserves_count_window_for_later_reset(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    _patch_scheduler_providers(monkeypatch)
    monkeypatch.setattr(service, "_market_context_has_fallback_provider", lambda: False)
    db_path = init_db(tmp_path / "scheduler-provider-failure-budget.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO provider_rate_limits(provider_key, hourly_count, daily_count, metadata_json)
            VALUES ('akshare', 550, 100, ?)
            """,
            ('{"last_success_at": "2026-05-25T17:30:00"}',),
        )
        service._record_provider_failure_conn(
            conn,
            "akshare",
            "temporary dns failure",
            now=datetime.fromisoformat("2026-05-25T17:32:00"),
            backoff_minutes=1,
        )
        metadata = conn.execute("SELECT metadata_json FROM provider_rate_limits WHERE provider_key = 'akshare'").fetchone()["metadata_json"]

    assert "last_success_at" in metadata
    assert "last_failure_at" in metadata

    run = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T18:15:00"))

    assert run["status"] == "success"
    with connect(db_path) as conn:
        row = conn.execute("SELECT hourly_count, daily_count FROM provider_rate_limits WHERE provider_key = 'akshare'").fetchone()
    assert row["hourly_count"] <= 40
    assert row["daily_count"] > 100


def test_market_context_fails_when_provider_returns_no_rows(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-market-empty.sqlite3")
    with connect(db_path) as conn:
        _seed_asset(conn, "000001", "Empty Flow Asset", "2026-05-23")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    monkeypatch.setattr(service, "_market_context_providers", lambda **kwargs: [EmptySchedulerProvider()])

    run = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T10:15:00"))

    assert run["status"] == "failed"
    assert run["updated_counts"]["capital_flow_rows"] == 0
    assert "no capital flow rows" in run["error"]


def test_market_context_falls_back_to_second_provider_when_akshare_capital_flow_fails(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-market-fallback.sqlite3")
    with connect(db_path) as conn:
        _seed_asset(conn, "000001", "Fallback Asset", "2026-05-23")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    monkeypatch.setattr(service, "_market_context_providers", lambda **kwargs: [FailingMarketContextProvider(), FakeSchedulerProvider()])

    run = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T10:15:00"))

    assert run["status"] == "success"
    assert run["updated_counts"]["capital_flow_rows"] == 2
    assert run["metadata"]["provider_by_subject"] == {
        "market:market": "fake",
        "stock:000001": "fake",
    }
    assert run["metadata"]["errors_by_subject"] == {}
    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM capital_flow_observations WHERE source = 'fake'").fetchone()["count"]
    assert count == 2


def test_market_context_uses_tushare_stock_fallback_for_planned_subjects(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-market-tushare-stock-fallback.sqlite3")
    with connect(db_path) as conn:
        _seed_asset(conn, "000001", "Fallback Asset", "2026-05-23")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    monkeypatch.setattr(service, "_market_context_providers", lambda **kwargs: [FailingMarketContextProvider(), TushareSchedulerProvider()])

    run = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T10:15:00"))

    assert run["status"] == "success"
    assert run["metadata"]["errors_by_subject"] == {}
    assert run["metadata"]["provider_by_subject"] == {
        "market:market": "tushare",
        "stock:000001": "tushare",
    }
    assert run["provider_request_counts"] == {"tushare": 2}


def test_market_context_uses_fallback_provider_when_primary_backoff_is_active(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-market-backoff-fallback.sqlite3")
    with connect(db_path) as conn:
        _seed_asset(conn, "000001", "Fallback Asset", "2026-05-23")
    record_provider_failure(
        db_path,
        "akshare",
        "eastmoney dns failed",
        now=datetime.fromisoformat("2026-05-25T10:00:00"),
        backoff_minutes=60,
    )
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    monkeypatch.setattr(service, "_market_context_has_fallback_provider", lambda: True)
    monkeypatch.setattr(service, "_market_context_providers", lambda **kwargs: [FailingMarketContextProvider(), FakeSchedulerProvider()])

    run = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T10:15:00"))

    assert run["status"] == "success"
    assert run["provider_request_counts"] == {"fake": 1}
    assert run["metadata"]["provider_by_subject"]["market:market"] == "fake"
    assert "stock:000001" not in run["metadata"]["provider_by_subject"]


def test_market_context_uses_fallback_provider_after_unrecovered_primary_failure(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-market-unrecovered-fallback.sqlite3")
    with connect(db_path) as conn:
        _seed_asset(conn, "000001", "Fallback Asset", "2026-05-23")
        conn.execute(
            """
            INSERT INTO provider_rate_limits(provider_key, hourly_count, daily_count, last_failure_reason, metadata_json)
            VALUES ('akshare', 10, 10, 'eastmoney dns failed', ?)
            """,
            ('{"last_success_at": "2026-05-25T08:00:00", "last_failure_at": "2026-05-25T09:00:00"}',),
        )
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    monkeypatch.setattr(service, "_market_context_has_fallback_provider", lambda: True)
    monkeypatch.setattr(service, "_market_context_providers", lambda **kwargs: [FakeSchedulerProvider()] if kwargs.get("skip_primary") else [FailingMarketContextProvider()])

    run = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T10:15:00"))

    assert run["status"] == "success"
    assert run["provider_request_counts"] == {"fake": 1}
    assert run["metadata"]["primary_unrecovered_failure"] is True
    assert run["updated_counts"]["capital_flow_subjects"] == 1


def test_market_context_records_subject_errors_without_blocking_other_subjects(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-market-partial.sqlite3")
    with connect(db_path) as conn:
        _seed_asset(conn, "000001", "Good Flow Asset", "2026-05-23")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    monkeypatch.setattr(service, "_market_context_providers", lambda **kwargs: [MarketOnlySchedulerProvider()])

    run = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T10:15:00"))

    assert run["status"] == "success"
    assert run["error"] == "1 planned capital-flow subjects failed while other rows were written"
    assert run["updated_counts"]["capital_flow_rows"] == 1
    assert run["updated_counts"]["failed_subjects"] == 1
    assert "stock:000001" in run["metadata"]["errors_by_subject"]


def test_price_nav_incremental_continues_after_one_asset_failure(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-price-partial.sqlite3")
    with connect(db_path) as conn:
        _seed_asset(conn, "000001", "Good Asset", "2026-05-23")
        _seed_asset(conn, "000004", "Missing Asset", "2026-05-23")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    monkeypatch.setattr(service, "_market_price_providers", lambda: [PartialPriceSchedulerProvider()])

    run = run_scheduler_job(db_path, "price_nav_post_close", now=datetime.fromisoformat("2026-05-26T17:30:00"))

    assert run["status"] == "success"
    assert run["updated_counts"]["written_price_rows"] == 1
    assert run["updated_counts"]["failed_assets"] == 1
    assert "stock:000004" in run["metadata"]["errors_by_asset"]
    with connect(db_path) as conn:
        written = conn.execute("SELECT COUNT(*) AS count FROM price_daily WHERE trade_date = '2026-05-26'").fetchone()["count"]
    assert written == 1


def test_price_nav_incremental_uses_tushare_fallback_after_primary_failure(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-price-fallback.sqlite3")
    with connect(db_path) as conn:
        _seed_asset(conn, "000001", "Fallback Price", "2026-05-23")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    monkeypatch.setattr(service, "_market_price_providers", lambda: [FailingPriceSchedulerProvider(), TushareSchedulerProvider()])

    run = run_scheduler_job(db_path, "price_nav_post_close", now=datetime.fromisoformat("2026-05-26T17:30:00"))

    assert run["status"] == "success"
    assert run["updated_counts"]["written_price_rows"] == 1
    assert run["updated_counts"]["failed_assets"] == 0
    assert run["metadata"]["errors_by_asset"] == {}
    assert run["metadata"]["provider_by_asset"] == {"stock:000001": "tushare"}
    with connect(db_path) as conn:
        row = conn.execute("SELECT source, trade_date FROM price_daily WHERE trade_date = '2026-05-26'").fetchone()
    assert row["source"] == "tushare"

    second = run_scheduler_job(db_path, "price_nav_post_close", now=datetime.fromisoformat("2026-05-26T17:45:00"))
    assert second["status"] == "skipped"
    assert second["updated_counts"]["stale_assets"] == 0


def test_price_nav_skips_current_day_fund_nav_pending_without_failure(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-price-fund-nav-pending.sqlite3")
    with connect(db_path) as conn:
        fund_id = upsert_asset(
            conn,
            {
                "code": "000001",
                "name": "Fund Pending NAV",
                "asset_type": "fund",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "akshare",
            },
        )
        upsert_price_daily(
            conn,
            asset_id=fund_id,
            source="akshare",
            price={
                "trade_date": "2026-05-25",
                "open": None,
                "high": None,
                "low": None,
                "close": 1.0,
                "volume": None,
                "amount": None,
                "pct_change": None,
                "adjusted_close": None,
                "nav": 1.0,
                "accumulated_nav": 1.0,
                "raw_payload": None,
            },
        )
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-26T08:00:00"))
    monkeypatch.setattr(service, "_market_price_providers", lambda: [FailingPriceSchedulerProvider()])

    run = run_scheduler_job(db_path, "price_nav_post_close", now=datetime.fromisoformat("2026-05-26T17:30:00"))

    assert run["status"] == "skipped"
    assert run["updated_counts"]["nav_pending_assets"] == 1
    assert run["updated_counts"]["failed_assets"] == 0
    assert run["metadata"]["nav_pending_assets"][0]["code"] == "000001"


def test_price_nav_no_history_failures_leave_lifecycle_review_evidence(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-price-lifecycle-review.sqlite3")
    with connect(db_path) as conn:
        _seed_asset(conn, "000001", "Good Asset", "2026-05-23")
        missing_id = _seed_asset(conn, "000004", "Missing Asset", "2026-05-23")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    monkeypatch.setattr(service, "_market_price_providers", lambda: [PartialPriceSchedulerProvider()])

    run = run_scheduler_job(db_path, "price_nav_post_close", now=datetime.fromisoformat("2026-05-26T17:30:00"))

    with connect(db_path) as conn:
        asset = conn.execute("SELECT code, name, status FROM assets WHERE id = ?", (missing_id,)).fetchone()
        watermark = conn.execute(
            """
            SELECT last_success_cursor, last_attempted_cursor, metadata_json
            FROM scheduler_watermarks
            WHERE job_key = 'price_nav_post_close'
              AND source_key = 'stock:000004'
            """
        ).fetchone()
    metadata = json.loads(watermark["metadata_json"])
    assert run["updated_counts"]["failed_assets"] == 1
    assert asset["status"] == "active"
    assert "no history" in metadata["error"]
    assert metadata["target_date"] == "2026-05-26"
    assert metadata["written_rows"] == 0
    assert watermark["last_success_cursor"] == "2026-05-23"
    assert watermark["last_attempted_cursor"] == "2026-05-26"


def test_features_incremental_fails_without_calculated_rows(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-features-empty.sqlite3")
    with connect(db_path) as conn:
        asset_id = _seed_asset(conn, "000001", "Feature Empty Asset", "2026-05-24")
        upsert_price_daily(
            conn,
            asset_id=asset_id,
            source="akshare",
            price={
                "trade_date": "2026-05-25",
                "open": 1.1,
                "high": 1.1,
                "low": 1.1,
                "close": 1.1,
                "volume": None,
                "amount": None,
                "pct_change": None,
                "adjusted_close": 1.1,
                "nav": None,
                "accumulated_nav": None,
                "raw_payload": None,
            },
        )
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    monkeypatch.setattr(service, "calculate_features_for_db", lambda *args, **kwargs: {})

    run = run_scheduler_job(db_path, "features_post_close", now=datetime.fromisoformat("2026-05-25T18:10:00"))

    assert run["status"] == "failed"
    assert run["updated_counts"]["affected_assets"] == 1
    assert run["updated_counts"]["written_feature_rows"] == 0
    assert "no rows" in run["error"]


def test_model_post_close_runs_real_model_services_after_readiness(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-model.sqlite3")
    calls = []

    monkeypatch.setattr(service, "run_latest_forecasts", lambda db_path_arg, horizons: calls.append(("forecast", db_path_arg, horizons)) or {1: 3})
    monkeypatch.setattr(service, "run_backtest", lambda db_path_arg, horizons, lookback_days: calls.append(("backtest", db_path_arg, horizons, lookback_days)) or {"run_ids": [10, 11, 12]})
    monkeypatch.setattr(service, "calculate_market_snapshot", lambda db_path_arg, snapshot_date: calls.append(("snapshot", db_path_arg, snapshot_date)) or {"id": 5})
    monkeypatch.setattr(service, "generate_daily_advice", lambda db_path_arg, advice_date: calls.append(("advice", db_path_arg, advice_date)) or 6)
    monkeypatch.setattr(service, "score_matured_advice", lambda db_path_arg, horizon_days: calls.append(("score", db_path_arg, horizon_days)) or 2)
    monkeypatch.setattr(service, "run_model_monitoring_report", lambda db_path_arg, report_date: calls.append(("monitoring", db_path_arg, report_date)) or {"count": 3, "report_ids": [1, 2, 3]})

    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO scheduler_watermarks(job_key, provider_key, source_key, scope_key, last_success_cursor, last_attempted_cursor, metadata_json)
            VALUES
              ('price_nav_post_close', 'akshare', 'stock:AAA', 'price_daily', '2026-05-25', '2026-05-25', '{}'),
              ('features_post_close', 'system', 'stock:AAA', 'features_daily', '2026-05-25', '2026-05-25', '{}')
            """
        )

    run = run_scheduler_job(db_path, "model_post_close", now=datetime.fromisoformat("2026-05-25T18:40:00"))

    assert run["status"] == "success"
    assert run["metadata"]["real_model_run"] is True
    assert run["updated_counts"]["forecast_rows"] == 3
    assert run["updated_counts"]["advice_id"] == 6
    assert [call[0] for call in calls] == ["forecast", "backtest", "snapshot", "advice", "score", "monitoring"]


def test_model_post_close_allows_model_services_to_write_without_scheduler_lock(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-model-lock.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO scheduler_watermarks(job_key, provider_key, source_key, scope_key, last_success_cursor, last_attempted_cursor, metadata_json)
            VALUES
              ('price_nav_post_close', 'akshare', 'stock:AAA', 'price_daily', '2026-05-25', '2026-05-25', '{}'),
              ('features_post_close', 'system', 'stock:AAA', 'features_daily', '2026-05-25', '2026-05-25', '{}')
            """
        )

    def write_task_log(db_path_arg, label):
        with connect(db_path_arg) as conn:
            conn.execute(
                "INSERT INTO task_logs(task_name, run_date, status, message) VALUES (?, ?, 'success', ?)",
                ("model_service_probe", "2026-05-25", label),
            )

    monkeypatch.setattr(service, "run_latest_forecasts", lambda db_path_arg, horizons: write_task_log(db_path_arg, "forecast") or {1: 1})
    monkeypatch.setattr(service, "run_backtest", lambda db_path_arg, horizons, lookback_days: write_task_log(db_path_arg, "backtest") or {"run_ids": [1]})
    monkeypatch.setattr(service, "calculate_market_snapshot", lambda db_path_arg, snapshot_date: write_task_log(db_path_arg, "snapshot") or {"id": 1})
    monkeypatch.setattr(service, "generate_daily_advice", lambda db_path_arg, advice_date: write_task_log(db_path_arg, "advice") or 1)
    monkeypatch.setattr(service, "score_matured_advice", lambda db_path_arg, horizon_days: write_task_log(db_path_arg, "score") or 1)
    monkeypatch.setattr(service, "run_model_monitoring_report", lambda db_path_arg, report_date: write_task_log(db_path_arg, "monitoring") or {"count": 1, "report_ids": [1]})

    run = run_scheduler_job(db_path, "model_post_close", now=datetime.fromisoformat("2026-05-25T18:40:00"))

    assert run["status"] == "success"
    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM task_logs WHERE task_name = 'model_service_probe'").fetchone()["count"]
    assert count == 6


def test_scheduler_pipeline_runs_real_outputs_before_expert_and_jarvis(tmp_path, monkeypatch):
    import investment_forecasting.agent_runtime.execution as execution
    import investment_forecasting.scheduler.service as service

    _patch_scheduler_providers(monkeypatch)
    monkeypatch.setattr(service, "run_latest_forecasts", lambda db_path_arg, horizons: {1: 3})
    monkeypatch.setattr(service, "run_backtest", lambda db_path_arg, horizons, lookback_days: {"run_ids": [1, 2, 3]})
    monkeypatch.setattr(service, "calculate_market_snapshot", lambda db_path_arg, snapshot_date: {"id": 1})
    monkeypatch.setattr(service, "generate_daily_advice", lambda db_path_arg, advice_date: 1)
    monkeypatch.setattr(service, "score_matured_advice", lambda db_path_arg, horizon_days: 0)
    monkeypatch.setattr(service, "run_model_monitoring_report", lambda db_path_arg, report_date: {"count": 1, "report_ids": [1]})
    monkeypatch.setattr(execution, "run_expert_codex_agents", lambda *args, **kwargs: {"ok": True, "run_date": kwargs["run_date"], "runs": [{"ok": True, "status": "completed"}]})
    monkeypatch.setattr(execution, "run_jarvis_codex_agent", lambda *args, **kwargs: {"ok": True, "run_date": kwargs["run_date"], "runs": [{"ok": True, "status": "completed", "notification": {"status": "dry_run"}}]})

    db_path = init_db(tmp_path / "scheduler-pipeline.sqlite3")
    with connect(db_path) as conn:
        _seed_asset(conn, "000001", "Pipeline Asset", "2026-05-23")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))

    news = run_scheduler_job(db_path, "news_hourly_incremental", now=datetime.fromisoformat("2026-05-25T10:05:00"))
    market = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T10:15:00"))
    price = run_scheduler_job(db_path, "price_nav_post_close", now=datetime.fromisoformat("2026-05-25T17:30:00"))
    features = run_scheduler_job(db_path, "features_post_close", now=datetime.fromisoformat("2026-05-25T18:10:00"))
    model = run_scheduler_job(db_path, "model_post_close", now=datetime.fromisoformat("2026-05-25T18:40:00"))
    expert = run_scheduler_job(db_path, "expert_t_day_agents", now=datetime.fromisoformat("2026-05-25T20:00:00"))
    jarvis = run_scheduler_job(db_path, "jarvis_t_plus_one", now=datetime.fromisoformat("2026-05-26T08:00:00"))

    assert [run["status"] for run in [news, market, price, features, model, expert, jarvis]] == ["success"] * 7
    assert news["execution_mode"] == "real_provider"
    assert market["execution_mode"] == "real_provider"
    assert price["execution_mode"] == "real_provider"
    assert features["execution_mode"] == "real_calculation"
    assert model["execution_mode"] == "real_model_run"
    assert expert["execution_mode"] == "agent_runtime"
    assert jarvis["execution_mode"] == "agent_runtime"
    assert price["updated_counts"]["written_price_rows"] == 1
    assert features["updated_counts"]["written_feature_rows"] >= 1
    assert model["updated_counts"]["forecast_rows"] == 3


def test_scheduler_health_exposes_agent_jobs_without_codex_app_automation(tmp_path):
    db_path = init_db(tmp_path / "scheduler-health.sqlite3")
    jobs = initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    status = scheduler_status(db_path)

    expert = next(job for job in jobs if job["job_key"] == "expert_t_day_agents")
    jarvis = next(job for job in jobs if job["job_key"] == "jarvis_t_plus_one")
    assert expert["enabled"] is True
    assert jarvis["enabled"] is True
    assert "scheduler_jobs" not in status
    assert status["jobs"]
    assert status["latest_runs"]["expert_t_day_agents"] is None


def test_scheduler_install_cron_writes_unified_launch_agent(tmp_path, monkeypatch):
    from investment_forecasting.scheduler import install_scheduler_cron

    monkeypatch.setenv("TUSHARE_TOKEN", "redacted-credential")
    monkeypatch.setenv("INVESTMENT_FORECASTING_CODEX_BIN", "/usr/local/bin/codex")
    monkeypatch.setenv("INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY", "owner_phone")
    monkeypatch.setenv("INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN", "false")
    db_path = init_db(tmp_path / "scheduler-cron.sqlite3")

    result = install_scheduler_cron(
        db_path,
        project_root=tmp_path,
        interval_minutes=5,
        python_bin="/usr/bin/python3",
        load=False,
        run_at_load=False,
        launch_agents_dir=tmp_path / "LaunchAgents",
    )

    assert result["ok"] is True
    assert result["label"] == "local.investment-forecasting.scheduler"
    assert result["interval_seconds"] == 300
    assert result["launch_agents_dir"] == str(tmp_path / "LaunchAgents")
    plist_text = open(result["plist_path"], encoding="utf-8").read()
    plist = plistlib.loads(plist_text.encode("utf-8"))
    env = plist["EnvironmentVariables"]
    assert "investment_forecasting.cli" in plist_text
    assert "scheduler" in plist_text
    assert "run-due" in plist_text
    assert "<key>PATH</key>" in plist_text
    assert "Codex.app/Contents/Resources" in plist_text
    assert "local.investment-forecasting.experts" not in plist_text
    assert plist["WorkingDirectory"] == str(tmp_path.resolve())
    assert plist["ProgramArguments"][-2:] == ["--db", str(db_path.resolve())]
    assert env["PYTHONPATH"] == str(tmp_path.resolve() / "src")
    assert env["INVESTMENT_FORECASTING_DB"] == str(db_path.resolve())
    assert env["INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY"] == "owner_phone"
    assert env["INVESTMENT_FORECASTING_NOTIFICATION_CHANNEL"] == "imessage"
    assert env["INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN"] == "false"
    assert env["INVESTMENT_FORECASTING_CODEX_BIN"] == "/usr/local/bin/codex"
    assert env["TUSHARE_TOKEN"] == "redacted-credential"
    assert "redacted-credential" not in json.dumps(result, ensure_ascii=False)
    assert result["loaded"] is False
    assert str(tmp_path / "LaunchAgents") in result["plist_path"]


def test_news_scheduler_missing_tushare_token_is_recorded_as_runtime_configuration_failure(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TS_TOKEN", raising=False)
    db_path = init_db(tmp_path / "scheduler-news-missing-token.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))

    run = run_scheduler_job(db_path, "news_hourly_incremental", now=datetime.fromisoformat("2026-05-25T10:05:00"))

    assert run["status"] == "failed"
    assert run["execution_mode"] == "real_provider"
    assert "Tushare provider requires TUSHARE_TOKEN" in run["error"]
    assert "redacted-credential" not in json.dumps(run, ensure_ascii=False)
    with connect(db_path) as conn:
        scheduler_run = conn.execute(
            "SELECT status, error FROM scheduler_runs WHERE job_key = 'news_hourly_incremental' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        provider_limit = conn.execute(
            """
            SELECT provider_key, failure_count, last_failure_reason, backoff_until, metadata_json
            FROM provider_rate_limits
            WHERE provider_key = 'news'
            """
        ).fetchone()

    assert scheduler_run["status"] == "failed"
    assert "Tushare provider requires TUSHARE_TOKEN" in scheduler_run["error"]
    assert provider_limit["failure_count"] == 1
    assert "Tushare provider requires TUSHARE_TOKEN" in provider_limit["last_failure_reason"]
    assert provider_limit["backoff_until"]
    provider_metadata = json.loads(provider_limit["metadata_json"])
    assert "last_failure_at" in provider_metadata
    assert "last_success_at" not in provider_metadata


def test_provider_hourly_and_daily_budget_defer_reasons_are_specific(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-provider-budget-reasons.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    monkeypatch.setattr(service, "_market_context_has_fallback_provider", lambda: False)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO provider_rate_limits(provider_key, hourly_count, daily_count, metadata_json)
            VALUES ('akshare', 80, 100, ?)
            """,
            ('{"last_success_at": "2026-05-25T10:00:00"}',),
        )

    hourly = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T10:15:00"))

    assert hourly["status"] == "deferred"
    assert hourly["deferred_reason"] == "provider hourly budget exhausted for akshare"

    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE provider_rate_limits
            SET hourly_count = 0,
                daily_count = 500,
                metadata_json = ?
            WHERE provider_key = 'akshare'
            """,
            ('{"last_success_at": "2026-05-25T09:00:00"}',),
        )

    daily = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T11:15:00"))

    assert daily["status"] == "deferred"
    assert daily["deferred_reason"] == "provider daily budget exhausted for akshare"


def test_market_context_surfaces_price_nav_provider_budget_starvation(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-provider-starvation.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    monkeypatch.setattr(service, "_market_context_has_fallback_provider", lambda: False)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO provider_rate_limits(provider_key, hourly_count, daily_count, metadata_json)
            VALUES ('akshare', 600, 640, ?)
            """,
            (
                json.dumps(
                    {
                        "last_success_at": "2026-05-25T17:30:00",
                        "last_job_key": "price_nav_post_close",
                    },
                    ensure_ascii=False,
                ),
            ),
        )

    run = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T17:45:00"))

    assert run["status"] == "deferred"
    assert run["deferred_reason"] == "provider hourly budget exhausted for akshare"
    assert run["provider_request_counts"] == {"akshare": 0}
    with connect(db_path) as conn:
        latest = conn.execute(
            """
            SELECT status, deferred_reason
            FROM scheduler_runs
            WHERE job_key = 'market_context_intraday'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    assert latest["status"] == "deferred"
    assert latest["deferred_reason"] == "provider hourly budget exhausted for akshare"


def test_scheduler_agent_job_invokes_runtime_and_advances_next_run(tmp_path, monkeypatch):
    import investment_forecasting.agent_runtime.execution as execution

    db_path = init_db(tmp_path / "scheduler-agent.sqlite3")
    captured = {}

    def fake_run_expert_codex_agents(*args, **kwargs):
        captured["db_path"] = args[0]
        captured.update(kwargs)
        return {"ok": True, "run_date": kwargs["run_date"], "runs": [{"ok": True, "status": "completed"}]}

    monkeypatch.setattr(execution, "run_expert_codex_agents", fake_run_expert_codex_agents)
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T19:50:00"))

    run = run_scheduler_job(db_path, "expert_t_day_agents", now=datetime.fromisoformat("2026-05-25T20:01:00"))

    assert run["status"] == "success"
    assert run["updated_counts"]["agent_runs"] == 1
    assert captured["db_path"] == db_path
    assert captured["run_date"] == "2026-05-25"
    with connect(db_path) as conn:
        next_run = conn.execute("SELECT next_run_at FROM scheduler_jobs WHERE job_key = 'expert_t_day_agents'").fetchone()["next_run_at"]
    assert next_run == "2026-05-26T20:00:00"


def test_scheduler_today_status_marks_missed_failed_and_not_yet_due(tmp_path):
    db_path = init_db(tmp_path / "scheduler-today.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO scheduler_runs(job_key, scheduled_at, started_at, finished_at, status, error)
            VALUES ('news_hourly_incremental', '2026-05-25T08:05:00', '2026-05-25 08:05:01', '2026-05-25 08:05:02', 'failed', 'provider down')
            """
        )
        conn.execute(
            """
            INSERT INTO task_logs(task_name, run_date, status, message, error)
            VALUES ('scheduler_job', '2026-05-25', 'failed', 'Running scheduler job news_hourly_incremental', 'provider down')
            """
        )

    status = scheduler_today_status(db_path, now=datetime.fromisoformat("2026-05-25T10:30:00"))
    by_key = {item["job_key"]: item for item in status["items"]}

    assert status["overall_status"] == "bad"
    assert by_key["news_hourly_incremental"]["status"] == "failed"
    assert by_key["news_hourly_incremental"]["failed_count"] == 1
    assert by_key["market_context_intraday"]["status"] == "missed"
    assert by_key["expert_t_day_agents"]["status"] == "not_yet_due"
    assert status["task_log_failures"][0]["error"] == "provider down"


def test_scheduler_today_status_keeps_same_day_failure_visible_after_manual_success(tmp_path):
    db_path = init_db(tmp_path / "scheduler-today-history.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO scheduler_runs(job_key, scheduled_at, started_at, finished_at, status, error)
            VALUES
              ('price_nav_post_close', '2026-05-25T17:30:00', '2026-05-25 17:30:01', '2026-05-25 17:30:02', 'failed', 'stock:000004 no history'),
              ('price_nav_post_close', '2026-05-25T17:30:00', '2026-05-25 17:45:01', '2026-05-25 17:45:02', 'success', NULL)
            """
        )
        conn.execute(
            """
            INSERT INTO task_logs(task_name, run_date, status, message, error)
            VALUES ('scheduler_job', '2026-05-25', 'failed', 'Running scheduler job price_nav_post_close', 'stock:000004 no history')
            """
        )

    status = scheduler_today_status(db_path, now=datetime.fromisoformat("2026-05-25T18:00:00"))
    by_key = {item["job_key"]: item for item in status["items"]}

    assert by_key["price_nav_post_close"]["status"] == "success"
    assert by_key["price_nav_post_close"]["failed_count"] == 0
    assert by_key["price_nav_post_close"]["recovered_count"] == 1


def test_run_scheduler_job_can_record_specific_scheduled_occurrence(tmp_path, monkeypatch):
    db_path = init_db(tmp_path / "scheduler-specific-occurrence.sqlite3")
    _patch_scheduler_providers(monkeypatch)
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))

    run = run_scheduler_job(
        db_path,
        "news_hourly_incremental",
        now=datetime.fromisoformat("2026-05-25T10:30:00"),
        scheduled_at=datetime.fromisoformat("2026-05-25T08:05:00"),
    )

    assert run["status"] == "success"
    assert run["scheduled_at"] == "2026-05-25T08:05:00"
    with connect(db_path) as conn:
        next_run = conn.execute("SELECT next_run_at FROM scheduler_jobs WHERE job_key = 'news_hourly_incremental'").fetchone()["next_run_at"]
    assert next_run == "2026-05-25T08:05:00"


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


def _patch_scheduler_providers(monkeypatch):
    import investment_forecasting.scheduler.service as service

    monkeypatch.setattr(service, "_news_provider", lambda: FakeSchedulerProvider())
    monkeypatch.setattr(service, "_news_provider_for_source", lambda source: FakeSchedulerProvider())
    monkeypatch.setattr(service, "_market_provider", lambda: FakeSchedulerProvider())


class FakeSchedulerProvider:
    source = "fake"

    def news(self, *, source: str, start_datetime: str, end_datetime: str):
        return [
            {
                "id": f"{source}-1",
                "title": "政策支持宽基指数，市场情绪回暖",
                "content": "政策支持宽基指数，市场情绪回暖。",
                "published_at": end_datetime,
                "url": "https://example.test/news/1",
            }
        ]

    def market_capital_flow(self):
        return [self._flow("market", "CN_A", "A股市场")]

    def stock_capital_flow(self, code: str):
        return [self._flow("stock", str(code).zfill(6), str(code).zfill(6))]

    def history(self, asset, start_date: str, end_date: str):
        trade_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
        return [
            {
                "trade_date": trade_date,
                "open": 1.1,
                "high": 1.2,
                "low": 1.0,
                "close": 1.15,
                "volume": 1000,
                "amount": 1150,
                "pct_change": 15.0,
                "adjusted_close": 1.15,
                "nav": None,
                "accumulated_nav": None,
                "raw_payload": None,
            }
        ]

    def _flow(self, scope: str, code: str, name: str):
        return {
            "flow_date": "2026-05-25",
            "scope": scope,
            "subject_code": code,
            "subject_name": name,
            "close": 1.0,
            "pct_change": 0.5,
            "main_net_inflow": 100.0,
            "main_net_inflow_pct": 1.0,
            "super_large_net_inflow": 50.0,
            "super_large_net_inflow_pct": 0.5,
            "large_net_inflow": 25.0,
            "large_net_inflow_pct": 0.25,
            "medium_net_inflow": 15.0,
            "medium_net_inflow_pct": 0.15,
            "small_net_inflow": 10.0,
            "small_net_inflow_pct": 0.1,
            "source": self.source,
            "raw_payload": None,
        }


class EmptySchedulerProvider(FakeSchedulerProvider):
    def market_capital_flow(self):
        return []

    def stock_capital_flow(self, code: str):
        return []


class FailingMarketContextProvider(FakeSchedulerProvider):
    source = "akshare"

    def market_capital_flow(self):
        raise RuntimeError("eastmoney dns failed")

    def stock_capital_flow(self, code: str):
        raise RuntimeError("eastmoney dns failed")


class TushareSchedulerProvider(FakeSchedulerProvider):
    source = "tushare"


class MarketOnlySchedulerProvider(FakeSchedulerProvider):
    def stock_capital_flow(self, code: str):
        raise RuntimeError("stock endpoint failed")


class PartialPriceSchedulerProvider(FakeSchedulerProvider):
    def history(self, asset, start_date: str, end_date: str):
        if asset.code == "000004":
            raise RuntimeError("no history")
        return super().history(asset, start_date, end_date)


class FailingPriceSchedulerProvider(FakeSchedulerProvider):
    source = "akshare"

    def history(self, asset, start_date: str, end_date: str):
        raise RuntimeError("akshare price endpoint failed")
