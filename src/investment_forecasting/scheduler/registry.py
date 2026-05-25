from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class SchedulerJobDefinition:
    job_key: str
    job_type: str
    cadence: str
    enabled: bool
    provider_key: str | None
    time_window: dict[str, Any]
    policy: dict[str, Any] = field(default_factory=dict)
    description: str = ""


DEFAULT_JOB_DEFINITIONS: tuple[SchedulerJobDefinition, ...] = (
    SchedulerJobDefinition(
        job_key="news_hourly_incremental",
        job_type="news_incremental",
        cadence="hourly",
        enabled=True,
        provider_key="news",
        time_window={"fixed_minute": 5, "timezone": "Asia/Shanghai"},
        policy={
            "window_minutes": 65,
            "request_cap": 200,
            "hourly_request_budget": 240,
            "daily_request_budget": 1200,
            "min_delay_seconds": 1,
            "jitter_seconds": 1,
            "backoff_minutes": 30,
            "sources": ["sina"],
            "watermark_scope": "source",
        },
        description="每小时固定在 :05 补齐资讯增量窗口。",
    ),
    SchedulerJobDefinition(
        job_key="market_context_intraday",
        job_type="market_context_incremental",
        cadence="fixed_times",
        enabled=True,
        provider_key="akshare",
        time_window={"fixed_times": ["09:45", "10:45", "11:45", "13:45", "14:45", "15:20"], "weekdays_only": True, "timezone": "Asia/Shanghai"},
        policy={
            "request_cap": 40,
            "hourly_request_budget": 80,
            "daily_request_budget": 500,
            "min_delay_seconds": 2,
            "jitter_seconds": 2,
            "backoff_minutes": 45,
            "watermark_scope": "market_context",
            "stock_limit": 20,
        },
        description="交易日固定时点同步轻量市场上下文和资金流，不拉全量历史。",
    ),
    SchedulerJobDefinition(
        job_key="price_nav_post_close",
        job_type="price_nav_incremental",
        cadence="daily",
        enabled=True,
        provider_key="akshare",
        time_window={"fixed_time": "17:30", "weekdays_only": True, "timezone": "Asia/Shanghai"},
        policy={
            "request_cap": 500,
            "hourly_request_budget": 600,
            "daily_request_budget": 2000,
            "min_delay_seconds": 2,
            "jitter_seconds": 3,
            "backoff_minutes": 60,
            "watermark_scope": "asset",
        },
        description="收盘后固定同步落后的行情/NAV 增量。",
    ),
    SchedulerJobDefinition(
        job_key="features_post_close",
        job_type="features_incremental",
        cadence="daily",
        enabled=True,
        provider_key="system",
        time_window={"fixed_time": "18:10", "weekdays_only": True, "timezone": "Asia/Shanghai"},
        policy={"request_cap": 0, "watermark_scope": "asset"},
        description="行情补齐后固定计算受影响资产的特征。",
    ),
    SchedulerJobDefinition(
        job_key="model_post_close",
        job_type="model_post_close",
        cadence="daily",
        enabled=True,
        provider_key="system",
        time_window={"fixed_time": "18:40", "weekdays_only": True, "timezone": "Asia/Shanghai"},
        policy={"request_cap": 0, "requires": ["price_nav_post_close", "features_post_close"]},
        description="特征就绪后固定运行预测、可靠性、监控和建议准备。",
    ),
    SchedulerJobDefinition(
        job_key="expert_t_day_agents",
        job_type="expert_agents",
        cadence="daily",
        enabled=False,
        provider_key="codex",
        time_window={"fixed_time": "20:00", "weekdays_only": True, "timezone": "Asia/Shanghai"},
        policy={"requires": ["model_post_close"], "readiness_gate": "t_market_model_evidence"},
        description="T 日晚间专家 agent 触发定义，默认关闭，等待 TASK-089 编排启用。",
    ),
    SchedulerJobDefinition(
        job_key="jarvis_t_plus_one",
        job_type="jarvis_agent",
        cadence="daily",
        enabled=False,
        provider_key="codex",
        time_window={"fixed_time": "08:00", "timezone": "Asia/Shanghai"},
        policy={"requires": ["expert_t_day_agents"], "readiness_gate": "expert_t_terminal"},
        description="T+1 早间 Jarvis agent 触发定义，默认关闭，等待 TASK-089 编排启用。",
    ),
)


def next_run_after(definition: SchedulerJobDefinition | dict[str, Any], after: datetime) -> datetime:
    cadence = definition.cadence if isinstance(definition, SchedulerJobDefinition) else definition["cadence"]
    window = definition.time_window if isinstance(definition, SchedulerJobDefinition) else definition["time_window"]
    if cadence == "hourly":
        return _next_hourly(after, int(window.get("fixed_minute", 0)))
    if cadence == "daily":
        return _next_daily(after, str(window["fixed_time"]), bool(window.get("weekdays_only")))
    if cadence == "fixed_times":
        return _next_fixed_time(after, list(window["fixed_times"]), bool(window.get("weekdays_only")))
    raise ValueError(f"unsupported scheduler cadence: {cadence}")


def _next_hourly(after: datetime, fixed_minute: int) -> datetime:
    candidate = after.replace(minute=fixed_minute, second=0, microsecond=0)
    if candidate <= after:
        candidate += timedelta(hours=1)
    return candidate


def _next_daily(after: datetime, fixed_time: str, weekdays_only: bool) -> datetime:
    hour, minute = _parse_hhmm(fixed_time)
    candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= after:
        candidate += timedelta(days=1)
    while weekdays_only and candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _next_fixed_time(after: datetime, fixed_times: list[str], weekdays_only: bool) -> datetime:
    for fixed_time in sorted(fixed_times):
        hour, minute = _parse_hhmm(fixed_time)
        candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > after and (not weekdays_only or candidate.weekday() < 5):
            return candidate
    tomorrow = after.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    while weekdays_only and tomorrow.weekday() >= 5:
        tomorrow += timedelta(days=1)
    hour, minute = _parse_hhmm(sorted(fixed_times)[0])
    return tomorrow.replace(hour=hour, minute=minute)


def _parse_hhmm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":", 1)
    return int(hour), int(minute)
