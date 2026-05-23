# TASK-040: Expert Committee WebUI

## Status

completed

## Purpose

Make the expert system inspectable in the local workbench. Users should be able
to compare active experts, current positions, daily plans, realized virtual
returns, risk, retirements, and lessons without reading raw tables first.

## Scope

- Add an `/experts` route and navigation entry.
- Show three active experts with style, current capital, cash, return, drawdown,
  score, and lifecycle state.
- Show today's plans and execution status.
- Show equity curves and benchmark comparison.
- Show probation/retired experts and lessons learned.
- Keep raw expert tables as secondary technical details.

## Non-Scope

- No new trading algorithms.
- No live trading controls.
- No hiding risk warnings or uncertainty.

## Files Likely To Change

- `src/investment_forecasting/web/app.py`
- `tests/test_web_app.py`
- `repo/CODE_INDEX.md`
- `repo/ARCHITECTURE.md`

## Acceptance Criteria

- `/experts` renders active roster, current virtual capital, latest plan, and
  key score metrics.
- Retired/probation experts are visibly distinct from active experts.
- Lessons from failed experts are visible in human language.
- Raw records are secondary/collapsible.
- Tests cover empty state, active experts, and at least one retired expert.

## Depends On

- `TASK-036`
- `TASK-037`
- `TASK-038`
- `TASK-039`
- `TASK-035`

## Implementation Notes

- Added `/experts` route and navigation entry.
- Added expert overview cards for lifecycle state, style, current virtual
  capital, cash, virtual return, drawdown, score, and latest review rationale.
- Added latest expert plan/execution table.
- Added equity curve / benchmark comparison table from persisted virtual
  valuations and scorecards.
- Added lesson table for failure/hiring lessons in human language.
- Kept scorecard and review records under secondary technical details.
- Added page styling for active, probation, and retired expert states.

## Verification

- `python3 -m pytest tests/test_web_app.py`
