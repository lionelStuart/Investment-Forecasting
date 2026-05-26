# TASK-093: Model Health Fact Layer

## Status

completed

## Purpose

Create a persistent model-health fact layer from replay evidence so model
quality can be compared by context instead of by one global score.

## Scope

- Add model-health persistence for monthly and rolling evaluation windows.
- Compute metrics by model version, horizon, asset type, same-category key,
  prediction month, and evaluation window.
- Include direction accuracy, Rank IC, bucket spread, top/bottom decile spread,
  MAE, median absolute error, raw high-confidence wrong rate, coverage rate,
  sample counts, and status.
- Add model-health CLI generation/report commands.
- Source data from `model_replay_predictions` and existing replay metrics.

## Non-Scope

- No operational prediction changes.
- No router implementation yet.
- No expert, Jarvis, advice, phone, WebUI, or portfolio behavior changes.
- No provider/network calls.

## Files Likely To Change

- `src/investment_forecasting/db.py`
- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/quant/model_validation.py`
- `src/investment_forecasting/cli.py`
- `tests/test_model_validation.py`
- `tests/test_db.py`
- `repo/CODE_INDEX.md`

## Implementation Checklist

- Add `model_health_metrics` or equivalent persistence.
- Add idempotent upsert/query helpers.
- Generate monthly metrics from matured replay rows only.
- Add rolling-window support if enough matured months exist; otherwise mark
  insufficient sample.
- Persist `minimum_sample_met` and `degradation_reason`.
- Keep fields JSON-serializable and point-in-time reproducible.

## Acceptance Criteria

- Model-health rows are persisted for replay run `1`.
- Metrics are grouped at least by model version, horizon, asset type, and
  prediction month.
- Rows with insufficient samples are explicit and do not look validated.
- Tests verify model health uses only matured replay rows.
- Tests verify no expert/Jarvis/advice/portfolio tables are read.

## Test Plan

- `python3 -m pytest tests/test_model_validation.py tests/test_db.py -q`

## Depends On

- `SPEC-015`
- `TASK-092`

## Result

- Added persisted `model_health_metrics` with context grain:
  `replay_run_id`, `model_version`, `horizon_days`, `asset_type`,
  `same_category_key`, `prediction_month`, and `evaluation_window`.
- Added idempotent DB helpers and `model-validation health-generate` /
  `model-validation health-report` CLI commands.
- Generated health facts for local replay run `1`: 1,512 rows from 255,201
  matured replay predictions, with 219 validated, 1,125 degraded, and 168
  insufficient-sample scopes.
- Health generation uses matured replay rows only and does not read expert,
  Jarvis, advice, portfolio, phone, or WebUI behavior tables.

## Verification

- `python3 -m pytest tests/test_model_validation.py tests/test_db.py -q`
- `python3 -m investment_forecasting.cli model-validation health-generate --db data/investment_forecasting.sqlite3 --run-id 1`
- `python3 -m investment_forecasting.cli model-validation health-report --db data/investment_forecasting.sqlite3 --run-id 1`
