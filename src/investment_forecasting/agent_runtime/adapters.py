from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from investment_forecasting.agent_runtime.artifacts import DEFAULT_RUNTIME_ROOT, default_prompt_from_request, prepare_artifacts
from investment_forecasting.agent_runtime.models import AgentRunHandle, CodexAgentLaunchRequest, CodexAgentRunResult
from investment_forecasting.agent_runtime.service import (
    cancel_agent_run,
    collect_agent_run_result,
    complete_agent_run,
    create_or_prepare_agent_run,
    fail_agent_run,
    start_agent_run,
)
from investment_forecasting.db import connect, get_agent_run, update_agent_run


Runner = Callable[..., subprocess.Popen[str]]
CompletedRunner = Callable[..., subprocess.CompletedProcess[str]]


class FakeCodexRuntimeAdapter:
    """Test double for the system-owned Codex runtime boundary."""

    def __init__(self, db_path: str | Path, *, terminal_status: str = "completed", output: dict[str, Any] | None = None) -> None:
        self.db_path = Path(db_path)
        self.terminal_status = terminal_status
        self.output = output or {"source": "fake_codex_runtime"}

    def prepare_run(self, request: CodexAgentLaunchRequest) -> AgentRunHandle:
        return create_or_prepare_agent_run(self.db_path, request)

    def start_run(self, agent_run_id: int) -> AgentRunHandle:
        return start_agent_run(self.db_path, agent_run_id, runtime_metadata={"runtime": "fake_codex"})

    def poll_run(self, agent_run_id: int) -> AgentRunHandle:
        result = collect_agent_run_result(self.db_path, agent_run_id)
        return AgentRunHandle(agent_run_id=agent_run_id, status=result.status)

    def cancel_run(self, agent_run_id: int, reason: str) -> AgentRunHandle:
        return cancel_agent_run(self.db_path, agent_run_id, reason=reason)

    def collect_result(self, agent_run_id: int) -> CodexAgentRunResult:
        if self.terminal_status in {"failed", "timed_out", "validation_failed"}:
            return fail_agent_run(self.db_path, agent_run_id, error=f"fake runtime {self.terminal_status}", status=self.terminal_status)
        return complete_agent_run(self.db_path, agent_run_id, status=self.terminal_status, output=self.output)


