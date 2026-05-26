# TASK-095: 20-Day Shadow Router Floor70 Cap05

## Status

completed

## Purpose

Run the conservative 20-day router as shadow evidence without changing
operational predictions.

## Scope

- Add shadow route named `router_floor70_cap05`.
- Blend 20-day baseline, momentum, and risk-adjusted candidates with:
  - baseline floor 70%;
  - monthly max turnover 5%;
  - walk-forward weights using only outcomes matured before each simulated
    decision month.
- Persist shadow predictions or shadow metrics separately from
  `model_predictions`.
- Compare the shadow route against fixed baseline by month and holdout window.
- Record turnover stability, direction accuracy, Rank IC, bucket spread,
  top/bottom decile spread, MAE, and high-confidence wrong rate.

## Non-Scope

- No production routing.
- No operational `model_predictions` overwrite.
- No same-type ranking usage.
- No expert, Jarvis, advice, phone, WebUI, or portfolio behavior changes.

## Files Likely To Change

- `src/investment_forecasting/db.py`
- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/quant/model_validation.py`
- `src/investment_forecasting/quant/forecast.py`
- `src/investment_forecasting/cli.py`
- `tests/test_model_validation.py`
- `tests/test_db.py`

## Implementation Checklist

- Add shadow route definitions and deterministic weight calculation.
- Enforce point-in-time monthly walk-forward training.
- Persist route weights and shadow metrics.
- Add a CLI command or option to run shadow routing from the latest replay.
- Compare `router_floor70_cap05` with fixed `baseline_mean_v1`.
- Explicitly mark route status as `shadow_only`.

## Acceptance Criteria

- Shadow route can be regenerated without touching operational predictions.
- Monthly route weights use only matured evidence available before the target
  month.
- Report shows baseline comparison and turnover.
- Tests prove the route cannot update `model_predictions`.
- Tests prove same-type ranking remains disabled for this route when metrics
  are non-positive.

## Test Plan

- `python3 -m pytest tests/test_model_validation.py tests/test_db.py -q`

## Depends On

- `TASK-094`

## Result

- Added persisted `model_shadow_routes` for monthly shadow-only route
  evidence, separate from operational `model_predictions`.
- Added `router_floor70_cap05` with 20-day horizon, 70% baseline floor, 5%
  monthly turnover cap, and deterministic monthly walk-forward weights.
- Route weights use only matured replay outcomes available before each target
  month's training cutoff.
- Added `model-validation shadow-router-run` and
  `model-validation shadow-router-report`.
- Local replay run `1` produced 4 monthly shadow rows for 2026-01 through
  2026-04. The route stayed `shadow_only`, kept baseline weight above 70%, and
  recorded `same_type_ranking_usage=disabled`.
- Production forecasts were unchanged; no operational prediction rows are
  inserted or updated by the shadow router.

## Verification

- `python3 -m pytest tests/test_model_validation.py tests/test_db.py -q`
- `python3 -m investment_forecasting.cli model-validation shadow-router-run --db data/investment_forecasting.sqlite3 --run-id 1`
- `python3 -m investment_forecasting.cli model-validation shadow-router-report --db data/investment_forecasting.sqlite3 --run-id 1`
