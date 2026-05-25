# TASK-089: Hourly Scheduler Orchestration And Health Surfaces

## Status

completed

## Purpose

Wire the system scheduler into the product flow and make freshness/backoff
visible. The system should run hourly incremental jobs and expose enough status
for Jarvis, experts, WebUI, and operators to know whether evidence is fresh,
stale, deferred, or failed.

## Scope

- Add hourly job orchestration for news, capital flow, data freshness, and
  lightweight health.
- Add post-close job definitions for price/features/prediction/monitoring.
- Add expert T-day and Jarvis T+1 job definitions, gated by readiness.
- Add WebUI/system-health display for scheduler status, latest runs,
  watermarks, and provider backoff.
- Add MCP or CLI status output usable by agents.
- Add optional launchd installation proposal only after the in-system scheduler
  is testable.

## Non-Scope

- No Codex app automation.
- No live trading.
- No broad UI redesign.
- No provider expansion.

## Files Likely To Change

- `src/investment_forecasting/scheduler/`
- `src/investment_forecasting/workflows/daily.py`
- `src/investment_forecasting/agent_runtime/execution.py`
- `src/investment_forecasting/web/app.py`
- `src/investment_forecasting/mcp/tools.py`
- `src/investment_forecasting/cli.py`
- `tests/test_scheduler.py`
- `tests/test_web_app.py`
- `tests/test_mcp_tools.py`

## Acceptance Criteria

- `scheduler run-due` can run hourly incremental jobs without Codex automation.
- Scheduler status shows latest successful news/data watermarks.
- Provider backoff/deferred state is visible in CLI and WebUI.
- Expert/Jarvis jobs are defined but gated by readiness.
- Tests verify hourly orchestration, stale/deferred display, and no full-history
  default behavior.

## Test Plan

- `python3 -m pytest tests/test_scheduler.py tests/test_web_app.py tests/test_mcp_tools.py -q`

## Depends On

- `TASK-088`

## Implementation Notes

- `scheduler run-due` now executes hourly incremental scheduler handlers
  without any Codex app automation.
- Scheduler status exposes latest runs, watermarks, and provider backoff state
  through CLI, WebUI settings, and MCP `get_scheduler_status`.
- Settings page shows system scheduler health, latest scheduler runs,
  watermarks, and provider backoff details.
- Expert T-day and Jarvis T+1 jobs remain defined but disabled/gated, so Codex
  is still only a runtime invoked by system workflow readiness, not the
  scheduler.
- Tests cover hourly orchestration, WebUI stale/deferred display, MCP status,
  and no full-history default behavior.
