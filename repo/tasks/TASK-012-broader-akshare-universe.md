# TASK-012: Broader AKShare Universe

## Status

completed

## Source

`README.md`, `SPEC-001`, `TASK-010`

## Goal

Expand the MVP tracked universe beyond the thin sample to representative
indices, ETFs, public funds, and at least one individual A-share while keeping
ingestion reliable and idempotent.

## Required Context

- `src/investment_forecasting/data/ingestion.py`
- `src/investment_forecasting/providers/akshare_provider.py`
- `repo/audits/README-MVP-COMPLETION-2026-05-23.md`

## Modify Scope

- Tracked universe configuration.
- AKShare provider methods for individual A-share histories.
- Ingestion tests and smoke commands.
- Data quality checks needed for the expanded universe.

## Forbidden

- Do not ingest a huge universe before representative small-batch reliability
  is proven.
- Do not let upper layers depend on AKShare raw field names.
- Do not require paid credentials.

## Acceptance

- Representative universe includes at least: 沪深300, 中证500, 创业板指,
  上证指数, one broad ETF, one industry ETF, one bond or money ETF, two public
  funds, and one individual A-share.
- Live or recorded smoke verifies successful idempotent ingestion for the
  expanded universe.
- Failures continue to write actionable `task_logs`.

## Test Plan

- Run provider normalization tests.
- Run a small live ingestion with the expanded universe.
- Verify row counts and uniqueness constraints.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Expanded `MVP_UNIVERSE` to 10 representative assets:
  - Indices: 沪深300 (`000300`), 中证500 (`000905`), 创业板指 (`399006`),
    上证指数 (`000001`).
  - ETFs: 沪深300ETF (`510300`), 半导体ETF (`512480`), 国债ETF (`511010`).
  - Public funds: 华夏成长混合 (`000001`), 易方达消费行业股票 (`110022`).
  - Individual A-share: 贵州茅台 (`600519`).
- Added individual A-share history support through AKShare.
- Fixed asset uniqueness to include `asset_type` so index `000001` and fund
  `000001` can coexist.
- Updated ingestion summary keys to `asset_type:code` to preserve auditability.
- Added stock fallback from Eastmoney history to AKShare daily history when
  provider access fails.
- Added tests for representative universe coverage, stock normalization, and
  stock fallback.
- Validation passed with `python3 -m pytest`.
- Live smoke command
  `investment-forecasting ingest mvp --db /tmp/investment_forecasting_task012_expanded_fallback.sqlite3 --start-date 20240520 --end-date 20240522`
  wrote 30 rows across 10 assets.
