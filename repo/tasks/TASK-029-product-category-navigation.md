# TASK-029: Product Category Navigation

## Status

completed

## Source

`repo/audits/PRODUCT-EXPERIENCE-ACCEPTANCE.md` next phase target: classify
financial products before filtering.

## Goal

Introduce product category navigation so users browse and filter financial
products by type before inspecting raw rows.

## Acceptance

- Before implementation, inspect existing asset type, fund info, dashboard
  asset coverage, and `/data` route capabilities; reuse existing categorization
  fields where possible.
- Assets are grouped into user-facing categories such as fund, ETF, index,
  stock, fixed-income/cash-like proxy, and macro/market indicator where data is
  available.
- Dashboard asset coverage counts link or drill into category views.
- Category views show category-specific summary metrics and empty states.
- `/data` must not show the full raw asset-list table as the primary content.
  Keep the asset selector and replace the table with a selected-asset summary
  and category/context cards. If the full asset list is still needed, move it
  behind a clearly secondary/collapsed technical details area.
- Existing `/data` and `/funds` flows keep working.
- Tests cover category grouping and at least one category navigation path.
- `ARCHITECTURE.md` and `CODE_INDEX.md` are updated if new routes, helpers, or
  category ownership rules are introduced.

## Implementation Notes

- Added `/categories` as the product category navigation route.
- Dashboard asset coverage now links into category views instead of being a
  static count chart.
- Categories currently reuse `assets.asset_type`, asset names/codes, latest
  `features_daily`, latest `model_predictions`, `market_snapshots`, and
  `macro_observations`.
- User-facing categories include public funds, ETF, fixed-income/cash proxies,
  market indices, stocks, and macro/market indicators.
- `/data` keeps the asset selector but now leads with selected-asset summary,
  category context, peer links, curve, history, and metrics. The full raw asset
  list is moved into a secondary technical details section.

## Verification

- `python3 -m pytest` passed with 67 tests.
- WebUI category route and `/data` route were smoke checked after restart.
