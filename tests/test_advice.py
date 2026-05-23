from __future__ import annotations

import json

import pytest

from investment_forecasting.advice.generator import (
    ADVICE_VERSION,
    ComplianceError,
    check_compliance,
    generate_daily_advice,
)
from investment_forecasting.db import connect, init_db, upsert_user_preference
from investment_forecasting.quant.backtest import run_backtest, run_latest_forecasts
from tests.test_features import seed_asset_with_prices


def test_generate_daily_advice_from_forecast_and_backtest_evidence(tmp_path):
    db_path = tmp_path / "advice.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    run_latest_forecasts(db_path, horizons=(5, 20, 60))
    run_backtest(db_path, horizons=(2,), lookback_days=3)

    advice_id = generate_daily_advice(db_path, advice_date="20260523")
    repeat_id = generate_daily_advice(db_path, advice_date="20260523")

    with connect(db_path) as conn:
        rows = conn.execute("SELECT COUNT(*) AS count FROM daily_advice").fetchone()["count"]
        advice = conn.execute("SELECT * FROM daily_advice WHERE id = ?", (advice_id,)).fetchone()
        logs = conn.execute("SELECT COUNT(*) AS count FROM task_logs WHERE status = 'success'").fetchone()["count"]

    allocation = json.loads(advice["allocation_json"])
    evidence = json.loads(advice["evidence_json"])
    assert repeat_id == advice_id
    assert rows == 1
    assert advice["model_version"] == ADVICE_VERSION
    assert advice["advice_date"] == "2026-05-23"
    assert advice["risk_level"] in {"low", "medium", "high"}
    assert "激进型" in advice["aggressive_advice"]
    assert "中等型" in advice["balanced_advice"]
    assert "保守型" in advice["conservative_advice"]
    assert allocation["profiles"]["aggressive"]["equity"] != allocation["profiles"]["conservative"]["equity"]
    assert allocation["focus_assets"]
    assert "近期优先关注" in advice["balanced_advice"]
    assert evidence["source_prediction_ids"]
    assert evidence["backtest_run_ids"]
    assert logs == 2


def test_compliance_guard_rejects_prohibited_language():
    with pytest.raises(ComplianceError, match="保本"):
        check_compliance("该策略保本并提供确定收益。")


def test_generate_daily_advice_failure_writes_task_log(tmp_path):
    db_path = tmp_path / "advice.sqlite3"
    init_db(db_path)

    with pytest.raises(Exception, match="model_predictions"):
        generate_daily_advice(db_path, advice_date="20260523")

    with connect(db_path) as conn:
        log = conn.execute("SELECT status, error FROM task_logs").fetchone()

    assert log["status"] == "failed"
    assert "model_predictions" in log["error"]


def test_generate_daily_advice_applies_active_user_preference(tmp_path):
    db_path = tmp_path / "advice-pref.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    run_latest_forecasts(db_path, horizons=(5, 20, 60))
    run_backtest(db_path, horizons=(2,), lookback_days=3)

    with connect(db_path) as conn:
        upsert_user_preference(
            conn,
            {
                "profile_name": "稳健账户",
                "risk_profile": "conservative",
                "investment_horizon_days": 60,
                "max_equity_pct": 0.3,
                "min_cash_pct": 0.25,
                "notes": "回撤敏感",
                "is_active": 1,
            },
        )

    advice_id = generate_daily_advice(db_path, advice_date="20260523")

    with connect(db_path) as conn:
        advice = conn.execute("SELECT * FROM daily_advice WHERE id = ?", (advice_id,)).fetchone()

    allocation = json.loads(advice["allocation_json"])
    assert allocation["user_preference"]["profile_name"] == "稳健账户"
    assert allocation["focus_assets"][0]["horizon_days"] == 60
    assert allocation["profiles"]["aggressive"]["equity"] == "30%-30%"
    assert "权益上限 30%" in advice["assumptions"]
    assert "稳健账户" in advice["market_summary"]
