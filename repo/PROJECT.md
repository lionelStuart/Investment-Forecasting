# Project

## Summary

Investment Forecasting is now productized as Jarvis, an AI intelligent
investment assistant. Its foundation is a reliable, reproducible, auditable local system
that collects market and fund data, stores raw and derived data in SQLite,
computes quantitative indicators, runs forecasts and backtests, operates a
virtual expert committee, exposes structured MCP tools to AI agents, generates
daily risk-aware advice, and shows results through a Jarvis-first consumer
product UI.

Jarvis is the final user-facing assistant. It synthesizes system-level market
information, prediction model output, and expert-system virtual investing
results into a simple daily wealth-management brief.

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
- Run system-owned scheduled workflows that update data, evaluate the market,
  generate forecasts, record scores, invoke role-scoped Codex agent runtime
  tasks when needed, and write daily advice or Jarvis briefs.
- Run hourly system-owned incremental update jobs for market/news freshness.
  Scheduled jobs must use watermarks, bounded windows, provider request caps,
  and backoff instead of repeated full-history ingestion.
- Provide a Jarvis-first WebUI organized around the user's daily decision
  journey, with five primary entries: 今日简报, 机会池, 专家团, 证据, 设置.
- Use historical data windows for forecast calibration and model improvement.
- Run a virtual expert committee where distinct expert styles create simulated
  investment plans, manage virtual capital, are scored over time, and can be
  retired or replaced based on evidence.
- Connect the local Mac workbench to the user's phone through safe,
  adapter-based communication, starting with iMessage notifications.
- Build Jarvis as the top-level assistant that combines market information,
  model predictions, expert plans, expert scores, and expert current returns
  into a simple daily recommendation.
- Add a bounded AI interaction layer for expert independent analysis and
  Jarvis daily financial analysis, using provider adapters, structured evidence
  packets, validation gates, deterministic fallback, and auditable source
  metadata.
- Add a searchable news evidence layer so Codex AI and Jarvis can retrieve
  relevant news by source, time window, asset, theme, event type, sentiment,
  and keyword when needed, without injecting bulk news into fixed prompts.
- Upgrade model reliability by emphasizing cross-sectional rank, calibrated
  probability, risk-adjusted score, validation quality, and promotion gates
  over raw point-return forecasts.
- Validate model algorithms through reproducible current-year replay audits:
  regenerate daily predictions from stored local history, score only matured
  outcomes, and use accuracy/confidence diagnostics to define tuning
  experiments before model defaults change.
- Introduce a system-scheduled Codex agent runtime access layer: the system
  owns triggers, audit, validation, persistence, and UI, while Codex runs
  expert and Jarvis role tasks through injected project skills, role prompts,
  role-scoped MCP/API tools, and structured output contracts.
- Make each expert committee member agentic: on T day, each active expert uses
  its own style, mandate, virtual portfolio, model evidence, news retrieval
  when needed, and allowed system tools to submit one virtual investment action
  or an explicit skipped/failed outcome.
- Make Jarvis agentic at T+1: after T expert actions are complete or explicitly
  skipped/failed, Jarvis uses the same system capabilities plus expert outputs,
  scores, current returns, and task health to produce the daily investment
  brief.

## Non-Goals

- Do not build a high-frequency trading system.
- Do not guarantee returns or produce deterministic investment conclusions.
- Do not start with a complex live trading or brokerage integration.
- Do not treat virtual expert plans as real-money execution instructions.
- Do not let phone communication trigger real-money trades or bypass local
  audit, allowlist, and safety controls.
- Do not optimize for a marketing landing page or a developer workbench. The
  WebUI is a consumer-facing Jarvis assistant with technical evidence available
  as secondary drill-down.
- Do not add first-level WebUI navigation entries beyond 今日简报, 机会池, 专家团,
  证据, 设置 without a new product-review task and ADR.
- Do not add advanced ML models before simple reproducible baselines and
  backtests exist.
- Do not frame model optimization as guaranteed accuracy improvement or return
  improvement. The product goal is reliability, selectivity, and better
  uncertainty handling.
