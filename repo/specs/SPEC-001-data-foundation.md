# SPEC-001: Data Foundation

## Status

draft

## Goal

Build the local data foundation for the MVP: Python project structure, SQLite
schema, migrations, provider adapters, normalized data writes, and data quality
checks.

## Non-Goals

- Do not add live brokerage or trading execution.
- Do not introduce paid-only data sources as required dependencies.
- Do not expose provider raw fields directly to quant, MCP, or WebUI modules.

## Inputs

- AKShare data for A-share indices, ETFs, public funds, and later individual
  A-shares.
- MVP tracked asset universe configuration.
- Existing README and `doc/pre-research.md` requirements.

## Outputs

- SQLite tables: `assets`, `price_daily`, `fund_info`, `features_daily`,
  `model_predictions`, `backtest_runs`, `backtest_results`, `daily_advice`,
  `task_logs`.
- Normalized Python models or records for assets, prices/NAVs, funds, and logs.
- Repeatable commands to initialize the database and run tests.

## Constraints

- Use SQLite for MVP persistence.
- Use AKShare first; later providers must be adapter-compatible.
- Data updates must be retryable and must record failures.
- Database writes should be idempotent by asset/date/source where practical.
- If network access fails, retrying with the local proxy from `AGENTS.md` is
  allowed.

## Error Cases

- Provider API returns changed columns or unexpected units.
- Provider download times out or returns empty data.
- Duplicate asset/date rows are fetched.
- Partial updates succeed before a later asset fails.
- SQLite schema is missing or migration has not run.

## Acceptance

- A clean checkout can install dependencies, initialize SQLite, and run tests.
- Schema creation is covered by tests or an equivalent verification command.
- Insert/update behavior prevents duplicated daily records for the same
  asset/date/source.
- Provider adapters normalize at least one index, one ETF, and one public fund
  history into stable fields.
- Failed data pulls write an actionable `task_logs` entry.

## Related Context

- `ARCHITECTURE.md`
- `decisions/ADR-001-mvp-local-first-akshare-sqlite.md`
- `tasks/TASK-001-python-skeleton-sqlite-schema.md`
- `tasks/TASK-002-akshare-ingestion.md`

