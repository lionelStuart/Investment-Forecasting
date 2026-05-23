# Project

## Summary

Investment Forecasting is a continuously evolving AI investment research and
wealth-management assistant. Its MVP builds a reliable, reproducible, auditable
local system that collects market and fund data, stores raw and derived data in
SQLite, computes quantitative indicators, runs forecasts and backtests, exposes
structured MCP tools to AI agents, generates daily risk-aware advice, and shows
results in a workbench-style WebUI.

The system is research and decision-support software. It does not provide
capital protection, guaranteed returns, or direct instructions to buy or sell.

## Goals

- Collect A-share, index, ETF, public fund, macro, and market-sentiment data.
- Persist raw data, cleaned data, features, predictions, backtests, advice, and
  task logs in SQLite.
- Encapsulate data queries, indicator calculation, model forecasting, backtest
  evaluation, and advice generation as callable services.
- Expose MCP tools so AI agents use structured system capabilities instead of
  inventing market judgments.
- Run a daily 08:00 Codex automation that updates data, evaluates the market,
  generates forecasts, records scores, and writes daily advice.
- Provide a WebUI for data inspection, model predictions, historical advice,
  scores, risks, and task logs.
- Use historical data windows for forecast calibration and model improvement.

## Non-Goals

- Do not build a high-frequency trading system.
- Do not guarantee returns or produce deterministic investment conclusions.
- Do not start with a complex live trading or brokerage integration.
- Do not optimize for a marketing landing page; the WebUI is an operating
  workbench.
- Do not add advanced ML models before simple reproducible baselines and
  backtests exist.

## Users

- Primary operator: the project owner using Codex and AI agents for daily
  investment research and product iteration.
- Secondary users: future reviewers who need to inspect model assumptions,
  historical scores, risk warnings, and task logs.

## Global Constraints

- Every prediction and advice item must include assumptions, risk boundaries,
  uncertainty, and evidence links to stored model/backtest outputs.
- Every model must have out-of-sample or rolling historical evaluation before it
  is trusted for daily advice.
- Time-series evaluation must avoid future leakage and random sample splitting.
- All scheduled jobs must be idempotent where practical and must write logs.
- Data updates must support retry, validation, and recoverable failure handling.
- SQLite is the MVP persistence layer; PostgreSQL or DuckDB can be considered
  later through an ADR.
- AKShare is the MVP primary data source; Tushare Pro and macro providers are
  later enhancements unless a task explicitly introduces them.

## Terminology

- `Asset`: A stock, index, ETF, public fund, or other investable/security-like
  instrument tracked by the system.
- `Feature`: A reproducible derived indicator such as return, volatility,
  drawdown, momentum, valuation state, or market condition.
- `Forecast`: A structured prediction for a horizon such as 5, 20, or 60
  trading days.
- `Backtest`: A historical replay that only uses information available before
  each prediction timestamp.
- `Daily Advice`: The stored daily output containing market view, risk state,
  risk-profile-specific allocation guidance, assumptions, and scores.
- `MCP Tool`: A structured callable interface used by AI agents to retrieve data
  or run system capabilities.

## Default Commands

- `dev`: `python3 -m pip install -e '.[dev]'`
- `db:init`: `investment-forecasting db init --db data/investment_forecasting.sqlite3`
- `ingest:mvp`: `investment-forecasting ingest mvp --db data/investment_forecasting.sqlite3 --start-date YYYYMMDD --end-date YYYYMMDD`
- `features:calculate`: `investment-forecasting features calculate --db data/investment_forecasting.sqlite3 --start-date YYYYMMDD --end-date YYYYMMDD`
- `market:snapshot`: `investment-forecasting market snapshot --db data/investment_forecasting.sqlite3 --date YYYYMMDD`
- `forecast:run`: `investment-forecasting forecast run --db data/investment_forecasting.sqlite3 --horizons 5,20,60`
- `backtest:run`: `investment-forecasting backtest run --db data/investment_forecasting.sqlite3 --horizons 5,20,60 --lookback-days 60`
- `advice:generate`: `investment-forecasting advice generate --db data/investment_forecasting.sqlite3 --date YYYYMMDD`
- `advice:score-outcomes`: `investment-forecasting advice score-outcomes --db data/investment_forecasting.sqlite3 --horizon-days 20`
- `mcp:list-tools`: `investment-forecasting mcp list-tools`
- `mcp:call`: `investment-forecasting mcp call TOOL_NAME --db data/investment_forecasting.sqlite3 --args '{}'`
- `mcp:serve`: `investment-forecasting-mcp --db data/investment_forecasting.sqlite3`
- `daily:run`: `investment-forecasting daily run --db data/investment_forecasting.sqlite3 --date YYYYMMDD --horizons 5,20,60 --lookback-days 60`
- `web:run`: `investment-forecasting web run --db data/investment_forecasting.sqlite3 --host 127.0.0.1 --port 8765`
- `calibration:run`: `investment-forecasting calibration run --db data/investment_forecasting.sqlite3 --date YYYYMMDD --horizons 5,20,60 --lookback-days 60`
- `test`: `python3 -m pytest`
- `build`: Not defined. The MVP WebUI is a local server-rendered workbench.
