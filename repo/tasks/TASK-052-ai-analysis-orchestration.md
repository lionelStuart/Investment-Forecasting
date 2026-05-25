# TASK-052: AI Analysis Orchestration For Experts And Jarvis

## Status

completed

## Purpose

Make AI interaction an explicit product capability. Each expert should produce
an independent AI analysis from an expert-specific evidence packet, and Jarvis
should produce the daily financial analysis after reviewing market data, model
forecasts, expert analyses, expert plans, expert scores, and expert returns.

## Scope

- Define structured evidence packets for expert AI analysis.
- Persist expert AI analysis records before expert plans are finalized.
- Add validation gates so AI analysis cannot invent unsupported evidence or
  bypass risk/compliance checks.
- Define the Jarvis daily AI analysis packet and output schema.
- Ensure Jarvis separates system facts, model predictions, each expert's
  independent view, expert performance, and Jarvis's final synthesis.
- Add task logs for expert AI analysis and Jarvis AI analysis runs.

## Non-Scope

- No live trading.
- No hidden LLM-only memory.
- No phone-originated execution commands.
- No replacement for deterministic portfolio accounting or scoring.

## Files Likely To Change

- `src/investment_forecasting/experts/`
- `src/investment_forecasting/jarvis/`
- `src/investment_forecasting/workflows/daily.py`
- `src/investment_forecasting/mcp/tools.py`
- `tests/test_experts.py`
- `tests/test_jarvis.py`

## Acceptance Criteria

- Each active expert can persist one independent AI analysis per date.
- Expert plans reference the expert AI analysis used to produce them.
- Jarvis daily brief references expert AI analyses, expert plans, model
  forecasts, scorecards, and current virtual returns.
- Compliance and evidence-link checks run before AI text is exposed.
- Tests cover missing evidence, unsupported AI claims, expert disagreement, and
  Jarvis synthesis over multiple expert analyses.

## Depends On

- `TASK-038`
- `TASK-041`
- `TASK-047`
- `TASK-048`

## Implementation Notes

- Added `ai_analysis_records` as the shared persistence table for expert and
  Jarvis AI analysis records, with `analysis_type`, `analysis_key`,
  `analysis_date`, evidence packet JSON, output JSON, validation JSON, status,
  source, and idempotent date/key/version uniqueness.
- Added `expert_plans.ai_analysis_id` so every new or backfilled expert plan
  references the expert AI analysis used before plan finalization.
- Added `investment_forecasting.ai_analysis` for deterministic, evidence-backed
  AI analysis packets and validation. Expert analysis captures thesis, watched
  signals, selected/rejected candidates, risk objections, confidence, stance,
  proposed action, supported prediction IDs, and unsupported-claim checks.
- Expert daily planning now writes an `expert_ai_analysis` task log, persists
  one analysis per active expert/date, and then validates and persists plans.
- Jarvis synthesis now reads each expert's latest AI analysis, includes AI
  thesis/confidence/stance in expert summaries, writes a `jarvis_ai_analysis`
  task log, persists Jarvis AI analysis, and stores `jarvis_ai_analysis_id` in
  brief evidence.
- Jarvis AI analysis separates system facts, model interpretation, expert
  independent views, expert performance, disagreement, final synthesis, risk
  boundaries, and watch triggers.

## Verification

- `python3 -m pytest tests/test_db.py tests/test_experts.py tests/test_jarvis.py`
- `python3 -m pytest tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_daily_workflow.py tests/test_web_app.py`
