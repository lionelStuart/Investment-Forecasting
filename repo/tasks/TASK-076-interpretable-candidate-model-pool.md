# TASK-076: Interpretable Candidate Model Pool

## Status

completed

## Purpose

Introduce practical, interpretable candidate models that compete against
`baseline_mean_v1` under the upgraded validation framework before any tree or
deep model becomes a production candidate.

## Scope

- Add `momentum_reversal_v1`.
- Add `risk_adjusted_factor_v1`.
- Optionally scaffold `tree_ranker_v1` as disabled/research-only only after
  validation can compare rank quality.
- Store model version, parameters, feature window, input evidence IDs, and
  reliability metadata.
- Compare candidates against `baseline_mean_v1` using `TASK-075` metrics.

## Non-Scope

- No production LightGBM/XGBoost until validation proves ranking lift.
- No transformer/foundation time-series models.
- No ensemble promotion.
- No automatic trading or portfolio rebalancing.

## Files Likely To Change

- `src/investment_forecasting/quant/forecast.py`
- `src/investment_forecasting/quant/backtest.py`
- `src/investment_forecasting/quant/calibration.py`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/cli.py`
- `tests/test_backtest.py`
- `tests/test_calibration.py`
- `tests/test_daily_workflow.py`

## Implementation Checklist

- Reuse existing `features_daily`, news aggregate features, capital-flow
  summaries, and market state where available.
- Keep every model deterministic and auditable for fixtures.
- Add model comparison output by horizon and asset type.
- Mark models as candidate/contextual unless promotion gates are met.

## Acceptance Criteria

- Candidate forecasts can be generated and backtested without breaking
  `baseline_mean_v1`.
- Candidate models produce rank/risk-adjusted fields from `TASK-074`.
- Validation compares each candidate against baseline using `TASK-075` metrics.
- No candidate becomes Jarvis-primary by default.

## Test Plan

- `python3 -m pytest tests/test_backtest.py tests/test_calibration.py tests/test_daily_workflow.py -q`

## Depends On

- `TASK-075`

## Completion Notes

- Added `quant/forecast.py` as the shared deterministic model-version
  registry for `baseline_mean_v1`, `momentum_reversal_v1`, and
  `risk_adjusted_factor_v1`.
- `run_latest_forecasts` and `run_backtest` now accept explicit
  `model_versions`, preserve the baseline default, and label candidates as
  contextual `candidate` model state.
- Candidate forecasts write ordinary `model_predictions` rows and refresh the
  `model_prediction_reliability` sidecar, so rank score, same-category rank,
  risk-adjusted score, validation status, Rank IC, and bucket-spread evidence
  are available without changing existing consumers.
- Backtest/calibration output compares candidates against
  `baseline_mean_v1` using the `TASK-075` financial validation metrics.
- Calibration keeps candidates contextual; no candidate becomes Jarvis-primary
  by default even when it wins a narrow candidate comparison.
- CLI and MCP forecast/backtest tools can request multiple model versions.

## Verification

- `python3 -m pytest tests/test_backtest.py tests/test_calibration.py tests/test_daily_workflow.py tests/test_mcp_tools.py -q`
- `python3 -m py_compile src/investment_forecasting/quant/forecast.py src/investment_forecasting/quant/backtest.py src/investment_forecasting/quant/calibration.py src/investment_forecasting/cli.py src/investment_forecasting/mcp/tools.py src/investment_forecasting/mcp/server.py`
- Full local SQLite forecast/backtest refresh for
  `baseline_mean_v1,momentum_reversal_v1,risk_adjusted_factor_v1` across
  5/20/60 day horizons.
