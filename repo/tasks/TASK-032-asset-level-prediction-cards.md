# TASK-032: Asset-Level Prediction Cards

## Status

completed

## Source

`repo/audits/PRODUCT-EXPERIENCE-ACCEPTANCE.md` next phase target: asset-level
forecast experience.

## Goal

Redesign the prediction priority area so each asset appears once with
short/medium/long horizon signals, rather than repeating one card per
asset-horizon row.

## Acceptance

- Before implementation, inspect existing prediction queries, recommendation
  cards, percent formatting, and asset-link helpers. Reuse existing data access
  patterns.
- Prediction priority section groups forecasts by asset.
- Each asset card shows 5/20/60 day expected return, up probability, downside
  risk, and confidence when available.
- Cards include a horizon agreement label such as consistent positive,
  mixed/uncertain, improving, weakening, or high downside risk.
- Raw prediction table remains available as technical detail.
- Tests verify repeated horizons are grouped under one asset card.
- `ARCHITECTURE.md` and `CODE_INDEX.md` are updated if prediction view-model
  ownership or shared product-experience helpers are added.

## Implementation Notes

- Added an asset-level prediction card section to `/predictions` that groups
  repeated horizon rows by asset.
- Each asset card shows 5/20/60 day expected return, up probability, downside
  risk, and confidence when available.
- Added horizon agreement labels: consistent positive, consistent weak,
  improving, weakening, mixed observation, and high downside risk.
- Preserved raw model prediction rows under a secondary technical-detail
  disclosure.
- Reused existing asset links, market percent formatting, table helpers, and
  server-rendered WebUI patterns.

## Verification

- `python3 -m pytest tests/test_web_app.py`
