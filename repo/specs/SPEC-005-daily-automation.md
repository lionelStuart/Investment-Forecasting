# SPEC-005: Daily Automation

## Status

draft

## Goal

Run the full data update, feature calculation, forecasting, scoring, and daily
advice generation workflow every day at 08:00 local time.

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
- Codex automation should call a deterministic project command or script rather
  than relying on ad hoc prompts only.

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
- Codex automation is configured for 08:00 Asia/Shanghai time once the command
  is available.

## Related Context

- `ARCHITECTURE.md`
- `tasks/TASK-007-daily-codex-automation.md`

