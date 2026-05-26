# TASK-092: Model Tuning Recommendation Report

## Status

completed

## Purpose

Turn replay diagnostics into a concrete model tuning plan with ranked
experiments, verification metrics, and stop conditions for model accuracy,
ranking quality, and confidence calibration only.

## Scope

- Add a deterministic tuning recommendation builder from replay metrics.
- Produce recommendations for:
  - horizon weighting;
  - candidate model activation/deactivation;
  - asset-type/theme-specific degradation gates;
  - probability calibration;
  - confidence calibration;
  - embargo/gap changes for overlapping labels;
  - risk overlay vs alpha model separation.
- Persist recommendations on `model_replay_runs.tuning_recommendations_json`.
- Add CLI command:
  `investment-forecasting model-validation tuning-plan`.

## Non-Scope

- No automatic model parameter change.
- No automatic promotion/demotion beyond existing governance status.
- No new black-box model.
- No expert committee, Jarvis, advice, MCP, WebUI, or portfolio changes.

## Files Likely To Change

- `src/investment_forecasting/quant/model_validation.py`
- `src/investment_forecasting/quant/calibration.py`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/cli.py`
- `tests/test_model_validation.py`

## Implementation Checklist

- Define recommendation schema:
  - priority;
  - title;
  - affected model/horizon/scope;
  - triggering metrics;
  - proposed experiment;
  - verification metric;
  - stop condition;
  - model-layer confidence impact.
- Rank recommendations by severity and breadth.
- Ensure recommendations use cautious language and do not imply guaranteed
  accuracy or return improvement.
- Add a "do not tune yet" outcome when sample size is insufficient.

## Acceptance Criteria

- The tuning plan contains ranked, evidence-backed recommendations.
- Each recommendation has a verification metric and stop condition.
- The report can recommend preserving `baseline_mean_v1` when candidates do
  not beat it.
- Tests cover representative diagnostic-to-recommendation mappings.

## Test Plan

- `python3 -m pytest tests/test_model_validation.py -q`

## Completion Notes

- Added `investment-forecasting model-validation tuning-plan`.
- Tuning recommendations are persisted on `model_replay_runs` and include
  priority, affected scope, triggering metrics, experiment, verification
  metric, stop condition, and model confidence impact.
- The 2026 replay run produced recommendations for rank gates, alpha strength
  reduction, probability calibration, and confidence cooling before any model
  default change.

## Depends On

- `TASK-091`
