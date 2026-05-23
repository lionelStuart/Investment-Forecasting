from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from investment_forecasting.advice.generator import generate_daily_advice
from investment_forecasting.db import connect, init_db
from investment_forecasting.experts.planning import run_expert_daily_plans
from investment_forecasting.experts.scoring import score_and_review_experts
from investment_forecasting.portfolio.accounting import ensure_expert_portfolios
from investment_forecasting.quant.backtest import run_backtest, run_latest_forecasts


class ToolError(RuntimeError):
    """Raised when a tool call cannot be completed."""


ToolHandler = Callable[[Path, dict[str, Any]], dict[str, Any]]


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_asset_list": {
        "description": "List stored assets, optionally filtered by asset_type.",
        "input_schema": {
            "type": "object",
            "properties": {"asset_type": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    "get_asset_history": {
        "description": "Return stored daily price/NAV history for one asset.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "market": {"type": "string", "default": "CN"},
                "source": {"type": "string", "default": "akshare"},
                "asset_type": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "limit": {"type": "integer", "default": 200},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    "get_fund_metrics": {
        "description": "Return latest stored feature/risk metrics for a fund.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "market": {"type": "string", "default": "CN"},
                "source": {"type": "string", "default": "akshare"},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    "get_market_snapshot": {
        "description": "Return latest structured market snapshot from stored predictions, features, and advice.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "run_forecast": {
        "description": "Run latest baseline forecasts and return stored row counts.",
        "input_schema": {
            "type": "object",
            "properties": {"horizons": {"type": "array", "items": {"type": "integer"}, "default": [5, 20, 60]}},
            "additionalProperties": False,
        },
    },
    "run_backtest": {
        "description": "Run rolling baseline backtests and return aggregate metrics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "horizons": {"type": "array", "items": {"type": "integer"}, "default": [5, 20, 60]},
                "lookback_days": {"type": "integer", "default": 60},
            },
            "additionalProperties": False,
        },
    },
    "get_daily_advice": {
        "description": "Return stored daily advice for a date, or the latest advice when date is omitted.",
        "input_schema": {
            "type": "object",
            "properties": {"date": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    "generate_daily_advice": {
        "description": "Generate and store daily advice from stored evidence.",
        "input_schema": {
            "type": "object",
            "properties": {"date": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    "list_experts": {
        "description": "List expert committee roster records and lifecycle state.",
        "input_schema": {
            "type": "object",
            "properties": {"state": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    "get_expert_plans": {
        "description": "Return persisted expert plans for a date, or latest plans when date is omitted.",
        "input_schema": {
            "type": "object",
            "properties": {"date": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    "run_expert_plans": {
        "description": "Run expert daily planning and simulated execution. Outputs are virtual research support only.",
        "input_schema": {
            "type": "object",
            "properties": {"date": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    "get_expert_portfolios": {
        "description": "Return virtual portfolio state for expert-owned portfolios.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "score_experts": {
        "description": "Score experts and review lifecycle status from persisted virtual portfolio records.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "window_days": {"type": "integer", "default": 20},
                "min_valuations": {"type": "integer", "default": 3},
            },
            "additionalProperties": False,
        },
    },
    "get_expert_scorecards": {
        "description": "Return persisted expert scorecards and lifecycle reviews.",
        "input_schema": {
            "type": "object",
            "properties": {"date": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    "get_expert_lessons": {
        "description": "Return structured expert lifecycle and hiring lessons.",
        "input_schema": {
            "type": "object",
            "properties": {"lesson_type": {"type": "string"}},
            "additionalProperties": False,
        },
    },
}


def list_tools() -> list[dict[str, Any]]:
    return [{"name": name, **schema} for name, schema in TOOL_SCHEMAS.items()]


def call_tool(db_path: str | Path, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return _error(tool_name, f"Unknown tool: {tool_name}")
    try:
        init_db(db_path)
        result = handler(Path(db_path), arguments)
        return {"ok": True, "tool": tool_name, "result": result, "error": None}
    except Exception as exc:
        return _error(tool_name, str(exc))


def get_asset_list(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    asset_type = arguments.get("asset_type")
    with connect(db_path) as conn:
        if asset_type:
            rows = conn.execute("SELECT * FROM assets WHERE asset_type = ? ORDER BY id", (asset_type,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM assets ORDER BY id").fetchall()
    return {"assets": [_row(row) for row in rows], "count": len(rows)}


def get_asset_history(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    code = _required(arguments, "code")
    market = arguments.get("market", "CN")
    source = arguments.get("source", "akshare")
    asset_type = arguments.get("asset_type")
    limit = int(arguments.get("limit", 200))
    start_date = _date_text(arguments.get("start_date"))
    end_date = _date_text(arguments.get("end_date"))

    with connect(db_path) as conn:
        asset = conn.execute(
            """
            SELECT *
            FROM assets
            WHERE code = ? AND market = ? AND source = ?
              AND (? IS NULL OR asset_type = ?)
            ORDER BY id
            LIMIT 1
            """,
            (code, market, source, asset_type, asset_type),
        ).fetchone()
        if asset is None:
            raise ToolError(f"Unknown asset: {code}/{market}/{source}")
        query = [
            """
            SELECT id, asset_id, trade_date, open, high, low, close, adjusted_close,
                   nav, accumulated_nav, volume, amount, pct_change, source
            FROM price_daily
            WHERE asset_id = ?
            """
        ]
        params: list[Any] = [asset["id"]]
        if start_date:
            query.append("AND trade_date >= ?")
            params.append(start_date)
        if end_date:
            query.append("AND trade_date <= ?")
            params.append(end_date)
        query.append("ORDER BY trade_date LIMIT ?")
        params.append(limit)
        rows = conn.execute("\n".join(query), params).fetchall()
    return {"asset": _row(asset), "history": [_row(row) for row in rows], "count": len(rows)}


def get_fund_metrics(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    code = _required(arguments, "code")
    market = arguments.get("market", "CN")
    source = arguments.get("source", "akshare")
    with connect(db_path) as conn:
        asset = conn.execute(
            "SELECT * FROM assets WHERE code = ? AND market = ? AND source = ?",
            (code, market, source),
        ).fetchone()
        if asset is None:
            raise ToolError(f"Unknown fund: {code}/{market}/{source}")
        if asset["asset_type"] != "fund":
            raise ToolError(f"Asset is not a fund: {code}")
        feature = conn.execute(
            """
            SELECT *
            FROM features_daily
            WHERE asset_id = ?
            ORDER BY feature_date DESC
            LIMIT 1
            """,
            (asset["id"],),
        ).fetchone()
        info = conn.execute("SELECT * FROM fund_info WHERE asset_id = ? ORDER BY updated_at DESC LIMIT 1", (asset["id"],)).fetchone()
    return {"asset": _row(asset), "fund_info": _row(info) if info else None, "metrics": _row(feature) if feature else None}


def get_market_snapshot(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    with connect(db_path) as conn:
        prediction_date = conn.execute("SELECT MAX(prediction_date) AS value FROM model_predictions").fetchone()["value"]
        feature_date = conn.execute("SELECT MAX(feature_date) AS value FROM features_daily").fetchone()["value"]
        advice = conn.execute("SELECT * FROM daily_advice ORDER BY advice_date DESC, id DESC LIMIT 1").fetchone()
        environment = conn.execute("SELECT * FROM market_snapshots ORDER BY snapshot_date DESC, id DESC LIMIT 1").fetchone()
        predictions = conn.execute(
            """
            SELECT COUNT(*) AS count, AVG(expected_return) AS avg_expected_return,
                   AVG(downside_risk) AS avg_downside_risk, AVG(confidence) AS avg_confidence
            FROM model_predictions
            WHERE prediction_date = COALESCE(?, prediction_date)
            """,
            (prediction_date,),
        ).fetchone()
    return {
        "prediction_date": prediction_date,
        "feature_date": feature_date,
        "prediction_summary": _row(predictions),
        "market_environment": _row(environment) if environment else None,
        "latest_advice": _row(advice) if advice else None,
    }


def run_forecast_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    horizons = tuple(int(value) for value in arguments.get("horizons", [5, 20, 60]))
    summary = run_latest_forecasts(db_path, horizons=horizons)
    return {"model_version": "baseline_mean_v1", "horizons": list(horizons), "summary": summary}


def run_backtest_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    horizons = tuple(int(value) for value in arguments.get("horizons", [5, 20, 60]))
    lookback_days = int(arguments.get("lookback_days", 60))
    return run_backtest(db_path, horizons=horizons, lookback_days=lookback_days)


def get_daily_advice(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    target_date = _date_text(arguments.get("date"))
    with connect(db_path) as conn:
        if target_date:
            row = conn.execute(
                "SELECT * FROM daily_advice WHERE advice_date = ? ORDER BY id DESC LIMIT 1",
                (target_date,),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM daily_advice ORDER BY advice_date DESC, id DESC LIMIT 1").fetchone()
    if row is None:
        raise ToolError("No daily advice found")
    return {"advice": _row(row)}


def generate_daily_advice_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    advice_id = generate_daily_advice(db_path, advice_date=arguments.get("date"))
    return {"advice_id": advice_id, "advice": get_daily_advice(db_path, arguments)["advice"]}


def list_experts_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    state = arguments.get("state")
    with connect(db_path) as conn:
        if state:
            rows = conn.execute("SELECT * FROM experts WHERE lifecycle_state = ? ORDER BY expert_key", (state,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM experts ORDER BY lifecycle_state, expert_key").fetchall()
    return {"experts": [_row(row) for row in rows], "count": len(rows)}


def get_expert_plans_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    target_date = _date_text(arguments.get("date"))
    with connect(db_path) as conn:
        if target_date:
            rows = conn.execute(
                """
                SELECT p.*, e.name AS expert_name, e.lifecycle_state
                FROM expert_plans p
                JOIN experts e ON e.id = p.expert_id
                WHERE p.plan_date = ?
                ORDER BY e.expert_key
                """,
                (target_date,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT p.*, e.name AS expert_name, e.lifecycle_state
                FROM expert_plans p
                JOIN experts e ON e.id = p.expert_id
                WHERE p.plan_date = (SELECT MAX(plan_date) FROM expert_plans)
                ORDER BY e.expert_key
                """
            ).fetchall()
    return {"plans": [_row(row) for row in rows], "count": len(rows)}


def run_expert_plans_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    plans = run_expert_daily_plans(db_path, plan_date=arguments.get("date"))
    return {"plans": plans, "count": len(plans), "virtual_research_only": True}


def get_expert_portfolios_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    ensure_expert_portfolios(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT vp.*, e.name AS expert_name, e.lifecycle_state,
                   vv.valuation_date, vv.total_value, vv.positions_value,
                   vv.missing_prices_json, vv.details_json
            FROM virtual_portfolios vp
            JOIN experts e ON e.id = vp.owner_id AND vp.owner_type = 'expert'
            LEFT JOIN virtual_valuations vv ON vv.id = (
                SELECT id FROM virtual_valuations
                WHERE portfolio_id = vp.id
                ORDER BY valuation_date DESC, id DESC
                LIMIT 1
            )
            ORDER BY e.expert_key
            """
        ).fetchall()
    return {"portfolios": [_row(row) for row in rows], "count": len(rows)}


def score_experts_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return score_and_review_experts(
        db_path,
        review_date=arguments.get("date"),
        window_days=int(arguments.get("window_days", 20)),
        min_valuations=int(arguments.get("min_valuations", 3)),
    )


def get_expert_scorecards_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    target_date = _date_text(arguments.get("date"))
    with connect(db_path) as conn:
        params: list[Any] = []
        where = ""
        if target_date:
            where = "WHERE sc.score_date = ?"
            params.append(target_date)
        scorecards = conn.execute(
            f"""
            SELECT sc.*, e.name AS expert_name, e.lifecycle_state
            FROM expert_scorecards sc
            JOIN experts e ON e.id = sc.expert_id
            {where}
            ORDER BY sc.score_date DESC, e.expert_key
            """,
            params,
        ).fetchall()
        reviews = conn.execute(
            """
            SELECT rv.*, e.name AS expert_name
            FROM expert_reviews rv
            JOIN experts e ON e.id = rv.expert_id
            ORDER BY rv.review_date DESC, rv.id DESC
            LIMIT 100
            """
        ).fetchall()
    return {"scorecards": [_row(row) for row in scorecards], "reviews": [_row(row) for row in reviews]}


def get_expert_lessons_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    lesson_type = arguments.get("lesson_type")
    with connect(db_path) as conn:
        if lesson_type:
            rows = conn.execute(
                """
                SELECT l.*, e.name AS expert_name
                FROM expert_lessons l
                LEFT JOIN experts e ON e.id = l.expert_id
                WHERE l.lesson_type = ?
                ORDER BY l.lesson_date DESC, l.id DESC
                """,
                (lesson_type,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT l.*, e.name AS expert_name
                FROM expert_lessons l
                LEFT JOIN experts e ON e.id = l.expert_id
                ORDER BY l.lesson_date DESC, l.id DESC
                """
            ).fetchall()
    return {"lessons": [_row(row) for row in rows], "count": len(rows)}


def _row(row: Any) -> dict[str, Any]:
    result = dict(row)
    for key in list(result):
        if key in result and result[key]:
            if key.endswith("_json"):
                result[key.removesuffix("_json")] = json.loads(result[key])
    return result


def _required(arguments: dict[str, Any], name: str) -> Any:
    value = arguments.get(name)
    if value in (None, ""):
        raise ToolError(f"Missing required argument: {name}")
    return value


def _date_text(value: str | None) -> str | None:
    if value and len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def _error(tool_name: str, message: str) -> dict[str, Any]:
    return {"ok": False, "tool": tool_name, "result": None, "error": {"message": message}}


_HANDLERS: dict[str, ToolHandler] = {
    "get_asset_list": get_asset_list,
    "get_asset_history": get_asset_history,
    "get_fund_metrics": get_fund_metrics,
    "get_market_snapshot": get_market_snapshot,
    "run_forecast": run_forecast_tool,
    "run_backtest": run_backtest_tool,
    "get_daily_advice": get_daily_advice,
    "generate_daily_advice": generate_daily_advice_tool,
    "list_experts": list_experts_tool,
    "get_expert_plans": get_expert_plans_tool,
    "run_expert_plans": run_expert_plans_tool,
    "get_expert_portfolios": get_expert_portfolios_tool,
    "score_experts": score_experts_tool,
    "get_expert_scorecards": get_expert_scorecards_tool,
    "get_expert_lessons": get_expert_lessons_tool,
}
