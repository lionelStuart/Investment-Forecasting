# TASK-062: AI Prompt And Evidence Schema Freeze

## Status

completed

## Purpose

Make real AI calls practical and reviewable by freezing the bounded evidence
packets, prompts, and structured output schemas for expert independent analysis
and Jarvis daily financial analysis.

## Scope

- Define expert-analysis input packets from stored expert, portfolio, model,
  market, scorecard, and task-health evidence.
- Define Jarvis-analysis input packets from stored market, macro, capital-flow,
  model, backtest, expert-analysis, expert-plan, expert-score, virtual-return,
  advice, and user-preference evidence.
- Define the news retrieval policy for prompts: when news context is needed,
  call `search_news_evidence` with explicit filters and cite returned evidence
  IDs. Do not embed bulk news content in the base prompt or evidence packet.
- Define structured output schemas for expert analysis and Jarvis synthesis.
- Add prompt instructions that force separation between facts, forecasts,
  expert opinion, expert performance, Jarvis synthesis, watch triggers, and
  risk boundaries.
- Add schema validation tests and example fixtures.

## Non-Scope

- No live provider calls.
- No new analysis fields unless they can be persisted or derived from existing
  evidence.
- No raw SQL dumps, provider raw payload dumps, or hidden prompt-only state.
- No direct news dump in the prompt. News context must be retrieved through the
  news evidence tool contract from `TASK-073`.
- No new product surface beyond tests and documentation.

## Files Likely To Change

- `src/investment_forecasting/ai_analysis.py`
- `src/investment_forecasting/ai_providers/`
- `src/investment_forecasting/experts/planning.py`
- `src/investment_forecasting/jarvis/synthesis.py`
- `tests/test_ai_providers.py`
- `tests/test_experts.py`
- `tests/test_jarvis.py`
- `repo/specs/SPEC-009-jarvis-ai-investment-assistant.md`

## Implementation Checklist

- Name and version the expert and Jarvis prompt/schema contracts.
- Add small fixture packets for one expert and one Jarvis brief.
- Validate that every model-facing claim has a source evidence reference.
- Validate that any news-based claim references returned news evidence IDs.
- Validate that returned JSON rejects unsupported IDs, unsupported certainty
  language, missing risk warnings, and opaque buy/sell instructions.

## Acceptance Criteria

- Expert and Jarvis provider requests can be built from existing stored
  evidence without querying extra data inside the provider layer.
- The structured output shape is stable, versioned, and tested.
- Invalid output is rejected before persistence or display.
- The schema can represent deterministic fallback and real provider output
  without changing downstream Jarvis or expert consumers.
- Prompt/schema docs tell AI how to retrieve news via `search_news_evidence`
  rather than receiving news by default.

## Test Plan

- `python3 -m pytest tests/test_ai_providers.py tests/test_experts.py tests/test_jarvis.py -q`

## Depends On

- `TASK-061`
- `TASK-073`

## Completion Notes

- Added versioned expert/Jarvis schema constants and prompt contracts in
  `investment_forecasting.ai_analysis`.
- Provider requests now carry bounded evidence packets, prompt text, output
  schemas, and metadata; prompts require explicit `search_news_evidence`
  retrieval and evidence IDs for any news-based claim.
- Validation rejects unsupported prediction IDs, unsupported news evidence IDs,
  unsafe certainty language, and Jarvis records without traceable evidence.
- Verified with `python3 -m pytest tests/test_ai_providers.py tests/test_experts.py tests/test_jarvis.py -q`.
