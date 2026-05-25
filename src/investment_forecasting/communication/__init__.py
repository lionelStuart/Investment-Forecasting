"""Channel-neutral outbound communication services."""

from investment_forecasting.communication.service import (
    AdapterResult,
    CommunicationError,
    DryRunAdapter,
    FailingAdapter,
    send_outbound_message,
)
from investment_forecasting.communication.templates import (
    RenderedNotification,
    render_daily_failure,
    render_daily_success,
    render_expert_plan_ready,
    render_expert_probation,
    render_expert_retirement,
    render_jarvis_daily_summary,
    render_provider_warning,
    send_rendered_notification,
)

__all__ = [
    "AdapterResult",
    "CommunicationError",
    "DryRunAdapter",
    "FailingAdapter",
    "RenderedNotification",
    "render_daily_failure",
    "render_daily_success",
    "render_expert_plan_ready",
    "render_expert_probation",
    "render_expert_retirement",
    "render_jarvis_daily_summary",
    "render_provider_warning",
    "send_outbound_message",
    "send_rendered_notification",
]
