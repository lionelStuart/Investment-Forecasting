# TASK-094: Model Applicability Profiles And Same-Type Disable Rules

## Status

completed

## Purpose

Derive context-specific model roles from model-health metrics so a model can be
used only for the output purposes supported by evidence.

## Scope

- Add `model_applicability_profiles` persistence or equivalent durable profile
  records.
- Derive roles:
  - `primary_forecast`
  - `allocation_bias`
  - `ranking_signal`
  - `risk_reference`
  - `observation_only`
- Add same-type ranking disable rules:
  - non-positive same-type Rank IC disables same-type ranking;
  - non-positive same-type bucket spread disables same-type ranking.
- Add `promotion_status`, `degradation_reason`, `consumer_display_level`, and
  sample-size gates.
- Add CLI report for applicability profiles.

## Non-Scope

- No production model promotion.
- No WebUI/Jarvis/advice consumption.
- No expert or portfolio behavior changes.
- No shadow router yet.

## Files Likely To Change

- `src/investment_forecasting/db.py`
- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/quant/model_validation.py`
- `src/investment_forecasting/cli.py`
- `tests/test_model_validation.py`
- `tests/test_db.py`

## Implementation Checklist

- Define deterministic role derivation rules from `model_health_metrics`.
- Implement same-type ranking disable logic.
- Mark 20-day same-type ranking as `observation_only` when same-type metrics
  are non-positive.
- Keep 5-day and 60-day baseline roles conservative.
- Record role rationale and source metric IDs.

## Acceptance Criteria

- Applicability profiles are generated from model-health rows.
- Same-type ranking is disabled when same-type Rank IC or bucket spread is
  non-positive.
- 20-day router-related roles cannot be production roles in this task.
- Tests cover role derivation and disable rules.

## Test Plan

- `python3 -m pytest tests/test_model_validation.py tests/test_db.py -q`

## Depends On

- `TASK-093`

## Result

- Added persisted `model_applicability_profiles` with one profile per
  model-health scope and a source pointer back to `model_health_metrics`.
- Added deterministic role derivation for `primary_forecast`,
  `allocation_bias`, `ranking_signal`, `risk_reference`, and
  `observation_only`.
- Added same-type ranking disable rules: non-positive same-type Rank IC or
  bucket spread forces `ranking_disabled=1` and prevents `ranking_signal`.
- Added `model-validation applicability-generate` and
  `model-validation applicability-report`.
- Generated profiles for local replay run `1`: 1,512 rows, with 8
  `primary_forecast`, 2 `allocation_bias`, 53 `ranking_signal`, 46
  `risk_reference`, 1,403 `observation_only`, and 1,125 same-type ranking
  disables.
- Kept production defaults unchanged; profile generation does not update
  operational `model_predictions`.

## Verification

- `python3 -m pytest tests/test_model_validation.py tests/test_db.py -q`
- `python3 -m investment_forecasting.cli model-validation applicability-generate --db data/investment_forecasting.sqlite3 --run-id 1`
- `python3 -m investment_forecasting.cli model-validation applicability-report --db data/investment_forecasting.sqlite3 --run-id 1`
