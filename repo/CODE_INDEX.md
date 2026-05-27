# Code Index

This index maps the main implementation surfaces so Agents can reuse existing
capabilities before adding new code. Update it whenever files, commands, routes,
tables, or task families are added, removed, renamed, or materially repurposed.

## Runtime Entry Points

| Surface | File | Notes |
| --- | --- | --- |
| CLI | `src/investment_forecasting/cli.py` | Commands for DB init, polite/incremental ingestion with explicit provider selection, macro/capital-flow/fund-holding/news ingestion, features, market snapshots, forecasts, backtests, monitoring, advice, preferences, generic simulated portfolios, expert roster/portfolios, communication configuration/inspection/notifications, Jarvis brief generation, AI provider inspection/dry-run, agent-run inspection, scheduler inspection/manual runs, MCP, daily workflow, calibration, and WebUI. Model-validation commands include `replay-ytd`, `report`, `tuning-plan`, `health-generate/report`, `applicability-generate/report`, `shadow-router-run/report`, `confidence-labels-generate/report`, and `governance-generate/report`. |
| WebUI server | `src/investment_forecasting/web/app.py` | Server-rendered Jarvis-first product routes, legacy technical routes, navigation, and product view helpers. |
| MCP server | `src/investment_forecasting/mcp/server.py` | Official MCP stdio transport. |
| MCP tools | `src/investment_forecasting/mcp/tools.py` | JSON-callable tool registry for assets, research workflows, advice, expert committee operations, Jarvis brief retrieval/generation, role-scoped agent manifests, agent output validation preview, and audited expert/Jarvis submission envelopes. |
| Daily workflow | `src/investment_forecasting/workflows/daily.py` | Orchestrates ingestion, features, market snapshot, forecast, backtest, advice, model monitoring, optional Jarvis generation, optional mobile notifications, and logs. |
| Scheduler cron registration | `src/investment_forecasting/scheduler/service.py`, `src/investment_forecasting/cli.py` | `scheduler install-cron` installs one local macOS LaunchAgent, `local.investment-forecasting.scheduler`, that wakes `scheduler run-due` every 5 minutes. Business cadence is owned by `scheduler_jobs`: market/news every two hours, post-close price/features/model services, expert T-day daily, and Jarvis T+1 daily with default phone notification environment. `scheduler today-status` exposes today's successful, failed, deferred, missed, and not-yet-due jobs, while latest runs expose `execution_mode` (`real_provider`, `real_calculation`, `real_model_run`, `agent_runtime`, or `readiness_only`). |
| Restart script | `scripts/restart_web.sh` | Restarts local WebUI and prints database health. |

## Core Modules

| Module | Files | Owns |
| --- | --- | --- |
| Persistence | `src/investment_forecasting/db.py`, `src/investment_forecasting/migrations/001_init.sql` | SQLite connection, schema, migrations, upsert/query helpers. |
| Data ingestion | `src/investment_forecasting/data/ingestion.py`, `src/investment_forecasting/data/quality.py`, `src/investment_forecasting/data/macro.py`, `src/investment_forecasting/data/capital_flow.py`, `src/investment_forecasting/data/fund_holdings.py`, `src/investment_forecasting/data/classification.py`, `src/investment_forecasting/data/news.py` | Asset universe ingestion, incremental date-range policy, data quality, macro observations, provider-neutral capital-flow observations, fund-holding reports, bounded news evidence ingestion, and deterministic industry/theme classification. |
| Providers | `src/investment_forecasting/providers/*.py` | AKShare default provider and optional Tushare provider, provider-specific fetching, normalization, retry/backoff, polite access policy, diagnostics, and optional Tushare news retrieval. |
| Scheduler | `src/investment_forecasting/scheduler/*` | System-owned fixed job registry, due-job selection, real incremental news/market/price/features handlers, post-close forecast/backtest/market/advice/monitoring orchestration, scheduler watermarks, provider request budgets/backoff state, task readiness gates, execution-mode reporting, and CLI/WebUI/MCP status/manual run commands. |
| Quant | `src/investment_forecasting/quant/*.py` | Features, forecasts, backtests, benchmark selection, calibration, model monitoring, market snapshots, rank validation, candidate-model comparison, and model reliability metadata. |
| Model validation replay | `src/investment_forecasting/quant/model_validation.py` | Current-year daily forecast replay from stored local history, replay run/prediction persistence, matured outcome scoring, diagnostics by model/horizon/asset group/month/regime, and evidence-backed tuning recommendations for model accuracy and confidence only. Replay rows must not overwrite operational `model_predictions` and must not evaluate expert/Jarvis/advice outputs. |
| Model applicability governance | `src/investment_forecasting/quant/model_validation.py` | Context-specific model-health facts, model applicability profiles, same-type ranking disable rules, 20-day shadow router `router_floor70_cap05`, confidence labels, and monthly governance summaries. Production `model_predictions` remain unchanged. |
| Advice | `src/investment_forecasting/advice/*.py` | Daily advice generation, target-volatility allocation proposals, correlation risk-budget evidence, capital-flow evidence summaries, benchmark-aware outcome scoring, compliance-oriented language. |
| AI analysis | `src/investment_forecasting/ai_analysis.py` | Versioned expert/Jarvis prompt and output-schema contracts, bounded evidence packets, provider request builders, structured analysis output, compliance checks, unsupported prediction/news evidence validation, persisted provider/fallback metadata, and deterministic fallback. |
| AI providers | `src/investment_forecasting/ai_providers/*` | Provider request/response/config contracts, environment config discovery, fake-provider dry runs, timeout/error fallback mapping, source metadata, and future model SDK/API calls. No other module should import model SDKs directly. |
| Codex runtime access | `src/investment_forecasting/agent_runtime/*` | System-owned role-scoped Codex agent run protocol, launch request/result/status dataclasses, runtime policy, service helpers, fake adapter, local Codex CLI adapter/readiness/smoke, per-run artifact layout, role manifests, prompt rendering, run/tool-call audit persistence, expert execution, Jarvis readiness including upstream scheduler evidence status, and CLI inspection. |
| Portfolio | `src/investment_forecasting/portfolio/*.py` | Simulated portfolios, transactions, positions, cash ledger, unfilled exceptions, and valuation. |
| Experts | `src/investment_forecasting/experts/*.py` | Expert roster initialization, daily evidence-backed planning, simulated execution handoff, scorecards, lifecycle reviews, retirement lessons, and replacement hiring. |
| Communication | `src/investment_forecasting/communication/*.py` | Channel-neutral outbound message service, notification templates, delivery policy checks, dry-run/failing adapters, iMessage adapter boundary, setup health, idempotency, allowlist enforcement, and communication logs. |
| Jarvis | `src/investment_forecasting/jarvis/*.py` | Persistence and deterministic/provider-backed synthesis for Jarvis daily briefs, model/expert/capital-flow summaries, disagreement explanation, confidence gates, evidence references, missing/stale evidence metadata, provider/fallback status, and safe-language validation. |
| WebUI | `src/investment_forecasting/web/app.py` | Five-entry Jarvis consumer IA, dashboard/Jarvis daily brief, timeline, market/macro indicators, theme allocation overview, category navigation, data, funds, predictions, backtests, advice, simulated portfolios, experts, communication status, settings, logs, and shared Chinese-market red/green value formatting. |

