from __future__ import annotations

import json

import pytest

from investment_forecasting.db import (
    connect,
    get_expert,
    init_db,
    list_experts,
    upsert_asset,
    upsert_expert,
    upsert_feature_daily,
    upsert_market_snapshot,
    upsert_model_prediction,
    upsert_price_daily,
)
from investment_forecasting.experts.planning import ExpertPlanningError, check_expert_plan_compliance, run_expert_daily_plans
from investment_forecasting.experts.roster import DEFAULT_EXPERTS, initialize_default_experts, list_roster
from investment_forecasting.portfolio.accounting import ensure_expert_portfolios


def test_initialize_default_experts_is_idempotent(tmp_path):
    db_path = tmp_path / "experts.sqlite3"

    first = initialize_default_experts(db_path)
    second = initialize_default_experts(db_path)

    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM experts").fetchone()["count"]

    assert len(first) == 3
    assert len(second) == 3
    assert count == 3
    assert {expert["name"] for expert in second} == {"稳健防守专家", "趋势进攻专家", "均衡轮动专家"}
    assert all(expert["lifecycle_state"] == "active" for expert in second)
    assert all(expert["focus_weights"] for expert in second)
    assert all(expert["allowed_asset_categories"] for expert in second)


def test_expert_upsert_updates_structured_configuration(tmp_path):
    db_path = init_db(tmp_path / "experts.sqlite3")
    expert = {
        "expert_key": "quality_value",
        "name": "质量价值专家",
        "short_description": "偏好基本面质量和风险折价。",
        "style_label": "质量价值",
        "focus_weights_json": json.dumps({"drawdown": 0.4, "valuation_proxy": 0.6}, ensure_ascii=False),
        "risk_budget_pct": 0.45,
        "max_drawdown_tolerance": 0.1,
        "allowed_asset_categories_json": json.dumps(["stock", "fund"], ensure_ascii=False),
        "default_cash_buffer_pct": 0.2,
        "review_cadence_days": 30,
        "lifecycle_state": "candidate",
        "mandate": "只作为虚拟研究角色，不构成真实买卖指令。",
        "source": "test",
    }

    with connect(db_path) as conn:
        first_id = upsert_expert(conn, expert)
        second_id = upsert_expert(conn, {**expert, "name": "质量价值候选专家", "lifecycle_state": "active"})
        row = get_expert(conn, "quality_value")

    assert first_id == second_id
    assert row is not None
    assert row["name"] == "质量价值候选专家"
    assert row["lifecycle_state"] == "active"
    assert json.loads(row["focus_weights_json"])["valuation_proxy"] == 0.6


def test_list_experts_filters_active_roster_and_preserves_lifecycle(tmp_path):
    db_path = tmp_path / "experts.sqlite3"
    initialize_default_experts(db_path)

    with connect(db_path) as conn:
        defensive = get_expert(conn, "defensive_income")
        assert defensive is not None
        upsert_expert(
            conn,
            {
                **dict(defensive),
                "lifecycle_state": "probation",
                "focus_weights_json": defensive["focus_weights_json"],
                "allowed_asset_categories_json": defensive["allowed_asset_categories_json"],
            },
        )
        active = list_experts(conn, lifecycle_state="active")
        probation = list_experts(conn, lifecycle_state="probation")

    assert len(active) == 2
    assert [row["expert_key"] for row in probation] == ["defensive_income"]


def test_list_roster_returns_json_fields_as_structures(tmp_path):
    db_path = tmp_path / "experts.sqlite3"
    initialize_default_experts(db_path)

    experts = list_roster(db_path, lifecycle_state="active")

    assert len(experts) == len(DEFAULT_EXPERTS)
    assert isinstance(experts[0]["focus_weights"], dict)
    assert isinstance(experts[0]["allowed_asset_categories"], list)
    assert "focus_weights_json" not in experts[0]