- Do not expand the next phase beyond the AI interaction layer closure:
  no new data providers, optimizer engines, experts, live trading, inbound
  phone commands, or broad UI redesign before `TASK-061` through `TASK-065`
  are product-reviewed.
- Do not treat Codex as the scheduler. Scheduling belongs to this system;
  Codex is only a role-scoped runtime invoked by the system.
- Do not use Codex app automation for data/news refresh. The old
  `investment-forecasting-daily-run` automation is removed from the operational
  path and replaced by `SPEC-013` system scheduling.
- Do not schedule full-history ingestion. Full refreshes must be explicit
  manual operations with provider-safety review.
- Do not treat `ai_providers` provider calls as the final agentic expert or
  Jarvis architecture. Provider calls can remain fallback or simple analysis,
  but expert/Jarvis product reasoning must go through the Codex runtime access
  layer once `SPEC-012` is implemented.
- Do not allow Codex agents to write SQLite directly, scrape WebUI pages for
  evidence, call shell commands to mutate product state, or bypass MCP/API
  validation and audit.
- Do not run Jarvis T+1 daily analysis before T expert actions are completed
  or explicitly skipped/failed.

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
- Model tuning must be evidence-led. Replaying and scoring historical
  predictions comes before parameter changes, model promotion, or stronger
  confidence language.
- Time-series evaluation must avoid future leakage and random sample splitting.
- All scheduled jobs must be idempotent where practical and must write logs.
- Data updates must support retry, validation, and recoverable failure handling.
- Scheduled data/news updates must be incremental by watermark. Hourly jobs
  must cap request windows, skip already-current assets/scopes, and honor
  provider backoff.
- SQLite is the MVP persistence layer; PostgreSQL or DuckDB can be considered
  later through an ADR.
- AKShare is the MVP primary data source; Tushare Pro and macro providers are
  later enhancements unless a task explicitly introduces them.
- Jarvis is the product protagonist. User-facing pages, copy, route grouping,
  and navigation must reinforce the assistant experience, not expose internal
  implementation modules as the default mental model.
- The WebUI primary navigation is capped at five entries: 今日简报, 机会池, 专家团,
  证据, 设置. Legacy technical routes can remain for direct links, agents, and
  evidence drill-down, but they must not appear as first-level consumer
  navigation.
- New UI work must answer which of the five entries owns the experience before
  adding or changing routes.

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
- `Expert`: A persisted virtual investment persona with style, model/data
  focus, risk limits, lifecycle state, and an auditable simulated portfolio.
- `Expert Plan`: A daily expert decision to buy, sell, rebalance, hold, or stay
  in cash, backed by stored evidence and risk checks.
- `Expert Scorecard`: A rolling evaluation of an expert's virtual return,
  drawdown, benchmark excess, evidence quality, and mandate adherence.
- `Communication Adapter`: A channel implementation that delivers controlled
  research notifications, starting with local iMessage on macOS.
- `Outbound Message`: An auditable send attempt with channel, recipient,
  rendered summary, status, idempotency key, timestamps, and errors.
- `Jarvis`: The final AI investment assistant that synthesizes market state,
  model forecasts, expert plans, expert scores, expert returns, and user risk
  context into a simple daily brief.
- `Jarvis Daily Brief`: A persisted daily output with focus directions,
  one-line stance, model summary, expert summaries, combined recommendation,
  risk warnings, and evidence links.
- `Jarvis Consumer IA`: The mandatory five-entry product structure: 今日简报,
  机会池, 专家团, 证据, 设置.
- `AI Provider Adapter`: The only boundary allowed to call external LLM/model
  APIs for expert and Jarvis analysis. It must return structured output or
  fall back to deterministic analysis.
- `Codex Runtime Access Layer`: A system-owned boundary that starts
  role-scoped Codex agent runs with project skills, generated prompts, allowed
  MCP/API tools, output schemas, audit records, and validation.
- `Codex Agent Runtime Protocol`: The `codex_agent_runtime_v1` interaction
  contract used by the system to prepare, start, poll, cancel, and collect
  role-scoped Codex runs. It carries role metadata, dates, overview skill,
  skill bundle, prompt/tool manifest refs, output contract, and runtime policy.
