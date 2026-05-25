# TASK-085: Remove Codex Automation And Lock Scheduler Migration

## Status

completed

## Purpose

Remove the old Codex app automation from the operational update path and make
the repository unambiguous: data/news updates are triggered by the system-owned
scheduler, not by Codex automation.

## Scope

- Delete or disable the `investment-forecasting-daily-run` Codex automation.
- Update docs that still describe Codex automation as the current scheduler.
- Add a migration note explaining historical `TASK-007` behavior and the new
  system-owned scheduler direction.
- Add a guardrail check or documented verification command for "no active Codex
  data-refresh automation".

## Non-Scope

- No scheduler implementation yet.
- No data ingestion changes.
- No Codex runtime changes.

## Files Likely To Change

- `repo/specs/SPEC-005-daily-automation.md`
- `repo/tasks/TASK-007-daily-codex-automation.md`
- `repo/STATUS.md`
- `repo/AGENTS.md`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`

## Acceptance Criteria

- No active Codex automation is required for data/news refresh.
- Docs say Codex automation is historical, not the product scheduler.
- `SPEC-013` and `ADR-009` are referenced as the active scheduler direction.
- Verification instructions are available for checking active automations.

## Test Plan

- Inspect `$HOME/.codex/automations` or app automation state.
- Documentation-only verification with `rg "Codex automation|daily 08:00" repo`.

## Completion Notes

- Completed on 2026-05-24.
- Deleted the old Codex app automation `investment-forecasting-daily-run`.
- Verified no Investment Forecasting automation remains under
  `$HOME/.codex/automations`.
- Updated project memory to point scheduler work at `SPEC-013` and `ADR-009`.

## Depends On

- `SPEC-013`
- `ADR-009`
