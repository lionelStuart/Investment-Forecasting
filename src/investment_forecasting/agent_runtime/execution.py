from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from investment_forecasting.agent_runtime.adapters import CodexCliRuntimeAdapter
from investment_forecasting.agent_runtime.manifests import get_role_tool_manifest
from investment_forecasting.agent_runtime.models import CodexRuntimePolicy
from investment_forecasting.agent_runtime.prompts import (
    EXPERT_AGENT_OUTPUT_SCHEMA,
    JARVIS_AGENT_OUTPUT_SCHEMA,
    render_expert_agent_prompt,
    render_jarvis_agent_prompt,
)
from investment_forecasting.agent_runtime.service import build_launch_request, list_runtime_agent_runs
from investment_forecasting.communication.config import notification_defaults
from investment_forecasting.db import connect, update_agent_run
from investment_forecasting.experts.planning import latest_expert_evidence_date, run_expert_agent_plan_from_output
from investment_forecasting.experts.roster import initialize_default_experts, list_roster
from investment_forecasting.jarvis.synthesis import generate_jarvis_brief
from investment_forecasting.agent_runtime.manifests import record_agent_tool_result, validate_agent_tool_call


def run_expert_codex_agents(
    db_path: str | Path,
    *,
    run_date: str | None = None,
    project_root: str | Path = ".",
    codex_bin: str | None = None,
    timeout_seconds: int = 180,
    expert_key: str | None = None,
) -> dict[str, Any]:
    requested_date = _date_text(run_date) if run_date else date.today().isoformat()
    target_date = latest_expert_evidence_date(db_path, requested_date) or requested_date
    initialize_default_experts(db_path)
    experts = [expert for expert in list_roster(db_path, lifecycle_state="active") if not expert_key or expert["expert_key"] == expert_key]
    adapter = CodexCliRuntimeAdapter(db_path, project_root=project_root, codex_bin=codex_bin)
    readiness = adapter.readiness()
    if not readiness.get("ok"):
        return {"ok": False, "stage": "readiness", "readiness": readiness, "runs": []}

    runs = []
    for expert in experts:
        manifest = get_role_tool_manifest("expert", expert["expert_key"]).to_dict()
        rendered = render_expert_agent_prompt(db_path, expert_key=expert["expert_key"], target_date=target_date)
        request = build_launch_request(
            role_type="expert",
            role_key=expert["expert_key"],
            run_date=target_date,
            target_evidence_date=target_date,
            trigger_reason="expert_agent_daily_execution",
            overview_skill="investment-expert-agent",
            skill_bundle=manifest["skill_bundle"],
            prompt_ref=rendered["prompt_ref"],
            tool_manifest_ref={"kind": "inline", "manifest_hash": f"manual-expert-tools-{expert['expert_key']}"},
            output_contract={"schema_version": "expert_agent_output_v1", "submission_tool": "submit_expert_virtual_action"},
            runtime_policy=CodexRuntimePolicy(timeout_seconds=timeout_seconds, max_tool_calls=8, max_retries=0, require_submission_tool=True),
        )
        handle = adapter.prepare_run(
            request,
            prompt=render_expert_agent_prompt(db_path, expert_key=expert["expert_key"], target_date=target_date, agent_run_id=None)["prompt"],
            output_schema=EXPERT_AGENT_OUTPUT_SCHEMA,
        )
        adapter.start_run(handle.agent_run_id)
        run = _wait_for_artifact(
            adapter,
            db_path,
            handle.agent_run_id,
            role_type="expert",
            role_key=expert["expert_key"],
            timeout_seconds=timeout_seconds,
            submission_tool="submit_expert_virtual_action",
        )
        if run["ok"]:
            try:
                plan = run_expert_agent_plan_from_output(
                    db_path,
                    plan_date=target_date,
                    expert_key=expert["expert_key"],
                    agent_run_id=handle.agent_run_id,
                    agent_output=run["output"],
                )
                run["plan_id"] = plan["id"]
                run["persisted"] = True
                with connect(db_path) as conn:
                    update_agent_run(
                        conn,
                        handle.agent_run_id,
                        status="completed",
                        submission_result={**run, "artifact_paths": run.get("artifact_paths")},
                    )
                run["status"] = "completed"
            except Exception as exc:
                with connect(db_path) as conn:
                    update_agent_run(conn, handle.agent_run_id, status="validation_failed", failure_reason=str(exc))
                run["ok"] = False
                run["status"] = "validation_failed"
                run["error"] = str(exc)
        runs.append(run)
    return {"ok": all(run["ok"] for run in runs), "run_date": target_date, "count": len(runs), "runs": runs}


