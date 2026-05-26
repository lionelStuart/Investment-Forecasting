from __future__ import annotations

import json
import sqlite3

from investment_forecasting.db import connect, init_db, upsert_asset, upsert_price_daily
from investment_forecasting.quant.model_validation import (
    build_applicability_report,
    build_confidence_label_report,
    build_model_health_report,
    build_model_governance_report,
    build_replay_report,
    build_shadow_router_report,
    build_tuning_plan,
    generate_applicability_profiles,
    generate_confidence_labels,
    generate_model_health_metrics,
    generate_model_governance_summary,
    replay_ytd_predictions,
    run_shadow_router_floor70,
)


def seed_prices(db_path, values: list[float], code: str = "600000", asset_type: str = "stock") -> int:
    init_db(db_path)
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": code,
                "name": code,
                "asset_type": asset_type,
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "test",
            },
        )
        for index, value in enumerate(values, start=1):
            upsert_price_daily(
                conn,
                asset_id=asset_id,
                source="test",
                price={
                    "trade_date": f"2026-01-{index:02d}",
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
    return asset_id


def seed_shadow_replay(db_path) -> int:
    init_db(db_path)
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": "600000",
                "name": "测试资产",
                "asset_type": "stock",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "test",
            },
        )
        run_id = conn.execute(
            """
            INSERT INTO model_replay_runs(
                run_key, year, start_date, end_date, horizons_json,
                model_versions_json, lookback_days, asset_scope, status
            )
            VALUES (
                'shadow-test', 2026, '2026-01-01', '2026-03-31', '[20]',
                '["baseline_mean_v1","momentum_reversal_v1","risk_adjusted_factor_v1"]',
                60, 'all', 'success'
            )
            RETURNING id
            """
        ).fetchone()["id"]
        observations = [
            ("2026-01-05", "2026-01-25", 0.03, {"baseline_mean_v1": 0.01, "momentum_reversal_v1": 0.05, "risk_adjusted_factor_v1": 0.02}),
            ("2026-01-15", "2026-01-30", -0.02, {"baseline_mean_v1": 0.01, "momentum_reversal_v1": -0.03, "risk_adjusted_factor_v1": -0.01}),
            ("2026-02-05", "2026-02-25", 0.04, {"baseline_mean_v1": 0.01, "momentum_reversal_v1": 0.06, "risk_adjusted_factor_v1": 0.03}),
            ("2026-02-15", "2026-02-27", -0.01, {"baseline_mean_v1": 0.01, "momentum_reversal_v1": -0.02, "risk_adjusted_factor_v1": -0.03}),
            ("2026-03-05", "2026-03-25", 0.02, {"baseline_mean_v1": 0.01, "momentum_reversal_v1": 0.04, "risk_adjusted_factor_v1": 0.02}),
        ]
        for prediction_date, outcome_date, actual_return, predictions in observations:
            for model_version, expected_return in predictions.items():
                conn.execute(
                    """
                    INSERT INTO model_replay_predictions(
                        replay_run_id, asset_id, prediction_date, horizon_days,
                        model_version, target, up_probability, expected_return,
                        expected_return_low, expected_return_high, downside_risk,
                        confidence, input_window_start, input_window_end,
                        outcome_date, actual_return, benchmark_return,
                        benchmark_identity, benchmark_source, prediction_score,
                        risk_score, advice_score, overall_score, score_status,
                        skip_reason, details_json
                    )
                    VALUES (
                        ?, ?, ?, 20, ?, 'return', 0.55, ?,
                        ?, ?, -0.05, 0.82, '2025-12-01', ?,
                        ?, ?, 0.0, 'test', 'test', 70, 80, 75, 75,
                        'matured', NULL, ?
                    )
                    """,
                    (
                        run_id,
                        asset_id,
                        prediction_date,
                        model_version,
                        expected_return,
                        expected_return - 0.01,
                        expected_return + 0.01,
                        prediction_date,
                        outcome_date,
                        actual_return,
                        json.dumps({"asset_type": "stock", "same_category_key": "stock:test"}),
                    ),
                )
    return run_id