## Target Primary WebUI Navigation

This table is a product and architecture constraint, not a temporary design
preference. See `decisions/ADR-007-jarvis-consumer-information-architecture.md`.

| Entry | Combines | Purpose |
| --- | --- | --- |
| 今日简报 | Dashboard, Jarvis, Daily Advice, Timeline core | Default Jarvis daily decision surface: stance, one-line conclusion, reasons, expert consensus/disagreement, focus assets, freshness, health, risks, and watch conditions. |
| 机会池 | Categories, Themes, Funds, Data, Predictions core | Product and asset discovery for funds, ETFs, stocks, and indices with risk-profile-aware context and prediction cards. |
| 专家团 | Experts | Consumer-facing expert opinions, disagreement, performance, lifecycle reviews, and lessons. |
| 证据 | Predictions, Backtests, Market, technical Data | Advanced model, market, data coverage, raw evidence, and technical tables for users and agents. |
| 设置 | Risk Settings, Communication, Logs/System Health | Risk preference, horizon, notification setup, communication health, data update state, and task logs as advanced details. |

## Current / Legacy WebUI Routes

| Route | Purpose |
| --- | --- |
| `/` | 今日简报 default Jarvis decision surface organized around six daily questions: 今天怎么看, 为什么, 能不能信, 关注哪些资产, 专家是否一致, and 风险边界/观察条件. It uses the latest Jarvis brief, advice, data freshness, run health, focus assets, expert consensus, and secondary evidence links. |
| `/opportunities` | 机会池 consumer flow combining category, theme, fund, holding look-through, data, and asset-level prediction discovery with product-type and risk-profile filters. |
| `/jarvis` | Jarvis first-screen daily brief with focus directions, one-line stance, model summary, capital-flow evidence link, expert summaries, scores, current returns, risk warnings, evidence links, history, and secondary raw JSON. |
| `/timeline` | Research run timeline connecting advice, market snapshots, predictions, backtests, task health, source links, and missing-stage recovery hints. |
| `/market` | Market snapshot and macro-indicator page showing latest regime metrics, capital-flow observations, latest macro observations, and historical market/macro/funds-flow technical details. |
| `/categories` | Product category navigation, category summaries, drill-in tables, and links into selected asset pages. |
| `/themes` | Theme allocation overview aggregating deterministic industry/theme labels into coverage, risk/return, expected-return, and representative-asset drill-ins. |
| `/data` | Asset selector, selected-asset summary, price/nav curve, history, and feature table. Full raw asset lists should be secondary technical details, not primary content. |
| `/funds` | Fund screening workflow with metadata/metric filters, conservative/balanced/aggressive presets, suitability explanations, latest fund-holding observations, filtered holding theme exposure, and technical details. |
| `/predictions` | Asset-level prediction cards grouping 5/20/60 day horizons, horizon agreement labels, and secondary raw model prediction table. |
| `/backtests` | Model-health summary, horizon score cards, degraded warnings, and secondary raw backtest run/result tables. |
| `/advice` | Daily advice selection, profile advice, assumptions, risks, target-volatility and correlation risk-budget panels, evidence cards, history, and collapsed raw advice JSON. |
| `/portfolios` | Simulated portfolio selector, holdings, transactions, valuation history, and equity curve using stored prices. |
| `/settings` | 设置 page combining active risk profile, editable preference form, communication/notification health, data update state, system health, task-log guidance, and secondary saved-preference/log fields. |
| `/evidence` | 证据 center combining model prediction cards, backtest/model health, market/macro/capital-flow evidence, data coverage, and collapsed raw technical rows. |
| `/logs` | Run-health summary, failure guidance, and secondary raw task log table. |
| `/experts` | Expert committee overview with compact active/probation/retired expert cards, one multi-expert return comparison curve, lightweight lessons, and click-through expert detail pages for plans, timelines, positions, returns, scoring, and reflections. Raw equity/benchmark and plan/execution tables should not reappear on the overview. |
| `/communication` | Communication setup/status view for adapters, iMessage preflight health, masked allowlisted recipients, WebUI dry-run test, recent outbound messages, and recent errors. |

