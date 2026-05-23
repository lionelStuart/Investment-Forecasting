from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

from investment_forecasting.db import connect, init_db, upsert_market_snapshot


MARKET_SNAPSHOT_SOURCE = "market_snapshot_v1"


class MarketSnapshotError(RuntimeError):
    """Raised when market environment cannot be calculated from stored data."""


def calculate_market_snapshot(db_path: str | Path, snapshot_date: str | None = None) -> dict[str, Any]:
    init_db(db_path)
    target_date = _date_text(snapshot_date)
    with connect(db_path) as conn:
        latest_feature_date = conn.execute("SELECT MAX(feature_date) AS value FROM features_daily").fetchone()["value"]
        if latest_feature_date is None:
            raise MarketSnapshotError("Cannot calculate market snapshot without features_daily rows")
        target_date = target_date or latest_feature_date

        features = conn.execute(
            """
            SELECT a.code, a.name, a.asset_type, f.feature_date, f.return_20d,
                   f.max_drawdown_60d, f.market_state
            FROM features_daily f
            JOIN assets a ON a.id = f.asset_id
            WHERE f.feature_date = (
                SELECT MAX(feature_date) FROM features_daily WHERE asset_id = a.id AND feature_date <= ?
            )
            """,
            (target_date,),
        ).fetchall()
        if not features:
            raise MarketSnapshotError(f"No feature rows available on or before {target_date}")

        index_returns = [row["return_20d"] for row in features if row["asset_type"] == "index" and row["return_20d"] is not None]
        asset_returns = [row["return_20d"] for row in features if row["return_20d"] is not None]
        index_trend = mean(index_returns) if index_returns else None
        breadth = sum(1 for value in asset_returns if value > 0) / len(asset_returns) if asset_returns else None
        liquidity_heat = _liquidity_heat(conn, target_date)
        stock_bond_proxy = _stock_bond_proxy(features)
        macro = _latest_macro_observations(conn, target_date)
        sentiment = _sentiment(index_trend, breadth, liquidity_heat, stock_bond_proxy)
        details = {
            "feature_date": latest_feature_date,
            "assets": [dict(row) for row in features],
            "macro": macro,
            "components": {
                "index_trend": "Average 20-day return across tracked indices.",
                "breadth": "Share of tracked assets with positive 20-day return.",
                "liquidity_heat": "Latest turnover amount versus recent average where amount is available.",
                "stock_bond_proxy": "沪深300 20-day return minus 国债ETF 20-day return when both exist.",
                "macro": "Latest stored FRED observations on or before the snapshot date, when available.",
            },
        }
        snapshot = {
            "snapshot_date": target_date,
            "source": MARKET_SNAPSHOT_SOURCE,
            "index_trend": index_trend,
            "breadth": breadth,
            "liquidity_heat": liquidity_heat,
            "stock_bond_proxy": stock_bond_proxy,
            "sentiment": sentiment,
            "details_json": json.dumps(details, ensure_ascii=False),
        }
        snapshot_id = upsert_market_snapshot(conn, snapshot)
    return {"snapshot_id": snapshot_id, **snapshot}


def _liquidity_heat(conn: Any, target_date: str) -> float | None:
    rows = conn.execute(
        """
        SELECT asset_id, trade_date, amount
        FROM price_daily
        WHERE amount IS NOT NULL
          AND trade_date <= ?
        ORDER BY asset_id, trade_date DESC
        """,
        (target_date,),
    ).fetchall()
    grouped: dict[int, list[float]] = {}
    for row in rows:
        grouped.setdefault(int(row["asset_id"]), []).append(float(row["amount"]))
    ratios = []
    for amounts in grouped.values():
        if len(amounts) < 2:
            continue
        latest = amounts[0]
        baseline = mean(amounts[: min(len(amounts), 20)])
        if baseline:
            ratios.append(latest / baseline)
    return mean(ratios) if ratios else None


def _stock_bond_proxy(features: Any) -> float | None:
    by_code = {row["code"]: row["return_20d"] for row in features if row["return_20d"] is not None}
    equity = by_code.get("000300")
    bond = by_code.get("511010")
    if equity is None or bond is None:
        return None
    return equity - bond


def _latest_macro_observations(conn: Any, target_date: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT m.series_id, m.observation_date, m.value, m.source
        FROM macro_observations m
        JOIN (
            SELECT series_id, MAX(observation_date) AS observation_date
            FROM macro_observations
            WHERE observation_date <= ?
            GROUP BY series_id
        ) latest
          ON latest.series_id = m.series_id
         AND latest.observation_date = m.observation_date
        ORDER BY m.series_id
        """,
        (target_date,),
    ).fetchall()
    return {row["series_id"]: dict(row) for row in rows}


def _sentiment(
    index_trend: float | None,
    breadth: float | None,
    liquidity_heat: float | None,
    stock_bond_proxy: float | None,
) -> str:
    score = 0
    if index_trend is not None:
        score += 1 if index_trend > 0.02 else -1 if index_trend < -0.02 else 0
    if breadth is not None:
        score += 1 if breadth >= 0.6 else -1 if breadth <= 0.4 else 0
    if liquidity_heat is not None:
        score += 1 if liquidity_heat >= 1.1 else -1 if liquidity_heat <= 0.8 else 0
    if stock_bond_proxy is not None:
        score += 1 if stock_bond_proxy > 0.01 else -1 if stock_bond_proxy < -0.01 else 0
    if score >= 2:
        return "risk_on"
    if score <= -2:
        return "risk_off"
    return "neutral"


def _date_text(value: str | None) -> str | None:
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value or date.today().isoformat()
