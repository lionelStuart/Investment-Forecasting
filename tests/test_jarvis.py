from __future__ import annotations

import json

import pytest

from investment_forecasting.cli import main as cli_main
from investment_forecasting.communication.templates import render_jarvis_daily_summary, send_rendered_notification
from investment_forecasting.db import (
    connect,
    get_jarvis_daily_brief,
    init_db,
    upsert_ai_analysis_record,
    upsert_communication_adapter_config,
    upsert_communication_recipient,
    upsert_model_prediction_reliability,
    upsert_user_preference,
)
from investment_forecasting.experts.roster import initialize_default_experts
from investment_forecasting.jarvis import JarvisPersistenceError, generate_jarvis_brief, get_jarvis_brief, save_jarvis_brief
from investment_forecasting.portfolio.accounting import ensure_expert_portfolios
from investment_forecasting.quant.backtest import run_backtest, run_latest_forecasts
from tests.test_features import seed_asset_with_prices


def sample_brief(**overrides):
    brief = {
        "brief_date": "2026-05-23",
        "focus_directions": [
            {"direction": "防守现金", "reason": "市场证据不足时保持观察"},
            {"direction": "ETF轮动", "reason": "等待趋势确认"},
        ],
        "one_line_stance": "偏防守，等待确认",
        "model_summary": {
            "status": "degraded",
            "horizons": [{"horizon_days": 20, "expected_return": 0.01, "confidence": 0.52}],
        },
        "expert_summary": [
            {
                "expert_name": "管仲",
                "action": "no_trade",
                "score": 50,
                "current_return": 0.0,
                "risk_state": "样本不足",
            }
        ],
        "combined_recommendation": "优先观察数据质量和专家分歧，暂不扩大风险暴露。",
        "risk_warnings": "仅作研究辅助，结果受数据新鲜度、模型稳定性和回撤风险影响。",
        "evidence": {
            "market_snapshot_ids": [1],
            "model_prediction_ids": [10, 11],
            "expert_plan_ids": [20],
            "scorecard_ids": [30],
        },
        "source": "test",
    }
    brief.update(overrides)
    return brief


def test_jarvis_brief_can_be_persisted_and_queried_by_date(tmp_path):
    db_path = init_db(tmp_path / "jarvis.sqlite3")

    saved = save_jarvis_brief(db_path, **sample_brief())
    fetched = get_jarvis_brief(db_path, brief_date="2026-05-23")

    assert fetched is not None
    assert fetched["id"] == saved["id"]
    assert fetched["brief_date"] == "2026-05-23"
    assert fetched["version"] == "jarvis_v1"
    assert fetched["focus_directions"][0]["direction"] == "防守现金"
    assert fetched["model_summary"]["status"] == "degraded"
    assert fetched["expert_summary"][0]["expert_name"] == "管仲"
    assert fetched["evidence"]["expert_plan_ids"] == [20]


def test_jarvis_brief_rerun_is_idempotent_for_same_date_and_version(tmp_path):
    db_path = init_db(tmp_path / "jarvis.sqlite3")

    first = save_jarvis_brief(db_path, **sample_brief())
    second = save_jarvis_brief(
        db_path,
        **sample_brief(one_line_stance="均衡观察", combined_recommendation="等待更多证据后再调整风险暴露。"),
    )

    with connect(db_path) as conn:
        row_count = conn.execute("SELECT COUNT(*) AS count FROM jarvis_daily_briefs").fetchone()["count"]
        row = get_jarvis_daily_brief(conn, "2026-05-23", "jarvis_v1")

    assert first["id"] == second["id"]
    assert row_count == 1
    assert row["one_line_stance"] == "均衡观察"


def test_jarvis_brief_persists_missing_and_stale_evidence_metadata(tmp_path):
    db_path = init_db(tmp_path / "jarvis.sqlite3")

    saved = save_jarvis_brief(
        db_path,
        **sample_brief(
            missing_evidence=[{"source": "expert_scorecards", "reason": "估值样本不足"}],
            stale_evidence=[{"source": "market_snapshots", "last_date": "2026-05-20"}],
        ),
    )

    assert saved["missing_evidence"] == [{"source": "expert_scorecards", "reason": "估值样本不足"}]
    assert saved["stale_evidence"] == [{"source": "market_snapshots", "last_date": "2026-05-20"}]


