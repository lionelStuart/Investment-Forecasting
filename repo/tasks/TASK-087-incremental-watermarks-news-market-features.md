# TASK-087: Incremental Watermarks For News, Market Data, And Features

## Status

completed

## Purpose

Make hourly updates incremental. News, price/NAV data, capital flow, and
features must update missing windows from persisted watermarks instead of
fetching broad full-history ranges.

## Scope

- Add watermark helpers for provider/source/scope keys.
- Integrate news ingestion with source-specific `published_at` or window-end
  watermarks.
- Integrate price/NAV ingestion with per-asset latest stored trade date.
- Integrate capital-flow ingestion with per-scope/subject latest flow date.
- Recompute features only for affected asset/date windows.
- Add dry-run summaries showing what would be fetched and skipped.

## Non-Scope

- No new provider.
- No full ingestion scheduler.
- No model changes.

## Files Likely To Change

- `src/investment_forecasting/scheduler/`
- `src/investment_forecasting/data/ingestion.py`
- `src/investment_forecasting/data/news.py`
- `src/investment_forecasting/data/capital_flow.py`
- `src/investment_forecasting/quant/features.py`
- `tests/test_scheduler.py`
- `tests/test_news_evidence.py`
- `tests/test_akshare_ingestion.py`

## Acceptance Criteria

- Hourly news update requests only the bounded missing source window.
- Market data update skips assets already current.
- Feature update only recalculates affected date ranges.
- Tests prove scheduled hourly jobs do not call full-history ingestion by
  default.

## Test Plan

- `python3 -m pytest tests/test_scheduler.py tests/test_news_evidence.py tests/test_akshare_ingestion.py -q`

## Depends On

- `TASK-086`

## Implementation Notes

- Added scheduler job handlers for news, market context, price/NAV, and
  features.
- News jobs compute source-specific bounded windows from
  `scheduler_watermarks` and never default to a full-history window.
- Market context jobs plan bounded capital-flow subjects under the job request
  cap.
- Price/NAV jobs compare each tracked asset's latest stored trade date against
  the target market date and skip assets already current.
- Feature jobs identify only assets whose latest price date is ahead of their
  latest feature date and record affected ranges.
- Scheduler metadata records dry-run/planned provider work with
  `real_provider_calls=false`; provider calls remain centrally gated by the
  scheduler policy.
