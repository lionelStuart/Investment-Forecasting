from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from investment_forecasting.db import complete_task_log, connect, init_db, list_experts, start_task_log, upsert_expert
from investment_forecasting.portfolio.accounting import DEFAULT_EXPERT_INITIAL_CAPITAL, create_virtual_portfolio


DEFAULT_SCORE_WINDOW_DAYS = 20
DEFAULT_MIN_VALUATIONS = 3


class ExpertScoringError(RuntimeError):
    pass


def score_and_review_experts(
    db_path: str | Path,
    review_date: str | None = None,
    *,
    window_days: int = DEFAULT_SCORE_WINDOW_DAYS,
    min_valuations: int = DEFAULT_MIN_VALUATIONS,
) -> dict[str, Any]:
    init_db(db_path)
    target_date = _date_text(review_date)
    with connect(db_path) as conn:
        log_id = start_task_log(conn, "expert_scoring_review", target_date, "Scoring expert committee")
        try:
            reviewed = []
            for expert in list_experts(conn):
                if expert["lifecycle_state"] == "retired":
                    continue
                portfolio = _expert_portfolio(conn, expert["id"])
                scorecard = build_expert_scorecard(conn, expert, portfolio, target_date, window_days, min_valuations)
                scorecard_id = _upsert_scorecard(conn, scorecard)
                review = _review_expert(conn, expert, scorecard | {"id": scorecard_id}, target_date)
                reviewed.append({**scorecard, "id": scorecard_id, "review": review})
            replacements = _hire_replacements_if_needed(conn, target_date)
            complete_task_log(conn, log_id, "success", f"Reviewed {len(reviewed)} experts; replacements={len(replacements)}")
        except Exception as exc:
            complete_task_log(conn, log_id, "failed", error=str(exc))
            conn.commit()
            raise
    return {"review_date": target_date, "reviewed": reviewed, "replacements": replacements}


def build_expert_scorecard(
    conn,
    expert,
    portfolio,
    score_date: str,
    window_days: int,
    min_valuations: int,
) -> dict[str, Any]:
    valuations = _window_valuations(conn, portfolio["id"], score_date, window_days)
    plans = _window_plans(conn, expert["id"], score_date, window_days)
    details: dict[str, Any] = {"valuation_dates": [row["valuation_date"] for row in valuations]}
    valuation_count = len(valuations)
    mature_enough = valuation_count >= min_valuations
    if valuation_count < 2:
        metrics = _empty_metrics()
    else:
        values = [float(row["total_value"]) for row in valuations]
        returns = [(values[index] / values[index - 1]) - 1.0 for index in range(1, len(values)) if values[index - 1]]
        portfolio_return = (values[-1] / values[0]) - 1.0 if values[0] else 0.0
        benchmark_return = _benchmark_return(conn, valuations[0]["valuation_date"], valuations[-1]["valuation_date"])
        max_drawdown = _max_drawdown(values)
        volatility = stdev(returns) if len(returns) >= 2 else 0.0
        cash_drag = mean(
            float(row["cash"]) / float(row["total_value"])
            for row in valuations
            if float(row["total_value"]) > 0
        )
        turnover = _turnover(conn, portfolio["id"], valuations[0]["valuation_date"], valuations[-1]["valuation_date"], mean(values))
        win_rate = sum(1 for value in returns if value > 0) / len(returns) if returns else 0.0
        evidence_completeness = _evidence_completeness(plans)
        mandate_adherence = _mandate_adherence(expert, max_drawdown, cash_drag)
        metrics = {
            "portfolio_return": portfolio_return,
            "benchmark_return": benchmark_return,
            "benchmark_excess": portfolio_return - benchmark_return if benchmark_return is not None else 0.0,
            "max_drawdown": max_drawdown,
            "volatility": volatility,
            "cash_drag": cash_drag,
            "turnover": turnover,
            "win_rate": win_rate,
            "evidence_completeness": evidence_completeness,
            "mandate_adherence": mandate_adherence,
        }
    overall_score = _overall_score(metrics, mature_enough)
    return {
        "expert_id": expert["id"],
        "portfolio_id": portfolio["id"],
        "score_date": score_date,
        "window_days": window_days,
        "valuation_count": valuation_count,
        "mature_enough": 1 if mature_enough else 0,
        **metrics,
        "overall_score": overall_score,
        "details_json": json.dumps(details | {"mature_enough": mature_enough}, ensure_ascii=False),
    }


