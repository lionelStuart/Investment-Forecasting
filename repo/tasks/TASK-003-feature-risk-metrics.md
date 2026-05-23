# TASK-003: Feature And Risk Metrics

## Status

completed

## Source

`SPEC-002`

## Goal

Compute reproducible daily features and risk metrics from stored historical
prices/NAVs.

## Required Context

- `PROJECT.md`
- `STATUS.md`
- `specs/SPEC-002-quant-forecast-backtest.md`
- `ARCHITECTURE.md`

## Modify Scope

- Feature calculation services.
- Risk metric services.
- Persistence writes for `features_daily`.
- Tests and fixtures.
- Project memory write-back files.

## Forbidden

- Do not calculate features from provider APIs directly.
- Do not overwrite raw historical data.
- Do not silently ignore missing date gaps.

## Acceptance

- Compute returns, volatility, maximum drawdown, Sharpe, Calmar, win rate, and
  momentum where data permits.
- Persist feature rows with model/calculation version metadata.
- Re-running feature calculation for the same date range is idempotent.
- Tests cover known metric examples and missing-data behavior.

## Test Plan

- Run metric tests against deterministic fixtures.
- Run feature calculation on ingested sample assets.
- Verify stored features match expected dates and assets.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added `investment-forecasting features calculate --db ...` to derive features
  from persisted `price_daily` rows.
- Added `features_v1` persisted rows for returns, volatility, maximum drawdown,
  Sharpe, Calmar, win rate, momentum, and market state where data permits.
- Added missing-data validation for non-positive values, duplicate/non-monotonic
  dates, and large calendar gaps.
- Added idempotent `features_daily` upsert support.
- Added tests for known metric examples, missing-gap behavior, idempotent
  persistence, and failure task logs.
- Validation passed with `python3 -m pytest`.
- Live validation calculated 6 feature rows from the 2024-05-20 through
  2024-05-22 MVP ingestion database, and a repeat run kept the row count at 6.

## Follow-Ups

- `TASK-004`: Baseline forecast, backtest, and scoring.
