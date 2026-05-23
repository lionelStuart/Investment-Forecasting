# TASK-037: Expert Virtual Portfolio Foundation

## Status

completed

## Purpose

Give each expert an independent simulated investment account so expert plans can
be evaluated as actual virtual portfolios rather than prose.

## Scope

- Extend or implement simulated portfolio tables for portfolios, positions,
  transactions, cash ledger, and daily valuations.
- Link each expert to one virtual portfolio.
- Support configurable initial capital, defaulting to CNY 500,000.
- Value positions using stored `price_daily` close/nav data only.
- Record unpriced or unfilled orders as explicit exceptions.

## Non-Scope

- No live brokerage execution.
- No automatic expert plan generation.
- No retirement or replacement logic.

## Files Likely To Change

- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/portfolio/`
- `src/investment_forecasting/experts/`
- `tests/test_portfolio.py`
- `tests/test_experts.py`

## Acceptance Criteria

- Each active expert can receive a CNY 500,000 virtual portfolio.
- The system can record cash, positions, transactions, and daily value.
- Valuation uses only stored prices available for the valuation date.
- Tests cover buy, sell, hold/no-trade, missing price, and daily valuation.

## Depends On

- `TASK-036`
- `TASK-022`

## Implementation Notes

- Added shared simulated portfolio tables:
  - `virtual_portfolios`
  - `virtual_positions`
  - `virtual_transactions`
  - `virtual_cash_ledger`
  - `virtual_valuations`
- Added `investment_forecasting.portfolio.accounting` for idempotent portfolio
  creation, expert portfolio initialization, buy/sell/no-trade recording,
  unfilled missing-price exceptions, cash ledger updates, positions, and daily
  valuation.
- Added `experts init-portfolios` CLI bootstrap for creating one CNY 500,000
  portfolio per active expert.
- Expert portfolios reuse the shared portfolio accounting path so later daily
  expert execution does not need a parallel账本.

## Verification

- `python3 -m pytest tests/test_portfolio.py tests/test_db.py`
- `python3 -m investment_forecasting.cli experts init-portfolios --db data/investment_forecasting.sqlite3`