def _review_expert(conn, expert, scorecard: dict[str, Any], review_date: str) -> dict[str, Any]:
    decision = _review_decision(conn, expert, scorecard)
    previous = expert["lifecycle_state"]
    new_state = _new_lifecycle_state(previous, decision)
    rationale = _review_rationale(expert, scorecard, decision)
    if new_state != previous:
        conn.execute(
            "UPDATE experts SET lifecycle_state = ?, updated_at = datetime('now') WHERE id = ?",
            (new_state, expert["id"]),
        )
    review_id = _insert_review(
        conn,
        expert_id=expert["id"],
        scorecard_id=scorecard["id"],
        review_date=review_date,
        decision=decision,
        previous_state=previous,
        new_state=new_state,
        rationale=rationale,
        evidence={"scorecard_id": scorecard["id"], "overall_score": scorecard["overall_score"]},
    )
    if decision == "retire":
        _insert_failure_lesson(conn, expert, review_id, review_date, scorecard)
    return {
        "id": review_id,
        "expert_id": expert["id"],
        "decision": decision,
        "previous_lifecycle_state": previous,
        "new_lifecycle_state": new_state,
        "rationale": rationale,
    }


def _review_decision(conn, expert, scorecard: dict[str, Any]) -> str:
    if not scorecard["mature_enough"]:
        return "keep"
    score = float(scorecard["overall_score"] or 0.0)
    if score >= 65:
        return "keep"
    latest_bad = conn.execute(
        """
        SELECT decision, new_lifecycle_state
        FROM expert_reviews
        WHERE expert_id = ? AND decision IN ('warn', 'probation')
        ORDER BY review_date DESC, id DESC
        LIMIT 1
        """,
        (expert["id"],),
    ).fetchone()
    if expert["lifecycle_state"] == "probation" and latest_bad is not None:
        return "retire"
    if latest_bad is not None and latest_bad["decision"] == "warn":
        return "probation"
    return "warn"


def _new_lifecycle_state(previous: str, decision: str) -> str:
    if decision == "probation":
        return "probation"
    if decision == "retire":
        return "retired"
    return previous


def _hire_replacements_if_needed(conn, review_date: str) -> list[dict[str, Any]]:
    replacements = []
    active_count = conn.execute("SELECT COUNT(*) AS count FROM experts WHERE lifecycle_state = 'active'").fetchone()["count"]
    while active_count < 3:
        replacement = _replacement_candidate(conn, review_date, active_count)
        expert_id = upsert_expert(conn, replacement)
        create_virtual_portfolio(
            conn,
            owner_type="expert",
            owner_id=expert_id,
            name=f"{replacement['name']}虚拟组合",
            initial_capital=DEFAULT_EXPERT_INITIAL_CAPITAL,
        )
        review_id = _insert_review(
            conn,
            expert_id=expert_id,
            scorecard_id=None,
            review_date=review_date,
            decision="hire_replacement",
            previous_state="candidate",
            new_state="active",
            rationale="Active expert count fell below three; hired a style-diverse replacement from recorded lessons.",
            evidence={"active_count_before": active_count},
        )
        _insert_hiring_lesson(conn, expert_id, review_id, review_date)
        replacements.append({"id": expert_id, **replacement})
        active_count += 1
    return replacements


