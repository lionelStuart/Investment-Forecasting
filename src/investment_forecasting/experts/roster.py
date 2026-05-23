from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from investment_forecasting.db import connect, init_db, list_experts, upsert_expert


DEFAULT_EXPERTS: tuple[dict[str, Any], ...] = (
    {
        "expert_key": "defensive_income",
        "name": "稳健防守专家",
        "short_description": "优先控制回撤和流动性风险，只有在证据充分时才提高仓位。",
        "style_label": "防守收益 / 回撤控制",
        "focus_weights": {
            "volatility": 0.24,
            "max_drawdown": 0.24,
            "cash_buffer": 0.18,
            "market_snapshot_risk": 0.18,
            "fund_metadata_quality": 0.16,
        },
        "risk_budget_pct": 0.35,
        "max_drawdown_tolerance": 0.08,
        "allowed_asset_categories": ["index", "etf", "fund"],
        "default_cash_buffer_pct": 0.35,
        "review_cadence_days": 20,
        "lifecycle_state": "active",
        "mandate": "在高波动或弱市场状态下允许保持现金，不因短期踏空被单独惩罚。",
    },
    {
        "expert_key": "momentum_growth",
        "name": "趋势进攻专家",
        "short_description": "寻找趋势和成长参与机会，但必须在回撤或置信度恶化时降低暴露。",
        "style_label": "趋势动量 / 成长参与",
        "focus_weights": {
            "return_20d": 0.2,
            "return_60d": 0.18,
            "up_probability": 0.2,
            "expected_return": 0.18,
            "confidence": 0.14,
            "market_breadth": 0.1,
        },
        "risk_budget_pct": 0.75,
        "max_drawdown_tolerance": 0.18,
        "allowed_asset_categories": ["stock", "index", "etf", "fund"],
        "default_cash_buffer_pct": 0.08,
        "review_cadence_days": 10,
        "lifecycle_state": "active",
        "mandate": "可以承担较高波动，但不得忽略下行风险、模型置信度下降和市场广度恶化。",
    },
    {
        "expert_key": "balanced_rotation",
        "name": "均衡轮动专家",
        "short_description": "比较类别之间的风险调整收益，偏好分散和小步再平衡。",
        "style_label": "均衡轮动 / 风险调整配置",
        "focus_weights": {
            "sharpe": 0.2,
            "calmar": 0.18,
            "benchmark_excess": 0.18,
            "category_diversification": 0.16,
            "backtest_quality": 0.16,
            "prediction_confidence": 0.12,
        },
        "risk_budget_pct": 0.55,
        "max_drawdown_tolerance": 0.12,
        "allowed_asset_categories": ["index", "etf", "fund", "stock"],
        "default_cash_buffer_pct": 0.18,
        "review_cadence_days": 20,
        "lifecycle_state": "active",
        "mandate": "以组合均衡和证据质量为核心，避免单一资产或单一风格过度集中。",
    },
)


def initialize_default_experts(db_path: str | Path) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        for expert in DEFAULT_EXPERTS:
            upsert_expert(conn, _serialize_expert(expert))
        rows = list_experts(conn, lifecycle_state="active")

    active = [_deserialize_expert(dict(row)) for row in rows]
    if len(active) != len(DEFAULT_EXPERTS):
        raise RuntimeError(f"Expected {len(DEFAULT_EXPERTS)} active experts, found {len(active)}")
    return active


def list_roster(db_path: str | Path, lifecycle_state: str | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        return [_deserialize_expert(dict(row)) for row in list_experts(conn, lifecycle_state=lifecycle_state)]


def _serialize_expert(expert: dict[str, Any]) -> dict[str, Any]:
    return {
        **expert,
        "focus_weights_json": json.dumps(expert["focus_weights"], ensure_ascii=False, sort_keys=True),
        "allowed_asset_categories_json": json.dumps(
            expert["allowed_asset_categories"],
            ensure_ascii=False,
            sort_keys=True,
        ),
        "source": expert.get("source", "system"),
    }


def _deserialize_expert(row: dict[str, Any]) -> dict[str, Any]:
    row["focus_weights"] = json.loads(row.pop("focus_weights_json"))
    row["allowed_asset_categories"] = json.loads(row.pop("allowed_asset_categories_json"))
    return row
