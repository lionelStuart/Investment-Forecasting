# TASK-060: Correlation Risk Budget Advice

## Status

completed

## Purpose

Advance the README portfolio-optimization goal beyond target volatility. Daily
advice should expose whether the candidate allocation is concentrated in
highly correlated assets and how much approximate risk contribution comes from
equity, fixed-income, cash, or other buckets.

## Scope

- Reuse stored `price_daily`, `features_daily`, active preferences, and the
  existing target-volatility candidate assets.
- Add a correlation-aware risk-budget proposal to `allocation_json`.
- Include evidence asset IDs and price-observation counts.
- Show a WebUI panel on `/advice` for correlation sample count, average
  absolute correlation, bucket risk contribution, and per-asset risk scores.
- Keep the result descriptive and research-oriented.

## Non-Scope

- No live trading or automatic rebalancing.
- No full covariance optimizer or new dependency.
- No guarantee that lower correlation improves returns.
- No schema migration.

## Files Changed

- `src/investment_forecasting/advice/allocation.py`
- `src/investment_forecasting/advice/generator.py`
- `src/investment_forecasting/web/app.py`
- `tests/test_advice.py`
- `tests/test_web_app.py`
- `README.md`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`
- `repo/INDEX.md`
- `repo/ROADMAP.md`
- `repo/STATUS.md`
- `repo/specs/SPEC-003-advice-generation.md`
- `repo/specs/SPEC-006-webui-workbench.md`

## Acceptance Criteria

- Daily advice `allocation_json` includes a `risk_budget` object.
- The risk-budget object is computed from stored prices and target-volatility
  candidate assets when enough overlapping return history exists.
- The output includes status, bucket risk contribution, pairwise-correlation
  summary, per-asset risk rows, evidence asset IDs, and price-observation
  count.
- `/advice` shows a "相关性风险预算" panel and "相关性证据" evidence chip.
- Existing target-volatility behavior remains intact.

## Verification

- `python3 -m pytest tests/test_advice.py tests/test_web_app.py -q`
- `scripts/restart_web.sh`