def _replacement_candidate(conn, review_date: str, active_count: int) -> dict[str, Any]:
    active_styles = {
        row["style_label"]
        for row in conn.execute("SELECT style_label FROM experts WHERE lifecycle_state = 'active'").fetchall()
    }
    retired_patterns = [
        row["avoid_hiring_patterns"]
        for row in conn.execute("SELECT avoid_hiring_patterns FROM expert_lessons WHERE lesson_type = 'failure'").fetchall()
    ]
    templates = [
        {
            "suffix": "quality_value",
            "name": "质量价值替补专家",
            "short_description": "偏重质量、估值安全边际和回撤纪律，避免单纯追涨。",
            "style_label": "质量价值 / 安全边际",
            "focus_weights": {"max_drawdown": 0.2, "sharpe": 0.2, "confidence": 0.2, "fund_metadata_quality": 0.2, "expected_return": 0.2},
            "risk_budget_pct": 0.45,
            "max_drawdown_tolerance": 0.1,
            "allowed_asset_categories": ["index", "etf", "fund", "stock"],
            "default_cash_buffer_pct": 0.25,
            "review_cadence_days": 20,
            "mandate": "优先证据质量和安全边际，避免复制已清退专家的过度集中或忽视回撤模式。",
        },
        {
            "suffix": "macro_defense",
            "name": "宏观防御替补专家",
            "short_description": "偏重市场环境、现金纪律和跨类别防御配置。",
            "style_label": "宏观防御 / 现金纪律",
            "focus_weights": {"market_snapshot_risk": 0.3, "cash_buffer": 0.2, "max_drawdown": 0.2, "volatility": 0.15, "confidence": 0.15},
            "risk_budget_pct": 0.35,
            "max_drawdown_tolerance": 0.08,
            "allowed_asset_categories": ["index", "etf", "fund"],
            "default_cash_buffer_pct": 0.35,
            "review_cadence_days": 20,
            "mandate": "在宏观风险升高时优先保护虚拟组合，不因短期落后而提高风险暴露。",
        },
    ]
    selected = next((template for template in templates if template["style_label"] not in active_styles), templates[0])
    avoid_note = "；".join(retired_patterns[-3:]) if retired_patterns else "避免复制已失败专家的单一风格。"
    key_date = review_date.replace("-", "")
    return {
        "expert_key": f"replacement_{selected['suffix']}_{key_date}_{active_count + 1}",
        "name": selected["name"],
        "short_description": selected["short_description"],
        "style_label": selected["style_label"],
        "focus_weights_json": json.dumps(selected["focus_weights"], ensure_ascii=False, sort_keys=True),
        "risk_budget_pct": selected["risk_budget_pct"],
        "max_drawdown_tolerance": selected["max_drawdown_tolerance"],
        "allowed_asset_categories_json": json.dumps(selected["allowed_asset_categories"], ensure_ascii=False),
        "default_cash_buffer_pct": selected["default_cash_buffer_pct"],
        "review_cadence_days": selected["review_cadence_days"],
        "lifecycle_state": "active",
        "mandate": f"{selected['mandate']} 历史 lessons: {avoid_note}",
        "source": "expert_hiring_v1",
    }


