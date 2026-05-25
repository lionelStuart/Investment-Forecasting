# TASK-039: Expert Scoring, Retirement, And Replacement Hiring

## Status

completed

## Purpose

Evaluate expert performance over time, identify experts that are failing their
mandate, record lessons, retire underperforming experts, and hire replacement
experts when active count falls below four.

## Scope

- Persist expert scorecards by rolling window.
- Score return, benchmark excess, max drawdown, volatility, cash drag,
  turnover, win rate, evidence completeness, and mandate adherence.
- Add lifecycle decisions: keep, warn, probation, retire, hire replacement.
- Persist expert reviews and failure/success lessons.
- Generate replacement candidates from style gaps and historical lessons.
- Require sufficient evaluation maturity before retirement.

## Non-Scope

- No live capital consequences.
- No one-day automatic firing.
- No opaque LLM-only hiring decisions.

## Files Likely To Change

- `src/investment_forecasting/experts/`
- `src/investment_forecasting/portfolio/`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/cli.py`
- `tests/test_expert_scoring.py`

## Acceptance Criteria

- Scorecards are reproducible from persisted virtual portfolio records.
- A bad expert can enter warning/probation before retirement.
- Retirement writes a structured lesson explaining failure causes and avoided
  future hiring patterns.
- Hiring restores the active expert count to four.
- Replacement experts improve committee diversity instead of cloning the
  retired expert's failed pattern.

## Depends On

- `TASK-037`
- `TASK-038`
- `TASK-024`

## Implementation Notes

- Added persisted expert lifecycle tables:
  - `expert_scorecards`
  - `expert_reviews`
  - `expert_lessons`
- Added `investment_forecasting.experts.scoring` to compute rolling scorecards
  from persisted virtual portfolio valuations, transactions, and expert plans.
- Scorecards include return, benchmark return/excess, max drawdown, volatility,
  cash drag, turnover, win rate, evidence completeness, mandate adherence, and
  overall score.
- Lifecycle review now supports keep, warn, probation, retire, and
  hire_replacement decisions.
- Retirement writes a structured failure lesson with overweighted signals,
  ignored signals, failed controls, and future hiring patterns to avoid.
- Replacement hiring restores the active expert count to four and creates a
  virtual portfolio for the replacement expert.
- Added `experts score` CLI for explicit scoring and lifecycle review.

## Verification

- `python3 -m pytest tests/test_expert_scoring.py tests/test_experts.py tests/test_portfolio.py tests/test_db.py`
- `python3 -m investment_forecasting.cli experts score --db data/investment_forecasting.sqlite3 --date 2026-05-23 --min-valuations 1`
