from __future__ import annotations

from investment_forecasting.advice.generator import generate_daily_advice
from investment_forecasting.advice.scoring import score_matured_advice
from investment_forecasting.db import connect, init_db, upsert_asset, upsert_price_daily
from investment_forecasting.quant.backtest import run_backtest, run_latest_forecasts
from investment_forecasting.quant.features import calculate_features_for_db


def seed_asset(conn, code: str, asset_type: str, values: list[float]) -> int:
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


def test_score_matured_advice_updates_daily_advice_and_score_table(tmp_path):
    db_path = tmp_path / "advice_score.sqlite3"
    init_db(db_path)
    with connect(db_path) as conn:
        seed_asset(conn, "000300", "index", [100, 101, 102, 103, 104, 105, 106])
        seed_asset(conn, "TEST", "stock", [100, 102, 104, 106, 108, 110, 112])
    calculate_features_for_db(db_path)
    run_latest_forecasts(db_path, horizons=(2,))
    run_backtest(db_path, horizons=(2,), lookback_days=3)
    advice_id = generate_daily_advice(db_path, advice_date="20260101")

    scored = score_matured_advice(db_path, horizon_days=2)

    with connect(db_path) as conn:
        score = conn.execute("SELECT * FROM advice_outcome_scores WHERE advice_id = ?", (advice_id,)).fetchone()
        advice = conn.execute("SELECT overall_score FROM daily_advice WHERE id = ?", (advice_id,)).fetchone()

    assert scored[advice_id] == score["id"]
    assert score["outcome_date"] == "2026-01-03"
    assert score["benchmark_return"] is not None
    assert score["benchmark_excess"] is not None
    assert advice["overall_score"] == score["overall_score"]

