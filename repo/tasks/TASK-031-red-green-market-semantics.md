# TASK-031: Red/Green Market Semantics

## Status

pending

## Source

`repo/audits/PRODUCT-EXPERIENCE-ACCEPTANCE.md` next phase target: intuitive
red/green gain-loss markers.

## Goal

Apply consistent Chinese market color semantics across the WebUI: red for
上涨/正收益 and green for 下跌/负收益, with non-color backup labels.

## Acceptance

- Before implementation, inspect existing WebUI CSS, formatting helpers,
  recommendation cards, tables, and curve rendering. Prefer shared utility
  helpers over route-specific styling.
- Dashboard, predictions, funds, advice focus assets, and data tables use
  consistent return/delta styling.
- Positive return-like values are red; negative return-like values are green;
  neutral values are visually distinct.
- Operational states such as success/failure do not reuse market gain/loss
  colors in a confusing way.
- Color is paired with sign, arrow, or text so the signal does not rely only on
  color.
- Browser smoke or tests cover at least dashboard, predictions, and fund
  screening.
- `CODE_INDEX.md` is updated if reusable formatting helpers or CSS conventions
  are added.
