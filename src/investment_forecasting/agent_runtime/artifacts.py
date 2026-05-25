from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from investment_forecasting.agent_runtime.models import CodexAgentLaunchRequest


DEFAULT_RUNTIME_ROOT = Path("data/agent_runtime")


@dataclass(frozen=True)
class AgentRunArtifactPaths:
    run_dir: Path
    request_json: Path
    prompt_md: Path
    output_schema_json: Path
    events_jsonl: Path
    last_message: Path
    stderr_log: Path
    result_json: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "run_dir": str(self.run_dir),
            "request_json": str(self.request_json),
            "prompt_md": str(self.prompt_md),
            "output_schema_json": str(self.output_schema_json),
            "events_jsonl": str(self.events_jsonl),
            "last_message": str(self.last_message),
            "stderr_log": str(self.stderr_log),
            "result_json": str(self.result_json),
        }


def artifact_paths(project_root: str | Path, agent_run_id: int, runtime_root: str | Path = DEFAULT_RUNTIME_ROOT) -> AgentRunArtifactPaths:
    root = Path(project_root)
    base = Path(runtime_root)
    if not base.is_absolute():
        base = root / base
    run_dir = base / "runs" / str(agent_run_id)
    return AgentRunArtifactPaths(
        run_dir=run_dir,
        request_json=run_dir / "request.json",
        prompt_md=run_dir / "prompt.md",
        output_schema_json=run_dir / "output_schema.json",
        events_jsonl=run_dir / "events.jsonl",
        last_message=run_dir / "last_message.txt",
        stderr_log=run_dir / "stderr.log",
        result_json=run_dir / "result.json",
    )


def prepare_artifacts(
    project_root: str | Path,
    request: CodexAgentLaunchRequest,
    *,
    agent_run_id: int,
    prompt: str,
    output_schema: dict[str, Any] | None = None,
    runtime_root: str | Path = DEFAULT_RUNTIME_ROOT,
) -> dict[str, Any]:
    paths = artifact_paths(project_root, agent_run_id, runtime_root)
    paths.run_dir.mkdir(parents=True, exist_ok=True)
    request_payload = request.to_dict()
    request_payload["agent_run_id"] = agent_run_id
    _write_json(paths.request_json, request_payload)
    paths.prompt_md.write_text(prompt, encoding="utf-8")
    _write_json(paths.output_schema_json, output_schema or _default_output_schema())
    # A role/date run is idempotent in the database, so reruns may reuse the
    # same agent_run_id. Clear output artifacts before launching a new process
    # to avoid reading stale last_message content from an earlier prompt/schema.
    for output_path in (paths.events_jsonl, paths.last_message, paths.stderr_log, paths.result_json):
        output_path.write_text("", encoding="utf-8")
    return {
        "artifact_paths": paths.to_dict(),
        "prompt_hash": _sha256_file(paths.prompt_md),
        "request_hash": _sha256_file(paths.request_json),
        "output_schema_hash": _sha256_file(paths.output_schema_json),
    }


def default_prompt_from_request(request: CodexAgentLaunchRequest) -> str:
    return "\n".join(
        [
            f"你是 Investment Forecasting 项目的 {request.role_type} agent。",
            "请严格使用系统提供的 MCP/API 工具和输出契约，不要直接写 SQLite，不要抓取 WebUI，不要用 shell 修改产品状态。",
            "如果缺少工具或证据，请输出结构化的 blocked/failed 原因，不要编造市场事实。",
            "",
            "运行请求 JSON:",
            json.dumps(request.to_dict(), ensure_ascii=False, indent=2),
        ]
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _default_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "status": {"type": "string"},
            "summary": {"type": "string"},
            "tool_requests": {"type": "array"},
            "submission": {"type": "object"},
            "blocked_reason": {"type": "string"},
        },
    }
