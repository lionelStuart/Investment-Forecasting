from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


PROTOCOL_VERSION = "codex_agent_runtime_v1"
AGENT_ROLE_TYPES = ("expert", "jarvis")
AGENT_RUN_STATUSES = (
    "pending",
    "running",
    "completed",
    "failed",
    "submitted",
    "completed_via_artifact",
    "skipped",
    "validation_failed",
    "cancelled",
    "timed_out",
)

AgentRoleType = Literal["expert", "jarvis"]
AgentRunStatusValue = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "submitted",
    "completed_via_artifact",
    "skipped",
    "validation_failed",
    "cancelled",
    "timed_out",
]


@dataclass(frozen=True)
class CodexRuntimePolicy:
    timeout_seconds: int = 900
    max_tool_calls: int = 40
    max_retries: int = 1
    require_submission_tool: bool = True
    model: str | None = None
    approval_policy: str = "never"
    sandbox: str = "workspace-write"
    bypass_approvals_and_sandbox: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CodexAgentLaunchRequest:
    agent_run_id: int | None
    role_type: AgentRoleType
    role_key: str
    run_date: str
    target_evidence_date: str
    trigger_reason: str
    overview_skill: str
    skill_bundle: list[str]
    prompt_ref: dict[str, Any]
    tool_manifest_ref: dict[str, Any]
    output_contract: dict[str, Any]
    runtime_policy: CodexRuntimePolicy = field(default_factory=CodexRuntimePolicy)
    protocol_version: str = PROTOCOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["runtime_policy"] = self.runtime_policy.to_dict()
        return data


@dataclass(frozen=True)
class AgentRunHandle:
    agent_run_id: int
    status: str
    runtime_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CodexAgentRunResult:
    agent_run_id: int
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    submission_result: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_role_type(role_type: str) -> None:
    if role_type not in AGENT_ROLE_TYPES:
        raise ValueError(f"unsupported agent role_type: {role_type}")


def validate_status(status: str) -> None:
    if status not in AGENT_RUN_STATUSES:
        raise ValueError(f"unsupported agent run status: {status}")
