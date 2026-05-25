# TASK-067: Today Brief Consolidation

## Status

completed

## Purpose

Make 贾维斯今日简报 the product's default daily decision surface by combining
the useful parts of the old dashboard, Jarvis page, daily advice, and research
timeline.

## Scope

- Build the 今日简报 page around the user's daily questions:
  - 今天怎么看?
  - 为什么?
  - 能不能信?
  - 关注哪些资产?
  - 专家是否一致?
  - 风险边界和观察条件是什么?
- Include today's judgment, one-line conclusion, three core reasons, expert
  consensus/disagreement, key focus assets, data freshness, task health, risk
  warnings, and watch conditions.
- Move raw timeline/advice/debug detail into tabs, collapsed sections, or
  evidence links.

## Non-Scope

- No new Jarvis synthesis logic unless needed to expose already persisted
  fields.
- No AI provider orchestration changes.
- No removal of historical advice or timeline routes.

## Files Likely To Change

- `src/investment_forecasting/web/app.py`
- `tests/test_web_app.py`
- `repo/specs/SPEC-006-webui-workbench.md`
- `repo/CODE_INDEX.md`

## Implementation Checklist

- Reuse existing Jarvis, dashboard brief, advice evidence, and timeline view
  helpers where possible.
- Keep raw rows and JSON behind secondary disclosure.
- Link to evidence rather than duplicating technical tables on the first
  screen.
- Add empty states for missing Jarvis brief, missing advice, or failed daily
  run.

## Acceptance Criteria

- A non-technical user can understand today's stance without opening timeline,
  daily advice, predictions, or logs.
- 今日简报 shows data freshness and task health in product language.
- Expert consensus and disagreement are visible before raw expert details.
- Technical details remain reachable but are not the primary page content.

## Test Plan

- `python3 -m pytest tests/test_web_app.py tests/test_jarvis.py -q`

## Depends On

- `TASK-066`
