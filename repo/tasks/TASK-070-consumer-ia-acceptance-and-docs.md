# TASK-070: Consumer IA Acceptance And Docs

## Status

completed

## Purpose

Close the Jarvis consumer information-architecture round with product
acceptance, documentation synchronization, and an explicit decision about
whether to resume AI interaction tasks.

## Scope

- Verify the product against the five-entry navigation acceptance gate.
- Update `ARCHITECTURE.md`, `CODE_INDEX.md`, `STATUS.md`, `INDEX.md`, and
  relevant specs/tasks to reflect implemented routes and route ownership.
- Record whether `TASK-062` through `TASK-065` should resume next or whether
  another product issue blocks them.
- Add a short acceptance note covering remaining UI risks.

## Non-Scope

- No new feature implementation except small fixes required to pass the IA
  acceptance gate.
- No AI provider orchestration work.
- No new data, expert, optimizer, or phone-command scope.

## Files Likely To Change

- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`
- `repo/INDEX.md`
- `repo/STATUS.md`
- `repo/specs/SPEC-006-webui-workbench.md`
- `tests/test_web_app.py`

## Implementation Checklist

- Confirm the rendered nav has exactly five primary entries.
- Confirm old technical pages are secondary/direct only.
- Confirm the default journey is 今日简报 -> 机会池 -> 专家团 -> 证据/设置 as
  needed.
- Run WebUI tests and any focused Jarvis/communication tests touched by the
  route consolidation.

## Acceptance Criteria

- Project memory and code index match the implemented five-entry IA.
- The phase has an explicit stop decision: accepted, blocked with exact reason,
  or requires another product review.
- The next recommended implementation task is named clearly.

## Test Plan

- `python3 -m pytest tests/test_web_app.py -q`
- `rg -n "TASK-066|TASK-067|TASK-068|TASK-069|TASK-070|今日简报|机会池|专家团|证据|设置" repo/STATUS.md repo/INDEX.md repo/specs/SPEC-006-webui-workbench.md repo/CODE_INDEX.md`

## Depends On

- `TASK-066`
- `TASK-067`
- `TASK-068`
- `TASK-069`
