# TASK-078: Jarvis Model Risk Officer Gates

## Status

completed

## Purpose

Make Jarvis actively reject or downgrade tempting but unreliable model signals
before they appear in the daily brief, WebUI, MCP output, or phone summary.

## Scope

- Add gates for:
  - degraded model status;
  - stale validation;
  - low/negative Rank IC;
  - insufficient sample count;
  - weak bucket spread;
  - asset-type or same-category underperformance;
  - model family disagreement;
  - low confidence or outlier expected return.
- Convert gated signals into watch-only language.
- Explain excluded horizons and degraded model families in 今日简报, `/jarvis`,
  MCP, and phone summary where applicable.

## Non-Scope

- No new model family.
- No direct portfolio action.
- No hiding raw values from 证据; only user-facing synthesis is gated.

## Files Likely To Change

- `src/investment_forecasting/jarvis/synthesis.py`
- `src/investment_forecasting/communication/templates.py`
- `src/investment_forecasting/mcp/tools.py`
- `src/investment_forecasting/web/app.py`
- `tests/test_jarvis.py`
- `tests/test_communication.py`
- `tests/test_mcp_tools.py`
- `tests/test_web_app.py`

## Implementation Checklist

- Extend existing confidence gates rather than creating a parallel gate system.
- Add gate reason codes and user-facing Chinese explanations.
- Add tests for high expected return plus negative Rank IC, weak bucket spread,
  and insufficient same-category samples.

## Acceptance Criteria

- Jarvis can answer why it should not trust a tempting signal.
- Gated model evidence remains visible in 证据 but is downgraded in daily brief
  and phone summary.
- MCP output includes gate reasons for agents.

## Test Plan

- `python3 -m pytest tests/test_jarvis.py tests/test_communication.py tests/test_mcp_tools.py tests/test_web_app.py -q`

## Depends On

- `TASK-077`

## Completion Notes

- Extended Jarvis confidence gates into an explicit model-risk-officer layer
  while reusing the existing `confidence_gates` field.
- Added gate codes and Chinese explanations for degraded model status, stale
  validation, missing backtests, insufficient/unvalidated samples, weak or
  negative Rank IC, weak or negative bucket spread, insufficient same-category
  samples, model-family disagreement, low confidence, and outlier expected
  return.
- Jarvis now writes `model_risk_summary`, `excluded_horizons`, and
  `degraded_model_families` into `model_summary`.
- Phone summaries include the first model-risk gate reason so mobile output
  also explains why tempting model signals are watch-only.
- MCP `get_jarvis_daily_brief` and `generate_jarvis_daily_brief` now return
  explicit `model_risk_gates` and `model_risk_summary` wrappers for agents.
- `/jarvis` keeps gated raw model evidence visible while adding validation,
  Rank IC, bucket spread, and risk-gate columns to the model panel.

## Verification

- `python3 -m pytest tests/test_jarvis.py tests/test_communication.py tests/test_mcp_tools.py tests/test_web_app.py -q`
- `python3 -m py_compile src/investment_forecasting/jarvis/synthesis.py src/investment_forecasting/communication/templates.py src/investment_forecasting/mcp/tools.py src/investment_forecasting/web/app.py`
- Local SQLite smoke:
  `investment-forecasting jarvis generate --db data/investment_forecasting.sqlite3 --date 20260524`
  produced `model_risk_summary.status=watch_only`, excluded horizons, and
  degraded model-family explanations.
