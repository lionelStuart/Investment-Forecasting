# TASK-081: Role-Scoped MCP/API Tool Manifest

## Status

completed

## Purpose

Give Codex expert and Jarvis agent runs a bounded tool surface. The system
should expose exactly which MCP/API tools a role may call, which tools are
read-only, which tools submit outputs, and which tools are unavailable.

## Scope

- Add a role-scoped tool manifest service for expert and Jarvis runs.
- Map each role manifest to the domain/function skills it may use.
- Group tools into read, submit, validation, and operations capabilities.
- Add submission-oriented API/MCP tools needed by agent runs:
  - submit expert analysis draft;
  - submit expert virtual plan/action;
  - record expert skipped/failed action;
  - submit Jarvis analysis draft;
  - submit Jarvis daily brief;
  - validation preview for expert/Jarvis output.
- Add an MCP/API surface to list allowed tools for a role.
- Audit tool calls against `agent_runs` when an agent run ID is provided.
- Enforce the runtime tool contract from `SPEC-012`: each call must include
  `agent_run_id`, role metadata, arguments, and idempotency key for submission
  tools.

## Non-Scope

- No prompt-template implementation.
- No live Codex execution.
- No direct SQLite write tools.
- No WebUI scraping or browser automation as an evidence path.

## Files Likely To Change

- `src/investment_forecasting/agent_runtime/`
- `src/investment_forecasting/mcp/tools.py`
- `src/investment_forecasting/mcp/server.py`
- `src/investment_forecasting/experts/planning.py`
- `src/investment_forecasting/jarvis/synthesis.py`
- `tests/test_agent_runtime.py`
- `tests/test_mcp_tools.py`
- `tests/test_mcp_server.py`

## Implementation Checklist

- Design and persist local Codex CLI runtime artifact directories inside the
  project before enabling role tool manifests.
- Define expert allowed read tools: market/model/news/asset/portfolio/expert
  context.
- Define expert allowed skill bundle: market data, model evidence, news
  evidence, asset research, expert portfolio, virtual action, output contract.
- Define expert allowed submission tools: expert analysis, expert plan/action,
  skipped/failed action.
- Define Jarvis allowed read tools: system market/model/news evidence, expert
  outputs, scorecards, virtual returns, task health, user preference.
- Define Jarvis allowed skill bundle: market data, model evidence, news
  evidence, asset research, expert portfolio read-only, Jarvis synthesis,
  output contract.
- Define Jarvis allowed submission tools: Jarvis analysis and daily brief.
- Ensure forbidden tools are not exposed for a role.
- Reject calls for missing/non-running `agent_run_id`, tools outside the role
  manifest, future-date evidence outside scope, or cross-role submissions.
- Add bounded output schemas for submission tools.

## Progress Notes

- Added the runtime-side foundation needed by role manifests:
  `CodexCliRuntimeAdapter` now checks local Codex CLI readiness, prepares
  per-run artifacts under `data/agent_runtime/runs/<agent_run_id>/`, builds
  non-interactive `codex exec` commands with `--ask-for-approval never` and
  `--sandbox workspace-write` by default, and records pid/command/artifact
  metadata back to `agent_runs.runtime_metadata_json`.
- Corrected runtime model selection after local smoke exposed that
  `gpt-5-codex` is not supported under the current ChatGPT-authenticated CLI.
  The adapter now uses the local Codex config model by default and only passes
  `--model` when runtime policy or `INVESTMENT_FORECASTING_CODEX_MODEL`
  explicitly sets one.
- Project artifact layout:
  - `request.json`: materialized `codex_agent_runtime_v1` request.
  - `prompt.md`: role prompt snapshot used for the run.
  - `output_schema.json`: structured final-response schema.
  - `events.jsonl`: Codex `--json` event stream.
  - `last_message.txt`: Codex `--output-last-message` artifact.
  - `stderr.log`: runtime stderr.
  - `result.json`: reserved validated system result artifact.
- `agent-runs codex-readiness` now verifies the local binary and login status.
- `agent-runs codex-smoke` now performs a real local Codex CLI runtime smoke
  using the same artifact path and marks the run `completed_via_artifact` when
  `last_message.txt` is produced.
- Added role-scoped manifests for expert and Jarvis runs with distinct skill
  bundles, read tools, submission tools, validation tools, operations tools,
  and explicit forbidden shell/SQL/WebUI/live-trading/communication-send
  capabilities.
- Added agent-aware tool validation and `agent_tool_calls` audit for allowed,
  rejected, submitted, and failed calls.
- Added MCP/API surfaces for `get_agent_tool_manifest`,
  `validate_agent_output`, `submit_expert_virtual_action`, and
  `submit_jarvis_daily_brief`. Submission tools currently persist audited
  envelopes only; `TASK-083`/`TASK-084` will connect those envelopes to final
  expert/Jarvis business validators.

## Acceptance Criteria

- A test can request an expert tool manifest and see only expert-safe tools.
- A test can request a Jarvis tool manifest and see Jarvis-specific tools.
- A test can request each role's allowed skill bundle and verify expert and
  Jarvis bundles are different.
- Submission tools validate required `agent_run_id`.
- Tool calls are auditable when associated with an agent run.
- Calls outside the role manifest are rejected and recorded as failed tool
  attempts.
- No role manifest grants shell, SQL, WebUI scraping, live trading, or
  communication-send privileges by default.

## Test Plan

- `python3 -m pytest tests/test_agent_runtime.py tests/test_mcp_tools.py tests/test_mcp_server.py -q`

## Depends On

- `TASK-080`

## Verification

- `python3 -m pytest tests/test_agent_runtime.py tests/test_mcp_tools.py tests/test_mcp_server.py -q`
- `python3 -m investment_forecasting.cli agent-runs codex-readiness --db data/investment_forecasting.sqlite3 --project-root /Users/wonderwall/project/Investment-Forecasting`
- `python3 -m investment_forecasting.cli agent-runs codex-smoke --db data/investment_forecasting.sqlite3 --project-root /Users/wonderwall/project/Investment-Forecasting --timeout-seconds 180`
  returned `ok=true`, `agent_run_id=4`, `status=completed_via_artifact`, and
  `last_message={"status":"ok","summary":"local codex runtime smoke passed"}`.
