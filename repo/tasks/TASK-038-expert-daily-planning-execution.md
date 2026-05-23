# TASK-038: Expert Daily Planning And Simulated Execution

## Status

completed

## Purpose

Let each active expert create a daily evidence-backed investment plan and
simulate execution against their virtual portfolio.

## Scope

- Build expert planning services that reuse stored features, predictions,
  backtests, market snapshots, fund metadata, user preferences, and daily
  advice.
- Convert each expert's style/focus weights into candidate scoring and risk
  checks.
- Allow valid actions: buy, sell, rebalance, hold, and no trade.
- Persist daily expert plans, plan items, evidence links, rationale, risk
  warnings, and execution status.
- Simulate fills against stored close/nav prices and update portfolio state.
- Add daily workflow integration behind a feature flag or explicit command.

## Non-Scope

- No expert retirement decisions.
- No replacement hiring.
- No claim that an expert plan is a direct buy/sell instruction for real money.

## Files Likely To Change

- `src/investment_forecasting/experts/`
- `src/investment_forecasting/portfolio/`
- `src/investment_forecasting/workflows/daily.py`
- `src/investment_forecasting/cli.py`
- `tests/test_experts.py`
- `tests/test_daily_workflow.py`

## Acceptance Criteria

- Each active expert can produce at most one plan per run date.
- Plans include action, target asset, target weight or amount, rationale,
  evidence, and risk checks.
- No-trade plans are first-class records.
- Executions update simulated cash/positions or record a clear unfilled reason.
- Compliance checks reject certainty language and unsupported evidence.

## Depends On

- `TASK-036`
- `TASK-037`
- `TASK-032`
- `TASK-033`

## Implementation Notes

- Added `expert_plans` and `expert_plan_items` persistence with a unique
  `(expert_id, plan_date)` constraint so each active expert can create at most
  one plan per day.
- Added `investment_forecasting.experts.planning` to build evidence-backed
  plans from stored predictions, features, market snapshots, expert focus
  weights, risk limits, and current virtual portfolio cash.
- Added first-class `no_trade` plans and execution records.
- Simulated execution uses the shared virtual portfolio accounting service, so
  filled orders update cash/positions and missing prices become unfilled
  transactions.
- Added `experts run-plans` as the explicit daily execution command.
- Added compliance checks for required prediction evidence and prohibited
  certainty language.

## Verification

- `python3 -m pytest tests/test_experts.py tests/test_portfolio.py tests/test_db.py`
- `python3 -m investment_forecasting.cli experts run-plans --db data/investment_forecasting.sqlite3 --date 2026-05-23`