def run_jarvis_codex_agent(
    db_path: str | Path,
    *,
    run_date: str | None = None,
    target_evidence_date: str | None = None,
    project_root: str | Path = ".",
    codex_bin: str | None = None,
    timeout_seconds: int = 180,
    notify_recipient_key: str | None = None,
    notification_channel: str | None = None,
    notification_dry_run: bool | None = None,
) -> dict[str, Any]:
    jarvis_date = _date_text(run_date) if run_date else date.today().isoformat()
    evidence_date = _date_text(target_evidence_date) if target_evidence_date else (datetime.fromisoformat(jarvis_date).date() - timedelta(days=1)).isoformat()
    notification = notification_defaults(
        recipient_key=notify_recipient_key,
        channel=notification_channel,
        dry_run=notification_dry_run,
    )
    adapter = CodexCliRuntimeAdapter(db_path, project_root=project_root, codex_bin=codex_bin)
    readiness = adapter.readiness()
    if not readiness.get("ok"):
        return {"ok": False, "stage": "readiness", "readiness": readiness, "runs": []}

    manifest = get_role_tool_manifest("jarvis", "jarvis").to_dict()
    expert_status = jarvis_agent_readiness(db_path, evidence_date)
    request = build_launch_request(
        role_type="jarvis",
        role_key="jarvis",
        run_date=jarvis_date,
        target_evidence_date=evidence_date,
        trigger_reason="jarvis_t_plus_one_agent_execution",
        overview_skill="jarvis-daily-agent",
        skill_bundle=manifest["skill_bundle"],
        prompt_ref={"kind": "generated", "prompt_hash": f"jarvis-agent-{jarvis_date}-{evidence_date}", "template": "jarvis_agent_prompt_v1"},
        tool_manifest_ref={"kind": "inline", "manifest_hash": "manual-jarvis-tools"},
        output_contract={"schema_version": "jarvis_agent_output_v1", "submission_tool": "submit_jarvis_daily_brief"},
        runtime_policy=CodexRuntimePolicy(timeout_seconds=timeout_seconds, max_tool_calls=8, max_retries=0, require_submission_tool=True),
    )
    if not expert_status["ready"]:
        handle = adapter.prepare_run(
            request,
            prompt=render_jarvis_agent_prompt(db_path, run_date=jarvis_date, target_evidence_date=evidence_date, readiness=expert_status)["prompt"],
            output_schema=JARVIS_AGENT_OUTPUT_SCHEMA,
        )
        with connect(db_path) as conn:
            update_agent_run(conn, handle.agent_run_id, status="skipped", failure_reason="expert agent evidence is pending", submission_result={"readiness": expert_status})
        return {"ok": False, "stage": "readiness", "run_date": jarvis_date, "target_evidence_date": evidence_date, "expert_runtime_status": expert_status, "runs": [{"ok": False, "agent_run_id": handle.agent_run_id, "status": "skipped"}]}
    handle = adapter.prepare_run(
        request,
        prompt=render_jarvis_agent_prompt(db_path, run_date=jarvis_date, target_evidence_date=evidence_date, readiness=expert_status)["prompt"],
        output_schema=JARVIS_AGENT_OUTPUT_SCHEMA,
    )
    adapter.start_run(handle.agent_run_id)
    run = _wait_for_artifact(
        adapter,
        db_path,
        handle.agent_run_id,
        role_type="jarvis",
        role_key="jarvis",
        timeout_seconds=timeout_seconds,
        submission_tool="submit_jarvis_daily_brief",
    )
    if run["ok"]:
        try:
            brief = generate_jarvis_brief(
                db_path,
                brief_date=jarvis_date,
                target_evidence_date=evidence_date,
                agent_run_id=handle.agent_run_id,
                agent_readiness=expert_status,
                agent_output=run["output"],
                notify_recipient_key=notification.recipient_key,
                notification_channel=notification.channel,
                notification_dry_run=notification.dry_run,
            )
            run["brief_id"] = brief["id"]
            if brief.get("notification"):
                run["notification"] = brief["notification"]
            run["persisted"] = True
            with connect(db_path) as conn:
                update_agent_run(conn, handle.agent_run_id, status="completed", submission_result={**run, "artifact_paths": run.get("artifact_paths")})
            run["status"] = "completed"
        except Exception as exc:
            with connect(db_path) as conn:
                update_agent_run(conn, handle.agent_run_id, status="validation_failed", failure_reason=str(exc))
            run["ok"] = False
            run["status"] = "validation_failed"
            run["error"] = str(exc)
    return {"ok": run["ok"], "run_date": jarvis_date, "target_evidence_date": evidence_date, "expert_runtime_status": expert_status, "runs": [run]}