## Jarvis Commands

| Command | Purpose |
| --- | --- |
| `investment-forecasting jarvis generate --db ... --date YYYYMMDD` | Generate and persist a Jarvis daily brief from stored market, model, expert, portfolio, task-log, and preference evidence. If `--notify-recipient-key` is omitted, Jarvis reads `INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY`, `INVESTMENT_FORECASTING_NOTIFICATION_CHANNEL`, and `INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN` from the environment for the phone summary. |
| `investment-forecasting daily run --generate-jarvis ...` | Run Jarvis generation as an explicit final daily workflow step. If `--notify-recipient-key` is omitted, daily workflow reads `INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY`, `INVESTMENT_FORECASTING_NOTIFICATION_CHANNEL`, and `INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN` from the environment. |

## Jarvis MCP Tools

| Tool | Purpose |
| --- | --- |
| `get_jarvis_daily_brief` | Return the latest or date/version-specific Jarvis daily brief as structured JSON, including Jarvis AI provider/fallback status when available. |
| `generate_jarvis_daily_brief` | Generate and persist a Jarvis daily brief from stored evidence, with task logging and AI provider/fallback status. |
| `search_news_evidence` | Return bounded news evidence by source/time/asset/theme/event/sentiment/keyword with evidence IDs, links, tags, match reasons, and no raw provider dump. |

## Codex Agent Runtime Surfaces

See `SPEC-012` and `ADR-008`. `TASK-080` through `TASK-084` implement the base
runtime access contract, local Codex CLI execution, role-scoped manifests,
domain/function skills, prompt rendering, expert T-day execution, Jarvis T+1
readiness, submission audit, and persistence links.

| Surface | Purpose |
| --- | --- |
| `agent_runs` | Implemented. Persists role type, role key, run date, target evidence date, trigger reason, status, launch request, Codex runtime metadata, timestamps, submission result, and failure/fallback reason. |
| `agent_tool_calls` | Implemented. Persists allowed/rejected/submitted/failed runtime tool attempts with sanitized arguments, role metadata, idempotency key, result summary, and errors. |
| Runtime adapter protocol | Implemented boundary shape with `prepare_run`, `start_run`, `poll_run`, `cancel_run`, and `collect_result`; tests use `FakeCodexRuntimeAdapter`, and `CodexCliRuntimeAdapter` starts local `codex exec` with non-interactive approval policy. The local adapter uses the configured Codex model by default and only passes `--model` when explicitly configured. |
| Launch request schema | Implemented serializable `codex_agent_runtime_v1` request containing role, dates, overview skill, skill bundle, prompt/tool manifest refs, output contract, and runtime policy. |
| Runtime artifact layout | Implemented under `data/agent_runtime/runs/<agent_run_id>/` with `request.json`, `prompt.md`, `output_schema.json`, `events.jsonl`, `last_message.txt`, `stderr.log`, and reserved `result.json`. |
| Submission protocol | Preferred tool-based submission; artifact fallback is allowed only when validated and re-submitted through system service validators. |
| Domain/function skills | Capability-specific skills such as market data, model evidence, news evidence, asset research, expert portfolio, virtual action, Jarvis synthesis, and output contract. They document bounded abilities but do not grant access unless included by a role overview skill and tool manifest. |
| `investment-expert-agent` skill | Expert overview skill for one expert's T-day virtual investment action. Composes only expert-safe domain/function skills and uses that expert's mandate, portfolio, evidence tools, and output schema. |
| `jarvis-daily-agent` skill | Jarvis overview skill for T+1 daily synthesis. Composes Jarvis-safe domain/function skills over system evidence and completed T expert outcomes. |
| Role-scoped tool manifest | Lists allowed read/submission/validation/operations tools for expert or Jarvis runs. |
| Expert submission tools | Implemented as audited submission envelopes for expert analysis draft, virtual action, and skipped/failed outcome. Expert Codex artifacts are validated and persisted into `expert_plans` with `evidence.agent_run_id`. |
| Jarvis submission tools | Implemented as audited submission envelopes for Jarvis analysis draft or daily brief. Jarvis Codex artifacts are validated and persisted into `jarvis_daily_briefs` with `evidence.agent_run_id` and readiness metadata. |
| Jarvis readiness gate | Blocks T+1 Jarvis execution until T expert runs are completed or explicitly skipped/failed. |
| Local scheduled runner | Implemented through the unified LaunchAgent installed by `scheduler install-cron`. The runner invokes `scheduler run-due`; the scheduler then triggers market/news incremental jobs, expert Codex runs, and Jarvis Codex runs through the same validated service paths that manual operations use. It is not a Codex app automation. |
| Today task status | Implemented through `scheduler today-status`, MCP `get_scheduler_today_status`, and the 设置 page system-health panel. It compares today's expected scheduler occurrences with `scheduler_runs` and today's failed `task_logs`, then marks jobs as `success`, `failed`, `deferred`, `missed`, `partial`, `not_yet_due`, or `no_run_expected`. |

