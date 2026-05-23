from __future__ import annotations

import json

from investment_forecasting.db import connect, get_expert, init_db, upsert_asset, upsert_price_daily
from investment_forecasting.experts.roster import initialize_default_experts
from investment_forecasting.experts.scoring import score_and_review_experts
from investment_forecasting.portfolio.accounting import ensure_expert_portfolios


def test_scorecards_are_reproducible_from_persisted_portfolio_records(tmp_path):
    db_path = seed_scoring_db(tmp_path, declining=False)

    first = score_and_review_experts(db_path, review_date="2026-05-23", min_valuations=3)
    second = score_and_review_experts(db_path, review_date="2026-05-23", min_valuations=3)

    with connect(db_path) as conn:
        scorecards = conn.execute("SELECT * FROM expert_scorecards").fetchall()
        reviews = conn.execute("SELECT * FROM expert_reviews").fetchall()

    assert len(first["reviewed"]) == 3
    assert len(second["reviewed"]) == 3
    assert len(scorecards) == 3
    assert len(reviews) == 6
    assert all(row["mature_enough"] == 1 for row in scorecards)
    assert all(row["overall_score"] is not None for row in scorecards)
    assert all(json.loads(row["details_json"])["valuation_dates"] for row in scorecards)


def test_bad_expert_warns_then_probation_then_retirement_and_replacement(tmp_path):
    db_path = seed_scoring_db(tmp_path, declining=True)

    first = score_and_review_experts(db_path, review_date="2026-05-23", min_valuations=3)
    second = score_and_review_experts(db_path, review_date="2026-05-24", min_valuations=3)
    third = score_and_review_experts(db_path, review_date="2026-05-25", min_valuations=3)

    with connect(db_path) as conn:
        active_count = conn.execute("SELECT COUNT(*) AS count FROM experts WHERE lifecycle_state = 'active'").fetchone()["count"]
        retired = conn.execute("SELECT * FROM experts WHERE lifecycle_state = 'retired'").fetchall()
        lessons = conn.execute("SELECT * FROM expert_lessons ORDER BY id").fetchall()
        replacement = conn.execute("SELECT * FROM experts WHERE source = 'expert_hiring_v1'").fetchone()

    assert any(item["review"]["decision"] == "warn" for item in first["reviewed"])
    assert any(item["review"]["decision"] == "probation" for item in second["reviewed"])
    assert any(item["review"]["decision"] == "retire" for item in third["reviewed"])
    assert active_count == 3
    assert retired
    assert any(row["lesson_type"] == "failure" for row in lessons)
    assert any("避免招聘复制" in row["avoid_hiring_patterns"] for row in lessons)
    assert replacement is not None
    assert replacement["style_label"] not in {row["style_label"] for row in retired}


def test_insufficient_maturity_keeps_expert_without_punishment(tmp_path):
    db_path = seed_scoring_db(tmp_path, declining=True, valuation_days=1)

    result = score_and_review_experts(db_path, review_date="2026-05-23", min_valuations=3)

    with connect(db_path) as conn:
        states = {row["lifecycle_state"] for row in conn.execute("SELECT lifecycle_state FROM experts").fetchall()}
        scorecards = conn.execute("SELECT * FROM expert_scorecards").fetchall()

    assert {item["review"]["decision"] for item in result["reviewed"]} == {"keep"}
    assert states == {"active"}
    assert all(row["mature_enough"] == 0 for row in scorecards)


def seed_scoring_db(tmp_path, *, declining: bool, valuation_days: int = 4):
    db_path = init_db(tmp_path / "expert-scoring.sqlite3")
    initialize_default_experts(db_path)
    ensure_expert_portfolios(db_path)
    with connect(db_path) as conn:
        benchmark_id = upsert_asset(
            conn,
            {
                "code": "000300",
                "name": "沪深300",
                "asset_type": "index",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "test",
            },
        )
        for index, close in enumerate([100, 101, 102, 103, 104], start=21):
            upsert_price_daily(
                conn,
                benchmark_id,
                "test",
                {
                    "trade_date": f"2026-05-{index:02d}",
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": None,
                    "amount": None,
                    "pct_change": None,
                    "adjusted_close": None,
                    "nav": None,
                    "accumulated_nav": None,
                    "raw_payload": "{}",
                },
            )
        experts = conn.execute("SELECT * FROM experts ORDER BY expert_key").fetchall()
        for expert_index, expert in enumerate(experts):
            portfolio = conn.execute(
                "SELECT * FROM virtual_portfolios WHERE owner_type = 'expert' AND owner_id = ?",
                (expert["id"],),
            ).fetchone()
            base = float(portfolio["initial_capital"])
            for day_offset in range(valuation_days):
                day = 21 + day_offset
                if declining and expert_index == 0:
                    total_value = base * (1.0 - (day_offset * 0.1))
                    cash = total_value * 0.02
                else:
                    total_value = base * (1.0 + (day_offset * 0.01))
                    cash = total_value * 0.35
                conn.execute(
                    """
                    INSERT INTO virtual_valuations(
                        portfolio_id, valuation_date, cash, positions_value, total_value,
                        missing_prices_json, details_json
                    )
                    VALUES (?, ?, ?, ?, ?, '[]', '{}')
                    """,
                    (portfolio["id"], f"2026-05-{day:02d}", cash, total_value - cash, total_value),
                )
                conn.execute(
                    """
                    INSERT INTO expert_plans(
                        expert_id, portfolio_id, plan_date, action, target_asset_id,
                        target_weight, target_amount, rationale, evidence_json,
                        risk_checks_json, risk_warnings, execution_status
                    )
                    VALUES (?, ?, ?, 'buy', NULL, 0.1, 1000, '测试计划', ?, '{}', '仅用于虚拟研究。', 'filled')
                    """,
                    (
                        expert["id"],
                        portfolio["id"],
                        f"2026-05-{day:02d}",
                        json.dumps({"prediction_id": 1, "asset": {"id": 1}}, ensure_ascii=False),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO virtual_transactions(
                        portfolio_id, trade_date, side, quantity, gross_amount,
                        fee, cash_delta, status, reason
                    )
                    VALUES (?, ?, 'buy', 1, 1000, 0, -1000, 'filled', '测试交易')
                    """,
                    (portfolio["id"], f"2026-05-{day:02d}"),
                )
    return db_path
