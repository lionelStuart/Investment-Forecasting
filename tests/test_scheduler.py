from __future__ import annotations

import json
from datetime import datetime

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
    assert watermark_count == 2
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
    assert run["updated_counts"]["inserted_news"] == 1
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
    assert run["provider_request_counts"] == {"news": 1}
    assert run["metadata"]["bounded_window"] is True
    assert run["metadata"]["real_provider_calls"] is True
    assert run["updated_counts"]["inserted_news"] == 1


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


def test_provider_budget_counts_reset_by_time_window(tmp_path, monkeypatch):
    _patch_scheduler_providers(monkeypatch)
    db_path = init_db(tmp_path / "scheduler-provider-budget.sqlite3")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO provider_rate_limits(provider_key, hourly_count, daily_count, metadata_json)
            VALUES ('akshare', 550, 550, ?)
            """,
            ('{"last_success_at": "2026-05-24T17:30:00"}',),
        )

    run = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T10:15:00"))

    assert run["status"] == "success"
    with connect(db_path) as conn:
        row = conn.execute("SELECT hourly_count, daily_count FROM provider_rate_limits WHERE provider_key = 'akshare'").fetchone()
    assert row["hourly_count"] <= 40
    assert row["daily_count"] <= 40


def test_market_context_fails_when_provider_returns_no_rows(tmp_path, monkeypatch):
    import investment_forecasting.scheduler.service as service

    db_path = init_db(tmp_path / "scheduler-market-empty.sqlite3")
    with connect(db_path) as conn:
        _seed_asset(conn, "000001", "Empty Flow Asset", "2026-05-23")
    initialize_scheduler(db_path, now=datetime.fromisoformat("2026-05-25T08:00:00"))
    monkeypatch.setattr(service, "_market_provider", lambda: EmptySchedulerProvider())

    run = run_scheduler_job(db_path, "market_context_intraday", now=datetime.fromisoformat("2026-05-25T10:15:00"))

    assert run["status"] == "failed"
    assert run["updated_counts"]["capital_flow_rows"] == 0
    assert "no capital flow rows" in run["error"]


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


def test_scheduler_install_cron_writes_unified_launch_agent(tmp_path):
    from investment_forecasting.scheduler import install_scheduler_cron

    db_path = init_db(tmp_path / "scheduler-cron.sqlite3")

    result = install_scheduler_cron(
        db_path,
        project_root=tmp_path,
        interval_minutes=5,
        python_bin="/usr/bin/python3",
        load=False,
        run_at_load=False,
    )

    assert result["ok"] is True
    assert result["label"] == "local.investment-forecasting.scheduler"
    assert result["interval_seconds"] == 300
    plist_text = open(result["plist_path"], encoding="utf-8").read()
    assert "investment_forecasting.cli" in plist_text
    assert "scheduler" in plist_text
    assert "run-due" in plist_text
    assert "<key>PATH</key>" in plist_text
    assert "Codex.app/Contents/Resources" in plist_text
    assert "local.investment-forecasting.experts" not in plist_text


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
