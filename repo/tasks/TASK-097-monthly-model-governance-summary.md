# TASK-097: Monthly Model Governance Summary

## Status

completed

## Purpose

Produce a monthly model-layer governance summary after matured holdout windows
so model changes are reviewed through evidence instead of parameter tinkering.

## Scope

- Add a monthly governance report generated from model health, applicability
  profiles, confidence labels, and shadow route comparisons.
- Answer four questions:
  1. Which model/horizon/scope remains safe as default?
  2. Which model/horizon/scope can continue in shadow mode?
  3. Which model signals must be downgraded or disabled inside the model layer?
  4. Did any model become promotion-review eligible under published gates?
- Persist report JSON and a short human-readable summary.
- Add CLI command to generate and inspect the latest governance summary.

## Non-Scope

- No automatic promotion.
- No production default change.
- No expert, Jarvis, advice, phone, WebUI, or portfolio behavior changes.
- No monthly parameter tinkering.

## Files Likely To Change

- `src/investment_forecasting/db.py`
- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/quant/model_validation.py`
- `src/investment_forecasting/cli.py`
- `tests/test_model_validation.py`
- `tests/test_db.py`

## Implementation Checklist

- Add governance summary persistence.
- Generate summary from existing model-health/profile/shadow evidence.
- Include promotion blockers and stop conditions.
- State explicitly when production defaults remain unchanged.
- Add a guardrail that any promotion eligibility is review-only.

## Acceptance Criteria

- A monthly governance summary can be generated from replay/shadow evidence.
- The report answers the four CEO review questions.
- Production defaults remain unchanged.
- Tests verify no operational prediction update occurs.

## Test Plan

- `python3 -m pytest tests/test_model_validation.py tests/test_db.py -q`

## Depends On

- `TASK-095`
- `TASK-096`

## Result

- Added persisted `model_governance_reviews` with one review per replay run
  and review month, storing report JSON, a short human-readable summary,
  review status, production-default guardrail state, and promotion-review
  eligibility.
- Added deterministic monthly governance generation from model-health facts,
  applicability profiles, confidence labels, and shadow-router comparisons.
- The report answers the four review questions:
  - safe default scopes;
  - shadow routes that can continue observing;
  - downgraded or disabled model signals;
  - promotion-review eligibility and blockers.
- Added `model-validation governance-generate` and
  `model-validation governance-report`.
- Generated the local replay run `1` review for `2026-05`: status
  `review_only`, 0 safe-default scopes under current confidence gates, 4
  `router_floor70_cap05` shadow months continuing in observation, 100
  downgraded/disabled sample scopes in the compact review list, no
  promotion-review eligibility, and `production_defaults_changed=0`.
- Guardrails explicitly state no operational `model_predictions` update, no
  automatic promotion, no same-type ranking use for the shadow router, and no
  expert/Jarvis/advice/phone/WebUI/portfolio impact.

## Verification

- `python3 -m pytest tests/test_model_validation.py tests/test_db.py -q`
- `python3 -m investment_forecasting.cli model-validation governance-generate --db data/investment_forecasting.sqlite3 --run-id 1`
- `python3 -m investment_forecasting.cli model-validation governance-report --db data/investment_forecasting.sqlite3 --run-id 1`
- SQLite evidence: `model_governance_reviews` has one `review_only`
  `2026-05` row for replay run `1`, with `production_defaults_changed=0` and
  `promotion_review_eligible=0`.
