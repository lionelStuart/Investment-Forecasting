# TASK-031: Red/Green Market Semantics

## Status

completed

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

## Implementation Notes

- Added shared WebUI market-value formatting helpers:
  `market_percent`, `plain_percent`, and table/stat-grid column/label
  detection in `src/investment_forecasting/web/app.py`.
- Positive return-like values now render red with an up arrow and `上涨`;
  negative values render green with a down arrow and `下跌`; neutral values
  render muted with a flat arrow and `持平`.
- Dashboard summary stats, recommendations, prediction tables, fund screening
  tables, category/data tables, Jarvis model/expert metrics, and expert return
  views reuse the shared formatter.
- Operational state styles such as task ok/warn/bad remain separate from
  market gain/loss colors.

## Verification

- `python3 -m pytest tests/test_web_app.py`
