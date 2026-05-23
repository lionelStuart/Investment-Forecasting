# TASK-027: Data Expansion And Channel Hardening

## Status

completed

## Source

User goal: 当前的数据太少了，你需要捞更多的数据，完善数据渠道和数据。

## Goal

Increase the default database coverage and harden ingestion commands so broader
stock/ETF/fund data can be pulled without one failed asset or one asset type
blocking useful coverage.

## Required Context

- `README.md`
- `src/investment_forecasting/data/ingestion.py`
- `src/investment_forecasting/providers/akshare_provider.py`
- `src/investment_forecasting/cli.py`
- `scripts/restart_web.sh`

## Modify Scope

- AKShare discovery and ingestion controls.
- Default database contents.
- Derived feature/forecast/backtest/advice refresh.
- Tests and project memory write-back.

## Forbidden

- Do not require paid providers for the default path.
- Do not erase existing SQLite data while expanding coverage.
- Do not ignore failed provider calls silently; quality reports must show them.

## Acceptance

- Research universe can continue after individual provider failures.
- Full dynamic ingestion can cap assets per type for balanced samples.
- Default database contains materially more assets and price rows.
- Features, forecasts, backtests, market snapshot, macro observations, and daily
  advice are refreshed after ingestion.
- Tests pass and the WebUI service is restarted.

## Test Plan

- Run `python3 -m pytest`.
- Run research ingestion against the default database.
- Run full dynamic ingestion with per-type cap.
- Recompute features, market snapshot, forecasts, backtests, and advice.
- Verify row counts and quality reports.
- Restart the background WebUI service.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added `--continue-on-error` for `investment-forecasting ingest mvp`, useful
  with the `research` universe.
- Added `--max-assets-per-type` for `investment-forecasting ingest full` so
  dynamically discovered samples can stay balanced across stocks, ETFs, and
  funds.
- Expanded the default database from 10 to 63 assets:
  - 6 indices
  - 21 ETFs
  - 18 public funds
  - 18 A-shares
- Expanded `price_daily` to 24,837 rows and `macro_observations` to 1,869 rows.
- Recomputed 24,774 feature rows, 219 model predictions, 49,708 backtest
  results, market snapshots, and daily advice.
- Wrote 63 data-quality reports; all current reports are `ok`.
- Validation passed with `python3 -m pytest`.
