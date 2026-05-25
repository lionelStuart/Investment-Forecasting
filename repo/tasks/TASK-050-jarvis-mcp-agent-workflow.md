# TASK-050: Jarvis MCP And Agent Workflow

## Status

completed

## Purpose

Expose Jarvis to Agents through structured commands and MCP tools so automation
can retrieve or generate the top-level daily assistant brief.

## Scope

- Add CLI commands for generating and inspecting Jarvis daily advice.
- Add MCP tools for `get_jarvis_daily_brief` and `generate_jarvis_daily_brief`.
- Add task logs for generation success/failure.
- Ensure tools return structured fields, not only prose.

## Non-Scope

- No direct phone sending.
- No live trading command.

## Files Likely To Change

- `src/investment_forecasting/cli.py`
- `src/investment_forecasting/mcp/tools.py`
- `src/investment_forecasting/mcp/server.py`
- `tests/test_mcp_tools.py`
- `tests/test_mcp_server.py`
- `tests/test_jarvis.py`

## Acceptance Criteria

- Agents can retrieve latest Jarvis brief as structured JSON.
- Agents can trigger generation from persisted evidence.
- Generation writes task logs.
- MCP output includes focus directions, model summary, expert summaries,
  current expert returns, and risk warnings.

## Depends On

- `TASK-048`
- `TASK-041`

## Implementation Notes

- Added MCP tool schemas and handlers for `get_jarvis_daily_brief` and
  `generate_jarvis_daily_brief`.
- Exposed both Jarvis tools through the official FastMCP stdio server.
- Jarvis MCP output returns structured fields including focus directions,
  one-line stance, model summary, expert summaries, current expert returns,
  risk warnings, evidence references, and missing/stale evidence.
- Generation reuses the Jarvis synthesis service and writes
  `jarvis_brief_generation` task logs.
- Existing CLI `jarvis generate` remains the command-line entry point for
  humans and automation outside MCP.

## Verification

- `python3 -m pytest tests/test_mcp_tools.py tests/test_mcp_server.py`
- `python3 -m pytest`
- `PYTHONPATH=src python3 -m investment_forecasting.cli db init --db data/investment_forecasting.sqlite3`