class CodexCliRuntimeAdapter:
    """Local Codex CLI runtime adapter for audited expert/Jarvis agent runs."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        project_root: str | Path = ".",
        codex_bin: str | None = None,
        runtime_root: str | Path = DEFAULT_RUNTIME_ROOT,
        runner: Runner | None = None,
        completed_runner: CompletedRunner | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.project_root = Path(project_root).resolve()
        self.codex_bin = codex_bin or os.environ.get("INVESTMENT_FORECASTING_CODEX_BIN") or "codex"
        self.runtime_root = runtime_root
        self.runner = runner or subprocess.Popen
        self.completed_runner = completed_runner or subprocess.run

    def readiness(self) -> dict[str, Any]:
        executable = shutil.which(self.codex_bin)
        login = self._login_status()
        return {
            "ok": bool(executable) and login["ok"],
            "codex_bin": self.codex_bin,
            "resolved_bin": executable,
            "project_root": str(self.project_root),
            "runtime_root": str(self.runtime_root),
            "login": login,
        }

    def prepare_run(
        self,
        request: CodexAgentLaunchRequest,
        *,
        prompt: str | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> AgentRunHandle:
        handle = create_or_prepare_agent_run(self.db_path, request)
        prepared = prepare_artifacts(
            self.project_root,
            request,
            agent_run_id=handle.agent_run_id,
            prompt=prompt or default_prompt_from_request(request),
            output_schema=output_schema,
            runtime_root=self.runtime_root,
        )
        with connect(self.db_path) as conn:
            update_agent_run(conn, handle.agent_run_id, runtime_metadata={"adapter": "codex_cli", **prepared})
        return AgentRunHandle(agent_run_id=handle.agent_run_id, status=handle.status, runtime_metadata={"adapter": "codex_cli", **prepared})

    def start_run(self, agent_run_id: int) -> AgentRunHandle:
        with connect(self.db_path) as conn:
            row = get_agent_run(conn, agent_run_id)
            if row is None:
                raise ValueError(f"agent run not found: {agent_run_id}")
            metadata = _json(row["runtime_metadata_json"])
            paths = metadata.get("artifact_paths") or {}
            if not paths:
                raise RuntimeError("agent run is missing prepared artifact paths")
            launch_request = _json(row["launch_request_json"])
            runtime_policy = launch_request.get("runtime_policy") or {}
            prompt_text = Path(paths["prompt_md"]).read_text(encoding="utf-8")
            command = self._command(runtime_policy, paths, prompt_text, row=row, launch_request=launch_request)
            events_file = open(paths["events_jsonl"], "a", encoding="utf-8")
            stderr_file = open(paths["stderr_log"], "a", encoding="utf-8")
            process = self.runner(
                command,
                cwd=self.project_root,
                stdout=events_file,
                stderr=stderr_file,
                text=True,
            )
            update_agent_run(
                conn,
                agent_run_id,
                status="running",
                runtime_metadata={
                    **metadata,
                    "adapter": "codex_cli",
                    "pid": process.pid,
                    "started_monotonic": time.monotonic(),
                    "command": _redacted_command(command),
                },
            )
            return AgentRunHandle(agent_run_id=agent_run_id, status="running", runtime_metadata={"pid": process.pid, "adapter": "codex_cli"})

    def poll_run(self, agent_run_id: int) -> AgentRunHandle:
        result = collect_agent_run_result(self.db_path, agent_run_id)
        metadata = _agent_metadata(self.db_path, agent_run_id)
        pid = metadata.get("pid")
        if result.status == "running" and pid and not _pid_is_alive(int(pid)):
            return AgentRunHandle(agent_run_id=agent_run_id, status="completed_via_artifact", runtime_metadata=metadata)
        return AgentRunHandle(agent_run_id=agent_run_id, status=result.status, runtime_metadata=metadata)

    def cancel_run(self, agent_run_id: int, reason: str) -> AgentRunHandle:
        metadata = _agent_metadata(self.db_path, agent_run_id)
        pid = metadata.get("pid")
        if pid and _pid_is_alive(int(pid)):
            os.kill(int(pid), signal.SIGTERM)
        return cancel_agent_run(self.db_path, agent_run_id, reason=reason)

    def collect_result(self, agent_run_id: int) -> CodexAgentRunResult:
        metadata = _agent_metadata(self.db_path, agent_run_id)
        paths = metadata.get("artifact_paths") or {}
        last_message_path = Path(paths.get("last_message", ""))
        if not last_message_path.exists():
            return fail_agent_run(self.db_path, agent_run_id, error="Codex CLI did not produce last_message artifact", status="failed")
        output = {
            "last_message_path": str(last_message_path),
            "last_message": last_message_path.read_text(encoding="utf-8"),
            "artifact_paths": paths,
        }
        return complete_agent_run(self.db_path, agent_run_id, status="completed_via_artifact", output=output)

    def _command(
        self,
        runtime_policy: dict[str, Any],
        paths: dict[str, str],
        prompt_text: str,
        *,
        row: Any | None = None,
        launch_request: dict[str, Any] | None = None,
    ) -> list[str]:
        command = [
            self.codex_bin,
            "--cd",
            str(self.project_root),
        ]
        model = runtime_policy.get("model") or os.environ.get("INVESTMENT_FORECASTING_CODEX_MODEL")
        if model:
            command[1:1] = ["--model", str(model)]
        if runtime_policy.get("bypass_approvals_and_sandbox"):
            command.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            command.extend(
                [
                    "--ask-for-approval",
                    str(runtime_policy.get("approval_policy") or "never"),
                    "--sandbox",
                    str(runtime_policy.get("sandbox") or "workspace-write"),
                ]
            )
        command.extend(self._mcp_config_args(row=row, launch_request=launch_request))
        command.extend(
            [
                "exec",
                "--json",
                "--output-schema",
                paths["output_schema_json"],
                "--output-last-message",
                paths["last_message"],
                prompt_text,
            ]
        )
        return command

    def _mcp_config_args(self, *, row: Any | None, launch_request: dict[str, Any] | None) -> list[str]:
        if os.environ.get("INVESTMENT_FORECASTING_CODEX_MCP_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
            return []
        if row is None or launch_request is None:
            return []
        role_type = str(launch_request.get("role_type") or row["role_type"])
        role_key = str(launch_request.get("role_key") or row["role_key"])
        agent_run_id = int(row["id"])
        server_name = "investment_forecasting_agent"
        db_path = str(self.db_path.resolve())
        src_path = str((self.project_root / "src").resolve())
        args = [
            "-m",
            "investment_forecasting.cli",
            "mcp",
            "serve",
            "--db",
            db_path,
            "--transport",
            "stdio",
            "--role-scoped",
            "--agent-run-id",
            str(agent_run_id),
            "--role-type",
            role_type,
            "--role-key",
            role_key,
        ]
        env = {
            "PYTHONPATH": src_path,
            "INVESTMENT_FORECASTING_DB": db_path,
        }
        return [
            "-c",
            f"mcp_servers.{server_name}.command={json.dumps(sys.executable)}",
            "-c",
            f"mcp_servers.{server_name}.args={json.dumps(args)}",
            "-c",
            f"mcp_servers.{server_name}.env={_toml_inline_table(env)}",
        ]

    def _login_status(self) -> dict[str, Any]:
        try:
            result = self.completed_runner(
                [self.codex_bin, "login", "status"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        return {"ok": result.returncode == 0, "returncode": result.returncode, "output": output[:1000]}


def _agent_metadata(db_path: str | Path, agent_run_id: int) -> dict[str, Any]:
    with connect(db_path) as conn:
        row = get_agent_run(conn, agent_run_id)
        if row is None:
            raise ValueError(f"agent run not found: {agent_run_id}")
        return _json(row["runtime_metadata_json"])


def _json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _redacted_command(command: list[str]) -> list[str]:
    if not command:
        return []
    return [*command[:-1], "<prompt>"]


def _toml_inline_table(values: dict[str, str]) -> str:
    items = ", ".join(f"{key}={json.dumps(value)}" for key, value in sorted(values.items()))
    return "{" + items + "}"
