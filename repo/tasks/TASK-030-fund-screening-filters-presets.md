# TASK-030: Fund Screening Filters And Presets

## Status

completed

## Source

`repo/audits/PRODUCT-EXPERIENCE-ACCEPTANCE.md` next phase target: upgrade fund
screening.

## Goal

Turn the fund page from a static ranking table into a practical screening
workflow with category-aware filters and risk-profile presets.

## Acceptance

- Before implementation, inspect existing `fund_info`, `features_daily`,
  `user_preferences`, and `/funds` rendering. Reuse existing query and format
  helpers before adding new ones.
- Fund page supports filters for fund type, manager, scale range, fee
  availability, 20-day return, 60-day drawdown, Sharpe, win rate, and market
  state where fields exist.
- Fund page includes at least conservative, balanced, and aggressive presets.
- Filtered results show a suitability or data-completeness explanation.
- Missing fund metadata is explained in product language instead of appearing
  only as `NULL`.
- Tests cover at least four filters and one preset.
- `ARCHITECTURE.md` and `CODE_INDEX.md` are updated if fund screening introduces
  shared view models, new routes, or reusable filter helpers.

## Implementation Notes

- `/funds` now renders a reusable filter form instead of only a static ranking
  table.
- Supported filters include fund type, manager, market state, scale range, fee
  availability, 20-day return, 60-day drawdown floor, Sharpe, and 60-day win
  rate.
- Added conservative, balanced, and aggressive preset links that translate into
  query filters.
- Results include suitability/data-completeness explanations such as return
  sample status, drawdown, Sharpe, fee completeness, and preset match.
- Missing fund metadata is shown as product language (`基金类型待补充`,
  `基金经理待补充`, `规模待补充`, `费率待补充`) rather than raw `NULL`.
- Raw fund fields remain available in a secondary technical details section.

## Verification

- `python3 -m pytest` passed with 68 tests.
- `/funds` was smoke checked after WebUI restart.