def test_jarvis_brief_rejects_unsafe_certainty_language(tmp_path):
    db_path = init_db(tmp_path / "jarvis.sqlite3")

    with pytest.raises(JarvisPersistenceError, match="unsafe certainty language"):
        save_jarvis_brief(db_path, **sample_brief(combined_recommendation="该方向稳赚，适合直接加仓。"))


def test_jarvis_brief_requires_traceable_evidence(tmp_path):
    db_path = init_db(tmp_path / "jarvis.sqlite3")

    with pytest.raises(JarvisPersistenceError, match="evidence is required"):
        save_jarvis_brief(db_path, **sample_brief(evidence={}))


def test_generate_jarvis_brief_synthesizes_model_and_all_active_experts(tmp_path):
    db_path = seed_jarvis_synthesis_state(tmp_path)

    brief = generate_jarvis_brief(db_path, brief_date="20260523")
    fetched = get_jarvis_brief(db_path, brief_date="2026-05-23")

    assert fetched is not None
    assert fetched["id"] == brief["id"]
    assert fetched["model_summary"]["top_forecasts"]
    assert "validation_status" in fetched["model_summary"]["top_forecasts"][0]
    assert "risk_adjusted_score" in fetched["model_summary"]["top_forecasts"][0]
    assert "evidence_ids" in fetched["model_summary"]["top_forecasts"][0]
    assert len(fetched["expert_summary"]) == 4
    assert all(row["expert_name"] for row in fetched["expert_summary"])
    assert all(row["action"] == "no_trade" for row in fetched["expert_summary"])
    assert all(row["current_return"] is not None for row in fetched["expert_summary"])
    assert fetched["evidence"]["model_prediction_ids"]
    assert fetched["evidence"]["expert_plan_ids"]
    assert fetched["evidence"]["expert_ai_analysis_ids"]
    assert fetched["evidence"]["expert_scorecard_ids"]
    assert fetched["evidence"]["capital_flow_ids"]
    assert fetched["model_summary"]["capital_flow"]["status"] == "available"
    assert fetched["evidence"]["jarvis_ai_analysis_id"]
    assert all(row["ai_analysis_id"] for row in fetched["expert_summary"])
    assert all(row["ai_thesis"] for row in fetched["expert_summary"])
    assert "Jarvis 仅作本地投资研究辅助" in fetched["risk_warnings"]


def test_jarvis_cites_degraded_model_packet_as_watch_only(tmp_path):
    db_path = seed_jarvis_synthesis_state(tmp_path)
    with connect(db_path) as conn:
        predictions = conn.execute("SELECT id FROM model_predictions").fetchall()
        for prediction in predictions:
            upsert_model_prediction_reliability(
                conn,
                {
                    "prediction_id": prediction["id"],
                    "rank_score": 1.0,
                    "rank_position": 1,
                    "rank_count": 3,
                    "same_category_key": "etf:broad_market",
                    "same_category_rank": 1,
                    "same_category_count": 3,
                    "risk_adjusted_score": 0.95,
                    "validation_status": "degraded",
                    "recent_rank_ic": -0.12,
                    "bucket_spread": -0.03,
                    "degraded_reason": "negative_rank_ic",
                    "evidence_json": json.dumps({"prediction_id": prediction["id"], "backtest_run_ids": [101]}),
                },
            )

    brief = generate_jarvis_brief(db_path, brief_date="20260523")

    top = brief["model_summary"]["top_forecasts"][0]
    gates = {item["gate"] for item in brief["model_summary"]["confidence_gates"]}
    assert top["validation_status"] == "degraded"
    assert top["watch_only"] is True
    assert {"degraded_model_signal", "negative_rank_ic", "negative_bucket_spread"}.issubset(gates)
    assert brief["model_summary"]["model_risk_summary"]["status"] == "watch_only"
    assert brief["model_summary"]["excluded_horizons"]
    assert brief["model_summary"]["degraded_model_families"]
    assert brief["evidence"]["confidence_gates"]
    assert any(direction.get("gate_status") == "watch_only" for direction in brief["focus_directions"])


