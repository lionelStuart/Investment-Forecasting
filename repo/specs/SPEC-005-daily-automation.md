# SPEC-005: Historical Daily Workflow Automation

## Status

superseded by `SPEC-013`

## Goal

Historical goal: run the full data update, feature calculation, forecasting,
scoring, and daily advice generation workflow every day at 08:00 local time.

Current direction: data/news refresh is owned by the system scheduler in
`SPEC-013`, using hourly incremental jobs, watermarks, provider request caps,
and backoff. Codex app automation is no longer the operational scheduler.

## Non-Goals

- Do not assume 08:00 contains current trading-day closing data.
- Do not silently skip failed steps.
- Do not require manual UI interaction for the normal daily run.

## Inputs

- Scheduler configuration.
- Data providers and local database.
- Quant, advice, and MCP services.

## Outputs

- Updated SQLite records.
- Daily advice for the run date.
- `task_logs` records with status, timings, failures, and summary metadata.

## Constraints

- The 08:00 run is a pre-market guidance run based mostly on previous
  trading-day data and available overnight context.
- The workflow must be safe to re-run for the same date.
- Every step should emit enough structured status to diagnose failures.
- The ingestion step should reuse local history and run provider calls through
  the polite access policy so scheduled runs do not repeatedly fetch full
  history or create unnecessary provider pressure.
- Historical Codex automation must not be used as the product scheduler.
  System scheduling must use `SPEC-013`.

## Error Cases

- Provider data is unavailable before the run.
- Partial data update succeeds but forecast generation fails.
- Advice already exists for the date.
- Scheduler environment lacks required credentials or Python dependencies.

## Acceptance

- A manual command can run the same workflow as the scheduler.
- Re-running the workflow for the same date updates or preserves records
  idempotently.
- Success and failure paths write `task_logs`.
- Historical 08:00 automation is superseded by system-owned scheduling.

## Related Context

- `ARCHITECTURE.md`
- `tasks/TASK-007-daily-codex-automation.md` historical
- `specs/SPEC-013-system-scheduler-incremental-updates.md`
