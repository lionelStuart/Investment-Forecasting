# TASK-032: Asset-Level Prediction Cards

## Status

pending

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
