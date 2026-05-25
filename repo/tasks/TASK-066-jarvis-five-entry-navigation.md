# TASK-066: Jarvis Five-Entry Navigation

## Status

completed

## Purpose

Move the WebUI from a developer workbench navigation model to a Jarvis-first
consumer information architecture. The first-level navigation should reflect
what the user wants to do each day, not how the system is implemented.

## Scope

- Replace the primary navigation with five entries:
  - 今日简报
  - 机会池
  - 专家团
  - 证据
  - 设置
- Make 今日简报 the default user entry.
- Keep legacy technical routes available for direct links, evidence drill-down,
  tests, and agents, but remove them from first-level navigation.
- Add route aliases or redirects only where needed to preserve existing links.

## Non-Scope

- No new data source, model, expert, AI provider behavior, or investment logic.
- No broad visual redesign beyond navigation and route grouping.
- No deletion of existing technical routes in this task.

## Files Likely To Change

- `src/investment_forecasting/web/app.py`
- `tests/test_web_app.py`
- `repo/specs/SPEC-006-webui-workbench.md`
- `repo/CODE_INDEX.md`

## Implementation Checklist

- Find the shared navigation builder or sidebar template in `web/app.py`.
- Replace old module labels with the five consumer labels.
- Ensure old labels such as 研究时间线, 产品分类, 数据与曲线, 基金筛选, 预测,
  回测评分, 每日建议, 风险设置, 任务日志 are not first-level nav items.
- Confirm direct route access still works for technical pages.

## Acceptance Criteria

- The rendered primary navigation contains exactly the five entries:
  今日简报, 机会池, 专家团, 证据, 设置.
- The default route leads to the 今日简报 experience or clearly links to it as
  the primary action.
- Legacy technical pages do not appear as first-level navigation.
- Existing route tests still pass after any alias or label changes.

## Test Plan

- `python3 -m pytest tests/test_web_app.py -q`

## Depends On

- `TASK-061`
