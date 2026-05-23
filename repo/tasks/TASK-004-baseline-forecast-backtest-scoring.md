# TASK-004: Baseline Forecast, Backtest, And Scoring

## Status

completed

## Source

`SPEC-002`

## Goal

Implement simple reproducible forecast baselines, rolling backtests, and scoring
records for prediction and advice quality.

## Required Context

- `PROJECT.md`
- `STATUS.md`
- `specs/SPEC-002-quant-forecast-backtest.md`
- `ARCHITECTURE.md`

## Modify Scope

- Forecast services.
- Backtest services.
- Scoring services.
- Persistence writes for `model_predictions`, `backtest_runs`,
  `backtest_results`.
- Tests and fixtures.
- Project memory write-back files.

## Forbidden

- Do not add complex ML models in this task.
- Do not use future rows during simulated predictions.
- Do not report only return without drawdown and benchmark context.

## Acceptance

- Forecasts run for 5, 20, and 60 trading-day horizons.
- Rolling backtest records input window, horizon, benchmark, model version, and
  metrics.
- Scores include direction accuracy, return error, risk hit, benchmark excess,
  drawdown control, and overall score.
- Tests explicitly guard against future leakage.

## Test Plan

- Run unit tests for time-series splitting.
- Run backtest on deterministic fixtures.
- Run a sample backtest on ingested assets if data exists.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added `baseline_mean_v1` latest forecast generation for 5/20/60 day horizons.
- Added rolling backtests with configurable horizons and lookback windows.
- Added score persistence for direction accuracy, return error, risk hit,
  benchmark excess versus a zero-return cash benchmark, drawdown-control hook,
  advice score, and overall score.
- Added idempotent writes for `model_predictions`, `backtest_runs`, and
  `backtest_results`.
- Added CLI commands:
  `investment-forecasting forecast run --db ... --horizons 5,20,60` and
  `investment-forecasting backtest run --db ... --horizons 5,20,60 --lookback-days 60`.
- Added tests for rolling time-series splits, future-leakage prevention,
  forecast persistence, backtest metrics, and empty result aggregation.
- Validation passed with `python3 -m pytest`.
- Sample validation wrote 9 forecast rows for the MVP ingestion database and a
  short-sample backtest wrote 1 run with 3 results.

## Follow-Ups

- `TASK-005`: Daily advice generator.
- `TASK-009`: Model calibration enhancement.