## Important Database Areas

| Area | Tables |
| --- | --- |
| Assets and prices | `assets`, `price_daily`, `fund_info`, `fund_holdings` |
| Derived metrics | `features_daily`, `market_snapshots`, `macro_observations`, `capital_flow_observations` |
| News evidence | `news_items`, `news_item_links`, `news_item_tags`, `news_feature_daily` |
| Forecasting and evaluation | `model_predictions`, `backtest_runs`, `backtest_results`, `model_monitoring_reports`, `advice_outcome_scores` including benchmark identity/source, calibration-related records |
| Model replay audit | `model_replay_runs`, `model_replay_predictions` for point-in-time YTD replay, matured/pending/skipped scoring, diagnostics, and tuning recommendations |
| Model applicability governance | `model_health_metrics` for persisted replay-derived health facts and confidence labels, `model_applicability_profiles` for context-specific roles, confidence labels, and same-type ranking disables, `model_shadow_routes` for shadow-only router weights/metrics, `model_governance_reviews` for review-only monthly governance reports |
| Advice and preferences | `daily_advice`, `user_preferences` |
| AI analysis orchestration | `ai_analysis_records` |
| Experts | `experts` |
| Portfolios and expert activity | `virtual_portfolios`, `virtual_positions`, `virtual_transactions`, `virtual_cash_ledger`, `virtual_valuations`, `expert_plans`, `expert_plan_items`, `expert_scorecards`, `expert_reviews`, `expert_lessons` |
| Communication | `communication_recipients`, `communication_adapter_configs`, `outbound_messages` |
| Agent runtime | `agent_runs`, `agent_tool_calls` |
| Jarvis | `jarvis_daily_briefs` |
| Scheduler operations | `scheduler_jobs`, `scheduler_runs`, `scheduler_watermarks`, `provider_rate_limits` |
| Operations | `task_logs`, `data_quality_reports` |

## Test Map

| Concern | Tests |
| --- | --- |
| Persistence/schema | `tests/test_db.py` |
| Data ingestion/quality | `tests/test_akshare_ingestion.py`, `tests/test_data_quality.py`, `tests/test_macro.py`, `tests/test_capital_flow.py`, `tests/test_fund_holdings.py` |
| Quant and calibration | `tests/test_features.py`, `tests/test_market.py`, `tests/test_backtest.py`, `tests/test_calibration.py`, `tests/test_monitoring.py`, `tests/test_model_validation.py` |
| Advice | `tests/test_advice.py`, `tests/test_advice_scoring.py`, `tests/test_daily_workflow.py` |
| Portfolio | `tests/test_portfolio.py` |
| Expert scoring | `tests/test_expert_scoring.py` |
| Jarvis | `tests/test_jarvis.py` |
| MCP | `tests/test_mcp_tools.py`, `tests/test_mcp_server.py` |
| News evidence search | `tests/test_news_evidence.py`, `tests/test_mcp_tools.py`, `tests/test_mcp_server.py` |
| WebUI | `tests/test_web_app.py` |
| Experts | `tests/test_experts.py` |
| Communication | `tests/test_communication.py` |

## Productized Research Flow Tasks

