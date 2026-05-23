# SPEC-002: Quant Forecast And Backtest

## Status

draft

## Goal

Provide reproducible quantitative features, baseline forecasts, rolling
backtests, and scoring so daily advice is grounded in measurable historical
behavior.

## Non-Goals

- Do not optimize for guaranteed directional accuracy.
- Do not add complex ML before simple baselines and leakage-safe backtests work.
- Do not use random train/test splitting for time-series validation.

## Inputs

- Historical prices/NAVs from SQLite.
- Asset metadata and benchmark relationships.
- Forecast horizons of 5, 20, and 60 trading days.

## Outputs

- `features_daily` records for returns, volatility, drawdown, momentum, and
  market state.
- `model_predictions` records with horizon, expected return range, upside
  probability, downside risk, confidence, model version, and generated time.
- `backtest_runs` and `backtest_results` records.
- Scores: `prediction_score`, `risk_score`, `advice_score`, `overall_score`.

## Constraints

- Every simulated forecast must only use data available before timestamp `T`.
- Backtests must record sample window, model version, parameters, benchmark, and
  costs/assumptions.
- Baselines must include simple historical mean, momentum, moving-average, or
  benchmark-relative models before ML enhancements.
- Risk metrics must include return, volatility, maximum drawdown, Sharpe,
  Calmar, and win rate where data permits.

## Error Cases

- Insufficient lookback window for an asset.
- Asset history has missing or non-monotonic dates.
- Benchmark history is unavailable.
- A model generates NaN or invalid confidence values.
- A backtest accidentally reads future rows.

## Acceptance

- Feature calculations are reproducible from stored inputs.
- Baseline forecasts can run for at least 5/20/60-day horizons.
- Rolling backtests cover multiple market windows where data exists.
- Backtest output includes direction accuracy, return error, risk hit,
  benchmark excess, drawdown control, and executable-advice scoring hooks.
- Tests cover future-leakage prevention for the backtest splitter or runner.

## Related Context

- `ARCHITECTURE.md`
- `tasks/TASK-003-feature-risk-metrics.md`
- `tasks/TASK-004-baseline-forecast-backtest-scoring.md`
- `tasks/TASK-009-model-calibration-enhancement.md`

