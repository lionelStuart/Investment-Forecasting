# TASK-071: News Evidence Persistence And Ingestion

## Status

completed

## Purpose

Create the minimal provider-neutral news evidence store so financial news
flashes can be retrieved later by source and time window. This task is the data
foundation only; it must not push news directly into AI prompts.

## Scope

- Add provider-neutral persistence for news items.
- Add optional Tushare `news` provider adapter support when credentials and
  permission are available.
- Add fake-provider fixtures for tests so default test runs do not require
  Tushare permission.
- Deduplicate news by source, published datetime, title/content hash, and
  provider ID when available.
- Add CLI ingestion for bounded source/date windows.
- Write task logs for success, provider failure, permission/config absence,
  counts, and skipped duplicates.

## Non-Scope

- No prompt injection of news.
- No AI-generated investment advice from news.
- No embeddings/vector database.
- No broad web crawling.
- No requirement that Tushare credentials exist for default workflows.

## Files Likely To Change

- `src/investment_forecasting/db.py`
- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/providers/tushare_provider.py`
- `src/investment_forecasting/data/news.py`
- `src/investment_forecasting/cli.py`
- `tests/test_news_evidence.py`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`

## Implementation Checklist

- Add `news_items` with provider/source, published datetime, title, content
  excerpt/body, channels, raw payload, content hash, and ingestion timestamp.
- Add idempotent upsert/query helpers.
- Add `ingest news` CLI with `--source`, `--start-datetime`,
  `--end-datetime`, and max-window guardrails.
- Normalize Tushare `datetime`, `title`, `content`, and `channels` fields.
- Keep provider-specific raw fields out of quant, WebUI, MCP, and AI modules.

## Acceptance Criteria

- A fake provider can ingest repeat news rows without duplicates.
- Optional Tushare ingestion is explicit and skipped/fails gracefully when not
  configured or not permitted.
- Task logs include source, time window, fetched count, inserted count,
  duplicate count, and error message when applicable.
- No expert/Jarvis prompt receives news content in this task.

## Test Plan

- `python3 -m pytest tests/test_news_evidence.py tests/test_db.py -q`

## Depends On

- `TASK-061`

## Result

- Added provider-neutral `news_items` persistence with source/time/hash indexes
  and idempotent `upsert_news_item` deduplication.
- Added `investment_forecasting.data.news` for bounded-window news ingestion,
  normalization, task logging, duplicate counts, and fake-provider-friendly
  tests.
- Added explicit `investment-forecasting ingest news` CLI using optional
  Tushare credentials. Missing credentials fail gracefully and do not affect
  default workflows.
- Added Tushare `news` adapter support without wiring news content into
  expert, Jarvis, advice, WebUI, or MCP prompts.

## Verification

- `python3 -m pytest tests/test_news_evidence.py tests/test_db.py tests/test_tushare_provider.py -q`
