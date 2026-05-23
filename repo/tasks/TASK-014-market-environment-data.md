# TASK-014: Market Environment Data

## Status

completed

## Source

`README.md`, `SPEC-001`, `TASK-010`

## Goal

Add market environment inputs such as breadth, liquidity/turnover heat,
style/sector rotation signals, stock-bond comparison proxies, macro indicators,
and sentiment snapshots where free data is available.

## Required Context

- `README.md` market environment requirements.
- Existing `features_daily`, `daily_advice`, and WebUI dashboard.

## Modify Scope

- New schema or JSON fields for market snapshots.
- Provider adapters for free market environment inputs.
- Feature/advice integration.
- MCP/WebUI snapshot output.

## Forbidden

- Do not require paid-only data sources for MVP.
- Do not present environment signals as deterministic predictions.

## Acceptance

- A stored market snapshot includes at least index trend, breadth proxy,
  turnover/liquidity heat, and one macro or stock-bond comparison proxy.
- `get_market_snapshot`, daily advice, and dashboard surface these fields.
- Failures are logged and do not silently erase prior snapshots.

## Test Plan

- Unit tests for snapshot normalization.
- Smoke command for snapshot ingestion.
- WebUI/MCP tests for snapshot output.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added `market_snapshots` persistence.
- Added `investment-forecasting market snapshot --db ... --date ...`.
- Snapshot fields include index trend, breadth, liquidity heat, stock-bond
  proxy, sentiment, and details JSON.
- Integrated market snapshot calculation into the daily workflow after feature
  calculation.
- Updated `get_market_snapshot` MCP output to include `market_environment`.
- Updated daily advice generation to reference the latest market snapshot and
  include `market_snapshot_id` in evidence.
- Updated WebUI dashboard to surface market environment fields.
- Added tests for snapshot calculation, idempotent persistence, and
  missing-feature failure.
- Validation passed with `python3 -m pytest`.
- Smoke validation on a 2024-04-01 through 2024-05-22 expanded-universe sample
  ingested 330 price rows, calculated 320 feature rows, produced a `risk_on`
  market snapshot with all core fields populated, and generated daily advice
  linked to the snapshot.
