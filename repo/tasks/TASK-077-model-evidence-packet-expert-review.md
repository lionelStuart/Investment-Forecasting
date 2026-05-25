# TASK-077: Model Evidence Packet And Expert Review

## Status

completed

## Purpose

Standardize the model evidence packet consumed by experts and Jarvis so expert
opinions review model reliability instead of bypassing model health checks.

## Scope

- Define a shared model evidence packet:
  - model version;
  - horizon days;
  - expected return;
  - up probability;
  - rank score;
  - risk-adjusted score;
  - validation status;
  - recent Rank IC;
  - bucket spread;
  - degraded reason;
  - evidence IDs.
- Update expert AI/planning evidence packets to consume this shape.
- Add style-specific weighting guidance for trend, defensive, balanced, and
  macro experts.
- Ensure degraded signals are watch-only context for expert plans.

## Non-Scope

- No new experts.
- No expert voting logic.
- No bypass of Jarvis/model gates.
- No UI expansion beyond existing 专家团/证据 surfaces.

## Files Likely To Change

- `src/investment_forecasting/ai_analysis.py`
- `src/investment_forecasting/experts/planning.py`
- `src/investment_forecasting/jarvis/synthesis.py`
- `tests/test_experts.py`
- `tests/test_jarvis.py`
- `tests/test_ai_providers.py`

## Implementation Checklist

- Add a model evidence packet builder shared by experts and Jarvis.
- Update expert plan rationale to state validation status and degraded reasons.
- Add tests where an expert sees a high-return but degraded signal and only
  uses it as observation context.

## Acceptance Criteria

- Expert evidence packets contain model reliability fields.
- Expert plans cannot turn degraded model evidence into strong buy/rebalance
  language.
- Jarvis can cite the same packet fields for disagreement and risk explanation.

## Test Plan

- `python3 -m pytest tests/test_experts.py tests/test_jarvis.py tests/test_ai_providers.py -q`

## Depends On

- `TASK-076`

## Completion Notes

- Added shared `model_evidence_packet_v1` construction in
  `ai_analysis.py`, covering model version, horizon, expected return,
  up probability, rank score, same-category rank, risk-adjusted score,
  validation status, recent Rank IC, bucket spread, degraded reason, and
  traceable evidence IDs.
- Expert AI evidence packets now include the shared model packet and
  style-specific guidance for trend, defensive, balanced, and macro experts.
- Expert planning now reads `model_prediction_reliability`, stores the shared
  packet in `expert_plans.evidence_json`, and treats degraded, negative-Rank-IC,
  or negative-bucket-spread signals as watch-only context.
- Jarvis top forecasts now use the same packet shape and cite reliability
  fields in confidence gates so degraded model evidence can explain
  watch-only conclusions.
- No new experts, voting logic, routes, or model promotion behavior were
  introduced.

## Verification

- `python3 -m pytest tests/test_experts.py tests/test_jarvis.py tests/test_ai_providers.py -q`
- `python3 -m py_compile src/investment_forecasting/ai_analysis.py src/investment_forecasting/experts/planning.py src/investment_forecasting/jarvis/synthesis.py`
- Local SQLite smoke:
  `investment-forecasting experts run-plans --db data/investment_forecasting.sqlite3 --date 20260524`
  and
  `investment-forecasting jarvis generate --db data/investment_forecasting.sqlite3 --date 20260524`.