def test_jarvis_risk_officer_gates_insufficient_category_and_weak_bucket(tmp_path):
    db_path = seed_jarvis_synthesis_state(tmp_path)
    with connect(db_path) as conn:
        predictions = conn.execute("SELECT id FROM model_predictions").fetchall()
        for prediction in predictions:
            upsert_model_prediction_reliability(
                conn,
                {
                    "prediction_id": prediction["id"],
                    "rank_score": 0.9,
                    "rank_position": 1,
                    "rank_count": 3,
                    "same_category_key": "etf:broad_market",
                    "same_category_rank": 1,
                    "same_category_count": 1,
                    "risk_adjusted_score": 0.8,
                    "validation_status": "validated",
                    "recent_rank_ic": 0.01,
                    "bucket_spread": 0.001,
                    "degraded_reason": None,
                    "evidence_json": json.dumps({"prediction_id": prediction["id"], "backtest_run_ids": [102]}),
                },
            )

    brief = generate_jarvis_brief(db_path, brief_date="20260523")

    gates = {item["gate"] for item in brief["model_summary"]["confidence_gates"]}
    assert {"insufficient_same_category_sample", "weak_rank_ic", "weak_bucket_spread"}.issubset(gates)
    assert brief["model_summary"]["model_risk_summary"]["watch_only_count"] >= 3
    assert "部分模型信号触发风险官信心门" in brief["risk_warnings"]


def test_jarvis_phone_summary_template_is_safe_and_idempotent(tmp_path):
    db_path = init_db(tmp_path / "jarvis-phone.sqlite3")
    saved = save_jarvis_brief(db_path, **sample_brief())
    seed_notification_recipient(db_path)

    with connect(db_path) as conn:
        notification = render_jarvis_daily_summary(saved)
        first = send_rendered_notification(conn, channel="imessage", recipient_key="owner_phone", notification=notification, dry_run=True)
        second = send_rendered_notification(conn, channel="imessage", recipient_key="owner_phone", notification=notification, dry_run=True)

    assert first["status"] == "dry_run"
    assert second["duplicate"] is True
    assert notification.template_key == "jarvis_daily_summary"
    assert "Jarvis 投资研究摘要" in notification.body
    assert "本消息仅作研究辅助" in notification.body
    assert "不构成真实买卖指令" in notification.body
    assert "raw" not in notification.body.lower()


def test_generate_jarvis_brief_can_send_phone_summary_dry_run(tmp_path):
    db_path = seed_jarvis_synthesis_state(tmp_path)
    seed_notification_recipient(db_path)

    first = generate_jarvis_brief(
        db_path,
        brief_date="20260523",
        notify_recipient_key="owner_phone",
        notification_dry_run=True,
    )
    second = generate_jarvis_brief(
        db_path,
        brief_date="20260523",
        notify_recipient_key="owner_phone",
        notification_dry_run=True,
    )

    with connect(db_path) as conn:
        messages = conn.execute("SELECT * FROM outbound_messages WHERE template_key = 'jarvis_daily_summary'").fetchall()

    assert first["notification"]["status"] == "dry_run"
    assert second["notification"]["duplicate"] is True
    assert len(messages) == 1
    assert "Jarvis 投资研究摘要" in messages[0]["body"]


def test_jarvis_cli_generate_uses_environment_notification_defaults(tmp_path, capsys, monkeypatch):
    db_path = seed_jarvis_synthesis_state(tmp_path)
    seed_notification_recipient(db_path)
    monkeypatch.setenv("INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY", "owner_phone")
    monkeypatch.setenv("INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN", "true")

    result = cli_main(["jarvis", "generate", "--db", str(db_path), "--date", "20260523"])

    output = capsys.readouterr().out
    with connect(db_path) as conn:
        messages = conn.execute("SELECT * FROM outbound_messages WHERE template_key = 'jarvis_daily_summary'").fetchall()
    assert result == 0
    assert '"status": "dry_run"' in output
    assert len(messages) == 1
    assert messages[0]["recipient_key"] == "owner_phone"


def test_jarvis_cli_can_send_weekly_summary_dry_run(tmp_path, capsys):
    db_path = init_db(tmp_path / "jarvis-weekly.sqlite3")
    save_jarvis_brief(db_path, **sample_brief())
    seed_notification_recipient(db_path)

    result = cli_main(
        [
            "jarvis",
            "send-weekly",
            "--db",
            str(db_path),
            "--start-date",
            "20260517",
            "--end-date",
            "20260523",
            "--recipient-key",
            "owner_phone",
            "--notification-dry-run",
        ]
    )
    output = capsys.readouterr().out

    assert result == 0
    assert '"template_key": "jarvis_weekly_summary"' in output
    assert '"status": "dry_run"' in output


