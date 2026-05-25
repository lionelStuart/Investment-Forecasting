from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from investment_forecasting.advice.generator import generate_daily_advice
from investment_forecasting.agent_runtime.manifests import (
    AgentToolAccessError,
    get_role_tool_manifest,
    record_agent_tool_result,
    validate_agent_tool_call,
)
from investment_forecasting.data.news import search_news_evidence
from investment_forecasting.db import connect, init_db
from investment_forecasting.experts.planning import run_expert_daily_plans
from investment_forecasting.experts.scoring import score_and_review_experts
from investment_forecasting.jarvis import get_jarvis_brief
from investment_forecasting.jarvis.synthesis import generate_jarvis_brief
from investment_forecasting.portfolio.accounting import ensure_expert_portfolios
from investment_forecasting.quant.backtest import run_backtest, run_latest_forecasts
from investment_forecasting.scheduler import scheduler_status


class ToolError(RuntimeError):
    """Raised when a tool call cannot be completed."""


ToolHandler = Callable[[Path, dict[str, Any]], dict[str, Any]]


def _submission_schema(role_type: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "agent_run_id": {"type": "integer"},
            "role_type": {"type": "string", "const": role_type},
            "role_key": {"type": "string"},
            "idempotency_key": {"type": "string"},
            "payload": {"type": "object"},
            "reason": {"type": "string"},
        },
        "required": ["agent_run_id", "role_type", "role_key", "idempotency_key"],
        "additionalProperties": False,
    }


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
            "properties": {
                "horizons": {"type": "array", "items": {"type": "integer"}, "default": [5, 20, 60]},
                "model_versions": {"type": "array", "items": {"type": "string"}, "default": ["baseline_mean_v1"]},
            },
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
                "embargo_days": {"type": "integer", "default": 0},
                "model_versions": {"type": "array", "items": {"type": "string"}, "default": ["baseline_mean_v1"]},
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
    "get_jarvis_daily_brief": {
        "description": "Return a structured Jarvis daily brief for a date, or the latest brief when date is omitted.",
        "input_schema": {
            "type": "object",
            "properties": {"date": {"type": "string"}, "version": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    "generate_jarvis_daily_brief": {
        "description": "Generate and store a Jarvis daily brief from persisted market, model, expert, portfolio, task-log, and preference evidence.",
        "input_schema": {
            "type": "object",
            "properties": {"date": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    "search_news_evidence": {
        "description": "Search bounded financial news evidence by source, time, asset, theme, event type, sentiment, or keyword. Results are context only, not buy/sell advice.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {"type": ["string", "array"], "items": {"type": "string"}},
                "start_datetime": {"type": "string"},
                "end_datetime": {"type": "string"},
                "asset_id": {"type": "integer"},
                "asset_code": {"type": "string"},
                "theme": {"type": "string"},
                "event_type": {"type": "string"},
                "sentiment": {"type": "string"},
                "keyword": {"type": "string"},
                "max_results": {"type": "integer", "default": 10, "maximum": 50},
                "dedupe": {"type": "string", "default": "content_hash"},
                "sort": {"type": "string", "default": "recency"},
            },
            "additionalProperties": False,
        },
    },
    "get_scheduler_status": {
        "description": "Return system scheduler jobs, latest runs, watermarks, and provider backoff state for evidence freshness checks.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "get_agent_tool_manifest": {
        "description": "Return the role-scoped tool manifest for a Codex expert or Jarvis agent run.",
        "input_schema": {
            "type": "object",
            "properties": {
                "role_type": {"type": "string", "enum": ["expert", "jarvis"]},
                "role_key": {"type": "string"},
            },
            "required": ["role_type"],
            "additionalProperties": False,
        },
    },
    "validate_agent_output": {
        "description": "Preview validation for a structured expert/Jarvis agent output without persisting investment records.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_run_id": {"type": "integer"},
                "role_type": {"type": "string", "enum": ["expert", "jarvis"]},
                "role_key": {"type": "string"},
                "output": {"type": "object"},
            },
            "required": ["agent_run_id", "role_type", "role_key", "output"],
            "additionalProperties": False,
        },
    },
    "submit_expert_analysis_draft": {
        "description": "Submit an expert analysis draft through runtime validation. MVP stores only the audited submission envelope.",
        "input_schema": _submission_schema("expert"),
    },
    "submit_expert_virtual_action": {
        "description": "Submit one expert virtual action for system validation. MVP stores only the audited submission envelope.",
        "input_schema": _submission_schema("expert"),
    },
    "record_expert_skipped_action": {
        "description": "Record that an expert skipped the T-day virtual action with a reason.",
        "input_schema": _submission_schema("expert"),
    },
    "record_expert_failed_action": {
        "description": "Record that an expert failed the T-day virtual action with a reason.",
        "input_schema": _submission_schema("expert"),
    },
    "submit_jarvis_analysis_draft": {
        "description": "Submit a Jarvis analysis draft through runtime validation. MVP stores only the audited submission envelope.",
        "input_schema": _submission_schema("jarvis"),
    },
    "submit_jarvis_daily_brief": {
        "description": "Submit a Jarvis daily brief through runtime validation. MVP stores only the audited submission envelope.",
        "input_schema": _submission_schema("jarvis"),
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


def call_agent_tool(db_path: str | Path, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    try:
        init_db(db_path)
        validation = validate_agent_tool_call(
            str(db_path),
            agent_run_id=arguments.get("agent_run_id"),
            role_type=arguments.get("role_type"),
            role_key=arguments.get("role_key"),
            tool_name=tool_name,
            arguments=arguments,
            idempotency_key=arguments.get("idempotency_key"),
        )
    except AgentToolAccessError as exc:
        return _error(tool_name, str(exc))

    handler_arguments = _strip_runtime_args(arguments) if tool_name in validation["manifest"]["tools"]["read"] else arguments
    result = call_tool(db_path, tool_name, handler_arguments)
    status = "submitted" if result["ok"] and tool_name in validation["manifest"]["tools"]["submission"] else ("allowed" if result["ok"] else "failed")
    record_agent_tool_result(
        str(db_path),
        agent_tool_call_id=validation["agent_tool_call_id"],
        status=status,
        result_summary={"ok": result["ok"], "tool": tool_name},
        error=(result.get("error") or {}).get("message") if result.get("error") else None,
    )
    result["agent_tool_call_id"] = validation["agent_tool_call_id"]
    return result


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
                   AVG(downside_risk) AS avg_downside_risk, AVG(confidence) AS avg_confidence,
                   AVG(r.rank_score) AS avg_rank_score,
                   AVG(r.risk_adjusted_score) AS avg_risk_adjusted_score
            FROM model_predictions p
            LEFT JOIN model_prediction_reliability r ON r.prediction_id = p.id
            WHERE p.prediction_date = COALESCE(?, p.prediction_date)
            """,
            (prediction_date,),
        ).fetchone()
        validation_rows = conn.execute(
            """
            SELECT horizon_days, metrics_json, parameters_json
            FROM backtest_runs
            WHERE model_version = (
                SELECT model_version
                FROM backtest_runs
                ORDER BY created_at DESC, id DESC
                LIMIT 1
            )
            ORDER BY horizon_days
            """
        ).fetchall()
        monitoring_rows = conn.execute(
            """
            SELECT model_version, metrics_json
            FROM model_monitoring_reports
            WHERE report_date = (SELECT MAX(report_date) FROM model_monitoring_reports)
            ORDER BY model_version
            """
        ).fetchall()
    return {
        "prediction_date": prediction_date,
        "feature_date": feature_date,
        "prediction_summary": _row(predictions),
        "validation_summary": [_validation_summary_row(row) for row in validation_rows],
        "model_governance": _model_governance_summary(monitoring_rows),
        "market_environment": _row(environment) if environment else None,
        "latest_advice": _row(advice) if advice else None,
    }


def run_forecast_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    horizons = tuple(int(value) for value in arguments.get("horizons", [5, 20, 60]))
    model_versions = tuple(str(value) for value in arguments.get("model_versions", ["baseline_mean_v1"]))
    summary = run_latest_forecasts(db_path, horizons=horizons, model_versions=model_versions)
    return {"model_versions": list(model_versions), "horizons": list(horizons), "summary": summary}


def run_backtest_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    horizons = tuple(int(value) for value in arguments.get("horizons", [5, 20, 60]))
    lookback_days = int(arguments.get("lookback_days", 60))
    embargo_days = int(arguments.get("embargo_days", 0))
    model_versions = tuple(str(value) for value in arguments.get("model_versions", ["baseline_mean_v1"]))
    return run_backtest(db_path, horizons=horizons, lookback_days=lookback_days, embargo_days=embargo_days, model_versions=model_versions)


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


def get_jarvis_daily_brief_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    brief = get_jarvis_brief(
        db_path,
        brief_date=_date_text(arguments.get("date")),
        version=arguments.get("version"),
    )
    if brief is None:
        raise ToolError("No Jarvis daily brief found")
    return {
        "brief": brief,
        "model_risk_gates": (brief.get("model_summary") or {}).get("confidence_gates", []),
        "model_risk_summary": (brief.get("model_summary") or {}).get("model_risk_summary", {}),
        "ai_analysis_status": _jarvis_ai_analysis_status(db_path, brief),
    }


def generate_jarvis_daily_brief_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    brief = generate_jarvis_brief(db_path, brief_date=arguments.get("date"))
    return {
        "brief_id": brief["id"],
        "brief": brief,
        "model_risk_gates": (brief.get("model_summary") or {}).get("confidence_gates", []),
        "model_risk_summary": (brief.get("model_summary") or {}).get("model_risk_summary", {}),
        "ai_analysis_status": _jarvis_ai_analysis_status(db_path, brief),
    }


def _jarvis_ai_analysis_status(db_path: Path, brief: dict[str, Any]) -> dict[str, Any] | None:
    analysis_id = (brief.get("evidence") or {}).get("jarvis_ai_analysis_id")
    if not analysis_id:
        return None
    with connect(db_path) as conn:
        row = conn.execute("SELECT id, source, status, validation_json FROM ai_analysis_records WHERE id = ?", (analysis_id,)).fetchone()
    if row is None:
        return None
    validation = json.loads(row["validation_json"] or "{}")
    return {
        "id": row["id"],
        "source": row["source"],
        "status": row["status"],
        "provider": validation.get("provider"),
    }


def search_news_evidence_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return search_news_evidence(db_path, **arguments)


def get_scheduler_status_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return scheduler_status(db_path)


def get_agent_tool_manifest_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    role_type = _required(arguments, "role_type")
    role_key = arguments.get("role_key")
    manifest = get_role_tool_manifest(role_type, role_key)
    return manifest.to_dict()


def validate_agent_output_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    output = arguments.get("output") or {}
    warnings = []
    if not isinstance(output, dict):
        return {"validation_status": "failed", "errors": ["output must be an object"], "warnings": warnings}
    if not output.get("status"):
        warnings.append("missing status")
    if arguments.get("role_type") == "expert" and arguments.get("role_key") in (None, "", "jarvis"):
        return {"validation_status": "failed", "errors": ["expert output requires an expert role_key"], "warnings": warnings}
    if arguments.get("role_type") == "jarvis" and arguments.get("role_key") != "jarvis":
        return {"validation_status": "failed", "errors": ["jarvis output requires role_key=jarvis"], "warnings": warnings}
    return {"validation_status": "passed", "errors": [], "warnings": warnings, "persisted": False}


def submit_agent_envelope_tool(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    payload = arguments.get("payload") or {}
    return {
        "accepted": True,
        "persisted": False,
        "submission_mode": "audit_envelope",
        "payload_keys": sorted(payload) if isinstance(payload, dict) else [],
        "reason": arguments.get("reason"),
        "next_step": "The agent runtime workflow validates and persists accepted expert/Jarvis artifacts after Codex execution.",
    }


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


def _validation_summary_row(row: Any) -> dict[str, Any]:
    metrics = json.loads(row["metrics_json"] or "{}")
    parameters = json.loads(row["parameters_json"] or "{}")
    return {
        "horizon_days": row["horizon_days"],
        "validation_status": metrics.get("validation_status"),
        "information_coefficient": metrics.get("information_coefficient"),
        "rank_ic": metrics.get("rank_ic"),
        "bucket_spread": metrics.get("bucket_spread"),
        "validation_policy": metrics.get("validation_policy") or parameters.get("validation_policy"),
        "asset_type_performance": metrics.get("asset_type_performance"),
        "same_category_performance": metrics.get("same_category_performance"),
        "probability_calibration": metrics.get("probability_calibration"),
    }


def _model_governance_summary(rows: Any) -> dict[str, Any]:
    models = {}
    for row in rows or []:
        metrics = json.loads(row["metrics_json"] or "{}")
        governance = metrics.get("governance")
        if governance:
            models[row["model_version"]] = governance
    return {
        "primary_model_version": "baseline_mean_v1" if "baseline_mean_v1" in models else None,
        "decision": "hold_primary" if "baseline_mean_v1" in models else "no_primary_available",
        "models": models,
        "rationale": "baseline_mean_v1 remains primary until a candidate passes promotion gates and product review.",
    }


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


def _strip_runtime_args(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in arguments.items()
        if key not in {"agent_run_id", "role_type", "role_key", "idempotency_key", "evidence_scope"}
    }


_HANDLERS: dict[str, ToolHandler] = {
    "get_asset_list": get_asset_list,
    "get_asset_history": get_asset_history,
    "get_fund_metrics": get_fund_metrics,
    "get_market_snapshot": get_market_snapshot,
    "run_forecast": run_forecast_tool,
    "run_backtest": run_backtest_tool,
    "get_daily_advice": get_daily_advice,
    "generate_daily_advice": generate_daily_advice_tool,
    "get_jarvis_daily_brief": get_jarvis_daily_brief_tool,
    "generate_jarvis_daily_brief": generate_jarvis_daily_brief_tool,
    "search_news_evidence": search_news_evidence_tool,
    "get_scheduler_status": get_scheduler_status_tool,
    "get_agent_tool_manifest": get_agent_tool_manifest_tool,
    "validate_agent_output": validate_agent_output_tool,
    "submit_expert_analysis_draft": submit_agent_envelope_tool,
    "submit_expert_virtual_action": submit_agent_envelope_tool,
    "record_expert_skipped_action": submit_agent_envelope_tool,
    "record_expert_failed_action": submit_agent_envelope_tool,
    "submit_jarvis_analysis_draft": submit_agent_envelope_tool,
    "submit_jarvis_daily_brief": submit_agent_envelope_tool,
    "list_experts": list_experts_tool,
    "get_expert_plans": get_expert_plans_tool,
    "run_expert_plans": run_expert_plans_tool,
    "get_expert_portfolios": get_expert_portfolios_tool,
    "score_experts": score_experts_tool,
    "get_expert_scorecards": get_expert_scorecards_tool,
    "get_expert_lessons": get_expert_lessons_tool,
}