def test_replay_ytd_uses_point_in_time_inputs_and_separate_tables(tmp_path):
    db_path = tmp_path / "replay.sqlite3"
    seed_prices(db_path, [100, 101, 102, 103, 104, 105, 106, 107])

    result = replay_ytd_predictions(
        db_path,
        year=2026,
        start_date="20260103",
        end_date="20260106",
        horizons=(2,),
        model_versions=("baseline_mean_v1",),
        lookback_days=3,
    )

    with connect(db_path) as conn:
        operational = conn.execute("SELECT COUNT(*) AS count FROM model_predictions").fetchone()["count"]
        rows = conn.execute("SELECT * FROM model_replay_predictions ORDER BY prediction_date").fetchall()

    assert result["written"]["matured"] == 4
    assert operational == 0
    assert rows[0]["prediction_date"] == "2026-01-03"
    assert rows[0]["input_window_end"] == "2026-01-03"
    assert rows[0]["outcome_date"] == "2026-01-05"


def test_replay_report_scores_only_matured_rows_and_counts_pending(tmp_path):
    db_path = tmp_path / "replay_report.sqlite3"
    seed_prices(db_path, [100, 101, 102, 103, 104])

    replay = replay_ytd_predictions(
        db_path,
        year=2026,
        start_date="20260103",
        end_date="20260105",
        horizons=(2,),
        model_versions=("baseline_mean_v1",),
        lookback_days=3,
    )
    report = build_replay_report(db_path, run_id=replay["run_id"])

    assert report["coverage"]["matured"] == 1
    assert report["coverage"]["pending"] == 2
    key = "baseline_mean_v1|2"
    assert report["by_model_horizon"][key]["count"] == 1


def test_tuning_plan_has_evidence_backed_recommendations(tmp_path):
    db_path = tmp_path / "tuning.sqlite3"
    seed_prices(db_path, [100, 102, 101, 103, 99, 104, 98, 105, 97, 106])

    replay = replay_ytd_predictions(
        db_path,
        year=2026,
        start_date="20260103",
        end_date="20260108",
        horizons=(1,),
        model_versions=("baseline_mean_v1",),
        lookback_days=3,
    )
    plan = build_tuning_plan(db_path, run_id=replay["run_id"])

    assert plan["recommendations"]
    assert {"priority", "title", "verification_metric", "stop_condition"}.issubset(plan["recommendations"][0])
    with connect(db_path) as conn:
        row = conn.execute("SELECT tuning_recommendations_json FROM model_replay_runs WHERE id = ?", (replay["run_id"],)).fetchone()
    assert json.loads(row["tuning_recommendations_json"])


def test_model_health_metrics_use_only_matured_replay_rows(tmp_path):
    db_path = tmp_path / "health.sqlite3"
    seed_prices(db_path, [100, 101, 102, 103, 104])

    replay = replay_ytd_predictions(
        db_path,
        year=2026,
        start_date="20260103",
        end_date="20260105",
        horizons=(2,),
        model_versions=("baseline_mean_v1",),
        lookback_days=3,
    )
    result = generate_model_health_metrics(db_path, run_id=replay["run_id"])
    report = build_model_health_report(db_path, run_id=replay["run_id"])

    assert result["matured_rows"] == 1
    assert result["pending_rows"] == 2
    assert report["count"] >= 1
    monthly = report["by_scope"]["baseline_mean_v1|2|stock|all|2026-01|monthly"]
    assert monthly["sample_count"] == 1
    assert monthly["status"] == "insufficient_sample"
    assert monthly["minimum_sample_met"] is False
    assert monthly["degradation_reason"] == "insufficient_sample"


def test_model_health_generation_does_not_read_product_behavior_tables(tmp_path):
    db_path = tmp_path / "health_guard.sqlite3"
    seed_prices(db_path, [100, 102, 101, 103, 99, 104])
    replay = replay_ytd_predictions(
        db_path,
        year=2026,
        start_date="20260103",
        end_date="20260105",
        horizons=(1,),
        model_versions=("baseline_mean_v1",),
        lookback_days=3,
    )

    blocked_tables = {"expert_plans", "jarvis_daily_briefs", "daily_advice", "virtual_transactions", "outbound_messages"}

    def authorizer(action, arg1, arg2, db_name, trigger_name):
        if action == sqlite3.SQLITE_READ and arg1 in blocked_tables:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    with connect(db_path) as conn:
        conn.set_authorizer(authorizer)
        result = generate_model_health_metrics(conn, run_id=replay["run_id"])

    assert result["written"] >= 1


