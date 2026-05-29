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
    upsert_model_prediction_reliability,
    upsert_price_daily,
    upsert_communication_adapter_config,
    upsert_communication_recipient,
    upsert_agent_run,
)
from investment_forecasting.ai_analysis import AIAnalysisValidationError, validate_ai_analysis_record
from investment_forecasting.experts.planning import ExpertPlanningError, check_expert_plan_compliance, run_expert_agent_plan_from_output, run_expert_daily_plans
from investment_forecasting.experts.roster import DEFAULT_ACTIVE_EXPERT_COUNT, DEFAULT_EXPERTS, initialize_default_experts, list_roster
from investment_forecasting.portfolio.accounting import ensure_expert_portfolios, record_virtual_order


def test_initialize_default_experts_is_idempotent(tmp_path):
    db_path = tmp_path / "experts.sqlite3"

    first = initialize_default_experts(db_path)
    second = initialize_default_experts(db_path)

    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM experts").fetchone()["count"]

    assert len(first) == DEFAULT_ACTIVE_EXPERT_COUNT
    assert len(second) == DEFAULT_ACTIVE_EXPERT_COUNT
    assert count == DEFAULT_ACTIVE_EXPERT_COUNT
    assert {expert["name"] for expert in second} == {"管仲", "白圭", "范蠡", "桑弘羊"}
    assert all("专家" not in expert["name"] for expert in second)
    assert all(expert["lifecycle_state"] == "active" for expert in second)
    assert all(expert["focus_weights"] for expert in second)
    assert all(expert["allowed_asset_categories"] for expert in second)


def test_initialize_default_experts_retires_legacy_style_named_roster(tmp_path):
    db_path = init_db(tmp_path / "legacy-experts.sqlite3")
    legacy_names = {
        "defensive_income": "稳健防守专家",
        "momentum_growth": "趋势进攻专家",
        "balanced_rotation": "均衡轮动专家",
    }
    with connect(db_path) as conn:
        for key, name in legacy_names.items():
            upsert_expert(
                conn,
                {
                    "expert_key": key,
                    "name": name,
                    "short_description": "旧版风格命名专家。",
                    "style_label": name.removesuffix("专家"),
                    "focus_weights_json": json.dumps({"test": 1.0}, ensure_ascii=False),
                    "risk_budget_pct": 0.4,
                    "max_drawdown_tolerance": 0.1,
                    "allowed_asset_categories_json": json.dumps(["etf"], ensure_ascii=False),
                    "default_cash_buffer_pct": 0.2,
                    "review_cadence_days": 20,
                    "lifecycle_state": "active",
                    "mandate": "旧版配置。",
                    "source": "system",
                },
            )

    active = initialize_default_experts(db_path)

    with connect(db_path) as conn:
        legacy = conn.execute("SELECT expert_key, name, lifecycle_state, source FROM experts WHERE expert_key IN ('defensive_income', 'momentum_growth', 'balanced_rotation')").fetchall()

    assert len(active) == DEFAULT_ACTIVE_EXPERT_COUNT
    assert {expert["name"] for expert in active} == {"管仲", "白圭", "范蠡", "桑弘羊"}
    assert {row["lifecycle_state"] for row in legacy} == {"retired"}
    assert all("专家" not in row["name"] for row in legacy)
    assert all(row["source"] == "obsolete_style_named_v1" for row in legacy)


