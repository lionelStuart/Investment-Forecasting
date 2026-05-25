# TASK-040: Expert Committee WebUI

## Status

completed

## Purpose

Make the expert system inspectable in the local workbench. Users should be able
to compare active experts, current positions, daily plans, realized virtual
returns, risk, retirements, and lessons without reading raw tables first.

## Scope

- Add an `/experts` route and navigation entry.
- Show four active experts with durable persona names, style metadata, current capital, cash, return, drawdown,
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
- Changed `/experts` into an overview-first page with clickable expert cards;
  `/experts?expert=<expert_key>` opens that expert's detail view with
  investment plan, recent timeline, invested capital, cash, total assets,
  current positions, and return curve.
- Added latest expert plan/execution table.
- Added equity curve / benchmark comparison table from persisted virtual
  valuations and scorecards.
- Removed the duplicate overview investment/benchmark table so the expert
  overview shows compact expert cards plus the multi-expert return curve only.
- Renamed the overview curve section to "专家收益对比" and removed residual raw
  scorecard/review queries so the overview no longer exposes or implies a
  separate equity/benchmark table.
- Added lesson table for failure/hiring lessons in human language.
- Kept scorecard and review records under secondary technical details.
- Added page styling for active, probation, and retired expert states.

## Verification

- `python3 -m pytest tests/test_web_app.py`
- `scripts/restart_web.sh`

## Follow-Up Fixes

- 2026-05-23: Removed the duplicated "总览投资 / 收益曲线" wording from the
  expert overview. The overview now shows only one multi-expert virtual return
  comparison curve, while benchmark/scorecard fields stay in expert detail or
  technical contexts.
- 2026-05-23: Removed the overview-level latest plan/execution table and
  switched lessons to compact cards, so `/experts` stays a true overview:
  expert cards plus the multi-expert return comparison. Full plans,
  timelines, investment records, reasons, analysis, and reflections remain on
  each expert detail page.
- 2026-05-23: Removed the duplicate valuation table that followed each expert
  detail return curve. The detail page now keeps the curve in a single
  "收益曲线" section, while total assets, invested capital, cash, timeline,
  plans, execution reasons, score analysis, and reflections remain available in
  their dedicated sections.
- 2026-05-23: Added an explicit regression check that the expert overview does
  not show the old "权益曲线与基准" block. The overview remains limited to
  compact expert cards, one multi-expert return comparison curve, and lessons.
