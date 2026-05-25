# TASK-064: Jarvis Confidence Gates And Expert Maturity Wording

## Status

completed

## Purpose

Prevent Jarvis from over-amplifying extreme model forecasts, stale evidence, or
immature expert performance when presenting a simple daily recommendation.

## Scope

- Add confidence gates for low-confidence, stale, degraded, or outlier model
  predictions before they become user-facing Jarvis focus directions.
- Add wording that labels extreme low-confidence forecasts as watch signals,
  not strong recommendations.
- Add expert-maturity wording when expert scorecards or virtual-return history
  have insufficient samples.
- Show confidence-gate and maturity status in `/jarvis`, MCP output, and phone
  summary source fields where relevant.

## Non-Scope

- No new forecast model.
- No covariance optimizer or rebalancing engine.
- No new expert lifecycle rules.
- No change to raw technical tables; raw forecasts can remain visible as
  evidence, but Jarvis synthesis must gate them.

## Files Likely To Change

- `src/investment_forecasting/jarvis/synthesis.py`
- `src/investment_forecasting/ai_analysis.py`
- `src/investment_forecasting/web/app.py`
- `src/investment_forecasting/communication/templates.py`
- `src/investment_forecasting/mcp/tools.py`
- `tests/test_jarvis.py`
- `tests/test_web_app.py`
- `tests/test_communication.py`
- `tests/test_mcp_tools.py`

## Implementation Checklist

- Define explicit thresholds for outlier expected return, low confidence,
  stale prediction/backtest evidence, and degraded model monitoring.
- Add structured `confidence_gates` or equivalent metadata to Jarvis evidence
  or output.
- Keep raw values traceable while changing the daily synthesis wording.
- Add tests with an extreme forecast and low confidence.

## Acceptance Criteria

- Jarvis does not present an extreme low-confidence forecast as a strong action
  direction.
- `/jarvis` clearly shows why a signal was gated or downgraded.
- Expert cards explain sample-poor score/return evidence when applicable.
- Existing safe-language validation still passes.

## Test Plan

- `python3 -m pytest tests/test_jarvis.py tests/test_web_app.py tests/test_communication.py tests/test_mcp_tools.py -q`

## Depends On

- `TASK-063`

## Completion Notes

- Jarvis synthesis now writes `confidence_gates` for stale model evidence,
  missing/degraded backtests, outlier expected returns, and low-confidence
  forecasts.
- Gated forecasts are downgraded to watch-only wording in focus directions and
  combined recommendations instead of strong daily action language.
- `/jarvis`, MCP output, and phone summary model text expose the gated/watch
  status; expert cards include sample-poor maturity wording.
- Verified with `python3 -m pytest tests/test_jarvis.py tests/test_web_app.py tests/test_communication.py tests/test_mcp_tools.py -q`.
