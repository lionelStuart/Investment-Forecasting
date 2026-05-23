# TASK-035: Progressive Disclosure For Technical Tables

## Status

pending

## Purpose

Raw database-like tables, evidence JSON, and operational logs are still too
prominent on several WebUI pages. This slows down investment research because
users must translate implementation details before they can decide what to
inspect next.

This task makes the workbench summary-first: each page should expose the
decision context, key signals, filters, and exceptions before showing raw
technical detail.

## Source

Product review after inspecting `http://127.0.0.1:8765/` and the user's
requirement that the full asset-list table under the `/data` selector should
not be part of the primary workflow.

## Scope

- `/data`: Keep the asset selector. Replace the full raw asset-list table as
  primary content with selected-asset summary, category context, key metrics,
  and curve/history sections.
- `/funds`: Add filter controls, profile presets, and top candidate summaries
  before any detailed fund table.
- `/predictions`: Show asset-level cards and horizon agreement before the raw
  prediction table.
- `/backtests`: Show model-health summary, horizon score cards, and degraded
  model warnings before historical result rows.
- `/advice`: Replace visible raw evidence JSON with evidence chips/cards and
  keep raw JSON only in a collapsed technical detail block.
- `/settings`: Show a human-readable active profile summary before any saved
  preference field table.
- `/logs`: Group latest run health, failure impact, and recovery guidance before
  raw task logs.

## Non-Scope

- Changing forecast, backtest, or advice algorithms.
- Removing technical detail completely. Technical users and Agents should still
  be able to inspect raw rows through clearly secondary details.
- Adding new providers or data sources.

## Files Likely To Change

- `src/investment_forecasting/web/app.py`
- `tests/test_web_app.py`
- `repo/CODE_INDEX.md`
- `repo/ARCHITECTURE.md` if shared disclosure helpers or view-model boundaries
  are introduced

## Implementation Checklist

- Inspect existing WebUI route helpers and formatting helpers before adding new
  rendering code.
- Identify which tables on `/data`, `/funds`, `/predictions`, `/backtests`,
  `/advice`, `/settings`, and `/logs` are primary workflow content versus
  secondary technical detail.
- Add or reuse shared helpers for secondary technical sections so table-heavy
  pages do not duplicate disclosure markup.
- Ensure every table-heavy page starts with user-facing summaries, filters,
  cards, warnings, or recovery guidance.
- Keep raw tables and JSON available behind clearly labeled secondary or
  collapsed technical details.
- Update `CODE_INDEX.md` and `ARCHITECTURE.md` when new shared helpers,
  route responsibilities, or view-model boundaries are added.

## Acceptance Criteria

- `/data` no longer shows the full raw asset-list table as the main content
  under the selector.
- `/funds` can be used through filters or presets before scanning raw rows.
- `/predictions` shows one primary card per asset before any raw prediction
  rows.
- `/backtests` communicates model quality and degraded states before historical
  result rows.
- `/advice` can be understood without reading raw JSON.
- `/settings` communicates the active risk profile in human language.
- `/logs` communicates latest run health and failure impact before raw logs.
- Technical detail sections are clearly labeled and secondary.

## Test Plan

- Add or update WebUI route tests for `/data`, `/advice`, `/logs`, and one
  analysis-heavy page such as `/predictions` or `/backtests`.
- Verify raw technical data remains available for debugging.
- Run `python3 -m pytest tests/test_web_app.py`.

## Dependencies

- `TASK-029`: Product category navigation and `/data` restructuring.
- `TASK-030`: Fund filters and presets.
- `TASK-032`: Asset-level prediction cards.
- `TASK-033`: Dashboard brief and run-health summary.
