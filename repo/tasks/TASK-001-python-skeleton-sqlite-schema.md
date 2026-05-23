# TASK-001: Python Skeleton And SQLite Schema

## Status

completed

## Source

`SPEC-001`

## Goal

Establish the implementation project skeleton, dependency management, SQLite
schema, migration/init command, and baseline tests.

## Required Context

- `PROJECT.md`
- `STATUS.md`
- `specs/SPEC-001-data-foundation.md`
- `ARCHITECTURE.md`
- `decisions/ADR-001-mvp-local-first-akshare-sqlite.md`

## Modify Scope

- Python packaging/config files.
- Application source directory.
- Tests directory.
- Database migration/schema files.
- README command notes if commands are added.
- `repo/STATUS.md`, `repo/INDEX.md`, this task file.

## Forbidden

- Do not introduce a WebUI framework yet unless required for packaging.
- Do not call external data providers in this task.
- Do not choose a non-SQLite primary store.

## Acceptance

- A documented command creates or migrates the SQLite database.
- Tables from `SPEC-001` exist with primary keys and uniqueness constraints
  suitable for idempotent daily writes.
- A documented test command runs successfully.
- Tests verify schema creation and at least one insert/query path.
- Project default commands in `PROJECT.md` are updated.

## Test Plan

- Run the schema initialization command against a temporary database.
- Run the test suite.
- Inspect the database schema or use tests to assert required tables.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added Python package configuration in `pyproject.toml`.
- Added `investment-forecasting db init --db ...` to create the SQLite schema.
- Added core README/SPEC-001 tables with primary keys, foreign keys, and
  idempotent uniqueness constraints for daily writes.
- Added tests for schema creation and asset upsert/query behavior.
- Validation passed with `python3 -m pytest`.

## Follow-Ups

- `TASK-002`: AKShare ingestion.