def test_expert_upsert_updates_structured_configuration(tmp_path):
    db_path = init_db(tmp_path / "experts.sqlite3")
    expert = {
        "expert_key": "quality_value",
        "name": "韩非",
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
        second_id = upsert_expert(conn, {**expert, "name": "韩非（候选）", "lifecycle_state": "active"})
        row = get_expert(conn, "quality_value")

    assert first_id == second_id
    assert row is not None
    assert row["name"] == "韩非（候选）"
    assert row["lifecycle_state"] == "active"
    assert json.loads(row["focus_weights_json"])["valuation_proxy"] == 0.6


def test_list_experts_filters_active_roster_and_preserves_lifecycle(tmp_path):
    db_path = tmp_path / "experts.sqlite3"
    initialize_default_experts(db_path)

    with connect(db_path) as conn:
        defensive = get_expert(conn, "guan_zhong")
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

    assert len(active) == DEFAULT_ACTIVE_EXPERT_COUNT - 1
    assert [row["expert_key"] for row in probation] == ["guan_zhong"]


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
        valuation_count = conn.execute("SELECT COUNT(*) AS count FROM virtual_valuations").fetchone()["count"]
        analysis_count = conn.execute("SELECT COUNT(*) AS count FROM ai_analysis_records WHERE analysis_type = 'expert'").fetchone()["count"]
        analysis_row = conn.execute("SELECT validation_json FROM ai_analysis_records WHERE analysis_type = 'expert' ORDER BY id LIMIT 1").fetchone()
        plans = conn.execute("SELECT * FROM expert_plans ORDER BY expert_id").fetchall()
        positions = conn.execute("SELECT COUNT(*) AS count FROM virtual_positions WHERE quantity > 0").fetchone()["count"]
        analysis_log = conn.execute("SELECT * FROM task_logs WHERE task_name = 'expert_ai_analysis' ORDER BY id DESC LIMIT 1").fetchone()

    assert len(first) == DEFAULT_ACTIVE_EXPERT_COUNT
    assert len(second) == DEFAULT_ACTIVE_EXPERT_COUNT
    assert plan_count == DEFAULT_ACTIVE_EXPERT_COUNT
    assert item_count == DEFAULT_ACTIVE_EXPERT_COUNT
    assert transaction_count == DEFAULT_ACTIVE_EXPERT_COUNT
    assert valuation_count == DEFAULT_ACTIVE_EXPERT_COUNT
    assert analysis_count == DEFAULT_ACTIVE_EXPERT_COUNT
    assert json.loads(analysis_row["validation_json"])["provider"]["fallback_reason"] == "provider_not_configured"
    assert {row["execution_status"] for row in plans} <= {"filled", "unfilled", "no_trade"}
    assert all(json.loads(row["evidence_json"])["prediction_id"] for row in plans)
    assert all(row["ai_analysis_id"] for row in plans)
    assert all(json.loads(row["evidence_json"])["ai_analysis_id"] == row["ai_analysis_id"] for row in plans)
    assert all("虚拟研究组合模拟" in row["risk_warnings"] for row in plans)
    assert analysis_log["status"] == "success"
    assert positions >= 1


def test_expert_plans_resolve_to_latest_fresh_price_feature_evidence_date(tmp_path):
    db_path = seed_expert_planning_db(tmp_path)
    with connect(db_path) as conn:
        asset = conn.execute("SELECT * FROM assets WHERE code = '510300'").fetchone()
        upsert_feature_daily(
            conn,
            {
                "asset_id": asset["id"],
                "feature_date": "2026-05-24",
                "return_1d": 0.02,
                "return_5d": 0.04,
                "return_20d": 0.09,
                "return_60d": 0.13,
                "volatility_20d": 0.02,
                "max_drawdown_60d": -0.03,
                "sharpe_60d": 1.3,
                "calmar_60d": 1.6,
                "win_rate_60d": 0.64,
                "momentum_20d": 0.09,
                "market_state": "bullish",
                "source": "test",
            },
        )
        upsert_model_prediction(
            conn,
            {
                "asset_id": asset["id"],
                "prediction_date": "2026-05-24",
                "horizon_days": 20,
                "model_version": "test_model",
                "target": "return",
                "up_probability": 0.72,
                "expected_return": 0.12,
                "expected_return_low": 0.03,
                "expected_return_high": 0.18,
                "downside_risk": -0.02,
                "confidence": 0.95,
                "input_window_start": "2026-04-01",
                "input_window_end": "2026-05-24",
                "assumptions": "stale price should not be tradable",
            },
        )

    plans = run_expert_daily_plans(db_path, plan_date="2026-05-24")

    assert {plan["plan_date"] for plan in plans} == {"2026-05-23"}
    with connect(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT plan_date FROM expert_plans ORDER BY plan_date").fetchall()
    assert [row["plan_date"] for row in rows] == ["2026-05-23"]


def test_expert_agent_sell_action_executes_virtual_sell(tmp_path):
    db_path = seed_expert_planning_db(tmp_path)
    with connect(db_path) as conn:
        expert = get_expert(conn, "bai_gui")
        portfolio = conn.execute("SELECT * FROM virtual_portfolios WHERE owner_type = 'expert' AND owner_id = ?", (expert["id"],)).fetchone()
        asset = conn.execute("SELECT * FROM assets WHERE code = '510300'").fetchone()
        record_virtual_order(conn, portfolio_id=portfolio["id"], trade_date="2026-05-23", side="buy", asset_id=asset["id"], quantity=2)
        agent_run_id = upsert_agent_run(
            conn,
            {
                "role_type": "expert",
                "role_key": "bai_gui",
                "run_date": "2026-05-24",
                "target_evidence_date": "2026-05-24",
                "trigger_reason": "test",
                "status": "running",
                "overview_skill": "investment-expert-agent",
                "skill_bundle": [],
                "prompt_ref": {},
                "tool_manifest_ref": {},
                "output_contract": {},
                "runtime_policy": {},
                "launch_request": {},
                "runtime_metadata": {},
                "idempotency_key": "test-bai-gui-sell",
            },
        )
        conn.execute(
            """
            INSERT INTO agent_tool_calls(
                agent_run_id, tool_name, role_type, role_key, arguments_json,
                idempotency_key, status, result_summary_json
            )
            VALUES (?, 'submit_expert_virtual_action', 'expert', 'bai_gui', ?, 'sell-action', 'submitted', '{}')
            """,
            (
                agent_run_id,
                json.dumps(
                    {
                        "payload": {
                            "action": "sell",
                            "target_asset_id": asset["id"],
                            "quantity": 2,
                            "target_amount": 200,
                            "rationale": "测试卖出虚拟持仓。",
                        }
                    },
                    ensure_ascii=False,
                ),
            ),
        )

    plan = run_expert_agent_plan_from_output(
        db_path,
        plan_date="2026-05-24",
        expert_key="bai_gui",
        agent_run_id=agent_run_id,
        agent_output={
            "status": "ok",
            "role": "expert",
            "role_key": "bai_gui",
            "outcome": "plan_action",
            "summary": "测试卖出。",
            "action": "sell",
            "reason": "测试卖出虚拟持仓。",
            "analysis": "测试卖出虚拟持仓。",
            "reflection": "测试卖出虚拟持仓。",
            "risk_note": "该操作仅用于虚拟研究组合模拟，不构成真实买卖指令。",
            "evidence_ids": ["prediction:1"],
            "news_evidence_ids": [],
        },
    )

    with connect(db_path) as conn:
        transaction = conn.execute("SELECT * FROM virtual_transactions WHERE id = ?", (plan["transaction_id"],)).fetchone()
        position = conn.execute("SELECT * FROM virtual_positions WHERE portfolio_id = ? AND asset_id = ?", (portfolio["id"], asset["id"])).fetchone()

    assert plan["action"] == "sell"
    assert plan["execution_status"] == "filled"
    assert transaction["side"] == "sell"
    assert transaction["quantity"] == 2
    assert transaction["cost_basis"] == 200
    assert position["quantity"] == 0


def test_expert_agent_buy_action_persists_virtual_buy(tmp_path):
    db_path = seed_expert_planning_db(tmp_path)
    with connect(db_path) as conn:
        expert = get_expert(conn, "bai_gui")
        portfolio = conn.execute("SELECT * FROM virtual_portfolios WHERE owner_type = 'expert' AND owner_id = ?", (expert["id"],)).fetchone()
        asset = conn.execute("SELECT * FROM assets WHERE code = '510300'").fetchone()
        agent_run_id = upsert_agent_run(
            conn,
            {
                "role_type": "expert",
                "role_key": "bai_gui",
                "run_date": "2026-05-24",
                "target_evidence_date": "2026-05-24",
                "trigger_reason": "test",
                "status": "running",
                "overview_skill": "investment-expert-agent",
                "skill_bundle": [],
                "prompt_ref": {},
                "tool_manifest_ref": {},
                "output_contract": {},
                "runtime_policy": {},
                "launch_request": {},
                "runtime_metadata": {},
                "idempotency_key": "test-bai-gui-buy",
            },
        )
        conn.execute(
            """
            INSERT INTO agent_tool_calls(
                agent_run_id, tool_name, role_type, role_key, arguments_json,
                idempotency_key, status, result_summary_json
            )
            VALUES (?, 'submit_expert_virtual_action', 'expert', 'bai_gui', ?, 'buy-action', 'submitted', '{}')
            """,
            (
                agent_run_id,
                json.dumps(
                    {
                        "payload": {
                            "action": "buy",
                            "target_asset_id": asset["id"],
                            "quantity": 3,
                            "target_amount": 300,
                            "rationale": "测试买入虚拟持仓。",
                        }
                    },
                    ensure_ascii=False,
                ),
            ),
        )

    plan = run_expert_agent_plan_from_output(
        db_path,
        plan_date="2026-05-24",
        expert_key="bai_gui",
        agent_run_id=agent_run_id,
        agent_output={
            "status": "ok",
            "role": "expert",
            "role_key": "bai_gui",
            "outcome": "plan_action",
            "summary": "测试买入。",
            "action": "buy",
            "reason": "测试买入虚拟持仓。",
            "analysis": "测试买入虚拟持仓。",
            "reflection": "测试买入虚拟持仓。",
            "risk_note": "该操作仅用于虚拟研究组合模拟，不构成真实买卖指令。",
            "evidence_ids": ["prediction:1"],
            "news_evidence_ids": [],
        },
    )

    with connect(db_path) as conn:
        transaction = conn.execute("SELECT * FROM virtual_transactions WHERE id = ?", (plan["transaction_id"],)).fetchone()
        position = conn.execute("SELECT * FROM virtual_positions WHERE portfolio_id = ? AND asset_id = ?", (portfolio["id"], asset["id"])).fetchone()
        valuation = conn.execute("SELECT * FROM virtual_valuations WHERE portfolio_id = ? AND valuation_date = '2026-05-23'", (portfolio["id"],)).fetchone()

    assert plan["action"] == "buy"
    assert plan["plan_date"] == "2026-05-23"
    assert plan["execution_status"] == "filled"
    assert transaction["side"] == "buy"
    assert transaction["quantity"] == 3
    assert transaction["cost_basis"] == pytest.approx(300)
    assert transaction["realized_pnl"] == 0
    assert position["quantity"] == 3
    assert position["average_cost"] == pytest.approx(100)
    assert valuation is not None


def test_degraded_model_evidence_is_watch_only_for_expert_plans(tmp_path):
    db_path = seed_expert_planning_db(tmp_path)
    with connect(db_path) as conn:
        prediction = conn.execute("SELECT id FROM model_predictions LIMIT 1").fetchone()
        upsert_model_prediction_reliability(
            conn,
            {
                "prediction_id": prediction["id"],
                "rank_score": 1.0,
                "rank_position": 1,
                "rank_count": 1,
                "same_category_key": "etf:broad_market",
                "same_category_rank": 1,
                "same_category_count": 1,
                "risk_adjusted_score": 0.9,
                "validation_status": "degraded",
                "recent_rank_ic": -0.08,
                "bucket_spread": -0.02,
                "degraded_reason": "negative_rank_ic",
                "evidence_json": json.dumps({"prediction_id": prediction["id"], "backtest_run_ids": [99]}),
            },
        )

    plans = run_expert_daily_plans(db_path, plan_date="2026-05-23")

    with connect(db_path) as conn:
        analysis = conn.execute("SELECT evidence_packet_json, output_json FROM ai_analysis_records WHERE analysis_type = 'expert' ORDER BY id LIMIT 1").fetchone()
        rows = conn.execute("SELECT action, rationale, evidence_json, risk_checks_json FROM expert_plans").fetchall()

    packet = json.loads(analysis["evidence_packet_json"])
    output = json.loads(analysis["output_json"])
    first_candidate = packet["candidates"][0]
    assert {plan["action"] for plan in plans} == {"no_trade"}
    assert first_candidate["validation_status"] == "degraded"
    assert first_candidate["watch_only"] is True
    assert first_candidate["recent_rank_ic"] == -0.08
    assert output["selected_candidates"][0]["watch_only"] is True
    assert all(json.loads(row["risk_checks_json"])["watch_only_model_signal"] is True for row in rows)
    assert all(json.loads(row["evidence_json"])["model_evidence_packet"]["validation_status"] == "degraded" for row in rows)
    assert all("只能作为观察线索" in row["rationale"] for row in rows)


def test_expert_plan_evidence_marks_stale_capital_flow_as_degraded(tmp_path):
    db_path = seed_expert_planning_db(tmp_path)
    with connect(db_path) as conn:
        asset = conn.execute("SELECT id, code, name FROM assets WHERE code = '510300'").fetchone()
        conn.execute(
            """
            INSERT INTO capital_flow_observations(
                flow_date, scope, subject_code, subject_name, asset_id,
                main_net_inflow, main_net_inflow_pct, source, raw_payload
            )
            VALUES ('2026-05-18', 'stock', ?, ?, ?, -1200000, -0.04, 'test', '{}')
            """,
            (asset["code"], asset["name"], asset["id"]),
        )

    run_expert_daily_plans(db_path, plan_date="2026-05-23")

    with connect(db_path) as conn:
        row = conn.execute("SELECT evidence_json FROM expert_plans ORDER BY id LIMIT 1").fetchone()

    evidence = json.loads(row["evidence_json"])
    assert evidence["capital_flow"]["status"] == "degraded"
    assert evidence["capital_flow"]["latest_date"] == "2026-05-18"
    assert evidence["capital_flow"]["stale"] is True


def test_run_expert_daily_plans_records_fake_provider_success(tmp_path, monkeypatch):
    monkeypatch.setenv("INVESTMENT_FORECASTING_AI_PROVIDER", "fake")
    db_path = seed_expert_planning_db(tmp_path)

    run_expert_daily_plans(db_path, plan_date="2026-05-23")

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT source, validation_json, output_json FROM ai_analysis_records WHERE analysis_type = 'expert' ORDER BY id LIMIT 1"
        ).fetchone()
        log = conn.execute("SELECT message FROM task_logs WHERE task_name = 'expert_ai_analysis' ORDER BY id DESC LIMIT 1").fetchone()

    validation = json.loads(row["validation_json"])
    output = json.loads(row["output_json"])
    assert row["source"].startswith("provider:fake:")
    assert validation["provider"]["status"] == "success"
    assert "provider_output" in output
    assert '"success": 4' in log["message"]


def test_expert_plan_ready_notification_is_rendered_from_persisted_plans(tmp_path):
    db_path = seed_expert_planning_db(tmp_path)
    seed_notification_recipient(db_path)

    first = run_expert_daily_plans(
        db_path,
        plan_date="2026-05-23",
        notify_recipient_key="owner_phone",
        notification_dry_run=True,
    )
    second = run_expert_daily_plans(
        db_path,
        plan_date="2026-05-23",
        notify_recipient_key="owner_phone",
        notification_dry_run=True,
    )

    with connect(db_path) as conn:
        messages = conn.execute("SELECT * FROM outbound_messages WHERE template_key = 'expert_plan_ready'").fetchall()

    assert len(first) == DEFAULT_ACTIVE_EXPERT_COUNT
    assert len(second) == DEFAULT_ACTIVE_EXPERT_COUNT
    assert len(messages) == 1
    assert messages[0]["status"] == "dry_run"
    assert "虚拟研究组合模拟" in messages[0]["body"]


def test_expert_plan_compliance_requires_evidence_and_rejects_certainty_language():
    valid = {
        "rationale": "基于已存储预测和风险检查，选择不交易。",
        "risk_warnings": "仅用于虚拟研究组合模拟，不构成真实买卖指令。",
        "evidence": {"prediction_id": 1, "ai_analysis_id": 2},
    }
    check_expert_plan_compliance(valid)

    with pytest.raises(ExpertPlanningError, match="prediction evidence"):
        check_expert_plan_compliance({**valid, "evidence": {}})
    with pytest.raises(ExpertPlanningError, match="AI analysis evidence"):
        check_expert_plan_compliance({**valid, "evidence": {"prediction_id": 1}})
    with pytest.raises(Exception, match="保本"):
        check_expert_plan_compliance({**valid, "rationale": "该计划保本。"})


def test_ai_analysis_validation_rejects_unsupported_prediction_claims():
    analysis = {
        "analysis_type": "expert",
        "analysis_key": "guan_zhong",
        "analysis_date": "2026-05-23",
        "evidence_packet": {"candidate_prediction_ids": [1]},
        "output": {
            "thesis": "基于已存证据保持观察。",
            "selected_candidates": [{"prediction_id": 2}],
            "rejected_candidates": [],
            "referenced_prediction_ids": [2],
        },
        "validation": {},
    }

    with pytest.raises(AIAnalysisValidationError, match="unsupported AI claims"):
        validate_ai_analysis_record(analysis)


def test_ai_analysis_validation_rejects_unsupported_news_evidence_claims():
    analysis = {
        "analysis_type": "expert",
        "analysis_key": "guan_zhong",
        "analysis_date": "2026-05-23",
        "evidence_packet": {"candidate_prediction_ids": [1], "news_evidence_ids": [10]},
        "output": {
            "thesis": "基于已存证据保持观察。",
            "selected_candidates": [{"prediction_id": 1}],
            "rejected_candidates": [],
            "referenced_prediction_ids": [1],
            "referenced_news_evidence_ids": [99],
        },
        "validation": {},
    }

    with pytest.raises(AIAnalysisValidationError, match="unsupported news evidence"):
        validate_ai_analysis_record(analysis)


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
