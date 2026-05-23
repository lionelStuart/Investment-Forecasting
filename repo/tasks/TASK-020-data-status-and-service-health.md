# TASK-020: Data Status and Service Health

## Status

completed

## Source

Latest README product goal: make the system reliable, auditable, and useful for
real local research workflows. Triggered by the service showing an empty default
database after restart.

## Goal

Make the active WebUI database and row-count health visible so a user can tell
whether the app has real data, is pointed at an empty database, or needs an
ingestion run.

## Required Context

- `src/investment_forecasting/web/app.py`
- `scripts/restart_web.sh`
- `tests/test_web_app.py`

## Modify Scope

- Dashboard status panel.
- Background WebUI restart output.
- WebUI tests.

## Forbidden

- Do not hide empty database states.
- Do not mutate user data while rendering status.
- Do not remove existing dashboard, advice, or product-link behavior.

## Acceptance

- Dashboard shows the active database path.
- Dashboard shows key row counts and latest dates.
- Empty databases show actionable guidance.
- `scripts/restart_web.sh` prints key row counts after successful restart.
- Tests cover the dashboard status panel.

## Test Plan

- Run `python3 -m pytest`.
- Run `scripts/restart_web.sh`.
- Verify `/` renders data status against the running service.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added a dashboard `数据状态` panel with active database path, counts for
  assets/prices/predictions/advice, and latest price/advice dates.
- Added empty-database guidance pointing users to ingestion or DB_PATH checks.
- Updated `scripts/restart_web.sh` to print row-count health and latest advice
  after restart.
- Added WebUI tests for the data status panel.
- Validation passed with `python3 -m pytest`.
