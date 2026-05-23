# TASK-002: AKShare Data Ingestion

## Status

completed

## Source

`SPEC-001`

## Goal

Implement provider adapters and ingestion commands for a small MVP universe of
indices, ETFs, and public funds using AKShare.

## Required Context

- `PROJECT.md`
- `STATUS.md`
- `specs/SPEC-001-data-foundation.md`
- `ARCHITECTURE.md`
- `decisions/ADR-001-mvp-local-first-akshare-sqlite.md`

## Modify Scope

- Data provider/adapters.
- Ingestion commands.
- Persistence repository methods needed for ingestion.
- Tests and fixtures.
- Project memory write-back files.

## Forbidden

- Do not let upper-layer services depend on AKShare raw column names.
- Do not require Tushare Pro credentials.
- Do not ingest a huge universe before small-universe reliability is proven.

## Acceptance

- Ingest at least one index, one ETF, and one public fund history into SQLite.
- Normalize provider fields into stable internal field names.
- Handle empty provider responses and changed columns with clear errors.
- Record ingestion failures in `task_logs`.
- Tests cover normalization and duplicate upsert behavior.

## Test Plan

- Run unit tests with fixture data.
- Run a small live or mocked ingestion command.
- Verify row counts and unique asset/date behavior.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added AKShare provider adapter with normalized internal price fields.
- Added MVP tracked universe: one index, one ETF, and one public fund.
- Added `investment-forecasting ingest mvp --db ... --start-date ... --end-date ...`.
- Added idempotent `price_daily` upsert and task log helpers.
- Added ETF fallback from Eastmoney history to Sina history.
- Added tests for normalization, missing columns, duplicate upserts, task-log
  failures, date filtering, and ETF fallback.
- Validation passed with `python3 -m pytest`.
- Live validation ingested 9 rows for 2024-05-20 through 2024-05-22:
  `{'000300': 3, '510300': 3, '000001': 3}`.

## Follow-Ups

- `TASK-003`: Feature and risk metrics.