| Task | Main Surfaces To Inspect First |
| --- | --- |
| `TASK-028` timeline | `web/app.py`, `workflows/daily.py`, `db.py`, `task_logs`, `daily_advice`, `market_snapshots`, `backtest_runs` |
| `TASK-029` categories | `web/app.py`, `assets`, `fund_info`, `features_daily`, `model_predictions`, `market_snapshots`, `macro_observations` |
| `TASK-030` fund filters | `web/app.py`, `fund_info`, `features_daily`, `user_preferences`, shared fund filter helpers, `tests/test_web_app.py` |
| `TASK-031` red/green semantics | `web/app.py` `market_percent`/`format_cell`/`format_stat`, CSS `.market-signal`, recommendation cards, tables, prediction/fund/advice views |
| `TASK-032` asset prediction cards | `web/app.py` `asset_prediction_view_models`/`asset_prediction_cards`, `model_predictions`, `assets`, prediction tests |
| `TASK-033` dashboard brief/run health | `web/app.py` `dashboard_daily_brief`/`dashboard_run_health`, `task_logs`, `daily_advice`, `market_snapshots`, `user_preferences`, `tests/test_web_app.py` |
| `TASK-035` technical table disclosure | `web/app.py` `collapsible`/`backtest_health_panel`/`advice_evidence_cards`/`active_preference_summary`/`log_failure_guidance`, `/data`, `/funds`, `/predictions`, `/backtests`, `/advice`, `/settings`, `/logs`, `tests/test_web_app.py` |
| `TASK-022` simulated portfolios | `portfolio/accounting.py`, `virtual_portfolios`, `virtual_positions`, `virtual_transactions`, `virtual_cash_ledger`, `virtual_valuations`, `cli.py portfolio`, `/portfolios`, `tests/test_portfolio.py`, `tests/test_web_app.py` |
| `TASK-023` target volatility allocation | `advice/allocation.py`, `advice/generator.py allocation_json.target_volatility`, `features_daily`, `user_preferences`, `/advice` target-volatility panel, `tests/test_advice.py`, `tests/test_web_app.py` |
| `TASK-060` correlation risk budget | `advice/allocation.py build_correlation_risk_budget_proposal`, `advice/generator.py allocation_json.risk_budget`, `/advice` risk-budget panel, `tests/test_advice.py`, `tests/test_web_app.py` |
| `TASK-024` model monitoring | `quant/monitoring.py`, `model_monitoring_reports`, `cli.py monitoring run`, `workflows/daily.py`, `/backtests` monitoring cards, `tests/test_monitoring.py`, `tests/test_daily_workflow.py`, `tests/test_web_app.py` |
| `TASK-025` Tushare provider expansion | `providers/tushare_provider.py`, `cli.py ingest --provider`, optional `.[tushare]` dependency extra, provider-neutral `assets`/`price_daily` source values, `tests/test_tushare_provider.py` |
| `TASK-026` fund peer benchmark scoring | `quant/benchmarks.py`, `quant/backtest.py`, `advice/scoring.py`, `advice_outcome_scores.benchmark_identity/source`, `backtest_results.details_json`, `tests/test_backtest.py`, `tests/test_advice_scoring.py`, `tests/test_db.py` |
| `TASK-027` polite ingestion | `providers/akshare_provider.py` `ProviderAccessPolicy`/request diagnostics, `data/ingestion.py` incremental history start, `cli.py ingest --provider-*`, `task_logs` JSON diagnostics, `data_quality_reports` incremental metadata, `tests/test_akshare_ingestion.py` |
| `TASK-036` expert roster | `experts/`, `db.py`, migrations, `cli.py`, `tests/test_experts.py`, `ARCHITECTURE.md` |
| `TASK-037` expert virtual portfolios | `portfolio/`, `experts/`, migrations, `db.py`, `tests/test_portfolio.py`, `tests/test_experts.py` |
| `TASK-038` expert daily execution | `experts/`, `portfolio/`, `cli.py`, `model_predictions`, `features_daily`, `market_snapshots`, `virtual_portfolios`, `expert_plans` |
| `TASK-039` expert scoring/lifecycle | `experts/scoring.py`, `portfolio/`, `expert_scorecards`, `expert_reviews`, `expert_lessons`, `tests/test_expert_scoring.py` |
| `TASK-040` expert WebUI | `web/app.py`, `/experts`, expert/portfolio query helpers, `tests/test_web_app.py` |
| `TASK-041` expert MCP/agent workflow | `mcp/tools.py`, `mcp/server.py`, `cli.py`, expert services, `task_logs`, MCP tests |
| `TASK-042` communication architecture | `communication/service.py`, `db.py` communication helpers, `communication_recipients`, `communication_adapter_configs`, `outbound_messages`, `cli.py communication`, `tests/test_communication.py`, `ARCHITECTURE.md` |
| `TASK-043` iMessage adapter | `communication/imessage.py`, `communication/service.py` default adapter resolution, `cli.py communication verify-setup/send-test --real-send`, macOS setup checks, AppleScript command construction, `tests/test_communication.py` |
| `TASK-044` mobile templates | `communication/templates.py`, `workflows/daily.py` optional notifications, `experts/planning.py`, `experts/scoring.py`, daily brief/run health/expert summaries, idempotency keys, communication tests |
| `TASK-045` communication WebUI/CLI | `web/app.py`, `/communication`, `cli.py communication list-adapters`, communication query helpers, masked recipient display, dry-run test send, `tests/test_web_app.py`, `tests/test_communication.py` |
| `TASK-046` inbound command design | `SPEC-008`, `decisions/ADR-006-safe-inbound-phone-commands.md`, `ARCHITECTURE.md` communication safety notes; no inbound execution code |
| `TASK-047` Jarvis persistence | `jarvis/`, `db.py`, migrations, `tests/test_jarvis.py`, `ARCHITECTURE.md` |
| `TASK-048` Jarvis synthesis | `jarvis/synthesis.py`, `jarvis/persistence.py`, `cli.py`, `workflows/daily.py`, `market_snapshots`, `capital_flow_observations`, `model_predictions`, `backtest_runs`, `experts`, `expert_plans`, `expert_scorecards`, `virtual_valuations`, `user_preferences`, `advice/generator.py` compliance helpers |
| `TASK-049` Jarvis WebUI | `web/app.py`, `/jarvis`, Jarvis query helpers, `tests/test_web_app.py` |
| `TASK-050` Jarvis MCP/Agent workflow | `mcp/tools.py`, `mcp/server.py`, `jarvis/synthesis.py`, `task_logs`, `tests/test_mcp_tools.py`, `tests/test_mcp_server.py` |
| `TASK-051` Jarvis phone summary | `communication/config.py`, `communication/templates.py`, `jarvis/synthesis.py`, `agent_runtime/execution.py`, `cli.py jarvis generate`, environment notification defaults, communication service, `tests/test_communication.py`, `tests/test_jarvis.py`, `tests/test_agent_runtime.py` |
| `TASK-052` AI analysis orchestration | `experts/`, `jarvis/`, `workflows/daily.py`, `mcp/tools.py`, expert/Jarvis analysis records, `tests/test_experts.py`, `tests/test_jarvis.py` |
| `TASK-053` market/macro WebUI | `web/app.py`, `/market`, `market_snapshots`, `macro_observations`, category drill-in link, `tests/test_web_app.py` |
| `TASK-054` industry/theme classification | `data/classification.py`, `web/app.py` theme labels/filtering on category/data/fund/prediction/market views, `tests/test_classification.py`, `tests/test_web_app.py` |
| `TASK-055` theme allocation overview | `web/app.py`, `/themes`, theme aggregation helpers, `tests/test_web_app.py` |
| `TASK-056` capital-flow observations | `data/capital_flow.py`, `providers/akshare_provider.py`, `db.py`, `capital_flow_observations`, `cli.py ingest capital-flow`, `/market`, `tests/test_capital_flow.py`, `tests/test_web_app.py` |
| `TASK-057` capital-flow evidence synthesis | `advice/generator.py`, `jarvis/synthesis.py`, `ai_analysis.py`, `/advice`, `/jarvis`, `capital_flow_observations`, `tests/test_advice.py`, `tests/test_jarvis.py`, `tests/test_web_app.py` |
| `TASK-058` fund holdings | `data/fund_holdings.py`, `providers/akshare_provider.py`, `db.py`, `fund_holdings`, `cli.py ingest fund-holdings`, `/funds`, `tests/test_fund_holdings.py`, `tests/test_web_app.py` |
| `TASK-059` fund holding look-through | `db.py latest_fund_holdings`, `web/app.py fund_holding_theme_exposure`, `/funds`, `tests/test_web_app.py` |
| `TASK-061` AI provider adapter contract | `ai_analysis.py`, new `ai_providers/`, `cli.py`, `db.py` task logs, `tests/test_ai_providers.py`, `tests/test_jarvis.py`, `tests/test_experts.py`, `ARCHITECTURE.md`, `CODE_INDEX.md` |
| `TASK-062` AI prompt/evidence schema freeze | `ai_analysis.py` prompt/schema constants and request builders, expert/Jarvis evidence packets, unsupported prediction/news validation, `tests/test_ai_providers.py`, `tests/test_experts.py`, `tests/test_jarvis.py`, `SPEC-009` |
| `TASK-063` provider-backed AI orchestration | `experts/planning.py`, `jarvis/synthesis.py`, `mcp/tools.py`, `ai_analysis.py`, `ai_providers/`, task logs, provider/fallback status in MCP, `tests/test_experts.py`, `tests/test_jarvis.py`, `tests/test_mcp_tools.py`, `tests/test_daily_workflow.py` |
| `TASK-064` Jarvis confidence gates | `jarvis/synthesis.py` confidence gates, `/jarvis` view helpers in `web/app.py`, phone summary model text in `communication/templates.py`, MCP brief evidence/status, `tests/test_jarvis.py`, `tests/test_web_app.py`, `tests/test_communication.py`, `tests/test_mcp_tools.py` |
| `TASK-065` architecture/code index synchronization | `ARCHITECTURE.md`, `CODE_INDEX.md`, `INDEX.md`, `STATUS.md`, related specs/tasks; no product feature code unless needed to expose provider/fallback status already produced by prior tasks |
| `TASK-066` Jarvis five-entry navigation | `web/app.py` navigation/sidebar helpers, route labels, default route, `tests/test_web_app.py`, `SPEC-006`, `CODE_INDEX.md` |
| `TASK-067` Today brief consolidation | `web/app.py` Jarvis/dashboard/advice/timeline helpers, `/` or `/jarvis`, `tests/test_web_app.py`, `tests/test_jarvis.py` |
| `TASK-068` Opportunity pool consolidation | `web/app.py` category/theme/fund/data/prediction helpers, new or repurposed opportunity route, `tests/test_web_app.py` |
| `TASK-069` Evidence/settings consolidation | `web/app.py` prediction/backtest/market/settings/log/communication helpers, `tests/test_web_app.py`, `tests/test_communication.py` |
| `TASK-070` Consumer IA acceptance/docs | `ARCHITECTURE.md`, `CODE_INDEX.md`, `INDEX.md`, `STATUS.md`, `SPEC-006`, WebUI smoke checks, `tests/test_web_app.py` |
| `TASK-071` news persistence/ingestion | `data/news.py`, `providers/tushare_provider.py`, `db.py`, `migrations/001_init.sql`, `cli.py ingest news`, `task_logs`, `tests/test_news_evidence.py`, `tests/test_db.py` |
| `TASK-072` news indexing/linking/features | `data/news.py`, `data/classification.py`, `db.py`, `news_item_links`, `news_item_tags`, optional `news_feature_daily`, `tests/test_news_evidence.py` |
| `TASK-073` news search/MCP | `data/news.py search_news_evidence`, `mcp/tools.py`, `mcp/server.py`, `/evidence` if needed, `tests/test_news_evidence.py`, `tests/test_mcp_tools.py`, `tests/test_mcp_server.py`, `tests/test_web_app.py` |
| `TASK-074` prediction target redesign | `db.py`, migrations, `quant/reliability.py`, `quant/backtest.py`, `web/app.py`, `mcp/tools.py`, sidecar `model_prediction_reliability`, rank/risk-adjusted evidence, `tests/test_db.py`, `tests/test_backtest.py`, `tests/test_web_app.py`, `tests/test_mcp_tools.py` |
| `TASK-075` financial validation upgrade | `quant/backtest.py`, `quant/monitoring.py`, `cli.py`, `mcp/server.py`, `mcp/tools.py`, `web/app.py`, IC/Rank IC/bucket spread/same-category/asset-type/probability calibration metrics, embargo policy, validation warnings, `tests/test_backtest.py`, `tests/test_monitoring.py`, `tests/test_web_app.py`, `tests/test_mcp_tools.py` |
| `TASK-076` candidate model pool | `quant/forecast.py`, `quant/backtest.py`, `quant/calibration.py`, `cli.py`, `mcp/tools.py`, `mcp/server.py`, candidate model versions, comparison reports, `model_prediction_reliability`, `tests/test_backtest.py`, `tests/test_calibration.py`, `tests/test_daily_workflow.py`, `tests/test_mcp_tools.py` |
| `TASK-077` model evidence packet/expert review | `ai_analysis.py build_model_evidence_packet`, `experts/planning.py` reliability-aware candidate loading/action gates, `jarvis/synthesis.py` shared top-forecast packets/confidence gates, `tests/test_experts.py`, `tests/test_jarvis.py`, `tests/test_ai_providers.py` |
| `TASK-078` Jarvis model risk gates | `jarvis/synthesis.py` model-risk-officer confidence gates and summaries, `communication/templates.py` phone risk reason text, `mcp/tools.py` `model_risk_gates` wrappers, `web/app.py` Jarvis model-risk columns, `tests/test_jarvis.py`, `tests/test_communication.py`, `tests/test_mcp_tools.py`, `tests/test_web_app.py` |
| `TASK-079` model promotion governance | `quant/calibration.py` promotion-gate governance, `quant/monitoring.py` persisted model-state summaries, `web/app.py` governance state cards, `mcp/tools.py` market snapshot `model_governance`, `tests/test_monitoring.py`, `tests/test_calibration.py`, `tests/test_web_app.py`, `tests/test_mcp_tools.py` |
| `TASK-080` Codex runtime access | `agent_runtime/`, launch request/result/status dataclasses, runtime adapter boundary, fake adapter, `db.py`, migrations, `cli.py`, `agent_runs`, `agent_tool_calls`, runtime metadata, `tests/test_agent_runtime.py`, `ARCHITECTURE.md`, `CODE_INDEX.md` |
| `TASK-081` role-scoped tool manifests | `agent_runtime/` Codex CLI adapter/artifact layout/manifests/tool-call validation, `mcp/tools.py`, `mcp/server.py`, role skill bundles, submission/validation envelope tools, tool-call audit, `tests/test_agent_runtime.py`, `tests/test_mcp_tools.py`, `tests/test_mcp_server.py` |
| `TASK-082` domain skills and expert overview | `repo/skills/investment-*-skill/SKILL.md`, `repo/skills/investment-expert-agent/SKILL.md`, `agent_runtime/prompts.py`, expert/Jarvis prompt rendering, output contracts, `tests/test_agent_runtime.py`, `tests/test_experts.py` |
| `TASK-083` expert daily agent execution | `agent_runtime/execution.py`, `experts/planning.py`, `mcp/tools.py`, `cli.py`, expert T-day Codex run status, artifact clearing, plan/action submission, `tests/test_agent_runtime.py`, `tests/test_experts.py` |
| `TASK-084` Jarvis T+1 agent workflow | `repo/skills/jarvis-daily-agent/SKILL.md`, `repo/skills/investment-jarvis-synthesis-skill/SKILL.md`, `agent_runtime/execution.py`, `jarvis/synthesis.py`, `mcp/tools.py`, `cli.py`, readiness gates, brief persistence links, `tests/test_agent_runtime.py`, `tests/test_jarvis.py` |
| `TASK-085` remove Codex automation | Codex app automation inventory/deletion, `SPEC-013`, `ADR-009`, `PROJECT.md`, `AGENTS.md`, `ROADMAP.md`, `STATUS.md`; no product code unless needed to prove the old automation is out of the operational path |
| `TASK-086` scheduler persistence/CLI | `scheduler/`, `db.py`, migrations, `cli.py scheduler ...`, fixed sync timing, `scheduler_jobs`, `scheduler_runs`, `scheduler_watermarks`, `provider_rate_limits`, `task_logs`, `tests/test_scheduler.py`, `tests/test_db.py` |
| `TASK-087` incremental watermarks | `scheduler/service.py`, bounded news windows, market-context subject planning, per-asset price/NAV freshness, feature affected ranges, dry-run summaries, no-full-history tests |
| `TASK-088` provider rate limits/backoff | `scheduler/registry.py`, `scheduler/service.py`, provider policy config, `provider_rate_limits`, deferred scheduler runs, task logs, rate-limit/backoff tests |
| `TASK-089` hourly orchestration/health | `scheduler/`, `web/app.py`, `mcp/tools.py`, `cli.py scheduler status`, post-close and T/T+1 readiness gates, scheduler-health tests |
| `TASK-090` YTD forecast replay corpus | `quant/model_validation.py`, `db.py`, migrations, `cli.py model-validation replay-ytd`, `price_daily`, replay tables, `tests/test_model_validation.py` |
| `TASK-091` replay scoring diagnostics | `quant/model_validation.py`, `quant/backtest.py` scoring helpers, benchmark selection, replay metrics JSON, `tests/test_model_validation.py`, `tests/test_backtest.py` |
| `TASK-092` model tuning recommendations | `quant/model_validation.py`, calibration/governance helpers, tuning recommendation schema, CLI report output, model-only scope checks, `tests/test_model_validation.py` |
| `TASK-093` model health facts | `quant/model_validation.py`, `db.py`, migrations, `cli.py model-validation health-generate/health-report`, `model_health_metrics`, monthly/all-history health metrics, no-product-table-read tests |
| `TASK-094` applicability profiles | `quant/model_validation.py`, `db.py`, migrations, `cli.py model-validation applicability-generate/applicability-report`, `model_applicability_profiles`, same-type ranking disable rules, no-production-prediction tests |
| `TASK-095` 20-day shadow router | `quant/model_validation.py`, `db.py`, migrations, `cli.py model-validation shadow-router-run/shadow-router-report`, `model_shadow_routes`, walk-forward monthly weights, no operational prediction overwrite tests |
| `TASK-096` confidence labels | `quant/model_validation.py`, `db.py`, migrations, `cli.py model-validation confidence-labels-generate/confidence-labels-report`, health/profile confidence labels, conservative gate tests |
| `TASK-097` monthly governance summary | `quant/model_validation.py`, `db.py`, migrations, `cli.py model-validation governance-generate/governance-report`, `model_governance_reviews`, model-health/profile/shadow/confidence evidence, review-only guardrail tests |