def jarvis_agent_readiness(db_path: str | Path, target_evidence_date: str) -> dict[str, Any]:
    initialize_default_experts(db_path)
    experts = list_roster(db_path, lifecycle_state="active")
    terminal = {"completed", "skipped", "failed", "validation_failed"}
    statuses: dict[str, str] = {}
    run_ids: dict[str, int] = {}
    for expert in experts:
        rows = [
            row
            for row in list_runtime_agent_runs(db_path, role_type="expert", role_key=expert["expert_key"], limit=10)
            if row["target_evidence_date"] == target_evidence_date and row["trigger_reason"] == "expert_agent_daily_execution"
        ]
        if not rows:
            statuses[expert["expert_key"]] = "missing"
            continue
        latest = rows[0]
        statuses[expert["expert_key"]] = latest["status"]
        run_ids[expert["expert_key"]] = latest["id"]
    pending = {key: value for key, value in statuses.items() if value not in terminal}
    completed = sum(1 for value in statuses.values() if value == "completed")
    degraded = sum(1 for value in statuses.values() if value in {"skipped", "failed", "validation_failed"})
    upstream = _jarvis_upstream_evidence_status(db_path, target_evidence_date)
    return {
        "ready": not pending and len(statuses) == len(experts),
        "status": "complete" if not pending and degraded == 0 else ("degraded" if not pending else "pending"),
        "target_evidence_date": target_evidence_date,
        "active_expert_count": len(experts),
        "completed": completed,
        "degraded": degraded,
        "statuses": statuses,
        "run_ids": run_ids,
        "pending": pending,
        "upstream_evidence_status": upstream,
    }


