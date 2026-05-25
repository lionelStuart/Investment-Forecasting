from __future__ import annotations

import json
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from investment_forecasting.communication.service import AdapterResult


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class IMessageConfig:
    service_type: str = "iMessage"
    timeout_seconds: int = 10

    @classmethod
    def from_json(cls, config_json: str | None) -> "IMessageConfig":
        if not config_json:
            return cls()
        raw = json.loads(config_json)
        return cls(
            service_type=str(raw.get("service_type") or raw.get("service_name") or "iMessage"),
            timeout_seconds=int(raw.get("timeout_seconds") or 10),
        )


class IMessageAdapter:
    def __init__(
        self,
        *,
        config: IMessageConfig | None = None,
        runner: Runner | None = None,
        run_system_preflight: bool = True,
    ) -> None:
        self.config = config or IMessageConfig()
        self.runner = runner or subprocess.run
        self.run_system_preflight = run_system_preflight

    @classmethod
    def from_config_json(cls, config_json: str | None) -> "IMessageAdapter":
        return cls(config=IMessageConfig.from_json(config_json))

    def send(self, *, recipient: Any, subject: str | None, body: str, payload_summary: str | None) -> AdapterResult:
        if self.run_system_preflight:
            preflight = system_preflight()
            if not preflight["ok"]:
                return AdapterResult(
                    status=preflight["status"],
                    error=preflight["error"],
                    details={"checks": preflight["checks"], "recipient_key": recipient["recipient_key"]},
                )

        script = build_imessage_applescript(
            address=recipient["address"],
            body=body,
            service_type=self.config.service_type,
        )
        try:
            completed = self.runner(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return AdapterResult(
                status="failed",
                error=f"iMessage send timed out after {self.config.timeout_seconds}s.",
                details={"recipient_key": recipient["recipient_key"], "timeout": exc.timeout},
            )
        except OSError as exc:
            return AdapterResult(status="failed", error=f"Failed to execute osascript: {exc}")

        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        if completed.returncode == 0:
            return AdapterResult(
                status="sent",
                details={
                    "recipient_key": recipient["recipient_key"],
                    "channel": recipient["channel"],
                    "service_type": self.config.service_type,
                    "stdout": stdout,
                    "payload_summary": payload_summary,
                    "body_length": len(body),
                },
            )

        status = "permission_required" if _looks_like_permission_error(stderr) else "failed"
        return AdapterResult(
            status=status,
            error=stderr or f"osascript exited with code {completed.returncode}",
            details={
                "recipient_key": recipient["recipient_key"],
                "returncode": completed.returncode,
                "stdout": stdout,
                "service_type": self.config.service_type,
            },
        )


def verify_imessage_setup(
    conn,
    *,
    recipient_key: str,
    channel: str = "imessage",
    run_system_probe: bool = True,
) -> dict[str, Any]:
    config = conn.execute("SELECT * FROM communication_adapter_configs WHERE channel = ?", (channel,)).fetchone()
    recipient = conn.execute("SELECT * FROM communication_recipients WHERE recipient_key = ?", (recipient_key,)).fetchone()
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "name": "adapter_config_enabled",
            "ok": bool(config and config["enabled"]),
            "detail": "Adapter config exists and is enabled." if config and config["enabled"] else "Run configure-adapter with --enabled before real sends.",
        }
    )
    checks.append(
        {
            "name": "recipient_allowlisted",
            "ok": bool(recipient and recipient["channel"] == channel and recipient["allowlisted"] and recipient["enabled"]),
            "detail": "Recipient is enabled and allowlisted." if recipient else "Recipient is missing.",
        }
    )
    if recipient and recipient["channel"] != channel:
        checks[-1]["detail"] = f"Recipient channel is {recipient['channel']}, not {channel}."
    elif recipient and not recipient["allowlisted"]:
        checks[-1]["detail"] = "Recipient exists but is not allowlisted."
    elif recipient and not recipient["enabled"]:
        checks[-1]["detail"] = "Recipient exists but is disabled."

    if run_system_probe:
        checks.extend(system_preflight()["checks"])
    else:
        checks.append({"name": "system_probe", "ok": True, "detail": "Skipped by request."})

    ok = all(check["ok"] for check in checks)
    status = "verified" if ok else "blocked"
    error = None if ok else "; ".join(check["detail"] for check in checks if not check["ok"])
    conn.execute(
        """
        UPDATE communication_adapter_configs
        SET setup_status = ?, last_verified_at = datetime('now'), last_error = ?, updated_at = datetime('now')
        WHERE channel = ?
        """,
        (status, error, channel),
    )
    return {
        "channel": channel,
        "recipient_key": recipient_key,
        "ok": ok,
        "status": status,
        "checks": checks,
        "error": error,
    }


def system_preflight() -> dict[str, Any]:
    checks = [
        {
            "name": "macos",
            "ok": platform.system() == "Darwin",
            "detail": "Running on macOS." if platform.system() == "Darwin" else "iMessage adapter requires macOS Messages.",
        },
        {
            "name": "osascript",
            "ok": shutil.which("osascript") is not None,
            "detail": "osascript is available." if shutil.which("osascript") else "osascript command was not found.",
        },
    ]
    ok = all(check["ok"] for check in checks)
    return {
        "ok": ok,
        "status": "failed" if not ok else "sent",
        "error": None if ok else "; ".join(check["detail"] for check in checks if not check["ok"]),
        "checks": checks,
    }


def build_imessage_applescript(*, address: str, body: str, service_type: str = "iMessage") -> str:
    escaped_address = _applescript_string(address)
    escaped_body = _applescript_string(body)
    service_selector = "iMessage" if service_type == "iMessage" else _applescript_string(service_type)
    return "\n".join(
        [
            'tell application "Messages"',
            f"  set targetService to first service whose service type = {service_selector}",
            f"  set targetBuddy to buddy {escaped_address} of targetService",
            f"  send {escaped_body} to targetBuddy",
            "end tell",
        ]
    )


def _applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _looks_like_permission_error(stderr: str) -> bool:
    normalized = stderr.lower()
    permission_markers = ("not authorized", "not authorised", "-1743", "automation", "tcc", "permission")
    return any(marker in normalized for marker in permission_markers)
