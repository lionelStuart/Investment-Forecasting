# TASK-073: News Evidence Search Service And MCP Tool

## Status

completed

## Purpose

Expose news as a bounded searchable evidence interface for Codex AI and
Jarvis. AI should retrieve relevant news on demand through a structured tool,
not receive raw news by default in prompts.

## Scope

- Add a service function for `search_news_evidence`.
- Add an MCP tool with filters for source, datetime range, asset code/ID,
  theme, event type, sentiment, keyword, max results, deduplication mode, and
  sort mode.
- Return stable evidence IDs, source, datetime, title, short excerpt, channels,
  linked assets/themes, tags, sentiment, intensity, match reasons, and raw
  audit references.
- Add a WebUI evidence-page section or technical entry only if it fits under
  the existing `证据` primary entry.
- Update AI prompt/schema docs so they instruct the AI to call the tool when
  news context is needed.

## Non-Scope

- No direct buy/sell advice from news.
- No unbounded news dump.
- No new first-level navigation entry.
- No automatic injection of all retrieved news into every expert/Jarvis prompt.
- No real provider-backed AI orchestration changes; resume `TASK-062` after
  this task is accepted.

## Files Likely To Change

- `src/investment_forecasting/data/news.py`
- `src/investment_forecasting/mcp/tools.py`
- `src/investment_forecasting/mcp/server.py`
- `src/investment_forecasting/web/app.py`
- `tests/test_news_evidence.py`
- `tests/test_mcp_tools.py`
- `tests/test_mcp_server.py`
- `tests/test_web_app.py`
- `repo/specs/SPEC-009-jarvis-ai-investment-assistant.md`
- `repo/CODE_INDEX.md`

## Implementation Checklist

- Implement bounded search with defaults such as `max_results <= 50` and
  excerpt length caps.
- Require at least one meaningful filter or a narrow recent window to avoid
  broad dumps.
- Add structured errors for missing news data, invalid date ranges, and unknown
  asset/theme filters.
- Ensure MCP output is deterministic and JSON-compatible.
- Document that prompts use this tool contract instead of bulk news context.

## Acceptance Criteria

- Codex AI can search news by source, date window, asset, theme, event type,
  sentiment, and keyword.
- Results include evidence IDs and match reasons suitable for Jarvis citations.
- Tool output is bounded and excludes raw provider dumps by default.
- WebUI evidence entry, if added, stays under `证据` and does not add a new
  primary navigation item.
- `TASK-062` prompt/schema planning can reference the tool contract.

## Test Plan

- `python3 -m pytest tests/test_news_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_web_app.py -q`

## Depends On

- `TASK-071`
- `TASK-072`

## Result

- Added `search_news_evidence` service with source, datetime, asset ID/code,
  theme, event type, sentiment, keyword, max-results, dedupe, and sort filters.
- Search requires a meaningful filter or a narrow recent window and caps output
  at 50 results.
- Results include stable evidence IDs, source/published timestamp, title,
  bounded excerpt, channels, linked assets/themes, event/sentiment tags,
  intensity, match reasons, and audit references without returning raw provider
  payloads.
- Added `search_news_evidence` to local MCP tool registry and stdio server.
- No WebUI primary navigation was added; future WebUI exposure should live
  under `证据`.

## Verification

- `python3 -m pytest tests/test_news_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_web_app.py -q`