- `Domain/Function Skill`: A bounded Codex skill describing one system
  capability area, such as market data, model evidence, news evidence, asset
  research, expert portfolio, virtual action, Jarvis synthesis, or output
  contract.
- `Role Overview Skill`: The Codex entry skill for a role. Expert and Jarvis
  overview skills compose different allowed domain/function skills and bind
  them to role prompts, tool manifests, output schemas, and stop conditions.
- `Agent Run`: A persisted expert or Jarvis runtime attempt with role, run
  date, target evidence date, status, runtime metadata, tool-call audit, output
  links, and error/fallback reason.
- `System Scheduler`: The product-owned scheduler that runs hourly and
  time-windowed update jobs, records scheduler runs and watermarks, and invokes
  downstream expert/Jarvis jobs only when readiness gates pass.
- `Scheduler Watermark`: A persisted cursor/date/datetime used by scheduled
  jobs to fetch only missing or stale increments.
- `Provider Backoff`: A persisted provider safety state that defers scheduled
  jobs after throttling, repeated empty suspicious responses, network failures,
  or request-budget exhaustion.
- `Expert Agent`: One active expert committee member executed through Codex
  runtime on T day using that expert's mandate, style, portfolio, model
  evidence, news retrieval when needed, and allowed submission tools.
- `Jarvis Agent`: The T+1 Codex runtime role that synthesizes system evidence
  and completed T expert outcomes into the consumer-facing Jarvis daily brief.
- `News Evidence`: Provider-neutral financial news records plus source/time,
  asset/theme, event, sentiment, and feature indexes exposed through bounded
  search tools for AI retrieval.
- `Model Reliability`: The model layer's ability to rank evidence, validate
  signal quality, identify degraded/weak/stale signals, and explain why Jarvis
  should stay watch-only.
- `Forecast Replay`: A separate historical audit corpus that simulates what a
  configured model would have predicted on past dates using only information
  available at each prediction date. Replay evidence does not overwrite
  operational `model_predictions`.
- `MCP Tool`: A structured callable interface used by AI agents to retrieve data
  or run system capabilities.

## Default Commands

- `dev`: `python3 -m pip install -e '.[dev]'`
- `db:init`: `investment-forecasting db init --db data/investment_forecasting.sqlite3`
- `ingest:mvp`: `investment-forecasting ingest mvp --db data/investment_forecasting.sqlite3 --start-date YYYYMMDD --end-date YYYYMMDD`
- `ingest:capital-flow`: `investment-forecasting ingest capital-flow --db data/investment_forecasting.sqlite3 --scope stock --asset-codes 600519 --max-days 20`
- `ingest:fund-holdings`: `investment-forecasting ingest fund-holdings --db data/investment_forecasting.sqlite3 --fund-codes 000001 --year 2024`
- `features:calculate`: `investment-forecasting features calculate --db data/investment_forecasting.sqlite3 --start-date YYYYMMDD --end-date YYYYMMDD`
- `market:snapshot`: `investment-forecasting market snapshot --db data/investment_forecasting.sqlite3 --date YYYYMMDD`
- `forecast:run`: `investment-forecasting forecast run --db data/investment_forecasting.sqlite3 --horizons 5,20,60`
- `backtest:run`: `investment-forecasting backtest run --db data/investment_forecasting.sqlite3 --horizons 5,20,60 --lookback-days 60`
- `monitoring:run`: `investment-forecasting monitoring run --db data/investment_forecasting.sqlite3 --date YYYYMMDD`
- `advice:generate`: `investment-forecasting advice generate --db data/investment_forecasting.sqlite3 --date YYYYMMDD`
- `advice:score-outcomes`: `investment-forecasting advice score-outcomes --db data/investment_forecasting.sqlite3 --horizon-days 20`
- `ai:provider-check`: `investment-forecasting ai provider-check`
- `agent:runs`: `investment-forecasting agent-runs list --db data/investment_forecasting.sqlite3`
  to inspect system-owned Codex expert/Jarvis runtime audit records.