## Development Guardrails

- Check this index and `ARCHITECTURE.md` before adding a new file or helper.
- For WebUI navigation work, preserve direct technical routes for agents and
  saved links, but expose only the five consumer entries in primary navigation.
- Every WebUI change must declare ownership under 今日简报, 机会池, 专家团, 证据,
  or 设置 before implementation.
- Do not create a new first-level WebUI route, sidebar item, dashboard module
  family, or landing page unless a product-review task and ADR update
  `ADR-007`.
- Keep technical labels and raw data surfaces secondary: predictions,
  backtests, timeline, market/data details, logs, provider payloads, and JSON
  belong under 机会池, 证据, 设置, or direct technical links.
- For news work, build retrieval first: persist/index news, expose bounded
  search tools, and let Codex AI call `search_news_evidence` on demand. Do not
  inject all news into fixed prompts.
- For model reliability work, do not jump to tree/deep models first. Add
  ranking targets and validation before candidate models, keep candidates
  contextual until promotion gates pass, and make Jarvis more selective rather
  than more aggressive.
- For model replay/tuning work, follow `SPEC-014`: replay current-year daily
  predictions from stored local data only, score only matured horizons, keep
  immature rows pending, persist replay evidence separately from operational
  `model_predictions`, and produce model accuracy/confidence tuning
  recommendations before changing any model default. Do not include expert
  committee predictions, Jarvis conclusions, investment advice, MCP/WebUI
  surfaces, or portfolio outcomes in this phase.
