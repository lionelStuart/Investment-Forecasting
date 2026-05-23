from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from investment_forecasting.db import connect, init_db, upsert_advice_outcome_score


class AdviceScoringError(RuntimeError):
    """Raised when advice outcomes cannot be scored without future leakage."""


def score_matured_advice(db_path: str | Path, horizon_days: int = 20) -> dict[int, int]:
    init_db(db_path)
    scored: dict[int, int] = {}
    with connect(db_path) as conn:
        advice_rows = conn.execute("SELECT * FROM daily_advice ORDER BY advice_date").fetchall()
        for advice in advice_rows:
            score = _score_one_advice(conn, advice, horizon_days)
            if score is None:
                continue
            score_id = upsert_advice_outcome_score(conn, score)
            scored[int(advice["id"])] = score_id
    return scored


def _score_one_advice(conn: Any, advice: Any, horizon_days: int) -> dict[str, Any] | None:
    asset_returns = []
    outcome_date = None
    for asset in conn.execute("SELECT id, code, asset_type FROM assets ORDER BY id").fetchall():
        prices = conn.execute(
            """
            SELECT trade_date, COALESCE(adjusted_close, close, nav) AS value
            FROM price_daily
            WHERE asset_id = ? AND trade_date >= ? AND COALESCE(adjusted_close, close, nav) IS NOT NULL
            ORDER BY trade_date
            LIMIT ?
            """,
            (asset["id"], advice["advice_date"], horizon_days + 1),
        ).fetchall()
        if len(prices) <= horizon_days:
            continue
        start = float(prices[0]["value"])
        end = float(prices[horizon_days]["value"])
        asset_returns.append((end / start) - 1.0)
        outcome_date = prices[horizon_days]["trade_date"]

    if not asset_returns or outcome_date is None:
        return None

    benchmark_return = _benchmark_return(conn, advice["advice_date"], outcome_date)
    portfolio_return = mean(asset_returns)
    benchmark_excess = portfolio_return - benchmark_return if benchmark_return is not None else 0.0
    drawdown_control = 1.0 if portfolio_return >= -0.05 else 0.0
    prediction_score = max(0.0, min(100.0, 50.0 + portfolio_return * 1000.0))
    risk_score = 100.0 if drawdown_control else max(0.0, 100.0 + portfolio_return * 1000.0)
    advice_score = max(0.0, min(100.0, 50.0 + benchmark_excess * 1000.0))
    overall_score = (prediction_score + risk_score + advice_score) / 3.0
    return {
        "advice_id": int(advice["id"]),
        "horizon_days": horizon_days,
        "outcome_date": outcome_date,
        "portfolio_return": portfolio_return,
        "benchmark_return": benchmark_return,
        "benchmark_excess": benchmark_excess,
        "drawdown_control": drawdown_control,
        "prediction_score": prediction_score,
        "risk_score": risk_score,
        "advice_score": advice_score,
        "overall_score": overall_score,
        "details_json": json.dumps(
            {
                "method": "equal_weight_tracked_assets",
                "no_future_leakage": "Only advice_date and the next horizon_days stored observations are used.",
            },
            ensure_ascii=False,
        ),
    }


def _benchmark_return(conn: Any, start_date: str, end_date: str) -> float | None:
    row = conn.execute("SELECT id FROM assets WHERE code = '000300' AND asset_type = 'index' ORDER BY id LIMIT 1").fetchone()
    if row is None:
        return None
    prices = conn.execute(
        """
        SELECT trade_date, COALESCE(adjusted_close, close, nav) AS value
        FROM price_daily
        WHERE asset_id = ? AND trade_date IN (?, ?)
        """,
        (row["id"], start_date, end_date),
    ).fetchall()
    by_date = {price["trade_date"]: float(price["value"]) for price in prices}
    if start_date not in by_date or end_date not in by_date:
        return None
    return (by_date[end_date] / by_date[start_date]) - 1.0

