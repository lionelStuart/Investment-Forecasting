from __future__ import annotations

import json

from investment_forecasting.cli import main as cli_main
from investment_forecasting.db import connect
from investment_forecasting.quant.backtest import run_backtest, run_latest_forecasts
from investment_forecasting.quant.monitoring import run_model_monitoring_report
from tests.test_features import seed_asset_with_prices


def test_model_monitoring_report_persists_scores_and_staleness(tmp_path):
    db_path = tmp_path / "monitoring.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    run_latest_forecasts(db_path, horizons=(2,))
    run_backtest(db_path, horizons=(2,), lookback_days=3)

    report = run_model_monitoring_report(db_path, report_date="20260107")
    repeat = run_model_monitoring_report(db_path, report_date="20260107")

    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM model_monitoring_reports").fetchall()
        task_log = conn.execute("SELECT * FROM task_logs WHERE task_name = 'model_monitoring' ORDER BY id DESC LIMIT 1").fetchone()

    assert report["count"] == 1
    assert repeat["report_ids"] == report["report_ids"]
    assert len(rows) == 1
    assert rows[0]["model_version"] == "baseline_mean_v1"
    assert rows[0]["latest_prediction_date"] == "2026-01-07"
    assert rows[0]["prediction_staleness_days"] == 0
    assert rows[0]["mean_prediction_score"] is not None
    assert rows[0]["mean_risk_score"] is not None
    assert rows[0]["mean_benchmark_excess"] is not None
    assert rows[0]["status"] in {"ok", "warning", "degraded"}
    metrics = json.loads(rows[0]["metrics_json"])
    assert metrics["latest_run_ids"]
    assert "mean_rank_ic" in metrics
    assert "mean_bucket_spread" in metrics
    assert metrics["validation_policies"]
    assert metrics["governance"]["governance_state"] == "baseline"
    assert metrics["governance"]["jarvis_primary_allowed"] is True
    assert task_log["status"] == "success"


def test_model_monitoring_governance_demotes_negative_rank_candidate(tmp_path):
    db_path = tmp_path / "monitoring-governance.sqlite3"
    seed_asset_with_prices(db_path, [100, 102, 101, 103, 102, 104, 103])
    run_latest_forecasts(
        db_path,
        horizons=(2,),
        model_versions=("baseline_mean_v1", "risk_adjusted_factor_v1"),
    )
    run_backtest(
        db_path,
        horizons=(2,),
        lookback_days=3,
        model_versions=("baseline_mean_v1", "risk_adjusted_factor_v1"),
    )

    report = run_model_monitoring_report(db_path, report_date="20260107")
    by_version = {row["model_version"]: json.loads(row["metrics_json"])["governance"] for row in report["reports"]}

    assert by_version["baseline_mean_v1"]["governance_state"] == "baseline"
    assert by_version["risk_adjusted_factor_v1"]["governance_state"] in {"contextual", "degraded"}
    assert by_version["risk_adjusted_factor_v1"]["promotion_allowed"] is False
    assert by_version["risk_adjusted_factor_v1"]["product_review_required_for_promotion"] is True


def test_model_monitoring_warns_on_insufficient_validation_sample(tmp_path):
    db_path = tmp_path / "monitoring-validation.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    run_latest_forecasts(db_path, horizons=(2,))
    run_backtest(db_path, horizons=(2,), lookback_days=3, embargo_days=1)

    report = run_model_monitoring_report(db_path, report_date="20260107")
    warnings = json.loads(report["reports"][0]["warnings_json"])

    assert any(item["code"] == "insufficient_validation_sample" for item in warnings)


def test_model_monitoring_marks_stale_inputs(tmp_path):
    db_path = tmp_path / "monitoring-stale.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    run_latest_forecasts(db_path, horizons=(2,))
    run_backtest(db_path, horizons=(2,), lookback_days=3)

    report = run_model_monitoring_report(db_path, report_date="20260220")
    warnings = report["reports"][0]["warnings_json"]

    assert report["reports"][0]["status"] in {"warning", "degraded"}
    assert "stale_predictions" in warnings
    assert "stale_backtests" in warnings


def test_monitoring_cli_generates_report(tmp_path, capsys):
    db_path = tmp_path / "monitoring-cli.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    run_latest_forecasts(db_path, horizons=(2,))
    run_backtest(db_path, horizons=(2,), lookback_days=3)

    assert cli_main(["monitoring", "run", "--db", str(db_path), "--date", "20260107"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["count"] == 1
    assert output["reports"][0]["model_version"] == "baseline_mean_v1"