def test_applicability_profiles_disable_non_positive_same_type_ranking(tmp_path):
    db_path = tmp_path / "applicability_disable.sqlite3"
    seed_prices(db_path, [100, 102, 101, 103, 99, 104, 98, 105, 97, 106])
    replay = replay_ytd_predictions(
        db_path,
        year=2026,
        start_date="20260103",
        end_date="20260108",
        horizons=(1,),
        model_versions=("baseline_mean_v1",),
        lookback_days=3,
    )
    generate_model_health_metrics(db_path, run_id=replay["run_id"])
    with connect(db_path) as conn:
        metric = conn.execute(
            """
            SELECT id
            FROM model_health_metrics
            WHERE replay_run_id = ?
              AND same_category_key != 'all'
            LIMIT 1
            """,
            (replay["run_id"],),
        ).fetchone()
        conn.execute(
            """
            UPDATE model_health_metrics
            SET sample_count = 40,
                minimum_sample_met = 1,
                status = 'degraded',
                rank_ic = 0,
                bucket_spread = -0.01,
                degradation_reason = 'negative_bucket_spread'
            WHERE id = ?
            """,
            (metric["id"],),
        )

    result = generate_applicability_profiles(db_path, run_id=replay["run_id"])
    report = build_applicability_report(db_path, run_id=replay["run_id"])
    disabled = [
        row
        for row in report["by_scope"].values()
        if row["source_metric_id"] == metric["id"]
    ][0]

    assert result["written"] >= 1
    assert disabled["ranking_disabled"] is True
    assert disabled["output_role"] == "observation_only"
    assert "non_positive_same_type_rank_ic" in disabled["ranking_disable_reason"]
    assert "non_positive_same_type_bucket_spread" in disabled["ranking_disable_reason"]


def test_applicability_profiles_keep_baseline_roles_conservative(tmp_path):
    db_path = tmp_path / "applicability_roles.sqlite3"
    seed_prices(db_path, [100, 101, 102, 103, 104, 105, 106, 107])
    replay = replay_ytd_predictions(
        db_path,
        year=2026,
        start_date="20260103",
        end_date="20260106",
        horizons=(5, 20, 60),
        model_versions=("baseline_mean_v1", "momentum_reversal_v1"),
        lookback_days=3,
    )
    generate_model_health_metrics(db_path, run_id=replay["run_id"])
    with connect(db_path) as conn:
        fixtures = [
            ("baseline_mean_v1", 5, "all", "validated", 40, 0.2, 0.03),
            ("baseline_mean_v1", 20, "all", "validated", 40, 0.1, 0.01),
            ("baseline_mean_v1", 60, "all", "degraded", 40, -0.1, -0.01),
            ("momentum_reversal_v1", 5, "all", "validated", 40, 0.3, 0.04),
        ]
        for model_version, horizon, category, status, sample_count, rank_ic, bucket_spread in fixtures:
            conn.execute(
                """
                INSERT INTO model_health_metrics(
                    replay_run_id, model_version, horizon_days, asset_type,
                    same_category_key, prediction_month, evaluation_window,
                    sample_count, direction_accuracy, rank_ic, bucket_spread,
                    top_bottom_decile_spread, mae, median_abs_error,
                    raw_high_conf_wrong_rate, coverage_rate, status,
                    output_role, promotion_status, degradation_reason,
                    minimum_sample_met, consumer_display_level, metrics_json
                )
                VALUES (
                    ?, ?, ?, 'stock', ?, '2026-01', 'monthly',
                    ?, 0.55, ?, ?, 0.02, 0.01, 0.01, 0.05, 0.1, ?,
                    'observation_only', 'not_reviewed',
                    CASE WHEN ? = 'degraded' THEN 'negative_rank_ic' ELSE NULL END,
                    1, 'internal', '{}'
                )
                ON CONFLICT(
                    replay_run_id, model_version, horizon_days, asset_type,
                    same_category_key, prediction_month, evaluation_window
                ) DO UPDATE SET
                    sample_count = excluded.sample_count,
                    minimum_sample_met = excluded.minimum_sample_met,
                    status = excluded.status,
                    rank_ic = excluded.rank_ic,
                    bucket_spread = excluded.bucket_spread,
                    degradation_reason = excluded.degradation_reason
                """,
                (replay["run_id"], model_version, horizon, category, sample_count, rank_ic, bucket_spread, status, status),
            )

    generate_applicability_profiles(db_path, run_id=replay["run_id"])
    report = build_applicability_report(db_path, run_id=replay["run_id"])

    assert report["by_scope"]["baseline_mean_v1|5|stock|all|2026-01|monthly"]["output_role"] == "primary_forecast"
    assert report["by_scope"]["baseline_mean_v1|20|stock|all|2026-01|monthly"]["output_role"] == "allocation_bias"
    assert report["by_scope"]["baseline_mean_v1|60|stock|all|2026-01|monthly"]["output_role"] == "risk_reference"
    assert report["by_scope"]["momentum_reversal_v1|5|stock|all|2026-01|monthly"]["output_role"] == "observation_only"


