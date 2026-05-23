# TASK-036: Expert Architecture And Roster Model

## Status

completed

## Purpose

Create the durable expert model required for a three-expert investment
committee. Each expert must have a distinct style, signal focus, risk limits,
allowed asset categories, lifecycle state, and audit trail.

## Scope

- Add expert roster persistence.
- Seed or create the initial three experts:
  - defensive income/drawdown control;
  - momentum/growth participation;
  - balanced rotation/risk-adjusted allocation.
- Store style, focus weights, risk limits, allowed categories, default cash
  buffer, review cadence, and lifecycle state.
- Add query/upsert helpers and tests.
- Document module ownership in `ARCHITECTURE.md` and `CODE_INDEX.md`.

## Non-Scope

- No virtual trades yet.
- No automatic retirement yet.
- No WebUI polish beyond minimal inspection if needed for verification.

## Files Likely To Change

- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/experts/`
- `src/investment_forecasting/cli.py`
- `tests/test_experts.py`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`

## Acceptance Criteria

- SQLite stores experts with lifecycle state and structured configuration.
- A command or service function can initialize exactly three active experts.
- Expert records are idempotent and can be queried in stable order.
- Tests cover creation, update, active roster filtering, and lifecycle status.

## Depends On

- `SPEC-007`
- `ADR-003`

## Implementation Notes

- Added the `experts` SQLite table with lifecycle state, risk limits, focus
  weights, allowed categories, default cash buffer, review cadence, mandate,
  and audit timestamps.
- Added `investment_forecasting.experts.roster` with the three default active
  experts from `SPEC-007`, idempotent initialization, and structured roster
  listing.
- Added persistence helpers for expert upsert, lookup, stable listing, and
  active/lifecycle filtering.
- Added CLI inspection commands:
  - `investment-forecasting experts init`
  - `investment-forecasting experts list`

## Verification

- `python3 -m pytest tests/test_experts.py tests/test_db.py`
- `python3 -m investment_forecasting.cli experts init --db /tmp/investment_experts_smoke.sqlite3`
