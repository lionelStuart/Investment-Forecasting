from __future__ import annotations

from investment_forecasting.db import connect, init_db
from investment_forecasting.workflows.daily import default_daily_config, run_daily_workflow
from tests.test_features import seed_asset_with_prices


def test_daily_workflow_skip_ingest_is_idempotent(tmp_path):
    db_path = tmp_path / "daily.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    config = default_daily_config(
        db_path=db_path,
        run_date="20260523",
        start_date="20260101",
        end_date="20260107",
        horizons=(2,),
        lookback_days=3,
        skip_ingest=True,
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

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["steps"]["ingest"] == {"skipped": True}
    assert advice_count == 1
    assert prediction_count == 1
    assert backtest_result_count == 3
    assert workflow_success_count == 2


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
