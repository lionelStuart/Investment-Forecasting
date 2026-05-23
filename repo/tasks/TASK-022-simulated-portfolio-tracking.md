# TASK-022: Simulated Portfolio Tracking

## Status

pending

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
