# TASK-011: MCP Stdio Transport

## Status

completed

## Source

`README.md`, `SPEC-004`, `TASK-010`

## Goal

Wrap the existing MCP-compatible tool registry in a real stdio MCP server so AI
clients can call tools through standard MCP transport rather than only the local
JSON CLI.

## Required Context

- `repo/specs/SPEC-004-mcp-service.md`
- `src/investment_forecasting/mcp/tools.py`
- `repo/audits/README-MVP-COMPLETION-2026-05-23.md`

## Modify Scope

- MCP transport/server module.
- Packaging dependencies or ADR if a new SDK is introduced.
- Tests or smoke scripts proving tool list and tool call over the transport.
- README/PROJECT command notes.
- `repo/STATUS.md`, `repo/INDEX.md`, this task file.

## Forbidden

- Do not duplicate tool business logic outside the registry.
- Do not expose destructive database tools.
- Do not return unstructured prose where JSON fields are needed.

## Acceptance

- A documented command starts the MCP stdio server.
- The server lists the eight MVP tools from `SPEC-004`.
- At least one read tool and one workflow tool can be called through the
  transport in a smoke test.
- Transport errors preserve structured error messages.

## Test Plan

- Run unit tests for the transport wrapper.
- Run a local smoke script that initializes the server, lists tools, and calls
  `get_market_snapshot` or equivalent.
- Run the full test suite.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added official MCP Python SDK dependency.
- Added `investment_forecasting.mcp.server` with `FastMCP` stdio transport over
  the existing `investment_forecasting.mcp.tools` registry.
- Added commands:
  - `investment-forecasting-mcp --db data/investment_forecasting.sqlite3`
  - `investment-forecasting mcp serve --db data/investment_forecasting.sqlite3`
- The server exposes all eight MVP tools from `SPEC-004`.
- Added stdio client smoke test covering `list_tools`, `get_market_snapshot`,
  `run_forecast`, and structured error output from `get_asset_history`.
- Added `ADR-002` documenting the official MCP Python SDK choice.
- Validation passed with `python3 -m pytest`.

## Follow-Ups

- Register the MCP server with the user's preferred AI client if requested.
