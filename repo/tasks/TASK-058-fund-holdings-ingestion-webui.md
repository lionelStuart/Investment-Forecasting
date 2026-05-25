# TASK-058: Fund Holdings Ingestion And WebUI

## Status

completed

## Purpose

Close the first fund-holdings data gap from the README. Users should be able to
persist quarterly public-fund stock holding reports and inspect representative
holdings on the fund workbench instead of judging funds only from returns,
drawdown, fees, and manager metadata.

## Scope

- Add provider-neutral `fund_holdings` persistence.
- Normalize AKShare `fund_portfolio_hold_em` stock-holding rows into stable
  fields.
- Add `investment-forecasting ingest fund-holdings`.
- Link holding stocks back to tracked stock assets when possible.
- Show latest holding observations on `/funds`, scoped to the current fund
  filter result.
- Include fund-holding counts in dashboard database status and restart health.

## Non-Scope

- No live trading or portfolio execution.
- No full fund look-through risk model yet.
- No bond holding ingestion yet.
- No advice/Jarvis synthesis changes yet.

## Files Changed

- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/providers/akshare_provider.py`
- `src/investment_forecasting/data/fund_holdings.py`
- `src/investment_forecasting/cli.py`
- `src/investment_forecasting/web/app.py`
- `scripts/restart_web.sh`
- `tests/test_fund_holdings.py`
- `tests/test_web_app.py`
- `repo/INDEX.md`
- `repo/STATUS.md`
- `repo/ROADMAP.md`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`
- `repo/specs/SPEC-001-data-foundation.md`
- `repo/specs/SPEC-006-webui-workbench.md`

## Acceptance Criteria

- Database initialization creates `fund_holdings` and indexes.
- Holding rows upsert by fund, report period, holding type, holding code, and
  source.
- AKShare holding rows normalize weight, shares, market value, rank, and report
  period.
- CLI help exposes `ingest fund-holdings` with fund code, year, and provider
  access controls.
- `/funds` shows latest fund-holding observations when data exists.
- Tests cover normalization, idempotent persistence, stock-asset linking, and
  WebUI rendering.

## Verification

- `python3 -m pytest tests/test_fund_holdings.py tests/test_web_app.py tests/test_db.py`
- `python3 -m investment_forecasting.cli ingest fund-holdings --help`
- `scripts/restart_web.sh`
