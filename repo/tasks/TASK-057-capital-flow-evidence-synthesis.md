# TASK-057: Capital Flow Evidence Synthesis

## Status

completed

## Purpose

Make the newly persisted capital-flow observations useful in the decision
support loop. Funds-flow data should not only sit on `/market`; daily advice
and Jarvis should carry the observation IDs, summarize whether inflow/outflow
evidence is available, and expose the evidence as a drill-down link.

## Scope

- Add capital-flow evidence to daily advice generation.
- Store `capital_flow_ids` in advice evidence JSON and include a structured
  `allocation_json.capital_flow` summary.
- Add capital-flow observations to Jarvis evidence collection, model summary,
  focus-direction logic, missing/stale evidence checks, and source evidence.
- Add capital-flow IDs/counts to persisted Jarvis AI-analysis evidence packets.
- Add WebUI evidence chips/links from `/advice` and `/jarvis` back to
  `/market`.
- Keep wording explicitly auxiliary: capital-flow observations are liquidity
  and crowding evidence, not standalone buy/sell signals.

## Non-Scope

- No real-money trading actions.
- No rule that capital flow alone changes allocation.
- No new provider endpoint beyond the existing `capital_flow_observations`
  table.
- No real LLM integration.

## Files Changed

- `src/investment_forecasting/advice/generator.py`
- `src/investment_forecasting/jarvis/synthesis.py`
- `src/investment_forecasting/ai_analysis.py`
- `src/investment_forecasting/web/app.py`
- `tests/test_advice.py`
- `tests/test_jarvis.py`
- `repo/INDEX.md`
- `repo/STATUS.md`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`
- `repo/specs/SPEC-003-advice-generation.md`
- `repo/specs/SPEC-009-jarvis-ai-investment-assistant.md`

## Acceptance Criteria

- Daily advice includes capital-flow IDs when observations exist.
- Daily advice summary language mentions available capital-flow coverage
  without treating it as a deterministic trading signal.
- Jarvis brief evidence includes `capital_flow_ids` when observations exist.
- Jarvis model summary includes a capital-flow summary and records missing or
  stale capital-flow evidence when applicable.
- Jarvis AI analysis packet carries capital-flow IDs/count.
- `/advice` and `/jarvis` expose links back to `/market` for capital-flow
  evidence.
- Tests cover advice and Jarvis synthesis with capital-flow evidence.

## Verification

- `python3 -m pytest tests/test_advice.py tests/test_jarvis.py tests/test_web_app.py tests/test_capital_flow.py`
- `scripts/restart_web.sh`
