# TASK-059: Fund Holding Theme Look-Through

## Status

completed

## Purpose

Turn ingested public-fund holdings into a readable look-through exposure view.
Users should be able to see which themes a filtered fund set is actually
holding, instead of only reading raw quarterly holding rows.

## Scope

- Reuse persisted `fund_holdings` rows and deterministic theme classification.
- Extend latest fund-holding query output with linked holding asset type.
- Aggregate `/funds` holding rows by theme within the current fund filter.
- Show total holding weight, covered funds, holding count, latest report period,
  and representative holdings before the raw holding table.
- Keep the raw holding rows available for audit.

## Non-Scope

- No new provider, taxonomy table, or LLM-based industry inference.
- No bond-holding ingestion.
- No advice/Jarvis allocation changes yet.
- No suitability or guaranteed-return claims.

## Files Changed

- `src/investment_forecasting/db.py`
- `src/investment_forecasting/web/app.py`
- `tests/test_web_app.py`
- `repo/INDEX.md`
- `repo/STATUS.md`
- `repo/ROADMAP.md`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`
- `repo/specs/SPEC-006-webui-workbench.md`
- `README.md`

## Acceptance Criteria

- `/funds` shows a holding look-through theme exposure panel when holding rows
  exist.
- The exposure panel is scoped to the current filtered fund set.
- Theme labels come from deterministic `classify_asset_theme` using linked
  holding asset fields when available.
- The panel shows readable weight percentages, fund count, holding count,
  latest report period, and top holdings.
- The existing raw fund-holding detail table remains available below the
  exposure summary.

## Verification

- `python3 -m pytest tests/test_web_app.py tests/test_fund_holdings.py tests/test_db.py -q`
- `scripts/restart_web.sh`
