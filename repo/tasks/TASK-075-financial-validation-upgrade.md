# TASK-075: Financial Validation Upgrade

## Status

completed

## Purpose

Upgrade validation from simple direction accuracy into financial-grade model
reliability reporting so candidate models can be promoted or rejected based on
rank quality, bucket spread, regime behavior, and leakage-safe evaluation.

## Scope

- Add validation metrics:
  - IC and Rank IC;
  - top/bottom bucket spread;
  - same-category performance;
  - asset-type performance;
  - horizon-specific performance;
  - benchmark excess;
  - drawdown and downside-risk behavior;
  - probability calibration summaries where available.
- Add gap/purge/embargo configuration for overlapping outcome windows.
- Persist validation metadata on backtest runs or monitoring reports.
- Expose model reliability status in `证据`, MCP, and Jarvis evidence fields.

## Non-Scope

- No new candidate models.
- No model promotion automation yet.
- No random train/test split.
- No UI expansion beyond existing evidence surfaces.

## Files Likely To Change

- `src/investment_forecasting/quant/backtest.py`
- `src/investment_forecasting/quant/monitoring.py`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/web/app.py`
- `src/investment_forecasting/mcp/tools.py`
- `tests/test_backtest.py`
- `tests/test_monitoring.py`
- `tests/test_web_app.py`
- `tests/test_mcp_tools.py`

## Implementation Checklist

- Add rank metric helpers with deterministic fixtures.
- Add bucket construction and same-category grouping.
- Add embargo/gap parameters to validation paths and record them.
- Mark validation as insufficient when sample count is too small.

## Acceptance Criteria

- Validation reports IC, Rank IC, bucket spread, asset-type and same-category
  results for fixtures.
- Overlapping horizons can be evaluated with a recorded gap/purge/embargo
  policy.
- Degraded/insufficient validation state is visible to Jarvis and MCP.
- Tests prevent future leakage in validation windows.

## Test Plan

- `python3 -m pytest tests/test_backtest.py tests/test_monitoring.py tests/test_web_app.py tests/test_mcp_tools.py -q`

## Depends On

- `TASK-074`

## Completion Notes

- `run_backtest` now records a validation policy with rolling time-series
  split, gap, label horizon, and configurable `embargo_days`.
- Added financial validation metrics to `backtest_runs.metrics_json`:
  information coefficient, Rank IC, top/bottom bucket spread, asset-type
  performance, same-category performance, and probability calibration bins.
- Validation status is now derived from sample count, Rank IC, and bucket
  spread so small samples become `insufficient_sample` and negative rank/bucket
  evidence becomes `degraded`.
- Model monitoring now summarizes mean Rank IC, mean bucket spread, validation
  statuses/policies, and emits warnings for insufficient samples, negative
  Rank IC, and negative bucket spread.
- MCP market snapshot returns a `validation_summary` per horizon, and
  `run_backtest` accepts `embargo_days`.
- `/backtests` now surfaces Rank IC, bucket spread, IC, and validation fields
  inside the existing evidence page without changing primary navigation.

## Verification

- `python3 -m pytest tests/test_backtest.py tests/test_monitoring.py tests/test_web_app.py tests/test_mcp_tools.py -q`
