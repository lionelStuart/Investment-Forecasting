# TASK-047: Jarvis Product Model And Persistence

## Status

completed

## Purpose

Create the durable product model for Jarvis, the top-level AI investment
assistant that synthesizes market information, model predictions, expert
outputs, and user context into a daily advice record.

## Scope

- Add persistence for Jarvis daily advice records.
- Store daily focus directions, one-line stance, model summary, expert summary,
  combined recommendation, risk warnings, and evidence references.
- Add idempotency/versioning for reruns.
- Add query helpers and tests.
- Update architecture and code index.

## Non-Scope

- No polished WebUI yet.
- No phone sending yet.
- No new forecasting algorithm.

## Files Likely To Change

- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/jarvis/`
- `tests/test_jarvis.py`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`

## Acceptance Criteria

- Jarvis records can be persisted and queried by date.
- Records include focus directions, model summary, expert summary, risk
  warnings, and evidence references.
- Reruns for the same date are idempotent or versioned.
- Tests cover creation, missing evidence metadata, and safe-language fields.

## Depends On

- `SPEC-009`
- `ADR-005`
- `TASK-036`
- `TASK-041`

## Implementation Notes

- Added the `jarvis_daily_briefs` SQLite table with `(brief_date, version)`
  idempotency, focus directions, stance, model/expert summaries, combined
  recommendation, risk warnings, evidence references, and missing/stale
  evidence metadata.
- Added `db.py` helpers for upserting, querying by date/version, and reading
  the latest Jarvis brief.
- Added `src/investment_forecasting/jarvis/` with a lightweight persistence
  API that validates required fields, serializes JSON payloads, round-trips
  saved records, and rejects unsafe certainty language.
- Added Jarvis persistence tests and included the table in schema coverage.

## Verification

- `python3 -m pytest tests/test_jarvis.py tests/test_db.py`
- `python3 -m pytest`
- `PYTHONPATH=src python3 -m investment_forecasting.cli db init --db data/investment_forecasting.sqlite3`
- `scripts/restart_web.sh`
