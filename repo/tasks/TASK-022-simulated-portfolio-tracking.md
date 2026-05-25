# TASK-022: Simulated Portfolio Tracking

## Status

completed

## Source

Updated `ROADMAP.md` backlog theme: simulated portfolio tracking.

## Goal

Store simulated portfolios, positions, transactions, daily valuation, and
portfolio-level performance so advice can be evaluated as an investable
research portfolio.

This is also the accounting foundation for `SPEC-007` expert committee virtual
investing. Expert portfolios must reuse the same simulated portfolio mechanics
instead of creating a separate accounting path.

## Acceptance

- SQLite stores portfolios, positions, transactions, and daily value.
- CLI can create a portfolio and record transactions.
- WebUI can inspect portfolio holdings and equity curve.
- Portfolio valuation uses stored asset prices only.
- The data model can link a portfolio owner to future expert records without a
  schema rewrite.

## Completion Notes

- Added the shared simulated portfolio schema earlier through
  `virtual_portfolios`, `virtual_positions`, `virtual_transactions`,
  `virtual_cash_ledger`, and `virtual_valuations`.
- Reused `investment_forecasting.portfolio.accounting` as the single accounting
  path for user and expert portfolios, including buy/sell/no-trade records,
  cash ledger updates, unfilled exceptions, and stored-price valuation.
- Added generic CLI commands:
  - `investment-forecasting portfolio create`
  - `investment-forecasting portfolio list`
  - `investment-forecasting portfolio trade`
  - `investment-forecasting portfolio value`
- Added `/portfolios` WebUI with portfolio selector, holdings, transactions,
  valuations, and an equity curve.
- Expert portfolios continue to use the same owner-aware schema through
  `owner_type='expert'` and `owner_id=<expert id>`.

## Verification

- `python3 -m pytest tests/test_portfolio.py tests/test_web_app.py`
