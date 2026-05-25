# TASK-056: Capital Flow Observations

## Status

completed

## Purpose

Close the first funds-flow data gap from the README by persisting provider
neutral capital-flow observations and surfacing them in the market workbench.
Users should be able to inspect whether tracked stocks or market-level
subjects are seeing main-money inflow or outflow alongside market snapshots and
macro observations.

## Scope

- Add a `capital_flow_observations` SQLite table for market, stock, sector, or
  fund subjects.
- Add idempotent persistence helpers for capital-flow rows.
- Add AKShare normalization for individual-stock and market capital-flow APIs.
- Add `investment-forecasting ingest capital-flow` for explicit, polite
  capital-flow ingestion.
- Show latest capital-flow observations and historical details on `/market`.
- Include capital-flow counts/dates in database status and market-indicator
  category coverage.

## Non-Scope

- No live trading or trade execution.
- No guarantee that capital flow predicts returns.
- No industry/sector capital-flow ingestion until a stable provider endpoint is
  selected.
- No fund-holding or fund-subscription/redemption data.

## Files Changed

- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/providers/akshare_provider.py`
- `src/investment_forecasting/data/capital_flow.py`
- `src/investment_forecasting/cli.py`
- `src/investment_forecasting/web/app.py`
- `scripts/restart_web.sh`
- `tests/test_capital_flow.py`
- `tests/test_web_app.py`
- `repo/INDEX.md`
- `repo/STATUS.md`
- `repo/ROADMAP.md`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`
- `repo/specs/SPEC-001-data-foundation.md`
- `repo/specs/SPEC-006-webui-workbench.md`

## Acceptance Criteria

- Database initialization creates `capital_flow_observations` and related
  indexes.
- Capital-flow rows upsert by scope, subject code, date, and source.
- AKShare capital-flow columns are normalized into stable main/super-large/
  large/medium/small inflow fields.
- CLI help exposes `ingest capital-flow` with scope, asset code, max-day, and
  provider access controls.
- `/market` shows latest funds-flow observations and a historical technical
  detail section when data exists.
- Tests cover normalization, persistence idempotency, and WebUI rendering.

## Verification

- `python3 -m pytest tests/test_capital_flow.py tests/test_web_app.py tests/test_db.py`
- `python3 -m investment_forecasting.cli ingest capital-flow --help`
- `scripts/restart_web.sh`
