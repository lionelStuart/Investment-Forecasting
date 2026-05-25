# TASK-063: Provider-Backed AI Orchestration

## Status

completed

## Purpose

Wire the AI provider adapter into the existing expert and Jarvis orchestration
so real AI analysis can replace deterministic summaries without changing the
database contract or creating a parallel investment engine.

## Scope

- Let expert planning request provider-backed independent analysis before plan
  finalization.
- Let Jarvis synthesis request provider-backed daily financial analysis after
  expert analyses, plans, scorecards, virtual returns, model evidence, and
  market evidence are available.
- Persist provider-backed outputs in `ai_analysis_records`.
- Preserve deterministic fallback on failure or validation rejection.
- Expose provider/fallback status through MCP and task logs.

## Non-Scope

- No changes to expert roster size, expert scoring rules, portfolio accounting,
  forecast models, or advice allocation engines.
- No phone delivery changes except using the persisted Jarvis brief that prior
  templates already render.
- No WebUI redesign beyond surfacing provider/fallback status if needed.

## Files Likely To Change

- `src/investment_forecasting/experts/planning.py`
- `src/investment_forecasting/jarvis/synthesis.py`
- `src/investment_forecasting/ai_analysis.py`
- `src/investment_forecasting/ai_providers/`
- `src/investment_forecasting/mcp/tools.py`
- `src/investment_forecasting/workflows/daily.py`
- `tests/test_experts.py`
- `tests/test_jarvis.py`
- `tests/test_mcp_tools.py`
- `tests/test_daily_workflow.py`

## Implementation Checklist

- Add provider selection to expert and Jarvis generation paths through shared
  configuration, not route-specific flags.
- Store the generated analysis ID on expert plans and Jarvis brief evidence as
  today.
- Write task logs for provider success, fallback, and validation rejection.
- Keep daily workflow non-blocking when provider calls fail.

## Acceptance Criteria

- A fake provider can generate all active experts' analyses and one Jarvis
  analysis in tests.
- If one expert provider call fails, that expert receives deterministic
  fallback and the run continues.
- Jarvis brief evidence references the expert AI analysis IDs and Jarvis AI
  analysis ID regardless of provider or fallback source.
- MCP output includes enough status for an agent to explain provider-backed vs
  fallback analysis.

## Test Plan

- `python3 -m pytest tests/test_experts.py tests/test_jarvis.py tests/test_mcp_tools.py tests/test_daily_workflow.py -q`

## Depends On

- `TASK-061`
- `TASK-062`

## Completion Notes

- Expert daily planning and Jarvis synthesis now call the shared AI provider
  adapter through `AIProviderRequest` and persist provider success/fallback
  metadata on `ai_analysis_records`.
- Fake-provider success is testable for all active experts and the Jarvis
  analysis path; validation rejection or provider failure preserves
  deterministic fallback.
- Expert and Jarvis task logs include provider status summaries.
- MCP Jarvis retrieval/generation now returns `ai_analysis_status` with
  provider/fallback metadata.
- Verified with `python3 -m pytest tests/test_experts.py tests/test_jarvis.py tests/test_mcp_tools.py tests/test_daily_workflow.py -q`.
