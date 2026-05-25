# ADR-009: System-Owned Incremental Scheduler

## Status

accepted

## Context

The project previously had a Codex app automation that ran the daily workflow
at 08:00. That was useful during early development, but it conflicts with the
current product architecture:

- the system should own scheduling;
- Codex should be used as a role-scoped agent runtime, not as the data-refresh
  cron runner;
- hourly market/news freshness requires incremental watermarks and provider
  backoff, which a prompt-based automation cannot reliably enforce;
- repeated broad ingestion risks provider throttling or temporary bans.

## Decision

Remove Codex app automation from the operational update path.

Introduce a system-owned scheduler that runs hourly and event/time-window jobs.
All data and news refresh jobs must be incremental by watermark, bounded by
provider request policy, and auditable through scheduler run records and
existing task logs.

Codex agent runs remain downstream business tasks invoked by this system:
expert agents after T evidence readiness, and Jarvis at T+1 after expert
outcomes are terminal.

## Consequences

- `investment-forecasting-daily-run` Codex automation must be deleted or kept
  inactive only as historical context.
- New scheduler work must implement persisted jobs, run records, watermarks,
  and provider backoff.
- Hourly jobs must default to bounded incremental windows.
- Full refreshes require explicit manual commands and must not be the default
  scheduled behavior.
- WebUI/system health should expose scheduler freshness, watermarks, and
  deferred/backoff states.

## Non-Goals

- No live trading.
- No Codex-owned scheduling.
- No hourly full-history provider calls.
- No bypass of provider politeness policy.

## Follow-Up

- Implement `SPEC-013` through `TASK-085` to `TASK-089`.
