# TASK-068: Opportunity Pool Consolidation

## Status

completed

## Purpose

Create one 机会池 flow for assets and products so users can browse what is
worth watching without jumping across 产品分类, 基金筛选, 数据与曲线, 主题, and
预测 pages.

## Scope

- Add or repurpose a route for 机会池.
- Combine category, theme, fund screening, selected-asset data, and asset-level
  prediction cards into a single discovery workflow.
- Support fund, ETF, stock, and index filtering.
- Sort or annotate opportunities by active risk preference where existing data
  supports it.
- Keep detailed curves, technical metrics, and raw prediction rows as
  drill-down or collapsed details.

## Non-Scope

- No new ranking model.
- No new data ingestion.
- No suitability claim beyond stored evidence and risk-profile context.
- No deletion of existing category/fund/data/prediction routes.

## Files Likely To Change

- `src/investment_forecasting/web/app.py`
- `tests/test_web_app.py`
- `repo/CODE_INDEX.md`

## Implementation Checklist

- Reuse existing category summaries, theme labels, fund filters, selected asset
  summaries, and prediction card helpers.
- Provide clear empty states when fund metadata, holdings, or predictions are
  missing.
- Link each opportunity to evidence and technical detail.

## Acceptance Criteria

- The 机会池 entry lets users filter by product type and risk preference.
- Asset-level prediction cards are visible inside the opportunity flow.
- Technical data and raw prediction rows are secondary, not first-screen
  requirements.
- Old discovery pages are reachable by links or direct route but no longer
  required for the main consumer journey.

## Test Plan

- `python3 -m pytest tests/test_web_app.py -q`

## Depends On

- `TASK-066`
