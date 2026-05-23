# TASK-009: Model Calibration Enhancement

## Status

completed

## Source

`SPEC-002`

## Goal

Use multi-period historical samples to calibrate and compare model versions, and
only promote enhancements that improve out-of-sample behavior or risk control.

## Required Context

- `PROJECT.md`
- `STATUS.md`
- `specs/SPEC-002-quant-forecast-backtest.md`
- `ARCHITECTURE.md`

## Modify Scope

- Model calibration services.
- Model comparison reports/records.
- Optional ML dependencies through ADR if introduced.
- Tests and fixtures.
- Project memory write-back files.

## Forbidden

- Do not tune repeatedly on the full dataset without holdout evaluation.
- Do not promote complex models without baseline comparison.
- Do not optimize direction accuracy while ignoring drawdown control.

## Acceptance

- Historical windows include multiple market regimes when data exists.
- Candidate model versions are compared against simple baselines.
- Promotion criteria include return, drawdown, benchmark excess, stability, and
  advice-score impact.
- Any new ML dependency is recorded in an ADR.

## Test Plan

- Run calibration tests on deterministic fixtures.
- Run model comparison on historical sample windows.
- Verify promoted model version is recorded and explainable.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added `model_calibration_reports` persistence for candidate comparison
  reports.
- Added `investment-forecasting calibration run --db ... --date ... --horizons ... --lookback-days ...`.
- Compared `baseline_mean_v1` against `momentum_last_return_v1` without adding
  ML dependencies.
- Calibration metrics include overall score, direction accuracy, return error,
  risk hit rate, stability, sample windows, and promotion rationale.
- Promotion requires candidate improvement over the baseline threshold before
  replacing the baseline.
- Added deterministic tests for multi-window construction, candidate
  predictions, idempotent report persistence, and insufficient-history failure.
- Validation passed with `python3 -m pytest`.
- Smoke validation on a deterministic 90-observation sample produced a report
  promoting `baseline_mean_v1` with dated calibration windows.

## Follow-Ups

- Consider LightGBM/XGBoost only after baseline comparison is working.
