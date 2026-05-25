# TASK-053: Market And Macro Indicator Page

## Status

completed

## Purpose

Make stored market snapshots and macro observations directly inspectable in the
WebUI instead of hiding them behind the dashboard, timeline, or category
placeholder. This closes the product gap where macro/market indicators were
ingested and used by advice/Jarvis but did not have their own workbench page.

## Scope

- Add a `/market` WebUI route and navigation item.
- Show the latest market snapshot with sentiment, index trend, breadth,
  liquidity heat, and stock-bond strength.
- Show latest macro observations by series with human labels.
- Keep market snapshot and macro history available as secondary technical
  details.
- Link the "宏观/市场指标" category drill-in to `/market`.

## Non-Scope

- No new data vendor.
- No new schema.
- No new prediction model or trading advice.

## Files Changed

- `src/investment_forecasting/web/app.py`
- `tests/test_web_app.py`
- `repo/INDEX.md`
- `repo/STATUS.md`
- `repo/ROADMAP.md`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`
- `repo/specs/SPEC-006-webui-workbench.md`

## Acceptance Criteria

- `/market` renders on a populated database.
- Empty market/macro states explain which command to run next.
- Category drill-in for macro/market indicators links to `/market`.
- Tests cover the new route and category link.

## Verification

- `python3 -m pytest tests/test_web_app.py`
- `scripts/restart_web.sh`
