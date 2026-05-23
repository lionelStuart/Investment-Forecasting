# Code Index

This index maps the main implementation surfaces so Agents can reuse existing
capabilities before adding new code. Update it whenever files, commands, routes,
tables, or task families are added, removed, renamed, or materially repurposed.

## Runtime Entry Points

| Surface | File | Notes |
| --- | --- | --- |
| CLI | `src/investment_forecasting/cli.py` | Commands for DB init, ingestion, features, market snapshots, forecasts, backtests, advice, preferences, expert roster/portfolios, MCP, daily workflow, calibration, and WebUI. |
| WebUI server | `src/investment_forecasting/web/app.py` | Server-rendered local workbench routes and product view helpers. |
| MCP server | `src/investment_forecasting/mcp/server.py` | Official MCP stdio transport. |
| MCP tools | `src/investment_forecasting/mcp/tools.py` | JSON-callable tool registry for assets, research workflows, advice, and expert committee operations. |
| Daily workflow | `src/investment_forecasting/workflows/daily.py` | Orchestrates ingestion, features, market snapshot, forecast, backtest, advice, and logs. |
| Restart script | `scripts/restart_web.sh` | Restarts local WebUI and prints database health. |

## Core Modules

| Module | Files | Owns |
| --- | --- | --- |
| Persistence | `src/investment_forecasting/db.py`, `src/investment_forecasting/migrations/001_init.sql` | SQLite connection, schema, migrations, upsert/query helpers. |
| Data ingestion | `src/investment_forecasting/data/ingestion.py`, `src/investment_forecasting/data/quality.py`, `src/investment_forecasting/data/macro.py` | Asset universe ingestion, data quality, macro observations. |
| Providers | `src/investment_forecasting/providers/*.py` | Provider-specific fetching and normalization. |
| Quant | `src/investment_forecasting/quant/*.py` | Features, forecasts, backtests, calibration, market snapshots. |
| Advice | `src/investment_forecasting/advice/*.py` | Daily advice generation, scoring, compliance-oriented language. |
| Portfolio | `src/investment_forecasting/portfolio/*.py` | Simulated portfolios, transactions, positions, cash ledger, unfilled exceptions, and valuation. |
| Experts | `src/investment_forecasting/experts/*.py` | Expert roster initialization, daily evidence-backed planning, simulated execution handoff, scorecards, lifecycle reviews, retirement lessons, and replacement hiring. |
| Communication | `src/investment_forecasting/communication/*.py` | Planned owner for channel-neutral outbound messages, delivery policies, iMessage adapter, templates, and communication logs. |
| WebUI | `src/investment_forecasting/web/app.py` | Dashboard, timeline, category navigation, data, funds, predictions, backtests, advice, experts, settings, logs. |

## Current WebUI Routes

| Route | Purpose |
| --- | --- |
| `/` | Dashboard, data status, market state, asset coverage, recommendations, latest advice. |
| `/timeline` | Research run timeline connecting advice, market snapshots, predictions, backtests, task health, source links, and missing-stage recovery hints. |
| `/categories` | Product category navigation, category summaries, drill-in tables, and links into selected asset pages. |
| `/data` | Asset selector, selected-asset summary, price/nav curve, history, and feature table. Full raw asset lists should be secondary technical details, not primary content. |
| `/funds` | Fund screening workflow with metadata/metric filters, conservative/balanced/aggressive presets, suitability explanations, and technical details. |
| `/predictions` | Priority assets and model prediction table. |
| `/backtests` | Backtest run summary and result table. |
| `/advice` | Daily advice selection, profile advice, assumptions, risks, evidence, history. |
| `/settings` | Active user risk preference and investment-horizon settings. |
| `/logs` | Task log table. |
| `/experts` | Expert committee view for active/probation/retired experts, virtual portfolios, latest plans, scorecards, reviews, and lessons. |
| `/communication` | Planned communication setup/status view for adapters, iMessage health, allowlisted recipients, and recent outbound messages. |

## Important Database Areas

| Area | Tables |
| --- | --- |
| Assets and prices | `assets`, `price_daily`, `fund_info` |
| Derived metrics | `features_daily`, `market_snapshots`, `macro_observations` |
| Forecasting and evaluation | `model_predictions`, `backtest_runs`, `backtest_results`, `advice_outcome_scores`, calibration-related records |
| Advice and preferences | `daily_advice`, `user_preferences` |
| Experts | `experts` |
| Portfolios and expert activity | `virtual_portfolios`, `virtual_positions`, `virtual_transactions`, `virtual_cash_ledger`, `virtual_valuations`, `expert_plans`, `expert_plan_items`, `expert_scorecards`, `expert_reviews`, `expert_lessons` |
| Planned communication | `communication_recipients`, `communication_adapter_configs`, `outbound_messages` |
| Operations | `task_logs`, `data_quality_reports` |

