# TASK-041: Expert Agent Workflow And MCP Integration

## Status

completed

## Purpose

Expose expert committee operations to Agents in a structured way so future
automation can inspect experts, run planning, score results, and review
retirement decisions without scraping WebUI pages.

## Scope

- Add MCP tools for listing experts, getting expert plans, running expert daily
  planning, getting virtual portfolio state, scoring experts, and retrieving
  expert lessons.
- Add CLI commands mirroring the core expert operations.
- Add task logs for expert planning, execution, scoring, review, retirement,
  and hiring.
- Add Agent guidance requiring existing capability inspection before expert
  feature development.

## Non-Scope

- No external trading APIs.
- No unconstrained autonomous execution.

## Files Likely To Change

- `src/investment_forecasting/mcp/tools.py`
- `src/investment_forecasting/mcp/server.py`
- `src/investment_forecasting/cli.py`
- `src/investment_forecasting/workflows/daily.py`
- `repo/AGENTS.md`
- `tests/test_mcp_tools.py`
- `tests/test_mcp_server.py`

## Acceptance Criteria

- MCP tools return structured JSON for expert roster, plans, portfolios,
  scores, reviews, and lessons.
- Expert automation writes task logs.
- Agents can run expert planning and scoring through commands or MCP without
  direct SQL editing.
- Documentation warns that expert outputs are virtual research support, not
  live trading instructions.

## Depends On

- `TASK-036`
- `TASK-038`
- `TASK-039`

## Implementation Notes

- Added structured MCP tools:
  - `list_experts`
  - `get_expert_plans`
  - `run_expert_plans`
  - `get_expert_portfolios`
  - `score_experts`
  - `get_expert_scorecards`
  - `get_expert_lessons`
- Registered those tools in both the JSON-callable tool registry and the
  official FastMCP stdio server.
- Expert planning and scoring services now write `task_logs` for success and
  failure paths.
- Existing CLI commands mirror the core expert operations:
  - `experts init`
  - `experts list`
  - `experts init-portfolios`
  - `experts run-plans`
  - `experts score`
- Tool descriptions and outputs keep expert activity framed as virtual research
  support, not live trading instructions.

## Verification

- `python3 -m pytest tests/test_mcp_tools.py tests/test_mcp_server.py`
