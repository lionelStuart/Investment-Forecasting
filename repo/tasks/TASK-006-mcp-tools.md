# TASK-006: MCP Tools

## Status

completed

## Source

`SPEC-004`

## Goal

Expose the MVP service capabilities as stable MCP tools for AI agents.

## Required Context

- `PROJECT.md`
- `STATUS.md`
- `specs/SPEC-004-mcp-service.md`
- `ARCHITECTURE.md`

## Modify Scope

- MCP server/tool definitions.
- Service adapters used by MCP.
- Tests or smoke scripts.
- Project memory write-back files.

## Forbidden

- Do not expose destructive database tools.
- Do not return only natural-language prose.
- Do not bypass service-layer validation.

## Acceptance

- Implement tools listed in `SPEC-004` or mark deferred ones explicitly.
- Tool schemas define inputs and stable JSON-compatible outputs.
- Tool failures return structured errors.
- Smoke tests cover asset list/history, market snapshot, forecast/backtest, and
  daily advice retrieval/generation paths where implemented.

## Test Plan

- Run MCP unit/smoke tests.
- Call representative tools locally.
- Verify outputs include IDs linking back to stored records.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added MCP-compatible tool registry in `investment_forecasting.mcp.tools`.
- Added JSON schemas and implementations for:
  `get_asset_list`, `get_asset_history`, `get_fund_metrics`,
  `get_market_snapshot`, `run_forecast`, `run_backtest`,
  `get_daily_advice`, and `generate_daily_advice`.
- Added structured envelopes for success and deterministic errors:
  `{ok, tool, result, error}`.
- Added CLI smoke interface:
  `investment-forecasting mcp list-tools` and
  `investment-forecasting mcp call TOOL_NAME --db ... --args '{}'`.
- Added tests covering schemas, asset list/history, fund metrics, snapshot,
  forecast, backtest, advice retrieval/generation, and structured errors.
- Validation passed with `python3 -m pytest`.
- Smoke validation listed 8 tools and returned a JSON market snapshot from the
  MVP sample database.

Deferred:

- A full stdio/network MCP transport wrapper is deferred. The stable tool
  registry is intentionally transport-neutral so an MCP SDK wrapper can be
  added without changing service behavior.

## Follow-Ups

- `TASK-007`: Daily Codex automation.
