from __future__ import annotations

from investment_forecasting.db import (
    connect,
    init_db,
    upsert_asset,
    upsert_communication_adapter_config,
    upsert_communication_recipient,
    upsert_price_daily,
)
from investment_forecasting.workflows.daily import default_daily_config, run_daily_workflow
from tests.test_features import seed_asset_with_prices


def test_daily_workflow_skip_ingest_is_idempotent(tmp_path):
    db_path = tmp_path / "daily.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    config = default_daily_config(
        db_path=db_path,
        run_date="20260103",
        start_date="20260101",
        end_date="20260107",
        horizons=(2,),
        lookback_days=3,
        skip_ingest=True,
        generate_jarvis=True,
    )

    first = run_daily_workflow(config)
    second = run_daily_workflow(config)

    with connect(db_path) as conn:
        advice_count = conn.execute("SELECT COUNT(*) AS count FROM daily_advice").fetchone()["count"]
        prediction_count = conn.execute("SELECT COUNT(*) AS count FROM model_predictions").fetchone()["count"]
        backtest_result_count = conn.execute("SELECT COUNT(*) AS count FROM backtest_results").fetchone()["count"]
        workflow_success_count = conn.execute(
            "SELECT COUNT(*) AS count FROM task_logs WHERE task_name = 'daily_workflow' AND status = 'success'"
        ).fetchone()["count"]
        advice_score_count = conn.execute("SELECT COUNT(*) AS count FROM advice_outcome_scores").fetchone()["count"]
        jarvis_count = conn.execute("SELECT COUNT(*) AS count FROM jarvis_daily_briefs").fetchone()["count"]
        monitoring_count = conn.execute("SELECT COUNT(*) AS count FROM model_monitoring_reports").fetchone()["count"]

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["steps"]["ingest"] == {"skipped": True}
    assert "advice_outcome_scores" in first["steps"]
    assert "monitoring" in first["steps"]
    assert "jarvis" in first["steps"]
    assert advice_count == 1
    assert prediction_count == 1
    assert backtest_result_count == 3
    assert advice_score_count == 1
    assert jarvis_count == 1
    assert monitoring_count == 1
    assert workflow_success_count == 2


def test_daily_workflow_success_notification_is_dry_run_and_idempotent(tmp_path):
    db_path = tmp_path / "daily-notification.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    seed_notification_recipient(db_path)
    config = default_daily_config(
        db_path=db_path,
        run_date="20260103",
        start_date="20260101",
        end_date="20260107",
        horizons=(2,),
        lookback_days=3,
        skip_ingest=True,
        notify_recipient_key="owner_phone",
        notification_dry_run=True,
    )

    first = run_daily_workflow(config)
    second = run_daily_workflow(config)

    with connect(db_path) as conn:
        messages = conn.execute("SELECT * FROM outbound_messages").fetchall()

    assert first["steps"]["notification"]["status"] == "dry_run"
    assert second["steps"]["notification"]["duplicate"] is True
    assert len(messages) == 1
    assert messages[0]["template_key"] == "daily_workflow_success"
    assert "仅供研究辅助" in messages[0]["body"]


def test_daily_workflow_uses_environment_default_notification_recipient(tmp_path, monkeypatch):
    db_path = tmp_path / "daily-env-notification.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    seed_notification_recipient(db_path)
    monkeypatch.setenv("INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY", "owner_phone")
    monkeypatch.setenv("INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN", "true")

    config = default_daily_config(
        db_path=db_path,
        run_date="20260103",
        start_date="20260101",
        end_date="20260107",
        horizons=(2,),
        lookback_days=3,
        skip_ingest=True,
    )
    result = run_daily_workflow(config)

    with connect(db_path) as conn:
        message = conn.execute("SELECT * FROM outbound_messages WHERE template_key = 'daily_workflow_success'").fetchone()

    assert config.notify_recipient_key == "owner_phone"
    assert config.notification_dry_run is True
    assert result["steps"]["notification"]["status"] == "dry_run"
    assert message["recipient_key"] == "owner_phone"


def test_daily_workflow_skips_invalid_asset_price_history(tmp_path):
    db_path = tmp_path / "daily-gap.sqlite3"
    good_asset_id = seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    with connect(db_path) as conn:
        bad_asset_id = upsert_asset(
            conn,
            {
                "code": "GAP",
                "name": "Gap Asset",
                "asset_type": "stock",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "test",
            },
        )
        for trade_date, value in [("2026-01-01", 100), ("2026-01-20", 101)]:
            upsert_price_daily(
                conn,
                asset_id=bad_asset_id,
                source="test",
                price={
                    "trade_date": trade_date,
                    "open": value,
                    "high": value,
                    "low": value,
                    "close": value,
                    "volume": None,
                    "amount": None,
                    "pct_change": None,
                    "adjusted_close": value,
                    "nav": None,
                    "accumulated_nav": None,
                    "raw_payload": None,
                },
            )
    config = default_daily_config(
        db_path=db_path,
        run_date="20260103",
        start_date="20260101",
        end_date="20260107",
        horizons=(2,),
        lookback_days=3,
        skip_ingest=True,
    )

    result = run_daily_workflow(config)

    with connect(db_path) as conn:
        feature_log = conn.execute(
            "SELECT status, message FROM task_logs WHERE task_name = 'feature_calculation' ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert result["ok"] is True
    assert result["steps"]["features"][good_asset_id] == 6
    assert result["steps"]["features"][bad_asset_id] == 0
    assert feature_log["status"] == "success"
    assert "skipped 1 assets" in feature_log["message"]


def test_daily_workflow_failure_writes_task_log(tmp_path):
    db_path = tmp_path / "daily.sqlite3"
    init_db(db_path)
    config = default_daily_config(
        db_path=db_path,
        run_date="20260523",
        start_date="20260101",
        end_date="20260107",
        horizons=(2,),
        lookback_days=3,
        skip_ingest=True,
    )

    try:
        run_daily_workflow(config)
    except Exception as exc:
        assert "features_daily" in str(exc)

    with connect(db_path) as conn:
        log = conn.execute(
            "SELECT status, error FROM task_logs WHERE task_name = 'daily_workflow'"
        ).fetchone()

    assert log["status"] == "failed"
    assert "features_daily" in log["error"]


def test_daily_workflow_failure_notification_does_not_hide_original_failure(tmp_path):
    db_path = tmp_path / "daily-failure-notification.sqlite3"
    init_db(db_path)
    seed_notification_recipient(db_path)
    config = default_daily_config(
        db_path=db_path,
        run_date="20260523",
        start_date="20260101",
        end_date="20260107",
        horizons=(2,),
        lookback_days=3,
        skip_ingest=True,
        notify_recipient_key="owner_phone",
        notification_dry_run=True,
    )

    try:
        run_daily_workflow(config)
    except Exception as exc:
        assert "features_daily" in str(exc)

    with connect(db_path) as conn:
        message = conn.execute("SELECT * FROM outbound_messages WHERE template_key = 'daily_workflow_failure'").fetchone()

    assert message["status"] == "dry_run"
    assert "日常研究流程失败" in message["body"]


def seed_notification_recipient(db_path) -> None:
    with connect(db_path) as conn:
        upsert_communication_adapter_config(conn, {"channel": "imessage", "enabled": 1, "dry_run_default": 1})
        upsert_communication_recipient(
            conn,
            {
                "recipient_key": "owner_phone",
                "display_name": "Owner",
                "channel": "imessage",
                "address": "+10000000000",
                "allowlisted": 1,
                "enabled": 1,
                "rate_limit_per_hour": 10,
            },
        )
