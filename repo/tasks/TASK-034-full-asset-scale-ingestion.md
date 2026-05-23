# TASK-034: Full Asset Scale Ingestion

## Status

completed

## Source

User request: "资产规模全量化".

## Goal

Move the default database from representative samples toward a broad, batchable
AKShare asset universe while keeping provider failures isolated per asset.

## Acceptance

- Full ingestion can be resumed in balanced batches by asset type.
- Full ingestion can skip assets already present in the local database.
- Fund detail failures do not abort an otherwise successful price/net-value
  batch.
- Feature calculation can continue past assets with invalid price histories.
- Default database materially increases asset and price coverage.
- Derived features, forecasts, backtests, advice, and WebUI service are refreshed.

## Result

- Discovered AKShare candidate universe size on 2026-05-23:
  - total: 23,952
  - stocks: 5,522
  - ETFs: 1,475
  - funds: 16,955
- Added `ingest full --offset-per-type` for resumable balanced batches.
- Added `ingest full --skip-existing-assets` to avoid re-fetching already
  registered assets.
- Added fund-info failure tolerance under `continue_on_error`.
- Added `features calculate --continue-on-error` to skip invalid single-asset
  histories without stopping the full run.
- Expanded the default SQLite database to 476 assets:
  - index: 6
  - stock: 155
  - ETF: 159
  - fund: 156
- Expanded `price_daily` to 153,175 rows and `features_daily` to 152,377 rows.
- Refreshed latest market snapshot, forecasts, backtests, and 2026-05-23 daily
  advice.

## Verification

- `python3 -m pytest` passed: 65 tests.
- `scripts/restart_web.sh` was run after completion.
