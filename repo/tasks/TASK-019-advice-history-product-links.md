# TASK-019: Advice History and Product Links

## Status

completed

## Source

User goal: 当前每日建议需要能选择查看历史记录，近期关注的标的需要能展开到该产品。

## Goal

Make the WebUI daily advice page useful for reviewing past advice and drilling
from focused assets into the corresponding product data page.

## Required Context

- `src/investment_forecasting/web/app.py`
- `tests/test_web_app.py`
- README WebUI goal for daily advice and focused assets.

## Modify Scope

- Daily advice page routing/query behavior.
- Focus asset card rendering.
- WebUI tests.

## Forbidden

- Do not change the persisted advice schema unless required.
- Do not remove existing advice evidence or risk-warning display.

## Acceptance

- `/advice` defaults to the latest advice record.
- `/advice?advice_id=...` renders the selected historical advice record.
- The advice page has a history selector and history links.
- Focus asset cards link to `/data?asset_id=...`.
- The product page shows the selected asset's curve/history context.

## Test Plan

- Add WebUI tests for advice history selection and focus asset links.
- Run the full test suite.
- Smoke the local WebUI route and follow one focus asset link.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added an advice history selector on `/advice`.
- Added a historical records table with links to `/advice?advice_id=...`.
- Changed `/advice` to render the selected advice record instead of dumping the
  latest 60 records inline.
- Made focus asset recommendation cards link to `/data?asset_id=...`, where
  the asset's curve, price history, and feature metrics are visible.
- Added tests covering history selection and focus-asset drill-down links.
- Validation passed with `python3 -m pytest`.
- HTTP smoke against a running local WebUI confirmed history links and product
  drill-down links.
