from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from investment_forecasting.agent_runtime.manifests import get_role_tool_manifest
from investment_forecasting.db import connect, init_db
from investment_forecasting.experts.roster import initialize_default_experts, list_roster


EXPERT_AGENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {"type": "string"},
        "role": {"type": "string", "enum": ["expert"]},
        "role_key": {"type": "string"},
        "outcome": {"type": "string", "enum": ["plan_action", "skipped", "failed"]},
        "summary": {"type": "string"},
        "action": {"type": "string", "enum": ["buy", "sell", "rebalance", "hold", "no_trade"]},
        "reason": {"type": "string"},
        "analysis": {"type": "string"},
        "reflection": {"type": "string"},
        "risk_note": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "news_evidence_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "status",
        "role",
        "role_key",
        "outcome",
        "summary",
        "action",
        "reason",
        "analysis",
        "reflection",
        "risk_note",
        "evidence_ids",
        "news_evidence_ids",
    ],
}

JARVIS_AGENT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {"type": "string"},
        "role": {"type": "string", "enum": ["jarvis"]},
        "role_key": {"type": "string", "enum": ["jarvis"]},
        "outcome": {"type": "string", "enum": ["daily_brief", "skipped", "failed"]},
        "summary": {"type": "string"},
        "expert_evidence_status": {"type": "string", "enum": ["complete", "incomplete", "degraded"]},
        "reason": {"type": "string"},
        "analysis": {"type": "string"},
        "reflection": {"type": "string"},
        "risk_note": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "status",
        "role",
        "role_key",
        "outcome",
        "summary",
        "expert_evidence_status",
        "reason",
        "analysis",
        "reflection",
        "risk_note",
        "evidence_ids",
    ],
}


def render_expert_agent_prompt(db_path: str | Path, *, expert_key: str, target_date: str, agent_run_id: int | None = None) -> dict[str, Any]:
    init_db(db_path)
    initialize_default_experts(db_path)
    expert = next((item for item in list_roster(db_path, lifecycle_state="active") if item["expert_key"] == expert_key), None)
    if expert is None:
        raise ValueError(f"active expert not found: {expert_key}")
    manifest = get_role_tool_manifest("expert", expert_key).to_dict()
    context = _expert_context(db_path, int(expert["id"]), target_date)
    prompt = "\n".join(
        [
            "# Role",
            f"You are expert {expert['name']} ({expert['expert_key']}). Return JSON only.",
            "",
            "# Runtime",
            f"agent_run_id: {agent_run_id if agent_run_id is not None else 'pending'}",
            f"target_evidence_date: {target_date}",
            "Use local research-only language. Do not run shell commands. Do not write SQLite. Do not scrape WebUI.",
            "The host injects a role-scoped MCP server for this run. Call its tools directly; the server injects agent_run_id, role_type, and role_key for audit.",
            "",
            "# Expert Identity",
            f"style_label: {expert['style_label']}",
            f"mandate: {expert['mandate']}",
            f"focus_weights: {json.dumps(expert['focus_weights'], ensure_ascii=False, sort_keys=True)}",
            f"risk_budget_pct: {expert['risk_budget_pct']}",
            f"max_drawdown_tolerance: {expert['max_drawdown_tolerance']}",
            f"allowed_asset_categories: {json.dumps(expert['allowed_asset_categories'], ensure_ascii=False)}",
            "",
            "# Context",
            json.dumps(context, ensure_ascii=False, sort_keys=True),
            "",
            "# Skill Bundle",
            json.dumps(manifest["skill_bundle"], ensure_ascii=False),
            "",
            "# Tool Policy",
            json.dumps(manifest["tools"], ensure_ascii=False, sort_keys=True),
            "Only use the MCP tools listed in tools.allowed. Do not claim a tool is unavailable unless the MCP call itself fails.",
            "",
            "# Required Outcome",
            "Return exactly one outcome: plan_action, skipped, or failed.",
            "Any model, portfolio, market, or news claim must cite evidence_ids or say evidence is insufficient.",
            "Output JSON must match the provided schema. Use action no_trade when evidence is insufficient.",
        ]
    )
    return {
        "prompt": prompt,
        "prompt_ref": {"kind": "generated", "prompt_hash": _hash(prompt), "template": "expert_agent_prompt_v1"},
        "manifest": manifest,
        "output_schema": EXPERT_AGENT_OUTPUT_SCHEMA,
    }


