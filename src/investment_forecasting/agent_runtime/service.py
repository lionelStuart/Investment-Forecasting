from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from investment_forecasting.agent_runtime.models import (
    PROTOCOL_VERSION,
    AgentRunHandle,
    CodexAgentLaunchRequest,
    CodexAgentRunResult,
    CodexRuntimePolicy,
    validate_role_type,
    validate_status,
)
from investment_forecasting.db import (
    connect,
    get_agent_run,
    init_db,
    list_agent_runs,
    update_agent_run,
    upsert_agent_run,
)


def build_launch_request(
    *,
    role_type: str,
    role_key: str,
    run_date: str,
    target_evidence_date: str,
    trigger_reason: str,
    overview_skill: str,
    skill_bundle: list[str],
    prompt_ref: dict[str, Any],
    tool_manifest_ref: dict[str, Any],
    output_contract: dict[str, Any],
    runtime_policy: CodexRuntimePolicy | None = None,
    agent_run_id: int | None = None,
) -> CodexAgentLaunchRequest:
    validate_role_type(role_type)
    return CodexAgentLaunchRequest(
        agent_run_id=agent_run_id,
        role_type=role_type,  # type: ignore[arg-type]
        role_key=role_key,
        run_date=run_date,
        target_evidence_date=target_evidence_date,
        trigger_reason=trigger_reason,
        overview_skill=overview_skill,
        skill_bundle=skill_bundle,
        prompt_ref=prompt_ref,
        tool_manifest_ref=tool_manifest_ref,
        output_contract=output_contract,
        runtime_policy=runtime_policy or CodexRuntimePolicy(),
    )


def create_or_prepare_agent_run(db_path: str | Path, request: CodexAgentLaunchRequest) -> AgentRunHandle:
    init_db(db_path)
    with connect(db_path) as conn:
        run_id = upsert_agent_run(conn, _run_record_from_request(request))
        materialized = _with_agent_run_id(request, run_id)
        update_agent_run(conn, run_id, launch_request=materialized.to_dict())
        row = get_agent_run(conn, run_id)
        return AgentRunHandle(agent_run_id=run_id, status=str(row["status"]), runtime_metadata=_json(row["runtime_metadata_json"]))


def start_agent_run(
    db_path: str | Path,
    agent_run_id: int,
    *,
    runtime_metadata: dict[str, Any] | None = None,
) -> AgentRunHandle:
    with connect(db_path) as conn:
        update_agent_run(
            conn,
            agent_run_id,
            status="running",
            runtime_metadata={"adapter": "fake", **(runtime_metadata or {})},
        )
        row = get_agent_run(conn, agent_run_id)
        return AgentRunHandle(agent_run_id=agent_run_id, status=str(row["status"]), runtime_metadata=_json(row["runtime_metadata_json"]))


def complete_agent_run(
    db_path: str | Path,
    agent_run_id: int,
    *,
    status: str = "completed",
    output: dict[str, Any] | None = None,
    submission_result: dict[str, Any] | None = None,
) -> CodexAgentRunResult:
    validate_status(status)
    with connect(db_path) as conn:
        update_agent_run(
            conn,
            agent_run_id,
            status=status,
            submission_result=submission_result or output or {"status": status},
        )
        row = get_agent_run(conn, agent_run_id)
        return CodexAgentRunResult(
            agent_run_id=agent_run_id,
            status=str(row["status"]),
            output=output or {},
            submission_result=_json(row["submission_result_json"]),
        )


def fail_agent_run(db_path: str | Path, agent_run_id: int, *, error: str, status: str = "failed") -> CodexAgentRunResult:
    validate_status(status)
    with connect(db_path) as conn:
        update_agent_run(conn, agent_run_id, status=status, failure_reason=error)
        row = get_agent_run(conn, agent_run_id)
        return CodexAgentRunResult(agent_run_id=agent_run_id, status=str(row["status"]), failure_reason=row["failure_reason"])


def cancel_agent_run(db_path: str | Path, agent_run_id: int, *, reason: str) -> AgentRunHandle:
    with connect(db_path) as conn:
        update_agent_run(conn, agent_run_id, status="cancelled", failure_reason=reason)
        row = get_agent_run(conn, agent_run_id)
        return AgentRunHandle(agent_run_id=agent_run_id, status=str(row["status"]), runtime_metadata=_json(row["runtime_metadata_json"]))


def collect_agent_run_result(db_path: str | Path, agent_run_id: int) -> CodexAgentRunResult:
    with connect(db_path) as conn:
        row = get_agent_run(conn, agent_run_id)
        if row is None:
            raise ValueError(f"agent run not found: {agent_run_id}")
        return CodexAgentRunResult(
            agent_run_id=agent_run_id,
            status=str(row["status"]),
            submission_result=_json(row["submission_result_json"]),
            failure_reason=row["failure_reason"],
        )


def list_runtime_agent_runs(
    db_path: str | Path,
    *,
    role_type: str | None = None,
    role_key: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = list_agent_runs(conn, role_type=role_type, role_key=role_key, status=status, limit=limit)
        return [_row_to_dict(row) for row in rows]


def _run_record_from_request(request: CodexAgentLaunchRequest) -> dict[str, Any]:
    request_data = request.to_dict()
    return {
        "role_type": request.role_type,
        "role_key": request.role_key,
        "run_date": request.run_date,
        "target_evidence_date": request.target_evidence_date,
        "version": request.protocol_version,
        "trigger_reason": request.trigger_reason,
        "status": "pending",
        "overview_skill": request.overview_skill,
        "skill_bundle_json": json.dumps(request.skill_bundle, ensure_ascii=False),
        "prompt_ref_json": json.dumps(request.prompt_ref, ensure_ascii=False),
        "tool_manifest_ref_json": json.dumps(request.tool_manifest_ref, ensure_ascii=False),
        "output_contract_json": json.dumps(request.output_contract, ensure_ascii=False),
        "runtime_policy_json": json.dumps(request.runtime_policy.to_dict(), ensure_ascii=False),
        "launch_request_json": json.dumps(request_data, ensure_ascii=False),
        "idempotency_key": _idempotency_key(request),
    }


def _with_agent_run_id(request: CodexAgentLaunchRequest, agent_run_id: int) -> CodexAgentLaunchRequest:
    return build_launch_request(
        role_type=request.role_type,
        role_key=request.role_key,
        run_date=request.run_date,
        target_evidence_date=request.target_evidence_date,
        trigger_reason=request.trigger_reason,
        overview_skill=request.overview_skill,
        skill_bundle=request.skill_bundle,
        prompt_ref=request.prompt_ref,
        tool_manifest_ref=request.tool_manifest_ref,
        output_contract=request.output_contract,
        runtime_policy=request.runtime_policy,
        agent_run_id=agent_run_id,
    )


def _idempotency_key(request: CodexAgentLaunchRequest) -> str:
    raw = "|".join(
        [
            PROTOCOL_VERSION,
            request.role_type,
            request.role_key,
            request.run_date,
            request.target_evidence_date,
            request.protocol_version,
        ]
    )
    return "agent_run:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    for key in (
        "skill_bundle_json",
        "prompt_ref_json",
        "tool_manifest_ref_json",
        "output_contract_json",
        "runtime_policy_json",
        "launch_request_json",
        "runtime_metadata_json",
        "submission_result_json",
    ):
        data[key.replace("_json", "")] = json.loads(data.pop(key) or "{}")
    return data
