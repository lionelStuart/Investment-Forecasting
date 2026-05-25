# TASK-090: YTD Forecast Replay Corpus

## Status

pending

## Purpose

Create a reproducible current-year daily prediction replay corpus so model
validation can evaluate what each model would have predicted on each trading
day using only information available at that time.

## Scope

- Add replay persistence for model replay runs and replay predictions.
- Add a model-validation service that iterates stored assets, trading dates,
  model versions, and horizons.
- Use existing `forecast_from_history`, `forecast_expected_return`, benchmark
  selection, and stored `price_daily`.
- Persist both matured and pending replay rows.
- Keep replay rows separate from operational `model_predictions`.
- Add CLI command:
  `investment-forecasting model-validation replay-ytd`.

## Non-Scope

- No provider/network ingestion.
- No model tuning implementation.
- No WebUI surface yet.
- No MCP surface yet.
- No expert committee, Jarvis, advice, or portfolio evaluation.
- No model promotion.

## Files Likely To Change

- `src/investment_forecasting/db.py`
- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/quant/model_validation.py`
- `src/investment_forecasting/cli.py`
- `tests/test_model_validation.py`
- `repo/CODE_INDEX.md`
- `repo/STATUS.md`

## Implementation Checklist

- Add `model_replay_runs` and `model_replay_predictions` schema.
- Add idempotent upsert/query helpers.
- Build date selection from local price history and explicit year/date
  arguments.
- For each replay date, pass only history ending at that date into forecast
  logic.
- Mark outcome windows as `matured` only when the outcome price exists.
- Mark recent unresolved rows as `pending`, not failed.
- Record skipped rows with reasons such as insufficient lookback or missing
  outcome.
- Write a `task_logs` entry for replay start/success/failure.

## Acceptance Criteria

- A local command replays 2026 year-to-date predictions without network calls.
- Replay rows never overwrite `model_predictions`.
- Prediction input windows always end on or before `prediction_date`.
- Rows without mature outcome dates are persisted or counted as pending.
- Re-running the same replay does not create ambiguous duplicate active
  evidence.

## Test Plan

- `python3 -m pytest tests/test_model_validation.py tests/test_db.py -q`
- CLI smoke with a tiny fixture DB and short date range.

## Depends On

- `SPEC-014`
- `TASK-079`
