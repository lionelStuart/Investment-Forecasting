# TASK-049: Jarvis WebUI First-Screen Experience

## Status

completed

## Purpose

Make Jarvis the primary user-facing product experience in WebUI: a simple daily
brief that appears before raw system pages.

## Scope

- Add `/jarvis` route and dashboard entry.
- Show today's focus directions, one-line stance, model summary, expert cards,
  expert scores/current returns, combined recommendation, and risk warnings.
- Link each section to evidence drill-downs: market, predictions, backtests,
  experts, task logs, and historical Jarvis records.
- Keep raw JSON/tables secondary.

## Non-Scope

- No new synthesis algorithm.
- No phone notification sending.

## Files Likely To Change

- `src/investment_forecasting/web/app.py`
- `tests/test_web_app.py`
- `repo/CODE_INDEX.md`

## Acceptance Criteria

- `/jarvis` renders a non-technical daily brief when a Jarvis record exists.
- Empty and stale-data states are clear.
- Expert cards include each active expert's style, stance, score, current
  return, drawdown, and lifecycle state.
- Evidence links work without requiring users to read raw tables first.

## Depends On

- `TASK-047`
- `TASK-048`
- `TASK-035`
- `TASK-040`

## Implementation Notes

- Added `/jarvis` route and navigation entry.
- Added dashboard Jarvis entry so the latest daily brief appears before raw
  system pages.
- Rendered a non-technical Jarvis daily brief with focus directions, one-line
  stance, combined recommendation, model summary, disagreement explanation,
  expert cards, risk warnings, and evidence links.
- Expert cards show style, action/stance, target, score, current return,
  drawdown, risk state, and lifecycle state.
- Added clear empty state, missing/stale evidence notices, historical Jarvis
  records, and secondary collapsible raw JSON.

## Verification

- `python3 -m pytest tests/test_web_app.py`
- `python3 -m pytest`
- `PYTHONPATH=src python3 -m investment_forecasting.cli db init --db data/investment_forecasting.sqlite3`