def test_applicability_generation_does_not_touch_operational_predictions(tmp_path):
    db_path = tmp_path / "applicability_guard.sqlite3"
    seed_prices(db_path, [100, 101, 102, 103, 104, 105])
    replay = replay_ytd_predictions(
        db_path,
        year=2026,
        start_date="20260103",
        end_date="20260105",
        horizons=(1,),
        model_versions=("baseline_mean_v1",),
        lookback_days=3,
    )
    generate_model_health_metrics(db_path, run_id=replay["run_id"])

    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) AS count FROM model_predictions").fetchone()["count"]
        result = generate_applicability_profiles(conn, run_id=replay["run_id"])
        after = conn.execute("SELECT COUNT(*) AS count FROM model_predictions").fetchone()["count"]

    assert result["written"] >= 1
    assert before == after == 0


def test_shadow_router_is_shadow_only_and_does_not_touch_operational_predictions(tmp_path):
    db_path = tmp_path / "shadow_router.sqlite3"
    run_id = seed_shadow_replay(db_path)

    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) AS count FROM model_predictions").fetchone()["count"]
        result = run_shadow_router_floor70(conn, run_id=run_id)
        after = conn.execute("SELECT COUNT(*) AS count FROM model_predictions").fetchone()["count"]

    report = build_shadow_router_report(db_path, run_id=run_id)

    assert before == after == 0
    assert result["status"] == "shadow_only"
    assert report["count"] == 3
    assert set(report["monthly"]) == {"2026-01", "2026-02", "2026-03"}
    for month in report["monthly"].values():
        assert month["status"] == "shadow_only"
        assert month["weights"]["baseline_mean_v1"] >= 0.70
        assert month["realized_turnover"] <= 0.0500001
        assert month["comparison"]["operational_impact"] == "none_shadow_only"
        assert month["comparison"]["same_type_ranking_usage"] == "disabled"


def test_shadow_router_weights_use_only_prior_matured_outcomes(tmp_path):
    db_path = tmp_path / "shadow_router_point_in_time.sqlite3"
    run_id = seed_shadow_replay(db_path)

    run_shadow_router_floor70(db_path, run_id=run_id)
    report = build_shadow_router_report(db_path, run_id=run_id)

    january = report["monthly"]["2026-01"]
    february = report["monthly"]["2026-02"]
    march = report["monthly"]["2026-03"]
    assert january["training_cutoff"] == "2026-01-01"
    assert january["weights"] == {"baseline_mean_v1": 0.9, "momentum_reversal_v1": 0.05, "risk_adjusted_factor_v1": 0.05}
    assert february["training_cutoff"] == "2026-02-01"
    assert march["training_cutoff"] == "2026-03-01"