def render_jarvis_agent_prompt(
    db_path: str | Path,
    *,
    run_date: str,
    target_evidence_date: str,
    readiness: dict[str, Any],
    agent_run_id: int | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    manifest = get_role_tool_manifest("jarvis", "jarvis").to_dict()
    context = _jarvis_context(db_path, target_evidence_date)
    prompt = "\n".join(
        [
            "# Role",
            "You are Jarvis, the user-facing local investment research assistant. Return JSON only.",
            "",
            "# Runtime",
            f"agent_run_id: {agent_run_id if agent_run_id is not None else 'pending'}",
            f"run_date: {run_date}",
            f"target_evidence_date: {target_evidence_date}",
            "Do not run shell commands. Do not write SQLite. Do not scrape WebUI. Do not send phone messages.",
            "The host injects a role-scoped MCP server for this run. Call its tools directly; the server injects agent_run_id, role_type, and role_key for audit.",
            "",
            "# Expert Readiness",
            json.dumps(readiness, ensure_ascii=False, sort_keys=True),
            "",
            "# Evidence Context",
            json.dumps(context, ensure_ascii=False, sort_keys=True),
            "",
            "# Skill Bundle",
            json.dumps(manifest["skill_bundle"], ensure_ascii=False),
            "",
            "# Tool Policy",
            json.dumps(manifest["tools"], ensure_ascii=False, sort_keys=True),
            "Only use the MCP tools listed in tools.allowed. Do not claim a tool is unavailable unless the MCP call itself fails.",
            "",
            "# Required Outcome",
            "Return outcome daily_brief when ready, skipped when blocked, failed when validation cannot pass.",
            "Separate system facts from synthesis. Include risk boundaries and uncertainty. Do not promise returns.",
        ]
    )
    return {
        "prompt": prompt,
        "prompt_ref": {"kind": "generated", "prompt_hash": _hash(prompt), "template": "jarvis_agent_prompt_v1"},
        "manifest": manifest,
        "output_schema": JARVIS_AGENT_OUTPUT_SCHEMA,
    }


def _expert_context(db_path: str | Path, expert_id: int, target_date: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        portfolio = conn.execute(
            "SELECT id, cash, initial_capital FROM virtual_portfolios WHERE owner_type = 'expert' AND owner_id = ?",
            (expert_id,),
        ).fetchone()
        plan = conn.execute(
            "SELECT id, plan_date, action, target_asset_id, rationale FROM expert_plans WHERE expert_id = ? AND plan_date < ? ORDER BY plan_date DESC, id DESC LIMIT 1",
            (expert_id, target_date),
        ).fetchone()
        scorecard = conn.execute(
            "SELECT id, score_date, overall_score, mature_enough, portfolio_return, max_drawdown FROM expert_scorecards WHERE expert_id = ? AND score_date <= ? ORDER BY score_date DESC, id DESC LIMIT 1",
            (expert_id, target_date),
        ).fetchone()
        lessons = conn.execute(
            "SELECT id, lesson_date, lesson_type, summary FROM expert_lessons WHERE expert_id = ? ORDER BY lesson_date DESC, id DESC LIMIT 3",
            (expert_id,),
        ).fetchall()
    return {
        "portfolio": dict(portfolio) if portfolio else None,
        "prior_plan": dict(plan) if plan else None,
        "latest_scorecard": dict(scorecard) if scorecard else None,
        "recent_lessons": [dict(row) for row in lessons],
    }


def _jarvis_context(db_path: str | Path, target_evidence_date: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        expert_runs = conn.execute(
            """
            SELECT id, role_key, status, submission_result_json
            FROM agent_runs
            WHERE role_type = 'expert' AND target_evidence_date = ?
            ORDER BY role_key, id DESC
            """,
            (target_evidence_date,),
        ).fetchall()
        model_predictions = conn.execute(
            "SELECT id, asset_id, prediction_date, horizon_days, expected_return, confidence FROM model_predictions WHERE prediction_date <= ? ORDER BY prediction_date DESC, id DESC LIMIT 8",
            (target_evidence_date,),
        ).fetchall()
        market = conn.execute(
            "SELECT id, snapshot_date, sentiment, details_json FROM market_snapshots WHERE snapshot_date <= ? ORDER BY snapshot_date DESC, id DESC LIMIT 1",
            (target_evidence_date,),
        ).fetchone()
    return {
        "expert_agent_runs": [{"id": row["id"], "role_key": row["role_key"], "status": row["status"]} for row in expert_runs],
        "model_prediction_ids": [row["id"] for row in model_predictions],
        "market_snapshot": dict(market) if market else None,
    }


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
