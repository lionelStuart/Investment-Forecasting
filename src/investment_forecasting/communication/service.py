from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol


SEVERITY_RANK = {"info": 1, "warning": 2, "critical": 3}
TERMINAL_STATUSES = {"sent", "dry_run", "skipped", "failed", "permission_required", "recipient_not_allowed", "rate_limited"}
UNSAFE_PHRASES = ("保证收益", "保本", "稳赚", "必赚", "guaranteed return", "capital protection")


class CommunicationError(ValueError):
    pass


@dataclass(frozen=True)
class AdapterResult:
    status: str
    provider_message_id: str | None = None
    error: str | None = None
    details: dict[str, Any] | None = None

    def as_json(self) -> str:
        return json.dumps(
            {
                "status": self.status,
                "provider_message_id": self.provider_message_id,
                "error": self.error,
                "details": self.details or {},
            },
            ensure_ascii=False,
        )


class CommunicationAdapter(Protocol):
    def send(self, *, recipient: Any, subject: str | None, body: str, payload_summary: str | None) -> AdapterResult:
        ...


class DryRunAdapter:
    def send(self, *, recipient: Any, subject: str | None, body: str, payload_summary: str | None) -> AdapterResult:
        return AdapterResult(
            status="dry_run",
            details={
                "recipient_key": recipient["recipient_key"],
                "channel": recipient["channel"],
                "subject": subject,
                "body_length": len(body),
                "payload_summary": payload_summary,
            },
        )


class FailingAdapter:
    def __init__(self, error: str = "adapter failure") -> None:
        self.error = error

    def send(self, *, recipient: Any, subject: str | None, body: str, payload_summary: str | None) -> AdapterResult:
        return AdapterResult(status="failed", error=self.error, details={"recipient_key": recipient["recipient_key"]})


def send_outbound_message(
    conn,
    *,
    channel: str,
    recipient_key: str,
    template_key: str,
    body: str,
    subject: str | None = None,
    severity: str = "info",
    payload_summary: str | None = None,
    idempotency_key: str | None = None,
    dry_run: bool | None = None,
    adapter: CommunicationAdapter | None = None,
) -> dict[str, Any]:
    _validate_request(severity, body)
    key = idempotency_key or _idempotency_key(channel, recipient_key, template_key, body)
    duplicate = conn.execute("SELECT * FROM outbound_messages WHERE idempotency_key = ?", (key,)).fetchone()
    if duplicate is not None:
        result = dict(duplicate)
        result["duplicate"] = True
        return result

    recipient = conn.execute("SELECT * FROM communication_recipients WHERE recipient_key = ?", (recipient_key,)).fetchone()
    if recipient is None or recipient["channel"] != channel or not recipient["allowlisted"] or not recipient["enabled"]:
        return _persist_message(
            conn,
            channel=channel,
            recipient=recipient,
            recipient_key=recipient_key,
            template_key=template_key,
            subject=subject,
            body=body,
            severity=severity,
            payload_summary=payload_summary,
            idempotency_key=key,
            result=AdapterResult(status="recipient_not_allowed", error="Recipient is missing, disabled, not allowlisted, or on a different channel."),
        )

    policy_status = _policy_status(conn, recipient, severity)
    if policy_status is not None:
        return _persist_message(
            conn,
            channel=channel,
            recipient=recipient,
            recipient_key=recipient_key,
            template_key=template_key,
            subject=subject,
            body=body,
            severity=severity,
            payload_summary=payload_summary,
            idempotency_key=key,
            result=policy_status,
        )

    config = conn.execute("SELECT * FROM communication_adapter_configs WHERE channel = ?", (channel,)).fetchone()
    effective_dry_run = bool(dry_run) if dry_run is not None else bool(config["dry_run_default"]) if config else True
    if effective_dry_run:
        result = DryRunAdapter().send(recipient=recipient, subject=subject, body=body, payload_summary=payload_summary)
    elif config is None or not config["enabled"]:
        result = AdapterResult(status="failed", error=f"Adapter channel '{channel}' is not enabled.")
    else:
        delivery_adapter = adapter or _default_adapter(channel, config["config_json"])
        result = delivery_adapter.send(recipient=recipient, subject=subject, body=body, payload_summary=payload_summary)

    return _persist_message(
        conn,
        channel=channel,
        recipient=recipient,
        recipient_key=recipient_key,
        template_key=template_key,
        subject=subject,
        body=body,
        severity=severity,
        payload_summary=payload_summary,
        idempotency_key=key,
        result=result,
    )


def _validate_request(severity: str, body: str) -> None:
    if severity not in SEVERITY_RANK:
        raise CommunicationError(f"unsupported severity: {severity}")
    normalized = body.lower()
    if any(phrase in body or phrase in normalized for phrase in UNSAFE_PHRASES):
        raise CommunicationError("message body contains unsafe certainty language")


def _policy_status(conn, recipient: Any, severity: str) -> AdapterResult | None:
    if SEVERITY_RANK[severity] < SEVERITY_RANK[recipient["min_severity"]]:
        return AdapterResult(status="skipped", error="Severity below recipient threshold.")
    limit = int(recipient["rate_limit_per_hour"] or 0)
    if limit <= 0:
        return AdapterResult(status="rate_limited", error="Recipient rate limit is zero.")
    recent_count = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM outbound_messages
        WHERE recipient_key = ?
          AND status IN ('sent', 'dry_run')
          AND requested_at >= datetime('now', '-1 hour')
        """,
        (recipient["recipient_key"],),
    ).fetchone()["count"]
    if recent_count >= limit:
        return AdapterResult(status="rate_limited", error="Recipient hourly rate limit reached.")
    return None


def _persist_message(
    conn,
    *,
    channel: str,
    recipient: Any | None,
    recipient_key: str,
    template_key: str,
    subject: str | None,
    body: str,
    severity: str,
    payload_summary: str | None,
    idempotency_key: str,
    result: AdapterResult,
) -> dict[str, Any]:
    if result.status not in TERMINAL_STATUSES:
        raise CommunicationError(f"unsupported adapter status: {result.status}")
    cursor = conn.execute(
        """
        INSERT INTO outbound_messages(
            channel, recipient_id, recipient_key, template_key, subject, body,
            severity, payload_summary, idempotency_key, status,
            adapter_result_json, error, sent_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 'sent' THEN datetime('now') ELSE NULL END)
        RETURNING *
        """,
        (
            channel,
            recipient["id"] if recipient is not None else None,
            recipient_key,
            template_key,
            subject,
            body,
            severity,
            payload_summary,
            idempotency_key,
            result.status,
            result.as_json(),
            result.error,
            result.status,
        ),
    )
    row = dict(cursor.fetchone())
    row["duplicate"] = False
    return row


def _idempotency_key(channel: str, recipient_key: str, template_key: str, body: str) -> str:
    digest = hashlib.sha256(f"{channel}|{recipient_key}|{template_key}|{body}".encode("utf-8")).hexdigest()
    return f"{channel}:{template_key}:{digest[:24]}"


def _default_adapter(channel: str, config_json: str | None) -> CommunicationAdapter:
    if channel == "imessage":
        from investment_forecasting.communication.imessage import IMessageAdapter

        try:
            return IMessageAdapter.from_config_json(config_json)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return FailingAdapter(f"Invalid iMessage adapter config_json: {exc}")
    return FailingAdapter(f"No delivery adapter is registered for channel '{channel}'.")
