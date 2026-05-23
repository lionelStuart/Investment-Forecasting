# SPEC-004: MCP Service

## Status

draft

## Goal

Expose stable JSON-oriented tools so AI agents can retrieve stored data, run
forecast/backtest workflows, and generate or read daily advice.

## Non-Goals

- Do not let AI agents bypass services and query provider raw fields directly.
- Do not return free-form prose where clients need stable schemas.
- Do not expose destructive database operations through MVP tools.

## Inputs

- Tool arguments such as asset filters, date ranges, horizons, model IDs, and
  advice dates.
- SQLite-backed service outputs.

## Outputs

- MCP tools:
  - `get_asset_list`
  - `get_asset_history`
  - `get_fund_metrics`
  - `get_market_snapshot`
  - `run_forecast`
  - `run_backtest`
  - `get_daily_advice`
  - `generate_daily_advice`

## Constraints

- Responses must be JSON-compatible and include error fields on failure.
- Tool schemas must document required and optional arguments.
- Long-running tools should report progress through logs or structured status.
- MCP must preserve auditability by referencing stored record IDs.

## Error Cases

- Unknown asset code or unsupported asset type.
- Invalid date range or forecast horizon.
- Missing database or stale schema.
- Forecast/backtest service raises validation errors.

## Acceptance

- Each MVP tool has a typed schema and a service-backed implementation.
- Tool responses include stable fields for AI consumption and WebUI reuse.
- Errors are deterministic enough for an agent to recover or explain.
- MCP integration tests or smoke tests cover the core tools.

## Related Context

- `ARCHITECTURE.md`
- `tasks/TASK-006-mcp-tools.md`

