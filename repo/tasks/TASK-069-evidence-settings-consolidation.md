# TASK-069: Evidence And Settings Consolidation

## Status

completed

## Purpose

Move technical trust and operational details out of primary consumer
navigation by consolidating them into 证据 and 设置.

## Scope

- Create a 证据 page or section that gives advanced users and Agents access to
  model predictions, backtests, model health, market snapshots, macro/capital
  flow, data coverage, and raw technical tables.
- Create or adapt 设置 so risk preferences, investment horizon, notification
  setup, communication health, data update status, and task logs live together.
- Treat task logs as system health advanced detail, not a first-level page.

## Non-Scope

- No new model metrics.
- No new communication channel.
- No schema migration unless strictly required for display.
- No removal of existing direct technical routes.

## Files Likely To Change

- `src/investment_forecasting/web/app.py`
- `tests/test_web_app.py`
- `repo/CODE_INDEX.md`

## Implementation Checklist

- Reuse existing prediction, backtest, market, logs, settings, and
  communication helpers.
- Provide links from 今日简报 and 机会池 into relevant evidence anchors.
- Ensure raw technical tables remain collapsed by default.
- Ensure task log failures remain findable from 设置 / 系统健康.

## Acceptance Criteria

- 证据 contains model prediction, backtest, market/data, model-health, and raw
  evidence entry points.
- 设置 contains risk preferences, horizon, notification setup, communication
  health, data update status, and task logs/system health.
- 回测评分 and 任务日志 are not first-level navigation items.
- Existing direct routes still work for agents and saved links.

## Test Plan

- `python3 -m pytest tests/test_web_app.py tests/test_communication.py -q`

## Depends On

- `TASK-066`
