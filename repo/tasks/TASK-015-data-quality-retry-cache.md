# TASK-015: Data Quality Retry Cache

## Status

completed

## Source

`README.md`, `SPEC-001`, `SPEC-005`, `TASK-010`

## Goal

Make provider updates more reliable and auditable with retry policy, local
response/cache metadata, data-quality checks, and recoverable workflow
diagnostics.

## Required Context

- `src/investment_forecasting/data/ingestion.py`
- `src/investment_forecasting/providers/akshare_provider.py`
- `src/investment_forecasting/workflows/daily.py`

## Modify Scope

- Provider retry/caching utilities.
- Data-quality report records or task-log metadata.
- Workflow failure and partial-success diagnostics.
- Tests and failure fixtures.

## Forbidden

- Do not hide provider failures by returning stale data without marking it.
- Do not make network access mandatory for unit tests.

## Acceptance

- Provider calls have deterministic retry behavior and optional proxy retry
  guidance.
- Ingestion records data-quality warnings for empty rows, missing required
  columns, duplicate dates, and large gaps.
- Daily workflow logs partial progress and enough metadata to recover.

## Test Plan

- Unit tests for retry decisions and cache metadata.
- Fixture tests for quality warnings.
- Simulated provider failure writes actionable logs.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added `data_quality_reports` persistence.
- Added deterministic provider retry configuration in `AkshareProvider`.
- Added retry wrapping for AKShare history and fund info calls.
- Existing ETF and stock fallback paths now participate in retry behavior.
- Ingestion now writes one quality report per asset with status, warnings, row
  count, date range, provider, and asset metadata.
- Quality validation detects empty rows, missing/invalid dates, duplicate dates,
  and large calendar gaps.
- Provider errors include proxy retry guidance from `AGENTS.md`.
- Added tests for retry behavior, quality warning generation, report
  serialization, and ingestion report persistence.
- Validation passed with `python3 -m pytest`.
- Live smoke wrote 10 `data_quality_reports` for the expanded MVP universe.
