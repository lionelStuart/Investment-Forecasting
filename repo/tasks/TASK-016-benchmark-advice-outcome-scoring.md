# TASK-016: Benchmark And Advice Outcome Scoring

## Status

completed

## Source

`README.md`, `SPEC-002`, `SPEC-003`, `TASK-010`

## Goal

Upgrade backtest and advice scoring from placeholder benchmark hooks to real
benchmark-relative results and matured advice-outcome scoring.

## Required Context

- `src/investment_forecasting/quant/backtest.py`
- `src/investment_forecasting/advice/generator.py`
- `backtest_results`, `daily_advice`, and tracked benchmark assets.

## Modify Scope

- Benchmark relationship configuration.
- Backtest scoring.
- Advice outcome scoring job.
- Tests and fixtures.

## Forbidden

- Do not score advice before the outcome horizon is available.
- Do not optimize only direction accuracy while ignoring drawdown and risk.

## Acceptance

- Backtests compare assets or portfolios against stored benchmarks such as
  沪深300 or relevant fund benchmarks.
- `benchmark_excess`, drawdown control, and risk-hit fields use real stored
  benchmark/outcome data.
- Matured daily advice records can be scored or linked to a score record after
  the outcome horizon.

## Test Plan

- Deterministic benchmark fixture tests.
- Future-leakage tests for advice outcome scoring.
- Smoke run on stored sample data where benchmark history exists.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Updated rolling backtests to calculate benchmark return from stored 沪深300
  index prices when prediction/outcome dates align.
- `benchmark_excess` now uses actual return minus benchmark return instead of
  a zero-return placeholder.
- Added benchmark-aware advice score weighting.
- Added `advice_outcome_scores` persistence.
- Added `investment-forecasting advice score-outcomes --db ... --horizon-days ...`.
- Outcome scoring uses only advice-date and future horizon observations that
  have already matured in SQLite, then updates `daily_advice` score fields.
- Added deterministic tests for benchmark excess and matured advice scoring.
- Validation passed with `python3 -m pytest`.
- Smoke validation on the 2024-04 to 2024-05 expanded-universe sample scored a
  5-trading-day advice outcome with portfolio return, 沪深300 benchmark return,
  benchmark excess, and overall score.
