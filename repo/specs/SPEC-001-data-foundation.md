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
- Deterministic industry/theme labels derived from stored asset metadata until
  provider-backed industry tables or fund holdings are available.
- Provider-neutral capital-flow observations for market or tracked-asset
  subjects, starting with AKShare A-share money-flow fields.
- Provider-neutral public-fund holding observations, starting with quarterly
  AKShare/Eastmoney stock-holding reports.
- Provider-neutral news evidence records for financial news flashes, starting
  with optional Tushare `news`, indexed by source, datetime, asset/theme link,
  event type, and directional sentiment.
- Repeatable commands to initialize the database and run tests.

## Constraints

- Use SQLite for MVP persistence.
- Use AKShare first; later providers must be adapter-compatible and explicit.
- Tushare Pro support is optional: credentials and the SDK are never required
  for default MVP commands, and provider selection must be logged/auditable.
- Data updates must be retryable and must record failures.
- Database writes should be idempotent by asset/date/source where practical.
- Residential-network AKShare ingestion must be sequential and polite by
  default, using configurable delay/jitter and retry backoff rather than
  concurrent bulk pulls.
- Provider history updates should use incremental date ranges when local
  history already exists.
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
- Optional Tushare ingestion writes normalized rows into the same provider
  neutral schema and uses `source='tushare'` rather than adding parallel tables.
- Failed data pulls write an actionable `task_logs` entry.
- Task logs and quality metadata record provider request counts, retry/backoff
  settings, incremental date decisions, and likely throttling/empty-response
  warnings where observable.
- Industry/theme classification is deterministic, auditable, and does not
  require a paid taxonomy or hidden LLM inference.
- Capital-flow observations persist stable main/super-large/large/medium/small
  inflow fields and retain raw payloads without exposing provider columns to
  quant or WebUI code.
- Fund holdings persist stable report-period, holding-code/name, weight,
  shares, market-value, rank, and source fields with raw payloads retained for
  audit.
- News evidence persists stable provider/source, published datetime, title,
  content excerpt, channels, deduplication hash, raw payload, linked
  asset/theme references, event tags, and sentiment direction without exposing
  provider raw columns directly to quant, WebUI, or MCP callers.

## Related Context

- `ARCHITECTURE.md`
- `decisions/ADR-001-mvp-local-first-akshare-sqlite.md`
- `tasks/TASK-001-python-skeleton-sqlite-schema.md`
- `tasks/TASK-002-akshare-ingestion.md`