def _upsert_scorecard(conn, scorecard: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO expert_scorecards(
            expert_id, portfolio_id, score_date, window_days, valuation_count,
            mature_enough, portfolio_return, benchmark_return, benchmark_excess,
            max_drawdown, volatility, cash_drag, turnover, win_rate,
            evidence_completeness, mandate_adherence, overall_score, details_json
        )
        VALUES (
            :expert_id, :portfolio_id, :score_date, :window_days, :valuation_count,
            :mature_enough, :portfolio_return, :benchmark_return, :benchmark_excess,
            :max_drawdown, :volatility, :cash_drag, :turnover, :win_rate,
            :evidence_completeness, :mandate_adherence, :overall_score, :details_json
        )
        ON CONFLICT(expert_id, score_date, window_days) DO UPDATE SET
            portfolio_id = excluded.portfolio_id,
            valuation_count = excluded.valuation_count,
            mature_enough = excluded.mature_enough,
            portfolio_return = excluded.portfolio_return,
            benchmark_return = excluded.benchmark_return,
            benchmark_excess = excluded.benchmark_excess,
            max_drawdown = excluded.max_drawdown,
            volatility = excluded.volatility,
            cash_drag = excluded.cash_drag,
            turnover = excluded.turnover,
            win_rate = excluded.win_rate,
            evidence_completeness = excluded.evidence_completeness,
            mandate_adherence = excluded.mandate_adherence,
            overall_score = excluded.overall_score,
            details_json = excluded.details_json,
            updated_at = datetime('now')
        RETURNING id
        """,
        scorecard,
    )
    return int(cursor.fetchone()["id"])


def _insert_review(
    conn,
    *,
    expert_id: int,
    scorecard_id: int | None,
    review_date: str,
    decision: str,
    previous_state: str | None,
    new_state: str | None,
    rationale: str,
    evidence: dict[str, Any],
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO expert_reviews(
            expert_id, scorecard_id, review_date, decision,
            previous_lifecycle_state, new_lifecycle_state, rationale, evidence_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (expert_id, scorecard_id, review_date, decision, previous_state, new_state, rationale, json.dumps(evidence, ensure_ascii=False)),
    )
    return int(cursor.fetchone()["id"])


def _insert_failure_lesson(conn, expert, review_id: int, review_date: str, scorecard: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO expert_lessons(
            expert_id, review_id, lesson_date, lesson_type, summary,
            overweighted_signals, ignored_signals, failed_controls, avoid_hiring_patterns
        )
        VALUES (?, ?, ?, 'failure', ?, ?, ?, ?, ?)
        """,
        (
            expert["id"],
            review_id,
            review_date,
            f"{expert['name']}在成熟评估窗口中得分{scorecard['overall_score']:.1f}，进入清退复盘。",
            expert["style_label"],
            "benchmark excess, drawdown tolerance, mandate adherence",
            f"max_drawdown={scorecard['max_drawdown']}, mandate_adherence={scorecard['mandate_adherence']}",
            f"避免招聘复制{expert['style_label']}且忽略回撤/基准劣后的专家。",
        ),
    )


def _insert_hiring_lesson(conn, expert_id: int, review_id: int, review_date: str) -> None:
    conn.execute(
        """
        INSERT INTO expert_lessons(
            expert_id, review_id, lesson_date, lesson_type, summary,
            overweighted_signals, ignored_signals, failed_controls, avoid_hiring_patterns
        )
        VALUES (?, ?, ?, 'hiring', ?, ?, ?, ?, ?)
        """,
        (
            expert_id,
            review_id,
            review_date,
            "补位专家根据风格缺口和历史失败 lessons 生成，用于保持三位 active 专家并行。",
            "diversity, risk discipline",
            "none",
            "none",
            "不要复制刚清退专家的失败风格。",
        ),
    )


def _window_valuations(conn, portfolio_id: int, score_date: str, window_days: int):
    return conn.execute(
        """
        SELECT *
        FROM virtual_valuations
        WHERE portfolio_id = ?
          AND valuation_date <= ?
          AND valuation_date >= date(?, ?)
        ORDER BY valuation_date
        """,
        (portfolio_id, score_date, score_date, f"-{window_days} day"),
    ).fetchall()


def _window_plans(conn, expert_id: int, score_date: str, window_days: int):
    return conn.execute(
        """
        SELECT *
        FROM expert_plans
        WHERE expert_id = ?
          AND plan_date <= ?
          AND plan_date >= date(?, ?)
        ORDER BY plan_date
        """,
        (expert_id, score_date, score_date, f"-{window_days} day"),
    ).fetchall()


def _benchmark_return(conn, start_date: str, end_date: str) -> float | None:
    rows = conn.execute(
        """
        SELECT pd.trade_date, COALESCE(pd.close, pd.nav, pd.adjusted_close) AS price_value
        FROM price_daily pd
        JOIN assets a ON a.id = pd.asset_id
        WHERE a.code = '000300'
          AND pd.trade_date IN (
            SELECT MAX(trade_date) FROM price_daily WHERE asset_id = a.id AND trade_date <= ?
            UNION
            SELECT MAX(trade_date) FROM price_daily WHERE asset_id = a.id AND trade_date <= ?
          )
          AND COALESCE(pd.close, pd.nav, pd.adjusted_close) IS NOT NULL
        ORDER BY pd.trade_date
        """,
        (start_date, end_date),
    ).fetchall()
    if len(rows) < 2 or not rows[0]["price_value"]:
        return None
    return (float(rows[-1]["price_value"]) / float(rows[0]["price_value"])) - 1.0