def test_generate_jarvis_brief_explains_model_expert_disagreement(tmp_path):
    db_path = seed_jarvis_synthesis_state(tmp_path)
    with connect(db_path) as conn:
        conn.execute("UPDATE model_predictions SET expected_return = 0.06, downside_risk = -0.02, confidence = 0.8")

    brief = generate_jarvis_brief(db_path, brief_date="20260523")

    disagreement = brief["model_summary"]["disagreement"]
    assert disagreement["has_disagreement"] is True
    assert "模型偏正向" in disagreement["summary"]
    assert "分歧提示" in brief["combined_recommendation"]


def test_jarvis_confidence_gates_extreme_low_confidence_forecast(tmp_path):
    db_path = seed_jarvis_synthesis_state(tmp_path)
    with connect(db_path) as conn:
        conn.execute("UPDATE model_predictions SET expected_return = 0.42, downside_risk = -0.03, confidence = 0.2")

    brief = generate_jarvis_brief(db_path, brief_date="20260523")

    gates = brief["model_summary"]["confidence_gates"]
    gate_names = {item["gate"] for item in gates}
    assert {"outlier_expected_return", "low_confidence_forecast"}.issubset(gate_names)
    assert brief["evidence"]["confidence_gates"]
    assert "观察信号" in brief["combined_recommendation"]
    assert any(direction.get("gate_status") == "watch_only" for direction in brief["focus_directions"])


def test_generate_jarvis_brief_records_fake_provider_success(tmp_path, monkeypatch):
    monkeypatch.setenv("INVESTMENT_FORECASTING_AI_PROVIDER", "fake")
    db_path = seed_jarvis_synthesis_state(tmp_path)

    brief = generate_jarvis_brief(db_path, brief_date="20260523")

    with connect(db_path) as conn:
        row = conn.execute("SELECT source, validation_json, output_json FROM ai_analysis_records WHERE id = ?", (brief["evidence"]["jarvis_ai_analysis_id"],)).fetchone()
        log = conn.execute("SELECT message FROM task_logs WHERE task_name = 'jarvis_ai_analysis' ORDER BY id DESC LIMIT 1").fetchone()

    validation = json.loads(row["validation_json"])
    output = json.loads(row["output_json"])
    assert row["source"].startswith("provider:fake:")
    assert validation["provider"]["status"] == "success"
    assert "provider_output" in output
    assert "provider_status=success" in log["message"]


def test_generate_jarvis_brief_records_missing_and_stale_evidence(tmp_path):
    db_path = init_db(tmp_path / "missing-jarvis.sqlite3")

    brief = generate_jarvis_brief(db_path, brief_date="20260523")

    missing_sources = {item["source"] for item in brief["missing_evidence"]}
    assert {"market_snapshots", "capital_flow_observations", "model_predictions", "backtest_runs", "experts", "user_preferences"}.issubset(missing_sources)
    assert brief["model_summary"]["status"] == "missing"
    assert brief["expert_summary"] == []
    assert "存在缺失证据" in brief["risk_warnings"]

    stale_db_path = seed_jarvis_synthesis_state(tmp_path)
    stale_brief = generate_jarvis_brief(stale_db_path, brief_date="20260530")
    stale_sources = {item["source"] for item in stale_brief["stale_evidence"]}
    assert {"market_snapshots", "model_predictions", "expert_plans", "expert_ai_analysis", "expert_scorecards", "virtual_valuations"}.issubset(stale_sources)
    assert "存在过期证据" in stale_brief["risk_warnings"]


