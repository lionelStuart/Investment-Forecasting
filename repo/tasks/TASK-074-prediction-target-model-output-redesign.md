# TASK-074: Prediction Target And Model Output Redesign

## Status

completed

## Purpose

Reframe model output from point-return prediction toward relative, measurable
model evidence. Keep `expected_return`, but stop treating it as the primary
product signal for Jarvis.

## Scope

- Extend model output/query helpers to support reliability fields:
  - rank score;
  - same-category rank;
  - risk-adjusted score;
  - validation status;
  - recent Rank IC;
  - bucket spread;
  - degraded reason;
  - evidence IDs.
- Define how these fields coexist with current `model_predictions` consumers.
- Add deterministic fallback values when a model does not yet provide the new
  fields.
- Update WebUI evidence labels only under `证据` or existing prediction cards;
  do not add new primary navigation.

## Non-Scope

- No new model family in this task.
- No LightGBM/XGBoost.
- No Jarvis promotion logic yet.
- No claim that ranking is reliable until `TASK-075` validation exists.

## Files Likely To Change

- `src/investment_forecasting/db.py`
- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/quant/backtest.py`
- `src/investment_forecasting/web/app.py`
- `src/investment_forecasting/mcp/tools.py`
- `tests/test_db.py`
- `tests/test_backtest.py`
- `tests/test_web_app.py`
- `tests/test_mcp_tools.py`

## Implementation Checklist

- Decide whether to extend `model_predictions` or add a sidecar
  `model_prediction_reliability` table; document the choice.
- Preserve existing forecast generation and advice behavior.
- Add same-category rank computation from existing asset metadata and
  deterministic theme/category helpers.
- Add risk-adjusted score derived from expected return, downside risk,
  volatility/drawdown evidence where available.

## Acceptance Criteria

- Existing predictions still render and feed advice/Jarvis.
- New ranking/reliability metadata can be stored or queried for predictions.
- WebUI/MCP can expose rank and risk-adjusted score as evidence, not as a
  guaranteed recommendation.
- Tests cover legacy predictions with missing reliability fields.

## Test Plan

- `python3 -m pytest tests/test_db.py tests/test_backtest.py tests/test_web_app.py tests/test_mcp_tools.py -q`

## Depends On

- `TASK-073`

## Completion Notes

- Added the sidecar `model_prediction_reliability` table instead of expanding
  `model_predictions`, preserving legacy forecast/advice/Jarvis consumers while
  allowing reliability metadata to be joined when available.
- `forecast run` now refreshes deterministic reliability rows for latest
  predictions: cross-sectional rank, same-category rank, risk-adjusted score,
  validation status, degraded reason, and evidence IDs.
- Same-category rank uses stored asset type plus deterministic theme
  classification. Risk-adjusted score is a conservative percentile derived from
  expected return, downside-risk penalty, and confidence.
- WebUI prediction cards and technical rows now expose rank, same-category,
  risk-adjusted score, and validation state as evidence under existing
  prediction surfaces without adding navigation.
- MCP market snapshot includes average rank and average risk-adjusted score for
  agents.
- Validation metrics such as Rank IC and bucket spread remain intentionally
  empty until `TASK-075` implements the financial validation upgrade.

## Verification

- `python3 -m pytest tests/test_db.py tests/test_backtest.py tests/test_web_app.py tests/test_mcp_tools.py -q`
