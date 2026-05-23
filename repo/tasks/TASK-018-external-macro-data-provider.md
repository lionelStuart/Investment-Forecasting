# TASK-018: External Macro Data Provider

## Status

completed

## Source

`README.md`, `TASK-010`, `TASK-014`

## Goal

Add a real external macro data path for free macro series so market
environment evidence is not limited to local price-derived proxies.

## Required Context

- README FRED / macro data requirement.
- `src/investment_forecasting/quant/market.py`
- Existing SQLite persistence and market snapshot workflow.

## Modify Scope

- Macro observation persistence.
- Free provider adapter.
- CLI ingestion command.
- Market snapshot evidence details.
- Tests and README command documentation.

## Forbidden

- Do not require a paid macro data source for MVP.
- Do not make macro observations deterministic trading signals.
- Do not fail market snapshots when macro data is absent.

## Acceptance

- FRED or another free macro provider can ingest bounded date ranges.
- Macro observations are persisted idempotently in SQLite.
- Market snapshots include latest stored macro observations as evidence when
  available.
- Network failures produce actionable proxy guidance.

## Test Plan

- Unit test macro provider ingestion through a mocked FRED fetch.
- Unit test idempotent persistence.
- Unit test market snapshot details include latest stored macro values.
- Smoke a real FRED command, using the local proxy if direct access fails.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added `macro_observations` persistence.
- Added a lightweight FRED CSV provider for free macro series, using `certifi`
  for a portable TLS CA bundle.
- Added `investment-forecasting ingest macro --db ... --start-date ... --end-date ... --series ...`.
- Defaults cover `DGS10`, `T10YIE`, and `DTWEXBGS`.
- Market snapshots now include latest stored macro observations in
  `details_json` when available, without failing if macro data is absent.
- README local commands and schema notes now include macro ingestion.
- Validation passed with `python3 -m pytest`.
- Real FRED smoke passed with
  `investment-forecasting ingest macro --db /tmp/investment_forecasting_task018_macro.sqlite3 --start-date 20240520 --end-date 20240524 --series DGS10,T10YIE`,
  writing 10 macro observations.
