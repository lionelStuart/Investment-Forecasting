from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationDefaults:
    recipient_key: str | None
    channel: str
    dry_run: bool | None


def notification_defaults(
    *,
    recipient_key: str | None = None,
    channel: str | None = None,
    dry_run: bool | None = None,
) -> NotificationDefaults:
    return NotificationDefaults(
        recipient_key=recipient_key or _env_text("INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY"),
        channel=channel or _env_text("INVESTMENT_FORECASTING_NOTIFICATION_CHANNEL") or "imessage",
        dry_run=dry_run if dry_run is not None else _env_bool("INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN"),
    )


def _env_text(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_bool(name: str) -> bool | None:
    value = _env_text(name)
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "on"}