def test_router_same_type_ranking_stays_disabled_when_metrics_are_non_positive(tmp_path):
    db_path = tmp_path / "router_applicability.sqlite3"
    run_id = seed_shadow_replay(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO model_health_metrics(
                replay_run_id, model_version, horizon_days, asset_type,
                same_category_key, prediction_month, evaluation_window,
                sample_count, direction_accuracy, rank_ic, bucket_spread,
                top_bottom_decile_spread, mae, median_abs_error,
                raw_high_conf_wrong_rate, coverage_rate, status, output_role,
                promotion_status, degradation_reason, minimum_sample_met,
                consumer_display_level, metrics_json
            )
            VALUES (
                ?, 'router_floor70_cap05', 20, 'stock', 'stock:test',
                '2026-02', 'monthly', 40, 0.55, 0, -0.01, -0.02,
                0.03, 0.02, 0.2, 0.5, 'degraded',
                'observation_only', 'shadow_only', 'negative_bucket_spread',
                1, 'internal', '{}'
            )
            """,
            (run_id,),
        )

    generate_applicability_profiles(db_path, run_id=run_id)
    report = build_applicability_report(db_path, run_id=run_id)
    router = report["by_scope"]["router_floor70_cap05|20|stock|stock:test|2026-02|monthly"]

    assert router["output_role"] == "observation_only"
    assert router["ranking_disabled"] is True
    assert router["promotion_status"] == "shadow_only"


def test_confidence_labels_cover_insufficient_cautious_and_stable_cases(tmp_path):
    db_path = tmp_path / "confidence_labels.sqlite3"
    run_id = seed_shadow_replay(db_path)
    with connect(db_path) as conn:
        fixtures = [
            ("weak_model", 20, "stock", "all", "2026-01", "monthly", 5, 0.2, 0.01, 0.05, 0.05),
            ("watch_model", 20, "stock", "all", "2026-01", "monthly", 40, 0.2, 0.01, 0.05, 0.05),
            ("stable_model", 20, "stock", "all", "2026-01", "monthly", 40, 0.2, 0.01, 0.05, 0.05),
            ("stable_model", 20, "stock", "all", "2026-02", "monthly", 40, 0.2, 0.01, 0.05, 0.05),
            ("stable_model", 20, "stock", "all", "all", "all_history", 80, 0.2, 0.01, 0.05, 0.05),
        ]
        for model, horizon, asset_type, category, month, window, sample, rank_ic, bucket, high_wrong, calibration_error in fixtures:
            conn.execute(
                """
                INSERT INTO model_health_metrics(
                    replay_run_id, model_version, horizon_days, asset_type,
                    same_category_key, prediction_month, evaluation_window,
                    sample_count, direction_accuracy, rank_ic, bucket_spread,
                    top_bottom_decile_spread, mae, median_abs_error,
                    raw_high_conf_wrong_rate, coverage_rate, status, output_role,
                    promotion_status, degradation_reason, minimum_sample_met,
                    consumer_display_level, metrics_json
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, 0.55, ?, ?, 0.02, 0.01, 0.01,
                    ?, 0.5, 'validated', 'observation_only', 'not_reviewed',
                    NULL, CASE WHEN ? >= 20 THEN 1 ELSE 0 END, 'internal', ?
                )
                """,
                (
                    run_id,
                    model,
                    horizon,
                    asset_type,
                    category,
                    month,
                    window,
                    sample,
                    rank_ic,
                    bucket,
                    high_wrong,
                    sample,
                    json.dumps({"probability_calibration": [{"calibration_error": calibration_error}]}),
                ),
            )

    generate_applicability_profiles(db_path, run_id=run_id)
    result = generate_confidence_labels(db_path, run_id=run_id)
    report = build_confidence_label_report(db_path, run_id=run_id)

    assert result["written"] >= 5
    assert report["by_scope"]["weak_model|20|stock|all|2026-01|monthly"]["confidence_label"] == "暂不强调"
    assert report["by_scope"]["watch_model|20|stock|all|2026-01|monthly"]["confidence_label"] == "谨慎观察"
    assert report["by_scope"]["stable_model|20|stock|all|all|all_history"]["confidence_label"] == "相对稳健"


def test_confidence_labels_downgrade_overconfident_contexts(tmp_path):
    db_path = tmp_path / "confidence_overconfident.sqlite3"
    run_id = seed_shadow_replay(db_path)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO model_health_metrics(
                replay_run_id, model_version, horizon_days, asset_type,
                same_category_key, prediction_month, evaluation_window,
                sample_count, direction_accuracy, rank_ic, bucket_spread,
                top_bottom_decile_spread, mae, median_abs_error,
                raw_high_conf_wrong_rate, coverage_rate, status, output_role,
                promotion_status, degradation_reason, minimum_sample_met,
                consumer_display_level, metrics_json
            )
            VALUES (
                ?, 'overconfident_model', 20, 'stock', 'all', '2026-01',
                'monthly', 50, 0.55, 0.2, 0.02, 0.02, 0.01, 0.01,
                0.35, 0.5, 'validated', 'observation_only', 'not_reviewed',
                'high_confidence_wrong_rate', 1, 'internal', ?
            )
            """,
            (run_id, json.dumps({"probability_calibration": [{"calibration_error": 0.04}]})),
        )

    generate_applicability_profiles(db_path, run_id=run_id)
    generate_confidence_labels(db_path, run_id=run_id)
    report = build_confidence_label_report(db_path, run_id=run_id)
    row = report["by_scope"]["overconfident_model|20|stock|all|2026-01|monthly"]

    assert row["confidence_label"] == "暂不强调"
    assert row["confidence_rationale"]["reason"] == "high-confidence wrong rate is elevated"


