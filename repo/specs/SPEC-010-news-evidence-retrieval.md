# SPEC-010: News Evidence Retrieval

## Status

draft

## Goal

Add a minimal news evidence layer that ingests financial news flashes, indexes
them by source, time window, asset, theme, event type, and directional
sentiment, then exposes searchable evidence tools for Codex AI and Jarvis.

News is a retrievable evidence source. It must not be directly injected into
fixed prompts or used as a standalone trading signal.

## Provider Context

Tushare `news` can provide financial news flashes with required `src`,
`start_date`, and `end_date` parameters, and output fields such as `datetime`,
`title`, `content`, and optional `channels`. Sources include Sina Finance,
Wallstreetcn, 10jqka, Eastmoney, CLS, Yicai, and others. The interface is
permission-gated and should be optional, not required for default workflows.

Reference: Tushare news interface documentation
`https://tushare.pro/document/2?doc_id=143`.

## Product Role

News improves the system in two ways:

- Retrieval: Codex AI and Jarvis can ask for relevant recent news when
  analyzing an asset, theme, date range, model disagreement, or risk event.
- Features: models and confidence gates can consume aggregate, leakage-safe
  news features such as event counts, sentiment balance, freshness, and source
  diversity.

News must remain traceable evidence. It should support explanations like
"模型看多，但近期监管负面新闻较多，因此降级为观察" without implying that news
alone proves future returns.

## Data Model Requirements

MVP persistence should support:

- `news_items`
  - provider/source, provider news ID or content hash;
  - published datetime;
  - title, content excerpt, channels;
  - raw payload for audit;
  - ingestion timestamp and source URL if available.
- `news_item_links`
  - news item ID;
  - linked asset ID when deterministic matching is possible;
  - linked theme label;
  - link type: asset_code, asset_name, theme_keyword, channel, manual/future;
  - confidence score and match reason.
- `news_item_tags`
  - event type such as policy, earnings, regulation, macro, liquidity,
    industry_trend, risk_event, company_event, unknown;
  - directional sentiment: positive, negative, neutral, mixed, unknown;
  - intensity and freshness score;
  - deterministic reason.
- Optional `news_feature_daily`
  - date, asset/theme scope, source window;
  - news count, source count, positive/negative/neutral counts;
  - risk-event count, policy count, freshness-weighted sentiment;
  - linked evidence IDs.

## Retrieval Requirements

The primary product capability is search, not prompt injection.

Search must support filters:

- source list;
- start/end datetime;
- asset code or asset ID;
- theme label;
- event type;
- sentiment/direction;
- keyword;
- max results;
- deduplication mode;
- sort by recency, relevance, or intensity.

Search responses must include stable IDs, source, datetime, title, short
content excerpt, channels, linked assets/themes, event tags, sentiment,
intensity, match reasons, and raw-evidence references.

## MCP / Codex AI Requirements

- Expose a structured tool such as `search_news_evidence`.
- The AI must call the tool when it needs news context. Prompts should describe
  when and how to call the tool; they should not receive all recent news by
  default.
- Tool results must be bounded by max result count and excerpt length.
- Tool output must never produce direct buy/sell advice.
- Tool output must include enough metadata for Jarvis to cite evidence IDs and
  explain why the news was relevant.

## Quant Feature Requirements

News features can influence confidence and model evaluation only after they are
constructed with time-safe windows.

- Feature windows must use news published at or before the prediction timestamp.
- Backtests must prevent future leakage.
- MVP features should be aggregate and deterministic; no complex NLP model is
  required.
- News features should be tested separately before being used to adjust Jarvis
  confidence.

## Non-Goals

- No direct prompt stuffing of all news content.
- No direct investment advice generated from news alone.
- No complex embeddings/vector database in the MVP.
- No paid Tushare dependency for default tests or daily workflow.
- No broad web crawling outside provider adapters.
- No guarantee that positive news predicts positive returns.

## Acceptance Criteria

- News can be ingested from a fake provider and, when configured, optional
  Tushare `news`.
- News records are deduplicated and indexed by source/time.
- Deterministic asset/theme linking and positive/negative/neutral tagging work
  on fixtures.
- `search_news_evidence` can filter by time window, source, asset, theme,
  sentiment, event type, and keyword.
- MCP tests verify bounded structured output and evidence IDs.
- Jarvis/AI prompt docs state that news must be retrieved through the tool,
  not injected into every prompt.
- Tests cover future-leakage prevention for any daily news features.

## Related Tasks

- `TASK-071`: News evidence persistence and ingestion.
- `TASK-072`: News indexing, linking, and feature extraction.
- `TASK-073`: News evidence retrieval service and MCP tool.