def test_run_expert_daily_plans_persists_one_plan_per_active_expert(tmp_path):
    db_path = seed_expert_planning_db(tmp_path)

    first = run_expert_daily_plans(db_path, plan_date="2026-05-23")
    second = run_expert_daily_plans(db_path, plan_date="2026-05-23")

    with connect(db_path) as conn:
        plan_count = conn.execute("SELECT COUNT(*) AS count FROM expert_plans").fetchone()["count"]
        item_count = conn.execute("SELECT COUNT(*) AS count FROM expert_plan_items").fetchone()["count"]
        transaction_count = conn.execute("SELECT COUNT(*) AS count FROM virtual_transactions").fetchone()["count"]
        plans = conn.execute("SELECT * FROM expert_plans ORDER BY expert_id").fetchall()
        positions = conn.execute("SELECT COUNT(*) AS count FROM virtual_positions WHERE quantity > 0").fetchone()["count"]

    assert len(first) == 3
    assert len(second) == 3
    assert plan_count == 3
    assert item_count == 3
    assert transaction_count == 3
    assert {row["execution_status"] for row in plans} <= {"filled", "unfilled", "no_trade"}
    assert all(json.loads(row["evidence_json"])["prediction_id"] for row in plans)
    assert all("虚拟研究组合模拟" in row["risk_warnings"] for row in plans)
    assert positions >= 1


def test_expert_plan_compliance_requires_evidence_and_rejects_certainty_language():
    valid = {
        "rationale": "基于已存储预测和风险检查，选择不交易。",
        "risk_warnings": "仅用于虚拟研究组合模拟，不构成真实买卖指令。",
        "evidence": {"prediction_id": 1},
    }
    check_expert_plan_compliance(valid)

    with pytest.raises(ExpertPlanningError, match="prediction evidence"):
        check_expert_plan_compliance({**valid, "evidence": {}})
    with pytest.raises(Exception, match="保本"):
        check_expert_plan_compliance({**valid, "rationale": "该计划保本。"})


def seed_expert_planning_db(tmp_path):
    db_path = init_db(tmp_path / "expert-planning.sqlite3")
    initialize_default_experts(db_path)
    ensure_expert_portfolios(db_path)
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": "510300",
                "name": "沪深300ETF",
                "asset_type": "etf",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "test",
            },
        )
        upsert_price_daily(
            conn,
            asset_id,
            "test",
            {
                "trade_date": "2026-05-23",
                "open": 100,
                "high": 100,
                "low": 100,
                "close": 100,
                "volume": None,
                "amount": None,
                "pct_change": None,
                "adjusted_close": None,
                "nav": None,
                "accumulated_nav": None,
                "raw_payload": "{}",
            },
        )
        upsert_feature_daily(
            conn,
            {
                "asset_id": asset_id,
                "feature_date": "2026-05-23",
                "return_1d": 0.01,
                "return_5d": 0.03,
                "return_20d": 0.08,
                "return_60d": 0.12,
                "volatility_20d": 0.02,
                "max_drawdown_60d": -0.03,
                "sharpe_60d": 1.2,
                "calmar_60d": 1.5,
                "win_rate_60d": 0.62,
                "momentum_20d": 0.08,
                "market_state": "bullish",
                "source": "test",
            },
        )
        upsert_model_prediction(
            conn,
            {
                "asset_id": asset_id,
                "prediction_date": "2026-05-23",
                "horizon_days": 20,
                "model_version": "test_model",
                "target": "return",
                "up_probability": 0.68,
                "expected_return": 0.09,
                "expected_return_low": 0.02,
                "expected_return_high": 0.16,
                "downside_risk": -0.02,
                "confidence": 0.9,
                "input_window_start": "2026-04-01",
                "input_window_end": "2026-05-23",
                "assumptions": "test evidence",
            },
        )
        upsert_market_snapshot(
            conn,
            {
                "snapshot_date": "2026-05-23",
                "source": "test",
                "index_trend": 0.04,
                "breadth": 0.7,
                "liquidity_heat": 1.1,
                "stock_bond_proxy": 0.02,
                "sentiment": "risk_on",
                "details_json": "{}",
            },
        )
    return db_path