def seed_jarvis_synthesis_state(tmp_path):
    db_path = tmp_path / "jarvis-synthesis.sqlite3"
    seed_asset_with_prices(db_path, [100, 101, 102, 103, 104, 105, 106, 107])
    run_latest_forecasts(db_path, horizons=(5, 20, 60))
    run_backtest(db_path, horizons=(2,), lookback_days=3)
    initialize_default_experts(db_path)
    ensure_expert_portfolios(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO market_snapshots(
                snapshot_date, source, index_trend, breadth, liquidity_heat,
                stock_bond_proxy, sentiment, details_json
            )
            VALUES ('2026-05-23', 'test', 0.01, 0.55, 0.4, 0.02, 'neutral', '{}')
            """
        )
        asset = conn.execute("SELECT id, code, name FROM assets ORDER BY id LIMIT 1").fetchone()
        conn.execute(
            """
            INSERT INTO capital_flow_observations(
                flow_date, scope, subject_code, subject_name, asset_id,
                main_net_inflow, main_net_inflow_pct, source, raw_payload
            )
            VALUES ('2026-05-23', 'stock', ?, ?, ?, 1200000, 0.04, 'test', '{}')
            """,
            (asset["code"], asset["name"], asset["id"]),
        )
        upsert_user_preference(
            conn,
            {
                "profile_name": "默认账户",
                "risk_profile": "balanced",
                "investment_horizon_days": 20,
                "max_equity_pct": 0.6,
                "min_cash_pct": 0.1,
                "notes": "测试偏好",
                "is_active": 1,
            },
        )
        experts = conn.execute(
            """
            SELECT e.id, e.expert_key, e.name, vp.id AS portfolio_id
            FROM experts e
            JOIN virtual_portfolios vp ON vp.owner_type = 'expert' AND vp.owner_id = e.id
            WHERE e.lifecycle_state = 'active'
            ORDER BY e.expert_key
            """
        ).fetchall()
        for index, expert in enumerate(experts):
            total_value = 500_000 + index * 5_000
            ai_analysis_id = upsert_ai_analysis_record(
                conn,
                {
                    "analysis_type": "expert",
                    "analysis_key": expert["expert_key"],
                    "analysis_date": "2026-05-23",
                    "expert_id": expert["id"],
                    "evidence_packet": {
                        "candidate_prediction_ids": [index + 1],
                        "expert": {"id": expert["id"], "name": expert["name"]},
                    },
                    "output": {
                        "thesis": f"{expert['name']}保持独立防守观察。",
                        "watched_signals": ["confidence", "downside_risk"],
                        "selected_candidates": [{"prediction_id": index + 1}],
                        "rejected_candidates": [],
                        "risk_objections": [],
                        "confidence": 0.6,
                        "proposed_action": "no_trade",
                        "stance": "防守观察",
                        "referenced_prediction_ids": [index + 1],
                    },
                    "validation": {
                        "supported_prediction_ids": [index + 1],
                        "unsupported_claims": [],
                        "compliance_ok": True,
                    },
                    "status": "valid",
                    "source": "test",
                },
            )
            conn.execute(
                """
                INSERT INTO virtual_valuations(
                    portfolio_id, valuation_date, cash, positions_value,
                    total_value, missing_prices_json, details_json
                )
                VALUES (?, '2026-05-23', 500000, 0, ?, '[]', '[]')
                """,
                (expert["portfolio_id"], total_value),
            )
            conn.execute(
                """
                INSERT INTO expert_plans(
                    expert_id, portfolio_id, ai_analysis_id, plan_date, action, target_asset_id,
                    target_weight, target_amount, rationale, evidence_json,
                    risk_checks_json, risk_warnings, execution_status
                )
                VALUES (?, ?, ?, '2026-05-23', 'no_trade', NULL, 0, 0, ?, ?, '{}', ?, 'no_trade')
                """,
                (
                    expert["id"],
                    expert["portfolio_id"],
                    ai_analysis_id,
                    f"{expert['name']}保持观察。",
                    json.dumps({"ai_analysis_id": ai_analysis_id, "prediction_id": index + 1}, ensure_ascii=False),
                    "虚拟研究组合风险提示。",
                ),
            )
            conn.execute(
                """
                INSERT INTO expert_scorecards(
                    expert_id, portfolio_id, score_date, window_days,
                    valuation_count, mature_enough, portfolio_return,
                    benchmark_return, benchmark_excess, max_drawdown,
                    volatility, cash_drag, turnover, win_rate,
                    evidence_completeness, mandate_adherence, overall_score,
                    details_json
                )
                VALUES (?, ?, '2026-05-23', 20, 3, 1, ?, 0.01, ?, -0.01, 0.02, 0.1, 0.0, 0.5, 1.0, 0.9, ?, '{}')
                """,
                (expert["id"], expert["portfolio_id"], index * 0.01, index * 0.01 - 0.01, 75 - index),
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
