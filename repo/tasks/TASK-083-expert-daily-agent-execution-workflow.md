# TASK-083: Expert Daily Agent Execution Workflow

## Status

completed

## Purpose

Replace the product meaning of expert daily planning with system-scheduled,
role-scoped expert Codex agent runs. Each active expert must complete or
explicitly skip/fail its T-day virtual investment action before Jarvis can run
the next-day synthesis.

## Scope

- Add a system workflow step that creates pending expert agent runs for a T
  date.
- Invoke or simulate Codex runtime through the access layer using the expert
  skill, prompt, allowed tool manifest, and output schema.
- Accept structured expert output only through submission APIs.
- Validate and persist the expert analysis and expert plan/action.
- Simulate execution through existing portfolio accounting.
- Record skipped/failed expert runs explicitly.
- Expose expert agent run status through CLI/MCP and optional WebUI evidence.

## Non-Scope

- No Jarvis T+1 workflow.
- No live trading.
- No multi-round debate among experts.
- No new data provider or model.

## Files Likely To Change

- `src/investment_forecasting/agent_runtime/`
- `src/investment_forecasting/experts/planning.py`
- `src/investment_forecasting/workflows/daily.py`
- `src/investment_forecasting/mcp/tools.py`
- `src/investment_forecasting/cli.py`
- `tests/test_agent_runtime.py`
- `tests/test_experts.py`
- `tests/test_daily_workflow.py`
- `tests/test_mcp_tools.py`

## Implementation Checklist

- Add `prepare_expert_agent_runs(date)` service.
- Add `run_expert_agent(date, expert_key)` service with deterministic test
  double support.
- Validate submitted action against expert mandate, risk limits, cash, price
  availability, and evidence IDs.
- Link `expert_plans.ai_analysis_id` and expert plan/action to `agent_run_id`.
- Make failure visible as skipped/failed, not hidden deterministic success.

## Acceptance Criteria

- For a seeded database, the workflow creates one expert agent run per active
  expert for T.
- Each expert run ends in completed, skipped, failed, or validation_failed.
- Completed runs persist an expert plan/action and simulated execution using
  existing portfolio services.
- Jarvis readiness can tell whether expert T actions are complete enough.
- Tests verify one success path, one validation failure path, and one skipped
  path.

## Test Plan

- `python3 -m pytest tests/test_agent_runtime.py tests/test_experts.py tests/test_daily_workflow.py tests/test_mcp_tools.py -q`

## Depends On

- `TASK-082`

## Completion Notes

- `agent-runs run-experts-codex` now runs one local Codex expert agent per
  active expert with the expert overview skill, schema, and manifest.
- Runtime artifacts are cleared on rerun to avoid stale output reuse.
- Accepted expert artifacts are audited through `agent_tool_calls`, validated,
  persisted into `expert_plans`, and linked through `evidence.agent_run_id`.
- Skipped/failed expert artifacts produce explicit `no_trade` plans rather
  than leaving hidden deterministic success.
