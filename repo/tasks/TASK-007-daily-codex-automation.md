# TASK-007: Daily Codex Automation

## Status

completed

## Source

`SPEC-005`

## Goal

Configure a daily 08:00 Asia/Shanghai Codex automation that runs the complete
data update, feature, forecast, score, and advice workflow.

## Required Context

- `PROJECT.md`
- `STATUS.md`
- `specs/SPEC-005-daily-automation.md`
- `ARCHITECTURE.md`

## Modify Scope

- Workflow command/script.
- Scheduler/automation configuration.
- Task logging.
- Tests or dry-run verification.
- Project memory write-back files.

## Forbidden

- Do not rely on an undocumented prompt-only workflow.
- Do not ignore partial failures.
- Do not assume current trading-day closing data is available at 08:00.

## Acceptance

- A manual command runs the full daily workflow.
- The workflow is safe to rerun for the same date.
- Success and failure paths write `task_logs`.
- Codex automation is created or proposed for daily 08:00 Asia/Shanghai.
- Status docs record how to inspect the latest run.

## Test Plan

- Run the workflow in dry-run or small-universe mode.
- Verify task log rows for success and simulated failure.
- Verify the automation configuration after creation/proposal.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added deterministic workflow command:
  `investment-forecasting daily run --db ... --date ... --horizons 5,20,60 --lookback-days 60`.
- The workflow runs ingestion, feature calculation, forecasts, backtests, and
  advice generation, then writes a top-level `daily_workflow` task log.
- Added `--skip-ingest` for dry-run and scheduler diagnostics using existing
  SQLite data.
- Added tests for idempotent dry-run execution and failure task logs.
- Validation passed with `python3 -m pytest`.
- Smoke validation ran the daily workflow against the MVP sample database and
  wrote a successful `daily_workflow` task log.
- Created active Codex app automation `investment-forecasting-daily-run` for
  daily 08:00 local time.

## Follow-Ups

- Monitor daily task reliability and add learning notes for provider failures.