## Test Map

| Concern | Tests |
| --- | --- |
| Persistence/schema | `tests/test_db.py` |
| Data ingestion/quality | `tests/test_akshare_ingestion.py`, `tests/test_data_quality.py`, `tests/test_macro.py` |
| Quant and calibration | `tests/test_features.py`, `tests/test_market.py`, `tests/test_backtest.py`, `tests/test_calibration.py` |
| Advice | `tests/test_advice.py`, `tests/test_advice_scoring.py`, `tests/test_daily_workflow.py` |
| Portfolio | `tests/test_portfolio.py` |
| Expert scoring | `tests/test_expert_scoring.py` |
| MCP | `tests/test_mcp_tools.py`, `tests/test_mcp_server.py` |
| WebUI | `tests/test_web_app.py` |
| Experts | `tests/test_experts.py` |
| Communication | `tests/test_communication.py` |

## Productized Research Flow Tasks

| Task | Main Surfaces To Inspect First |
| --- | --- |
| `TASK-028` timeline | `web/app.py`, `workflows/daily.py`, `db.py`, `task_logs`, `daily_advice`, `market_snapshots`, `backtest_runs` |
| `TASK-029` categories | `web/app.py`, `assets`, `fund_info`, `features_daily`, `model_predictions`, `market_snapshots`, `macro_observations` |
| `TASK-030` fund filters | `web/app.py`, `fund_info`, `features_daily`, `user_preferences`, shared fund filter helpers, `tests/test_web_app.py` |
| `TASK-031` red/green semantics | `web/app.py` CSS/helpers, recommendation cards, tables, prediction/fund/advice views |
| `TASK-032` asset prediction cards | `web/app.py`, `model_predictions`, `assets`, prediction tests |
| `TASK-033` dashboard brief/run health | `web/app.py`, `workflows/daily.py`, `task_logs`, `daily_advice`, `market_snapshots`, `user_preferences` |
| `TASK-035` technical table disclosure | `web/app.py`, shared table/detail helpers, `/data`, `/funds`, `/predictions`, `/backtests`, `/advice`, `/settings`, `/logs`, `tests/test_web_app.py` |
| `TASK-036` expert roster | `experts/`, `db.py`, migrations, `cli.py`, `tests/test_experts.py`, `ARCHITECTURE.md` |
| `TASK-037` expert virtual portfolios | `portfolio/`, `experts/`, migrations, `db.py`, `tests/test_portfolio.py`, `tests/test_experts.py` |
| `TASK-038` expert daily execution | `experts/`, `portfolio/`, `cli.py`, `model_predictions`, `features_daily`, `market_snapshots`, `virtual_portfolios`, `expert_plans` |
| `TASK-039` expert scoring/lifecycle | `experts/scoring.py`, `portfolio/`, `expert_scorecards`, `expert_reviews`, `expert_lessons`, `tests/test_expert_scoring.py` |
| `TASK-040` expert WebUI | `web/app.py`, `/experts`, expert/portfolio query helpers, `tests/test_web_app.py` |
| `TASK-041` expert MCP/agent workflow | `mcp/tools.py`, `mcp/server.py`, `cli.py`, expert services, `task_logs`, MCP tests |
| `TASK-042` communication architecture | `communication/`, `db.py`, migrations, `cli.py`, `task_logs`, `tests/test_communication.py`, `ARCHITECTURE.md` |
| `TASK-043` iMessage adapter | `communication/imessage.py`, `communication/service.py`, `cli.py`, macOS setup checks, `tests/test_communication.py` |
| `TASK-044` mobile templates | `communication/templates.py`, `workflows/daily.py`, `experts/`, daily brief/run health/expert summaries |
| `TASK-045` communication WebUI/CLI | `web/app.py`, `/communication`, `cli.py`, communication query helpers, `tests/test_web_app.py` |
| `TASK-046` inbound command design | `SPEC-008`, `decisions/`, communication safety notes |

## Development Guardrails

- Check this index and `ARCHITECTURE.md` before adding a new file or helper.
- Prefer shared formatting/view-model helpers in `web/app.py` over repeating
  presentation logic per route.
- Keep SQL ownership close to existing persistence or route query patterns; do
  not introduce ad hoc duplicate queries when a helper already exists.
- Add or update tests in the mapped test file for every product behavior change.
