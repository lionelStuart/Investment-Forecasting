from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from investment_forecasting.db import connect, get_agent_run, insert_agent_tool_call


EXPERT_SKILL_BUNDLE = [
    "investment-market-data-skill",
    "investment-model-evidence-skill",
    "investment-news-evidence-skill",
    "investment-asset-research-skill",
    "investment-expert-portfolio-skill",
    "investment-virtual-action-skill",
    "investment-agent-output-contract",
]

JARVIS_SKILL_BUNDLE = [
    "investment-market-data-skill",
    "investment-model-evidence-skill",
    "investment-news-evidence-skill",
    "investment-asset-research-skill",
    "investment-expert-portfolio-readonly-skill",
    "investment-jarvis-synthesis-skill",
    "investment-agent-output-contract",
]

EXPERT_READ_TOOLS = [
    "get_asset_list",
    "get_asset_history",
    "get_fund_metrics",
    "get_market_snapshot",
    "get_daily_advice",
    "list_experts",
    "get_expert_plans",
    "get_expert_portfolios",
    "get_expert_scorecards",
    "get_expert_lessons",
    "search_news_evidence",
]

JARVIS_READ_TOOLS = [
    "get_asset_list",
    "get_asset_history",
    "get_fund_metrics",
    "get_market_snapshot",
    "get_daily_advice",
    "list_experts",
    "get_expert_plans",
    "get_expert_portfolios",
    "get_expert_scorecards",
    "get_expert_lessons",
    "get_jarvis_daily_brief",
    "search_news_evidence",
]

EXPERT_SUBMISSION_TOOLS = [
    "submit_expert_analysis_draft",
    "submit_expert_virtual_action",
    "record_expert_skipped_action",
    "record_expert_failed_action",
]

JARVIS_SUBMISSION_TOOLS = [
    "submit_jarvis_analysis_draft",
    "submit_jarvis_daily_brief",
]

VALIDATION_TOOLS = [
    "validate_agent_output",
]

OPERATIONS_TOOLS = [
    "get_agent_tool_manifest",
]

FORBIDDEN_TOOL_NAMES = {
    "run_forecast",
    "run_backtest",
    "generate_daily_advice",
    "run_expert_plans",
    "score_experts",
    "generate_jarvis_daily_brief",
    "send_outbound_message",
    "shell",
    "sql",
    "webui_scrape",
    "live_trade",
}


@dataclass(frozen=True)
class AgentToolManifest:
    role_type: str
    role_key: str
    skill_bundle: list[str]
    read_tools: list[str]
    submission_tools: list[str]
    validation_tools: list[str]
    operations_tools: list[str]
    forbidden_tools: list[str]

    @property
    def allowed_tools(self) -> list[str]:
        return sorted(set(self.read_tools + self.submission_tools + self.validation_tools + self.operations_tools))

    def to_dict(self) -> dict[str, Any]:
        return {
            "role_type": self.role_type,
            "role_key": self.role_key,
            "skill_bundle": self.skill_bundle,
            "tools": {
                "read": self.read_tools,
                "submission": self.submission_tools,
                "validation": self.validation_tools,
                "operations": self.operations_tools,
                "allowed": self.allowed_tools,
                "forbidden": self.forbidden_tools,
            },
            "safety": {
                "no_shell": True,
                "no_direct_sql": True,
                "no_webui_scraping": True,
                "no_live_trading": True,
                "no_communication_send": True,
            },
        }


class AgentToolAccessError(RuntimeError):
    """Raised when a role-scoped runtime tool call is not allowed."""


def get_role_tool_manifest(role_type: str, role_key: str | None = None) -> AgentToolManifest:
    if role_type == "expert":
        return AgentToolManifest(
            role_type="expert",
            role_key=role_key or "*",
            skill_bundle=[*EXPERT_SKILL_BUNDLE],
            read_tools=[*EXPERT_READ_TOOLS],
            submission_tools=[*EXPERT_SUBMISSION_TOOLS],
            validation_tools=[*VALIDATION_TOOLS],
            operations_tools=[*OPERATIONS_TOOLS],
            forbidden_tools=sorted(FORBIDDEN_TOOL_NAMES),
        )
    if role_type == "jarvis":
        return AgentToolManifest(
            role_type="jarvis",
            role_key=role_key or "jarvis",
            skill_bundle=[*JARVIS_SKILL_BUNDLE],
            read_tools=[*JARVIS_READ_TOOLS],
            submission_tools=[*JARVIS_SUBMISSION_TOOLS],
            validation_tools=[*VALIDATION_TOOLS],
            operations_tools=[*OPERATIONS_TOOLS],
            forbidden_tools=sorted(FORBIDDEN_TOOL_NAMES),
        )
    raise AgentToolAccessError(f"unsupported role_type: {role_type}")


