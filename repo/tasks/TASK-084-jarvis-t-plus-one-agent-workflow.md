# TASK-084: Jarvis T+1 Agent Workflow And Readiness Gates

## Status

completed

## Purpose

Make Jarvis a T+1 Codex agent that synthesizes the prior day expert actions,
system evidence, model predictions, news retrieval, expert performance, and
risk context into the consumer-facing daily investment brief.

## Scope

- Add `repo/skills/jarvis-daily-agent/SKILL.md`.
- Add `repo/skills/investment-jarvis-synthesis-skill/SKILL.md` as a
  Jarvis-only domain/function skill.
- Make `repo/skills/jarvis-daily-agent/SKILL.md` the Jarvis overview skill
  that composes Jarvis-safe domain/function skills.
- Add a Jarvis prompt-template builder for `(run_date=T+1,
  target_evidence_date=T)`.
- Add readiness gate requiring all active expert T runs to be completed or
  explicitly skipped/failed before Jarvis runs.
- Invoke or simulate Codex runtime through the access layer with the Jarvis
  overview skill, included domain/function skills, prompt, allowed tool
  manifest, and output schema.
- Submit Jarvis output through system APIs, validate it, persist it, and link
  to the producing `agent_run_id`.
- Surface readiness and agent-run status through MCP/CLI and optional WebUI
  evidence.

## Non-Scope

- No expert execution changes.
- No phone inbound commands.
- No real-money trade execution.
- No broad UI redesign.

## Files Likely To Change

- `repo/skills/jarvis-daily-agent/SKILL.md`
- `repo/skills/investment-jarvis-synthesis-skill/SKILL.md`
- `src/investment_forecasting/agent_runtime/`
- `src/investment_forecasting/jarvis/synthesis.py`
- `src/investment_forecasting/workflows/daily.py`
- `src/investment_forecasting/mcp/tools.py`
- `src/investment_forecasting/cli.py`
- `tests/test_agent_runtime.py`
- `tests/test_jarvis.py`
- `tests/test_daily_workflow.py`
- `tests/test_mcp_tools.py`

## Implementation Checklist

- Define Jarvis readiness query for T+1 over T expert runs.
- Define Jarvis skill bundle and ensure it differs from the expert skill
  bundle.
- Render prompt with T+1 context and T expert action evidence.
- Require Jarvis to distinguish system facts, model evidence, expert views,
  expert scores/returns, Jarvis synthesis, watch triggers, and risk boundaries.
- Validate referenced evidence IDs and expert output IDs.
- Persist failed readiness as a blocked/skipped Jarvis run with reason.

## Acceptance Criteria

- Jarvis T+1 run is blocked when any active expert T run is pending.
- Jarvis T+1 can run when all expert T runs are completed or explicitly
  skipped/failed.
- Jarvis overview skill exists and composes Jarvis-safe domain/function skills.
- Jarvis skill bundle includes Jarvis synthesis and excludes expert virtual
  action submission.
- Persisted Jarvis brief links to the producing `agent_run_id`.
- Jarvis output includes expert action completeness status and downgrades
  confidence when expert evidence is incomplete.
- Tests verify blocked, degraded, and successful T+1 paths.

## Test Plan

- `python3 -m pytest tests/test_agent_runtime.py tests/test_jarvis.py tests/test_daily_workflow.py tests/test_mcp_tools.py -q`

## Depends On

- `TASK-083`

## Completion Notes

- Added `jarvis-daily-agent` and `investment-jarvis-synthesis-skill`.
- `agent-runs run-jarvis-codex` now checks T expert readiness before running
  Jarvis T+1; pending experts create a skipped Jarvis run with readiness
  details.
- Successful Jarvis artifacts are audited, validated, persisted as Jarvis
  briefs, and linked through `evidence.agent_run_id` and
  `evidence.expert_agent_readiness`.
