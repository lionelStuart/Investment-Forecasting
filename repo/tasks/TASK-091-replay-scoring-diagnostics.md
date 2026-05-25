# TASK-091: Replay Scoring And Diagnostics

## Status

pending

## Purpose

Score matured replay predictions against stored historical outcomes and
produce the diagnostic metrics needed to judge model reliability by horizon,
model version, asset type, theme, and market period.

## Scope

- Reuse existing `score_forecast`, `aggregate_scores`, benchmark selection,
  rank IC, bucket spread, probability calibration, and group performance logic
  where possible.
- Aggregate replay metrics by:
  - model version;
  - horizon;
  - month;
  - asset type;
  - same-category/theme;
  - market regime when available.
- Separate matured, pending, and skipped coverage.
- Persist aggregate metrics on `model_replay_runs.metrics_json`.
- Add CLI command:
  `investment-forecasting model-validation report`.

## Non-Scope

- No new model family.
- No expert committee, Jarvis, advice, or portfolio scoring.
- No MCP/WebUI surface.
- No broad UI redesign.

## Files Likely To Change

- `src/investment_forecasting/quant/model_validation.py`
- `src/investment_forecasting/quant/backtest.py`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/cli.py`
- `tests/test_model_validation.py`
- `tests/test_backtest.py`

## Implementation Checklist

- Score only rows with `score_status='matured'`.
- Compute direction accuracy, return error, risk hit rate, benchmark excess,
  score components, IC, Rank IC, bucket spread, and calibration bins.
- Add overconfidence and high-confidence-wrong-direction diagnostics.
- Identify negative Rank IC and negative bucket-spread windows.
- Record sample counts and insufficient-sample status for every slice.
- Keep all metrics JSON serializable and stable so future surfaces can reuse
  them after this model-only phase is accepted.

## Acceptance Criteria

- Matured replay rows produce aggregate metrics by model/horizon.
- Pending rows are counted in coverage but excluded from accuracy metrics.
- Diagnostics identify at least high-confidence wrong predictions, negative
  rank windows, negative bucket-spread slices, and downside-risk misses.
- Tests cover no future leakage and maturity filtering.
- Tests prove scoring does not read expert, Jarvis, advice, or portfolio
  tables.

## Test Plan

- `python3 -m pytest tests/test_model_validation.py tests/test_backtest.py -q`

## Depends On

- `TASK-090`