def validate_agent_tool_call(
    db_path: str,
    *,
    agent_run_id: int | None,
    role_type: str | None,
    role_key: str | None,
    tool_name: str,
    arguments: dict[str, Any],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    if agent_run_id is None:
        raise AgentToolAccessError("agent runtime tool calls require agent_run_id")
    if not role_type:
        raise AgentToolAccessError("agent runtime tool calls require role_type")
    if not role_key:
        raise AgentToolAccessError("agent runtime tool calls require role_key")

    with connect(db_path) as conn:
        run = get_agent_run(conn, agent_run_id)
        if run is None:
            raise AgentToolAccessError(f"agent run not found: {agent_run_id}")
        if run["status"] != "running":
            _reject(conn, agent_run_id, tool_name, role_type, role_key, arguments, idempotency_key, "agent run is not running")
            raise AgentToolAccessError(f"agent run is not running: {run['status']}")
        if run["role_type"] != role_type or run["role_key"] != role_key:
            _reject(conn, agent_run_id, tool_name, role_type, role_key, arguments, idempotency_key, "agent role does not match run")
            raise AgentToolAccessError("agent role metadata does not match the run")

        manifest = get_role_tool_manifest(role_type, role_key)
        if tool_name not in manifest.allowed_tools:
            _reject(conn, agent_run_id, tool_name, role_type, role_key, arguments, idempotency_key, "tool is outside role manifest")
            raise AgentToolAccessError(f"tool is not allowed for {role_type}: {tool_name}")
        if _has_future_evidence_scope(run["target_evidence_date"], arguments):
            _reject(conn, agent_run_id, tool_name, role_type, role_key, arguments, idempotency_key, "future evidence scope")
            raise AgentToolAccessError("tool call requests evidence beyond target_evidence_date")
        if tool_name in manifest.submission_tools and not idempotency_key:
            _reject(conn, agent_run_id, tool_name, role_type, role_key, arguments, idempotency_key, "missing idempotency key")
            raise AgentToolAccessError("submission tool calls require idempotency_key")

        call_id = _audit(conn, agent_run_id, tool_name, role_type, role_key, arguments, idempotency_key, "allowed", None)
        return {"agent_tool_call_id": call_id, "manifest": manifest.to_dict()}


def record_agent_tool_result(
    db_path: str,
    *,
    agent_tool_call_id: int,
    status: str,
    result_summary: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE agent_tool_calls
            SET status = ?,
                result_summary_json = ?,
                error = ?
            WHERE id = ?
            """,
            (status, json.dumps(result_summary or {}, ensure_ascii=False), error, agent_tool_call_id),
        )


def _audit(
    conn: Any,
    agent_run_id: int,
    tool_name: str,
    role_type: str,
    role_key: str,
    arguments: dict[str, Any],
    idempotency_key: str | None,
    status: str,
    error: str | None,
) -> int:
    return insert_agent_tool_call(
        conn,
        {
            "agent_run_id": agent_run_id,
            "tool_name": tool_name,
            "role_type": role_type,
            "role_key": role_key,
            "arguments_json": json.dumps(arguments, ensure_ascii=False),
            "idempotency_key": idempotency_key,
            "status": status,
            "result_summary_json": "{}",
            "error": error,
        },
    )


def _reject(
    conn: Any,
    agent_run_id: int,
    tool_name: str,
    role_type: str,
    role_key: str,
    arguments: dict[str, Any],
    idempotency_key: str | None,
    error: str,
) -> int:
    call_id = _audit(conn, agent_run_id, tool_name, role_type, role_key, arguments, idempotency_key, "rejected", error)
    conn.commit()
    return call_id


def _has_future_evidence_scope(target_evidence_date: str, arguments: dict[str, Any]) -> bool:
    for key in ("date", "end_date", "prediction_date", "brief_date"):
        value = arguments.get(key)
        if value and _date_text(str(value)) > target_evidence_date:
            return True
    end_datetime = arguments.get("end_datetime")
    if end_datetime:
        try:
            return datetime.fromisoformat(str(end_datetime).replace("Z", "+00:00")).date().isoformat() > target_evidence_date
        except ValueError:
            return False
    evidence_scope = arguments.get("evidence_scope")
    if isinstance(evidence_scope, dict):
        end = evidence_scope.get("end_date") or evidence_scope.get("date")
        if end and _date_text(str(end)) > target_evidence_date:
            return True
    return False


def _date_text(value: str) -> str:
    text = value.strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10]
