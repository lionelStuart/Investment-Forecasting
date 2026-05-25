# TASK-025: Provider Expansion With Tushare

## Status

completed

## Source

Updated `ROADMAP.md` backlog theme: Tushare Pro enhancement provider.

## Goal

Add a Tushare provider path for users with credentials while keeping AKShare as
the free default provider.

## Acceptance

- Tushare credentials are optional and never required for MVP commands.
- Provider selection is explicit and logged.
- Schema remains provider-neutral.

## Implementation Notes

- Added optional `investment_forecasting.providers.tushare_provider.TushareProvider`.
- Tushare usage requires an explicit token via `--tushare-token`,
  `TUSHARE_TOKEN`, or `TS_TOKEN`; default AKShare commands do not require
  Tushare credentials or the optional package.
- Added optional Python extra `.[tushare]` for users who want to install the
  Tushare SDK.
- CLI `ingest mvp` and `ingest full` now expose `--provider akshare|tushare`;
  AKShare remains the default free provider.
- Tushare history normalization supports index, stock/ETF via `pro_bar`, and
  public fund NAV rows via `fund_nav`, all written into the existing provider
  neutral `assets` and `price_daily` schema.
- Ingestion records `source='tushare'` for assets/prices and task logs include
  `provider=TushareProvider`, making provider selection auditable.

## Verification

- `python3 -m pytest tests/test_tushare_provider.py tests/test_akshare_ingestion.py`
