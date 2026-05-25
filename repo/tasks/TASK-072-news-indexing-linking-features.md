# TASK-072: News Indexing, Linking, And Features

## Status

completed

## Purpose

Make news retrievable and model-safe by adding deterministic indexes for
source, time, asset/theme association, event type, sentiment, and aggregate
time-window features.

## Scope

- Link news to stored assets by code/name keyword matches and to deterministic
  theme labels by keyword/channel matches.
- Add event tags such as policy, earnings, regulation, macro, liquidity,
  industry_trend, risk_event, company_event, and unknown.
- Add directional sentiment tags: positive, negative, neutral, mixed, unknown.
- Add match reasons and confidence scores for every asset/theme link and tag.
- Add optional daily aggregate news features by asset/theme scope using only
  news available at or before the feature timestamp.

## Non-Scope

- No complex NLP model or LLM tagging in the MVP.
- No embeddings/vector search.
- No claim that sentiment predicts returns.
- No use of future news in features or backtests.

## Files Likely To Change

- `src/investment_forecasting/data/news.py`
- `src/investment_forecasting/data/classification.py`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/migrations/001_init.sql`
- `tests/test_news_evidence.py`
- `tests/test_db.py`

## Implementation Checklist

- Add `news_item_links` for asset/theme links with link type, confidence, and
  reason.
- Add `news_item_tags` for event type, sentiment, intensity, freshness, and
  reason.
- Add deterministic keyword dictionaries in code or a small config constant.
- Add `news_feature_daily` only if needed for aggregate model/Jarvis confidence
  inputs; otherwise expose aggregate query helpers first.
- Add leakage tests: feature windows must exclude news after the target time.

## Acceptance Criteria

- Fixtures link news to assets/themes deterministically with auditable reasons.
- Positive/negative/neutral/risk tags are deterministic and test-covered.
- Aggregate features can be queried by asset/theme and date window.
- Future news is excluded from feature windows and tests prove it.

## Test Plan

- `python3 -m pytest tests/test_news_evidence.py tests/test_db.py -q`

## Depends On

- `TASK-071`

## Result

- Added `news_item_links`, `news_item_tags`, and `news_feature_daily` schema
  areas with indexes for asset/theme/tag/feature lookup.
- Added deterministic news indexing in `investment_forecasting.data.news`:
  asset code/name links, theme keyword/channel links, event-type tags,
  directional sentiment tags, confidence, intensity, and auditable reasons.
- `ingest_news` now indexes each persisted/updated news row immediately.
- Added `build_news_feature` for asset/theme aggregate windows with evidence
  IDs, source counts, sentiment/event counts, and freshness-weighted sentiment.
- Leakage protection is explicit: aggregate windows only include
  `published_at <= window_end`.

## Verification

- `python3 -m pytest tests/test_news_evidence.py tests/test_db.py -q`