def test_governance_summary_answers_four_questions_and_is_review_only(tmp_path):
    db_path = tmp_path / "governance.sqlite3"
    run_id = seed_shadow_replay(db_path)
    generate_model_health_metrics(db_path, run_id=run_id)
    generate_applicability_profiles(db_path, run_id=run_id)
    run_shadow_router_floor70(db_path, run_id=run_id)
    generate_confidence_labels(db_path, run_id=run_id)

    result = generate_model_governance_summary(db_path, run_id=run_id, review_month="2026-03")
    report = build_model_governance_report(db_path, run_id=run_id)

    assert result["status"] == "review_only"
    assert result["guardrails"]["production_defaults_changed"] is False
    assert result["guardrails"]["operational_model_predictions_updated"] is False
    assert {"safe_as_default", "continue_shadow_mode", "downgrade_or_disable", "promotion_review"}.issubset(result["questions"])
    assert result["questions"]["promotion_review"]["review_only"] is True
    assert "生产默认保持不变" in result["summary_text"]
    assert report["production_defaults_changed"] is False
    assert report["promotion_review_eligible"] is False


def test_governance_summary_does_not_touch_operational_predictions(tmp_path):
    db_path = tmp_path / "governance_guard.sqlite3"
    run_id = seed_shadow_replay(db_path)

    with connect(db_path) as conn:
        before = conn.execute("SELECT COUNT(*) AS count FROM model_predictions").fetchone()["count"]
        result = generate_model_governance_summary(conn, run_id=run_id, review_month="2026-03")
        after = conn.execute("SELECT COUNT(*) AS count FROM model_predictions").fetchone()["count"]

    assert before == after == 0
    assert result["guardrails"]["expert_jarvis_advice_phone_portfolio_impact"] == "none"


def test_full_governance_chain_does_not_read_product_behavior_tables(tmp_path):
    db_path = tmp_path / "governance_product_guard.sqlite3"
    run_id = seed_shadow_replay(db_path)
    blocked_tables = {
        "experts",
        "expert_plans",
        "expert_plan_items",
        "expert_scorecards",
        "expert_reviews",
        "expert_lessons",
        "jarvis_daily_briefs",
        "daily_advice",
        "communication_recipients",
        "outbound_messages",
        "virtual_portfolios",
        "virtual_positions",
        "virtual_transactions",
        "virtual_cash_ledger",
        "virtual_valuations",
    }

    def authorizer(action, arg1, arg2, db_name, trigger_name):
        if action == sqlite3.SQLITE_READ and arg1 in blocked_tables:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    with connect(db_path) as conn:
        conn.set_authorizer(authorizer)
        result = generate_model_governance_summary(conn, run_id=run_id, review_month="2026-03")

    assert result["status"] == "review_only"
    assert result["guardrails"]["expert_jarvis_advice_phone_portfolio_impact"] == "none"
