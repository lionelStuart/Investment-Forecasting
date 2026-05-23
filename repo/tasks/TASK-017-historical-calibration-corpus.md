# TASK-017: Historical Calibration Corpus

## Status

completed

## Source

`README.md`, `SPEC-002`, `TASK-010`

## Goal

Build a larger historical data corpus and calibration workflow spanning
multiple market regimes so model comparisons are meaningful beyond deterministic
fixtures and tiny live samples.

## Required Context

- `src/investment_forecasting/quant/calibration.py`
- `TASK-012` broader universe
- README sample-window requirements

## Modify Scope

- Historical ingestion commands/windows.
- Calibration sample definitions.
- Model comparison reports.
- Documentation of promotion criteria.

## Forbidden

- Do not tune repeatedly on the full dataset without holdout windows.
- Do not add ML dependencies without an ADR.

## Acceptance

- Historical samples cover multiple years and at least three market windows
  when provider data exists.
- Calibration reports use stored historical rows, not synthetic fixtures.
- Promotion criteria include overall score, return error, risk hit, benchmark
  excess, drawdown control, and stability.

## Test Plan

- Run historical ingestion in a bounded representative universe.
- Run calibration over the defined samples.
- Verify report persistence and rationale.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added `investment-forecasting calibration corpus --db ... --start-date ... --end-date ...`.
- The command can ingest the expanded universe, calculate features, and run
  model calibration in one reproducible workflow.
- Added `--skip-ingest` for rerunning calibration on an already populated
  historical corpus.
- Calibration metrics now include benchmark excess and drawdown-control
  aggregates in addition to overall score, direction accuracy, return error,
  risk hit rate, and stability.
- Adjusted calendar-gap tolerance to allow A-share long holiday gaps while
  still detecting unusually large missing-data gaps.
- Added deterministic corpus tests.
- Validation passed with `python3 -m pytest`.
- Live historical smoke populated/reused an expanded-universe corpus from
  2023-01-01 through 2025-12-31 and produced a three-window report spanning
  2023-01-03 to 2025-12-31. The promoted model was `baseline_mean_v1`.
