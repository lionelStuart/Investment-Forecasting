# TASK-013: Fund Info Ingestion

## Status

completed

## Source

`README.md`, `SPEC-001`, `TASK-010`

## Goal

Populate `fund_info` and fund-oriented ranking fields so the fund page and MCP
fund metrics reflect fund type, manager, fee/scale where available, and
stage-return context.

## Required Context

- `fund_info` schema in `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/providers/akshare_provider.py`
- `src/investment_forecasting/web/app.py`

## Modify Scope

- AKShare fund info adapter.
- Persistence methods for `fund_info`.
- Fund page/MCP output fields.
- Tests and fixtures.

## Forbidden

- Do not scrape raw webpages directly if AKShare adapter output is sufficient.
- Do not expose provider-specific raw columns to upper layers.

## Acceptance

- Fund info ingestion populates `fund_info` for tracked public funds.
- WebUI fund page and `get_fund_metrics` include available fund metadata.
- Empty or changed provider fields produce clear errors or nullable fields with
  logs.

## Test Plan

- Unit tests with fixture fund info rows.
- Smoke ingestion for at least one tracked fund.
- WebUI render test confirms metadata appears.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added AKShare fund info normalization from `fund_individual_basic_info_xq`.
- Added stage-return and fee proxy enrichment from `fund_open_fund_rank_em`.
- Expanded `fund_info` schema with fund company, custodian, purchase fee,
  benchmark, strategy, objective, and `stage_returns_json`.
- Added idempotent `upsert_fund_info` persistence.
- Integrated fund info ingestion into the MVP ingestion workflow for tracked
  public funds.
- Updated `get_fund_metrics` to include `fund_info`.
- Updated WebUI fund page to show fund type, manager, scale, and fee proxy.
- Added fixture tests for fund info normalization and persistence.
- Validation passed with `python3 -m pytest`.
- Live smoke command populated `fund_info` for 华夏成长混合 (`000001`) and
  易方达消费行业股票 (`110022`).