- `scheduler:status`: Planned by `TASK-086`; inspect system scheduler jobs,
  watermarks, latest runs, and provider backoff.
- `agent:codex-readiness`: `investment-forecasting agent-runs codex-readiness --db data/investment_forecasting.sqlite3 --project-root /Users/wonderwall/project/Investment-Forecasting`
  to verify the local Codex CLI binary and login state before runtime use.
- `agent:codex-smoke`: `investment-forecasting agent-runs codex-smoke --db data/investment_forecasting.sqlite3 --project-root /Users/wonderwall/project/Investment-Forecasting --timeout-seconds 180`
  to run a real local Codex CLI artifact-mode smoke test.
- `portfolio:create`: `investment-forecasting portfolio create --db data/investment_forecasting.sqlite3 --name NAME --initial-capital 100000`
- `portfolio:trade`: `investment-forecasting portfolio trade --db data/investment_forecasting.sqlite3 --portfolio-id ID --date YYYY-MM-DD --side buy --asset-id ASSET_ID --quantity QTY`
- `portfolio:value`: `investment-forecasting portfolio value --db data/investment_forecasting.sqlite3 --portfolio-id ID --date YYYY-MM-DD`
- `communication:configure-adapter`: `investment-forecasting communication configure-adapter --db data/investment_forecasting.sqlite3 --channel imessage --enabled`
- `communication:list-adapters`: `investment-forecasting communication list-adapters --db data/investment_forecasting.sqlite3`
- `communication:upsert-recipient`: `investment-forecasting communication upsert-recipient --db data/investment_forecasting.sqlite3 --recipient-key owner_phone --display-name NAME --address ADDRESS --allowlisted`
- `communication:verify-setup`: `investment-forecasting communication verify-setup --db data/investment_forecasting.sqlite3 --recipient-key owner_phone`
- `communication:send-test`: `investment-forecasting communication send-test --db data/investment_forecasting.sqlite3 --recipient-key owner_phone`
- `mcp:list-tools`: `investment-forecasting mcp list-tools`
- `mcp:call`: `investment-forecasting mcp call TOOL_NAME --db data/investment_forecasting.sqlite3 --args '{}'`
- `mcp:serve`: `investment-forecasting-mcp --db data/investment_forecasting.sqlite3`
- `daily:run`: `investment-forecasting daily run --db data/investment_forecasting.sqlite3 --date YYYYMMDD --horizons 5,20,60 --lookback-days 60`; defaults to `INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY` for phone notification when set.
- `daily:run-notify`: `investment-forecasting daily run --db data/investment_forecasting.sqlite3 --date YYYYMMDD --notify-recipient-key owner_phone --notification-dry-run`
- `jarvis:generate`: `investment-forecasting jarvis generate --db data/investment_forecasting.sqlite3 --date YYYYMMDD`; when `INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY` is set, the Jarvis phone summary is sent through the audited communication path after the brief is persisted.
- `jarvis:generate-notify`: `investment-forecasting jarvis generate --db data/investment_forecasting.sqlite3 --date YYYYMMDD --notify-recipient-key owner_phone --notification-dry-run`
- `web:run`: `investment-forecasting web run --db data/investment_forecasting.sqlite3 --host 127.0.0.1 --port 8765`
- `calibration:run`: `investment-forecasting calibration run --db data/investment_forecasting.sqlite3 --date YYYYMMDD --horizons 5,20,60 --lookback-days 60`
- `model-validation:replay-ytd`: Planned by `TASK-090`;
  `investment-forecasting model-validation replay-ytd --db data/investment_forecasting.sqlite3 --year 2026 --horizons 5,20,60`
- `model-validation:report`: Planned by `TASK-091`;
  `investment-forecasting model-validation report --db data/investment_forecasting.sqlite3 --run-id latest`
- `model-validation:tuning-plan`: Planned by `TASK-092`;
  `investment-forecasting model-validation tuning-plan --db data/investment_forecasting.sqlite3 --run-id latest`
- `test`: `python3 -m pytest`
- `build`: Not defined. The MVP WebUI is a local server-rendered workbench.