- For model applicability/shadow-routing work, follow `SPEC-015` and
  `ADR-010`: derive context-specific model roles from health metrics, run
  `router_floor70_cap05` as 20-day shadow-only evidence, disable same-type
  ranking when same-type Rank IC or bucket spread is non-positive, downgrade
  raw confidence into evidence-quality labels, and keep operational
  `model_predictions` unchanged.
- For the AI interaction layer, inspect `ai_analysis.py`, `jarvis/synthesis.py`,
  `experts/planning.py`, and the existing `ai_providers/` boundary before
  adding code. Do not create a second AI pipeline or call model SDKs from
  feature modules.
- For Codex agent runtime work, treat scheduling as system-owned. Implement
  role-scoped expert/Jarvis runs through `agent_runtime`, MCP/API tool
  manifests, project skills, prompt templates, output submission APIs, and
  audit records. Do not let Codex write SQLite directly, scrape WebUI, mutate
  state through shell commands, or run Jarvis before T expert outcomes are
  complete or explicitly skipped/failed.
- For local scheduled operations, use `scheduler install-cron` to install one
  system-owned macOS LaunchAgent. Do not create separate Codex app automations
  or separate expert/Jarvis cron jobs. Jarvis notifications should flow through
  the communication adapter layer and default environment variables, not direct
  iMessage calls.
- For scheduler work, follow `SPEC-013` and `ADR-009`: use the system scheduler,
  not Codex app automation; run two-hour market/news updates as incremental
  watermark-based jobs; cap request windows; skip current scopes; persist
  provider backoff/deferred states; and never schedule full-history refresh.
- Prefer shared formatting/view-model helpers in `web/app.py` over repeating
  presentation logic per route.
- Keep SQL ownership close to existing persistence or route query patterns; do
  not introduce ad hoc duplicate queries when a helper already exists.
- Add or update tests in the mapped test file for every product behavior change.
- Stop after the current task's acceptance criteria pass. New data providers,
  optimization engines, experts, inbound phone commands, and large UI redesigns
  require a new roadmap update before implementation.
