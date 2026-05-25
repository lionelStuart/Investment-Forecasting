# TASK-080: Codex Runtime Access Contract And Agent Run Audit

## Status

completed

## Purpose

Introduce a system-owned Codex runtime access layer and a concrete interaction
protocol so expert and Jarvis agent runs are launched, tracked, validated, and
audited by the Investment Forecasting system instead of being confused with
Codex scheduled automation or plain AI provider calls.

## Scope

- Add a runtime access contract for role-scoped Codex agent tasks.
- Add serializable launch request, runtime policy, result, and status schemas.
- Add a fake runtime adapter for tests and a real-adapter placeholder boundary.
- Add persisted agent-run audit records for expert and Jarvis runs.
- Record run date, target evidence date, role type, role key, trigger reason,
  protocol version, overview skill, skill bundle, prompt/tool manifest refs,
  output contract, status, runtime metadata, timestamps, submission result, and
  failure/fallback reason.
- Add tool-call audit persistence or a minimal placeholder model for the next
  task to fill.
- Add CLI or service inspection for pending/completed/failed agent runs.
- Keep the existing daily workflow and provider adapter working while clearly
  marking them as separate layers.

## Non-Scope

- No live Codex invocation implementation beyond a testable boundary.
- No expert prompt templates yet.
- No Jarvis T+1 execution yet.
- No new investment model, data provider, live trading, or WebUI redesign.

## Files Likely To Change

- `src/investment_forecasting/agent_runtime/`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/cli.py`
- `tests/test_agent_runtime.py`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`

## Implementation Checklist

- Define agent run status values: pending, running, completed, failed,
  submitted, completed_via_artifact, skipped, validation_failed, cancelled,
  and timed_out.
- Define role types: expert, jarvis.
- Create idempotent run identity for `(role_type, role_key, run_date,
  target_evidence_date, version)`.
- Define `CodexAgentLaunchRequest`, `CodexRuntimePolicy`,
  `CodexAgentRunResult`, and `AgentRunHandle` dataclasses or equivalent typed
  dictionaries.
- Define fake adapter behavior for start, poll, cancel, and collect-result.
- Add service helpers to create, start, complete, fail, and list agent runs.
- Ensure no helper allows direct SQL mutation by Codex output.
- Add test fixtures for one expert run and one Jarvis run.

## Acceptance Criteria

- A test can create and complete one expert agent run for a T date.
- A test can create and fail one Jarvis agent run for a T+1 date with an error.
- A test can render a launch request with overview skill, skill bundle, prompt
  ref, tool manifest ref, output contract, and runtime policy.
- A fake adapter can move a run through pending -> running -> completed.
- A fake adapter can move a run through pending -> running -> timed_out or
  cancelled.
- Duplicate run creation is idempotent or explicitly versioned.
- Agent run records are queryable through a service or CLI inspection command.
- Documentation clearly distinguishes system scheduler, Codex runtime access
  layer, and AI provider adapter.

## Test Plan

- `python3 -m pytest tests/test_agent_runtime.py -q`
- `python3 -m pytest tests/test_db.py -q`

## Depends On

- `SPEC-012`
- `ADR-008`

## Completion Notes

- Added `agent_runs` and `agent_tool_calls` audit tables with idempotent
  `(role_type, role_key, run_date, target_evidence_date, version)` run
  identity.
- Added `investment_forecasting.agent_runtime` with serializable
  `codex_agent_runtime_v1` launch request, runtime policy, handle, result,
  status constants, service helpers, and a fake Codex runtime adapter for
  tests.
- Added db helpers to create/prepare, update, list, and record agent runtime
  audit rows without allowing Codex output to mutate investment tables
  directly.
- Added `investment-forecasting agent-runs list` for inspecting expert/Jarvis
  runtime audit records.
- Kept real Codex invocation, role-scoped tool manifests, expert prompt
  templates, expert execution, and Jarvis T+1 readiness for `TASK-081` through
  `TASK-084`.

## Verification

- `python3 -m pytest tests/test_agent_runtime.py tests/test_db.py -q`
- `python3 -m investment_forecasting.cli agent-runs list --db /tmp/agent_runtime_smoke.sqlite3 --limit 5`
