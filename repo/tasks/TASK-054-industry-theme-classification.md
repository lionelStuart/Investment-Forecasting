# TASK-054: Industry And Theme Classification

## Status

completed

## Purpose

Add a first industry/theme classification layer so the expanded asset universe
is not only grouped by asset type. This makes ETF, fund, stock, and index
records easier to inspect by sector-like themes while keeping the classification
deterministic and auditable.

## Scope

- Add a deterministic asset theme classifier based on stored code, name,
  asset type, and fund type.
- Surface the theme label in category drill-in tables, selected asset summary,
  fund screening results, prediction cards, and market snapshot movers.
- Add a theme filter to the fund screening form.
- Keep raw source records unchanged; no schema migration.

## Non-Scope

- No paid industry taxonomy.
- No fund holding ingestion.
- No capital-flow ingestion.
- No LLM-only classification.

## Files Changed

- `src/investment_forecasting/data/classification.py`
- `src/investment_forecasting/web/app.py`
- `tests/test_classification.py`
- `tests/test_web_app.py`
- `repo/INDEX.md`
- `repo/STATUS.md`
- `repo/ROADMAP.md`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`
- `repo/specs/SPEC-001-data-foundation.md`
- `repo/specs/SPEC-006-webui-workbench.md`

## Acceptance Criteria

- Theme classification is deterministic and includes an explanation reason.
- WebUI surfaces theme labels on data/category/fund/prediction/market views.
- Fund screening can filter by theme.
- Tests cover classifier behavior and WebUI theme visibility/filtering.

## Verification

- `python3 -m pytest tests/test_classification.py tests/test_web_app.py`
- `scripts/restart_web.sh`
