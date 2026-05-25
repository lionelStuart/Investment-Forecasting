# TASK-065: Architecture And Code Index Synchronization

## Status

completed

## Purpose

Close the AI interaction layer milestone by updating the architecture diagram,
module design, code index, and development guardrails so future agents reuse
the new AI provider boundary instead of adding duplicate pipelines.

## Scope

- Update `ARCHITECTURE.md` with the implemented AI provider adapter, prompt
  boundary, fallback path, task-log policy, and data flow.
- Update `CODE_INDEX.md` with new modules, commands, tests, WebUI/MCP surfaces,
  and task-family inspection hints.
- Update `INDEX.md`, `STATUS.md`, and related specs/tasks with final status.
- Add a short product acceptance note that states whether the phase is done or
  which exact acceptance item remains.

## Non-Scope

- No new product feature beyond exposing provider/fallback status already
  produced by prior tasks.
- No new data source, optimizer, expert, communication channel, or page family.
- No broad refactor unrelated to the AI interaction layer.

## Files Likely To Change

- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`
- `repo/INDEX.md`
- `repo/STATUS.md`
- `repo/specs/SPEC-009-jarvis-ai-investment-assistant.md`
- `repo/tasks/TASK-061-ai-provider-adapter-contract.md`
- `repo/tasks/TASK-062-ai-prompt-evidence-schema-freeze.md`
- `repo/tasks/TASK-063-provider-backed-ai-orchestration.md`
- `repo/tasks/TASK-064-jarvis-confidence-gates.md`

## Implementation Checklist

- Confirm all new code paths are represented in the architecture diagram.
- Confirm `CODE_INDEX.md` tells agents where to inspect before editing AI,
  expert, Jarvis, WebUI, MCP, workflow, and tests.
- Confirm all phase tasks include verification commands and final status.
- Record final stop condition in `STATUS.md`.

## Acceptance Criteria

- Project memory lets a new agent understand the AI interaction layer without
  reverse-engineering the code.
- There is one documented AI provider boundary and no documented parallel path.
- The phase has an explicit stop decision: complete, blocked with exact reason,
  or requires product review.

## Test Plan

- `rg -n "TASK-061|TASK-062|TASK-063|TASK-064|TASK-065|AI provider|ai_providers|fallback" repo/ARCHITECTURE.md repo/CODE_INDEX.md repo/INDEX.md repo/STATUS.md repo/specs/SPEC-009-jarvis-ai-investment-assistant.md`

## Depends On

- `TASK-061`
- `TASK-062`
- `TASK-063`
- `TASK-064`

## Completion Notes

- Updated architecture, code index, project status, task statuses, and
  SPEC-009 to describe the AI provider boundary, prompt/schema freeze,
  provider/fallback orchestration, Jarvis confidence gates, MCP status, and
  stop condition for the AI interaction layer.
- The documented stop decision is complete: future AI work must reuse
  `investment_forecasting.ai_providers` and `ai_analysis.py` rather than
  adding route-specific provider calls.
- Verification: `rg -n "TASK-061|TASK-062|TASK-063|TASK-064|TASK-065|AI provider|ai_providers|fallback" repo/ARCHITECTURE.md repo/CODE_INDEX.md repo/INDEX.md repo/STATUS.md repo/specs/SPEC-009-jarvis-ai-investment-assistant.md`.
