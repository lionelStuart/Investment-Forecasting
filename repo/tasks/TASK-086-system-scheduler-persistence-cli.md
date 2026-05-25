# TASK-086: System Scheduler Persistence, Registry, And CLI

## Status

completed

## Purpose

Add the local system scheduler foundation: job definitions, run records,
watermarks, provider rate-limit state, and CLI commands to list and run due
jobs manually.

## Scope

- Add scheduler persistence tables or equivalent migration.
- Add a scheduler job registry with hourly news/data jobs and daily downstream
  jobs disabled/enabled by configuration.
- Add CLI commands:
  - `scheduler list-jobs`;
  - `scheduler status`;
  - `scheduler run-due`;
  - `scheduler run-job JOB_KEY`.
- Write `scheduler_runs` and summarized `task_logs`.
- Keep scheduler commands deterministic and testable without real provider
  calls.

## Non-Scope

- No OS-level launchd/systemd installation yet.
- No live provider calls in unit tests.
- No expert/Jarvis agent scheduling yet beyond job definitions.

## Files Likely To Change

- `src/investment_forecasting/scheduler/`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/cli.py`
- `tests/test_scheduler.py`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`

## Acceptance Criteria

- Scheduler jobs can be listed from CLI.
- `scheduler run-due` runs due fake jobs and records `scheduler_runs`.
- Job status exposes next run time, last run status, and watermarks.
- Existing task logs receive a scheduler summary.

## Test Plan

- `python3 -m pytest tests/test_scheduler.py tests/test_db.py -q`

## Depends On

- `TASK-085`

## Completion Notes

- Added scheduler persistence tables: `scheduler_jobs`, `scheduler_runs`,
  `scheduler_watermarks`, and `provider_rate_limits`.
- Added fixed system job registry:
  - news incremental refresh every hour at `:05`;
  - intraday market context refresh at `09:45`, `10:45`, `11:45`, `13:45`,
    `14:45`, and `15:20` on weekdays;
  - post-close price/NAV at `17:30`;
  - features at `18:10`;
  - model/advice preparation at `18:40`;
  - disabled definitions for expert T-day `20:00` and Jarvis T+1 `08:00`.
- Added CLI commands: `scheduler list-jobs`, `scheduler status`,
  `scheduler run-due`, and `scheduler run-job`.
- `run-due` and `run-job` currently execute deterministic foundation runs,
  record scheduler audit rows, update watermarks, and write `task_logs`
  without calling live providers. Real incremental provider work is left to
  `TASK-087`.
