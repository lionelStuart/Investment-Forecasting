# TASK-096: Confidence Calibration Labels

## Status

completed

## Purpose

Stop treating raw model confidence as predictive certainty by deriving
conservative confidence labels from realized replay and model-health evidence.

## Scope

- Add model-layer confidence labels:
  - `暂不强调`
  - `谨慎观察`
  - `相对稳健`
- Derive labels from:
  - minimum sample size;
  - Rank IC;
  - bucket spread;
  - probability calibration separation;
  - high-confidence wrong rate;
  - horizon and asset-scope stability.
- Persist labels in model-health/applicability records.
- Add CLI report fields that explain confidence label rationale.

## Non-Scope

- No UI wording changes.
- No Jarvis, expert, advice, phone, or portfolio changes.
- No model promotion.
- No probability guarantee.

## Files Likely To Change

- `src/investment_forecasting/quant/model_validation.py`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/cli.py`
- `tests/test_model_validation.py`

## Implementation Checklist

- Define measurable label gates.
- Add overconfidence detection from replay diagnostics.
- Add "no strong confidence" result when tiers do not separate realized
  accuracy or high-confidence wrong rate.
- Persist rationale with source metrics.

## Acceptance Criteria

- Labels are deterministic from model-health evidence.
- Overconfident contexts receive `暂不强调` or `谨慎观察`.
- `相对稳健` requires multiple matured windows with positive separation.
- Tests cover insufficient, cautious, and relatively stable label cases.

## Test Plan

- `python3 -m pytest tests/test_model_validation.py -q`

## Depends On

- `TASK-094`

## Result

- Added conservative confidence labels on both `model_health_metrics` and
  `model_applicability_profiles`.
- Added deterministic label generation:
  - `暂不强调` for insufficient samples, non-positive Rank IC/bucket spread,
    elevated high-confidence wrong rate, or large calibration error.
  - `谨慎观察` for watchable evidence that lacks multiple stable matured
    monthly windows.
  - `相对稳健` only for all-history scopes with at least two matured monthly
    windows passing positive rank/bucket, calibration, and overconfidence gates.
- Added `model-validation confidence-labels-generate` and
  `model-validation confidence-labels-report`.
- Local replay run `1` produced 1,512 labels: 1,508 `暂不强调`, 4 `谨慎观察`,
  and 0 `相对稳健`, reflecting that current evidence should not support strong
  confidence language.
- No UI, Jarvis, expert, advice, phone, portfolio, model-promotion, or
  operational prediction behavior changed.

## Verification

- `python3 -m pytest tests/test_model_validation.py tests/test_db.py -q`
- `python3 -m investment_forecasting.cli model-validation confidence-labels-generate --db data/investment_forecasting.sqlite3 --run-id 1`
- `python3 -m investment_forecasting.cli model-validation confidence-labels-report --db data/investment_forecasting.sqlite3 --run-id 1`
