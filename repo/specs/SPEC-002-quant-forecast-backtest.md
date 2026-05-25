# SPEC-002: Quant Forecast And Backtest

## Status

draft

## Goal

Provide reproducible quantitative features, baseline forecasts, rolling
backtests, and scoring so daily advice is grounded in measurable historical
behavior.

The next model phase should prioritize reliability over stronger point-return
claims: cross-sectional ranking, calibrated probability, risk-adjusted score,
and model health gates should become first-class outputs.

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
- Reliability metadata for model outputs, including rank score,
  same-category rank, risk-adjusted score, validation status, recent Rank IC,
  bucket spread, and degraded reason where available.
- `backtest_runs` and `backtest_results` records.
- Scores: `prediction_score`, `risk_score`, `advice_score`, `overall_score`.
- `model_monitoring_reports` records for model-version health, score drift,
  benchmark excess, and input staleness.
- Benchmark selection details for scored results, including benchmark identity,
  source, peer count, and fallback reason when applicable.

## Constraints

- Every simulated forecast must only use data available before timestamp `T`.
- Backtests must record sample window, model version, parameters, benchmark, and
  costs/assumptions.
- Validation for overlapping 20/60-day labels must use a gap, purge, or embargo
  policy before models are promoted.
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
- Model reliability output includes IC, Rank IC, top-bucket vs bottom-bucket
  spread, same-category performance, asset-type performance, horizon-level
  performance, and probability calibration quality where available.
- Fund backtests use relevant same-bucket fund peer benchmarks when enough
  stored peer history is available, and otherwise record explicit fallback to
  stored 沪深300 or unavailable benchmark state.
- Monitoring output summarizes prediction score, risk score, benchmark excess,
  overall score, score drift, and stale input state by model version.
- Tests cover future-leakage prevention for the backtest splitter or runner.

## Related Context

- `ARCHITECTURE.md`
- `tasks/TASK-003-feature-risk-metrics.md`
- `tasks/TASK-004-baseline-forecast-backtest-scoring.md`
- `tasks/TASK-009-model-calibration-enhancement.md`