def _turnover(conn, portfolio_id: int, start_date: str, end_date: str, average_value: float) -> float:
    if average_value <= 0:
        return 0.0
    total = conn.execute(
        """
        SELECT SUM(ABS(cash_delta)) AS value
        FROM virtual_transactions
        WHERE portfolio_id = ?
          AND status = 'filled'
          AND trade_date >= ?
          AND trade_date <= ?
        """,
        (portfolio_id, start_date, end_date),
    ).fetchone()["value"]
    return float(total or 0.0) / average_value


def _evidence_completeness(plans) -> float:
    if not plans:
        return 0.0
    complete = 0
    for plan in plans:
        evidence = json.loads(plan["evidence_json"])
        if evidence.get("prediction_id") and evidence.get("asset"):
            complete += 1
    return complete / len(plans)


def _mandate_adherence(expert, max_drawdown: float | None, cash_drag: float | None) -> float:
    if max_drawdown is None:
        return 0.0
    tolerance = float(expert["max_drawdown_tolerance"])
    drawdown_score = max(0.0, 1.0 - max(0.0, abs(max_drawdown) - tolerance) / max(tolerance, 0.01))
    cash_buffer = float(expert["default_cash_buffer_pct"])
    cash_score = 1.0 if cash_drag is None or cash_drag >= cash_buffer * 0.5 else 0.75
    return min(1.0, (drawdown_score * 0.75) + (cash_score * 0.25))


def _overall_score(metrics: dict[str, Any], mature_enough: bool) -> float:
    if not mature_enough:
        return 50.0
    portfolio = float(metrics["portfolio_return"] or 0.0)
    excess = float(metrics["benchmark_excess"] or 0.0)
    drawdown = abs(float(metrics["max_drawdown"] or 0.0))
    volatility = float(metrics["volatility"] or 0.0)
    evidence = float(metrics["evidence_completeness"] or 0.0)
    mandate = float(metrics["mandate_adherence"] or 0.0)
    win_rate = float(metrics["win_rate"] or 0.0)
    score = (
        50.0
        + portfolio * 180.0
        + excess * 120.0
        - drawdown * 140.0
        - volatility * 80.0
        + evidence * 10.0
        + mandate * 20.0
        + (win_rate - 0.5) * 10.0
    )
    return round(max(0.0, min(100.0, score)), 2)


def _max_drawdown(values: list[float]) -> float:
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            worst = min(worst, (value / peak) - 1.0)
    return worst


def _empty_metrics() -> dict[str, Any]:
    return {
        "portfolio_return": None,
        "benchmark_return": None,
        "benchmark_excess": None,
        "max_drawdown": None,
        "volatility": None,
        "cash_drag": None,
        "turnover": None,
        "win_rate": None,
        "evidence_completeness": 0.0,
        "mandate_adherence": 0.0,
    }


def _review_rationale(expert, scorecard: dict[str, Any], decision: str) -> str:
    if not scorecard["mature_enough"]:
        return f"{expert['name']}评估样本不足，暂不做生命周期处罚。"
    return (
        f"{expert['name']}滚动得分{scorecard['overall_score']:.1f}，"
        f"组合收益{scorecard['portfolio_return']:.2%}，"
        f"最大回撤{scorecard['max_drawdown']:.2%}，决策为{decision}。"
    )


def _expert_portfolio(conn, expert_id: int):
    row = conn.execute(
        "SELECT * FROM virtual_portfolios WHERE owner_type = 'expert' AND owner_id = ?",
        (expert_id,),
    ).fetchone()
    if row is None:
        raise ExpertScoringError(f"Missing virtual portfolio for expert_id={expert_id}")
    return row


def _date_text(value: str | None) -> str:
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value or date.today().isoformat()
