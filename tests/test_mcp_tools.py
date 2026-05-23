from __future__ import annotations

import json

from investment_forecasting.advice.generator import generate_daily_advice
from investment_forecasting.db import connect, upsert_asset, upsert_fund_info, upsert_price_daily
from investment_forecasting.experts.planning import run_expert_daily_plans
from investment_forecasting.experts.roster import initialize_default_experts
from investment_forecasting.experts.scoring import score_and_review_experts
from investment_forecasting.mcp.tools import call_tool, list_tools
from investment_forecasting.portfolio.accounting import ensure_expert_portfolios
from investment_forecasting.quant.backtest import run_backtest, run_latest_forecasts
from investment_forecasting.quant.features import calculate_features_for_db
from investment_forecasting.quant.market import calculate_market_snapshot
from tests.test_features import seed_asset_with_prices


def seed_fund(db_path) -> int:
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": "FUND",
                "name": "Fixture Fund",
                "asset_type": "fund",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "akshare",
            },
        )
        for index, value in enumerate([1.0, 1.01, 1.02, 1.03], start=1):
            upsert_price_daily(
                conn,
                asset_id=asset_id,
                source="akshare",
                price={
                    "trade_date": f"2026-01-{index:02d}",
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": value,
                    "volume": None,
                    "amount": None,
                    "pct_change": None,
                    "adjusted_close": None,
                    "nav": value,
                    "accumulated_nav": value,
                    "raw_payload": None,
                },
            )
        upsert_fund_info(
            conn,
            asset_id=asset_id,
            source="akshare",
            info={
                "fund_type": "混合型-偏股",
                "fund_company": "Fixture Fund Co",
                "manager": "Fixture Manager",
                "custodian": "Fixture Custodian",
                "management_fee": None,
                "custody_fee": None,
                "purchase_fee": 0.15,
                "scale": 12.34,
                "inception_date": "2020-01-01",
                "benchmark": "Fixture Benchmark",
                "strategy": "Fixture Strategy",
                "objective": "Fixture Objective",
                "stage_returns_json": '{"return_1m": 1.23}',
                "raw_payload": "{}",
            },
        )
    return asset_id


def prepare_tool_db(tmp_path):
    db_path = tmp_path / "tools.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106])
    seed_fund(db_path)
    calculate_features_for_db(db_path)
    calculate_market_snapshot(db_path, snapshot_date="20260104")
    run_latest_forecasts(db_path, horizons=(5, 20, 60))
    run_backtest(db_path, horizons=(2,), lookback_days=3)
    generate_daily_advice(db_path, advice_date="20260523")
    initialize_default_experts(db_path)
    ensure_expert_portfolios(db_path)
    run_expert_daily_plans(db_path, plan_date="20260107")
    score_and_review_experts(db_path, review_date="20260107", min_valuations=1)
    return db_path


def test_list_tools_includes_spec_tools():
    names = {tool["name"] for tool in list_tools()}

    assert {
        "get_asset_list",
        "get_asset_history",
        "get_fund_metrics",
        "get_market_snapshot",
        "run_forecast",
        "run_backtest",
        "get_daily_advice",
        "generate_daily_advice",
        "list_experts",
        "get_expert_plans",
        "run_expert_plans",
        "get_expert_portfolios",
        "score_experts",
        "get_expert_scorecards",
        "get_expert_lessons",
    }.issubset(names)


def test_asset_history_and_fund_metrics_tools(tmp_path):
    db_path = prepare_tool_db(tmp_path)

    assets = call_tool(db_path, "get_asset_list", {})
    history = call_tool(db_path, "get_asset_history", {"code": "TEST", "source": "test", "limit": 2})
    metrics = call_tool(db_path, "get_fund_metrics", {"code": "FUND"})

    assert assets["ok"] is True
    assert assets["result"]["count"] == 2
    assert history["ok"] is True
    assert history["result"]["count"] == 2
    assert history["result"]["history"][0]["trade_date"] == "2026-01-01"
    assert metrics["ok"] is True
    assert metrics["result"]["fund_info"]["manager"] == "Fixture Manager"
    assert metrics["result"]["metrics"]["source"] == "features_v1"


def test_snapshot_forecast_backtest_and_advice_tools(tmp_path):
    db_path = prepare_tool_db(tmp_path)

    snapshot = call_tool(db_path, "get_market_snapshot", {})
    forecast = call_tool(db_path, "run_forecast", {"horizons": [5]})
    backtest = call_tool(db_path, "run_backtest", {"horizons": [2], "lookback_days": 3})
    advice = call_tool(db_path, "get_daily_advice", {"date": "20260523"})
    generated = call_tool(db_path, "generate_daily_advice", {"date": "20260524"})

    assert snapshot["ok"] is True
    assert snapshot["result"]["prediction_summary"]["count"] >= 3
    assert snapshot["result"]["market_environment"]["sentiment"] in {"risk_on", "risk_off", "neutral"}
    assert forecast["ok"] is True
    assert forecast["result"]["horizons"] == [5]
    assert backtest["ok"] is True
    assert backtest["result"]["horizons"][2]["count"] > 0
    assert advice["ok"] is True
    assert json.loads(advice["result"]["advice"]["evidence_json"])["source_prediction_ids"]
    assert generated["ok"] is True
    assert generated["result"]["advice"]["advice_date"] == "2026-05-24"


def test_expert_mcp_tools_and_task_logs(tmp_path):
    db_path = prepare_tool_db(tmp_path)

    experts = call_tool(db_path, "list_experts", {"state": "active"})
    plans = call_tool(db_path, "get_expert_plans", {})
    portfolios = call_tool(db_path, "get_expert_portfolios", {})
    score = call_tool(db_path, "score_experts", {"date": "20260107", "min_valuations": 1})
    scorecards = call_tool(db_path, "get_expert_scorecards", {"date": "20260107"})
    lessons = call_tool(db_path, "get_expert_lessons", {})
    rerun_plans = call_tool(db_path, "run_expert_plans", {"date": "20260107"})

    with connect(db_path) as conn:
        log_names = {
            row["task_name"]
            for row in conn.execute("SELECT task_name FROM task_logs WHERE task_name LIKE 'expert_%'").fetchall()
        }

    assert experts["ok"] is True
    assert experts["result"]["count"] == 3
    assert plans["ok"] is True
    assert plans["result"]["count"] == 3
    assert portfolios["ok"] is True
    assert portfolios["result"]["count"] == 3
    assert score["ok"] is True
    assert score["result"]["reviewed"]
    assert scorecards["ok"] is True
    assert scorecards["result"]["scorecards"]
    assert lessons["ok"] is True
    assert lessons["result"]["lessons"] == []
    assert rerun_plans["ok"] is True
    assert rerun_plans["result"]["virtual_research_only"] is True
    assert {"expert_daily_planning", "expert_scoring_review"}.issubset(log_names)


def test_tool_errors_are_structured(tmp_path):
    db_path = tmp_path / "empty.sqlite3"

    response = call_tool(db_path, "get_asset_history", {"code": "NOPE"})

    assert response == {
        "ok": False,
        "tool": "get_asset_history",
        "result": None,
        "error": {"message": "Unknown asset: NOPE/CN/akshare"},
    }