def _jarvis_upstream_evidence_status(db_path: str | Path, target_evidence_date: str) -> dict[str, Any]:
    required = ("news_hourly_incremental", "market_context_intraday", "price_nav_post_close", "features_post_close", "model_post_close")
    with connect(db_path) as conn:
        rows = {
            row["job_key"]: row
            for row in conn.execute(
                """
                SELECT *
                FROM scheduler_runs
                WHERE substr(scheduled_at, 1, 10) = ?
                  AND job_key IN ('news_hourly_incremental', 'market_context_intraday', 'price_nav_post_close', 'features_post_close', 'model_post_close')
                ORDER BY started_at DESC, id DESC
                """,
                (target_evidence_date,),
            ).fetchall()
        }
    missing = [key for key in required if key not in rows]
    not_success = [key for key, row in rows.items() if row["status"] != "success"]
    readiness_only = []
    for key, row in rows.items():
        metadata = json.loads(row["metadata_json"] or "{}")
        if key == "model_post_close" and not metadata.get("real_model_run"):
            readiness_only.append(key)
        if key in {"news_hourly_incremental", "market_context_intraday", "price_nav_post_close"} and not metadata.get("real_provider_calls"):
            readiness_only.append(key)
        if key == "features_post_close" and not metadata.get("real_calculation") and row["status"] == "success":
            readiness_only.append(key)
    return {
        "ready": not missing and not not_success and not readiness_only,
        "missing_jobs": missing,
        "not_success_jobs": not_success,
        "readiness_only_jobs": sorted(set(readiness_only)),
    }


def _wait_for_artifact(
    adapter: CodexCliRuntimeAdapter,
    db_path: str | Path,
    agent_run_id: int,
    *,
    role_type: str,
    role_key: str,
    timeout_seconds: int,
    submission_tool: str | None = None,
) -> dict[str, Any]:
    metadata = list_runtime_agent_runs(db_path, role_type=role_type, role_key=role_key, limit=1)[0]["runtime_metadata"]
    paths = metadata["artifact_paths"]
    last_message = Path(paths["last_message"])
    stderr_log = Path(paths["stderr_log"])
    deadline = time.time() + max(1, timeout_seconds)
    while time.time() < deadline:
        if last_message.exists() and last_message.read_text(encoding="utf-8").strip():
            raw_output = last_message.read_text(encoding="utf-8").strip()
            try:
                output = json.loads(raw_output)
                if submission_tool:
                    _audit_agent_submission(db_path, agent_run_id, role_type, role_key, submission_tool, output)
            except Exception as exc:
                adapter.cancel_run(agent_run_id, f"{role_type} output validation failed: {exc}")
                return {
                    "ok": False,
                    "agent_run_id": agent_run_id,
                    "role_type": role_type,
                    "role_key": role_key,
                    "status": "validation_failed",
                    "error": str(exc),
                    "last_message": raw_output,
                }
            result = adapter.collect_result(agent_run_id)
            return {
                "ok": result.status == "completed_via_artifact",
                "agent_run_id": agent_run_id,
                "role_type": role_type,
                "role_key": role_key,
                "status": result.status,
                "last_message": result.submission_result.get("last_message"),
                "output": output,
                "artifact_paths": result.submission_result.get("artifact_paths"),
            }
        time.sleep(2)
    adapter.cancel_run(agent_run_id, f"{role_type} Codex execution timed out")
    return {
        "ok": False,
        "agent_run_id": agent_run_id,
        "role_type": role_type,
        "role_key": role_key,
        "status": "timed_out",
        "stderr_tail": stderr_log.read_text(encoding="utf-8")[-2000:] if stderr_log.exists() else "",
    }

def _audit_agent_submission(db_path: str | Path, agent_run_id: int, role_type: str, role_key: str, tool_name: str, output: dict[str, Any]) -> None:
    validation = validate_agent_tool_call(
        str(db_path),
        agent_run_id=agent_run_id,
        role_type=role_type,
        role_key=role_key,
        tool_name=tool_name,
        arguments={
            "agent_run_id": agent_run_id,
            "role_type": role_type,
            "role_key": role_key,
            "idempotency_key": f"{tool_name}:{agent_run_id}",
            "payload": output,
        },
        idempotency_key=f"{tool_name}:{agent_run_id}",
    )
    record_agent_tool_result(
        str(db_path),
        agent_tool_call_id=validation["agent_tool_call_id"],
        status="submitted",
        result_summary={"accepted": True, "payload_keys": sorted(output)},
    )


def _date_text(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value
