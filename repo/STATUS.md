# Status

## Current Focus

- Active phase is `M17 Model Applicability And Shadow Routing Governance`
  (`SPEC-015`, `ADR-010`, `TASK-093` through `TASK-097`). Data
  expert replay research and CEO review both reject "best model wins" as the
  next optimization strategy. This phase builds a durable model-layer
  governance loop: model-health facts, applicability roles,
  same-type ranking disable rules, 20-day shadow routing, confidence labels,
  and monthly governance summaries.

- CEO-approved boundaries for M17: keep production defaults unchanged; run
  `router_floor70_cap05` only as 20-day shadow evidence; do not use 20-day
  router output for same-type asset ranking; do not let shadow output affect
  expert actions, Jarvis stance, investment advice, phone summaries, or
  operational `model_predictions`; do not introduce black-box models.

- `TASK-093` through `TASK-097` are complete. The system now persists
  context-specific health metrics, derives applicability profiles, runs the
  conservative 20-day shadow router, applies confidence labels, and writes a
  monthly governance review without changing operational predictions or
  Jarvis/expert/advice behavior. Local replay run `1` has 1,512 persisted
  health rows and 1,512 applicability profiles: 8 `primary_forecast`, 2
  `allocation_bias`, 53 `ranking_signal`, 46 `risk_reference`, 1,403
  `observation_only`, and 1,125 same-type ranking disables. It also has 4
  monthly `router_floor70_cap05` shadow-only route rows for 2026-01 through
  2026-04 with baseline weight floor 70%, monthly turnover cap 5%, and
  same-type ranking disabled. The confidence label pass produced 1,508
  `暂不强调`, 4 `谨慎观察`, and 0 `相对稳健` labels, so no strong confidence
  language is supported by the current replay evidence. The `2026-05`
  governance review is `review_only`, has no promotion-review eligible model,
  and records `production_defaults_changed=0`.

- `M16 YTD Model Accuracy And Confidence Replay Audit` (`SPEC-014`,
  `TASK-090` through `TASK-092`) has been implemented for the 2026 local
  corpus. The system now has `model-validation replay-ytd`, `report`, and
  `tuning-plan` commands, persisted `model_replay_runs` /
  `model_replay_predictions`, and deterministic replay diagnostics that stay
  separate from operational `model_predictions`.

- Local replay run on 2026-05-25: run id `1`, `2026-01-01` through
  `2026-05-22`, all assets, horizons `5,20,60`, models
  `baseline_mean_v1`, `momentum_reversal_v1`, and
  `risk_adjusted_factor_v1`. It wrote 374,922 replay rows: 255,201 matured,
  119,487 pending, and 234 skipped. No provider/network calls were used.

- Replay findings: `baseline_mean_v1` 5-day validated with 0.556 direction
  accuracy and positive Rank IC/bucket spread; `baseline_mean_v1` 20-day is
  degraded due negative Rank IC and bucket spread; 60-day baseline and
  risk-adjusted variants rank better but have larger return errors. The tuning
  plan currently recommends rank gates, alpha-amplitude reduction where bucket
  spread is negative, probability calibration, and confidence cooling before
  any model default changes.

- Previous development phase was `M15 System Scheduler And Incremental Updates`
  (`SPEC-013`, `ADR-009`, `TASK-085` through `TASK-089`). The old Codex app
  automation `investment-forecasting-daily-run` was deleted on 2026-05-24 and
  must not be recreated for market/news refresh. The system itself must own
  hourly incremental updates for market data and news evidence, using
  persisted watermarks, bounded windows, provider request budgets, and backoff
  to avoid accidental full refreshes or provider blocking.

- `TASK-085` through `TASK-089` are complete. The scheduler now has persisted
  job definitions, run records, watermarks, provider backoff state, CLI
  commands, incremental job handlers, provider request-budget/backoff
  enforcement, and CLI/WebUI/MCP health surfaces. Hourly news/market jobs,
  post-close price/features/model gates, and disabled/gated expert/Jarvis
  definitions are observable through scheduler status without Codex app
  automation.

- Follow-up operational fix on 2026-05-26: scheduling is now centralized under
  one project-owned cron registration command. `scheduler install-cron`
  installs `local.investment-forecasting.scheduler`, which wakes
  `scheduler run-due` every 5 minutes. The scheduler owns all business cadence:
  market and news incremental jobs every 2 hours, expert T-day Codex runs at
  20:00 Monday-Friday, and Jarvis T+1 daily brief plus default `owner_phone`
  communication-adapter notification at 08:00 daily. Separate expert/Jarvis
  LaunchAgents are removed from the intended operational path. The scheduler
  now also exposes today's task履约 through `scheduler today-status`, MCP
  `get_scheduler_today_status`, and 设置 / 系统健康, including failed,
  deferred, missed, partial, successful, and not-yet-due job states.

- Follow-up scheduler defect fix on 2026-05-27: the P0 audit findings in
  `repo/audits/SCHEDULER_PIPELINE_DEFECTS_2026-05-27.md` were addressed for
  the front half of the timed pipeline. Scheduler handlers now call the real
  news, capital-flow, price/NAV, feature, forecast/backtest, market snapshot,
  advice, advice-scoring, and monitoring services instead of only advancing
  watermarks or readiness gates. Scheduler runs now expose `execution_mode`
  so CLI/MCP/WebUI can distinguish `real_provider`, `real_calculation`,
  `real_model_run`, `agent_runtime`, and `readiness_only`. Jarvis readiness
  now reports whether upstream scheduler evidence for the target date was
  truly executed, so a completed expert committee no longer hides stale
  market/model evidence. Regression coverage was added for scheduler success
  semantics, expert buy/sell action persistence, and virtual portfolio
  average-cost/realized/unrealized return calculations.

- Follow-up market/news interface recovery on 2026-05-29: Tushare news
  retrieval now retries through environment, direct, and local proxy profiles
  with token-safe diagnostics. `market_context_intraday` can recover market-level
  capital-flow evidence through Tushare when the AKShare/Eastmoney
  market-context path has a newer unrecovered failure or active provider gate,
  and records the actual provider used per subject. Local operational evidence:
  `news_hourly_incremental` run `114` completed `success`; `market_context_intraday`
  run `120` completed `success` with Tushare fallback and 5 written
  capital-flow rows. Test evidence after the fix: `267 passed, 3 xfailed`.

- Follow-up market data green-path repair on 2026-05-29: the remaining
  market/data warning was traced to historical same-day provider failures plus
  missing secondary fallbacks. Tushare price fallback now uses the installed
  `tushare 1.4.29` `pro_bar(api=...)` signature for stocks and `fund_daily`
  for ETFs, `price_nav_post_close` records the provider actually used per
  asset, and `market_context_intraday` can use Tushare stock-level moneyflow
  for planned subjects instead of failing whenever Eastmoney stock flow is
  unavailable. Operational evidence: `market_context_intraday` run `136`
  completed `success`, wrote 105 capital-flow rows across 21 subjects, and had
  `failed_subjects = 0`. Test evidence after the fix: `271 passed, 3 xfailed`.

- Follow-up Jarvis/short-message recovery on 2026-05-29: today's Jarvis
  failure was traced to the `sang_hongyang` expert run for target evidence date
  `2026-05-28` timing out and being stored as `cancelled`, which kept Jarvis
  readiness pending and prevented a new phone summary. Runtime timeouts now
  persist `timed_out`, successful recovered agent runs clear stale
  `failure_reason` text, `sang_hongyang` recovered as `agent_runs.id = 30` /
  `expert_plans.id = 27`, and Jarvis recovered as `agent_runs.id = 26` /
  `jarvis_daily_briefs.id = 6`. The real iMessage adapter created
  `outbound_messages.id = 9` with `status = sent` at `2026-05-29 01:43:45`
  for `owner_phone`; device-side receipt still needs human confirmation before
  TASK-098 can claim accepted phone delivery. Test evidence after the fix:
  `269 passed, 3 xfailed`.

- Sequential scheduler/data/Jarvis repair on 2026-05-29: the remaining
  TASK-098 D1/D2/D3 expected-failure defects are fixed. `scheduler
  today-status` now tracks due scheduled occurrences, recovery counts, and
  operator-interrupted manual probes correctly; Jarvis marks stale capital-flow
  summaries as `degraded`; new expert plans carry capital-flow
  freshness/degradation evidence. Operational recovery evidence:
  `price_nav_post_close` run `143` completed `success` with 159 written price
  rows and one explicit `stock:000004` no-history asset; `news_hourly_incremental`
  run `146` completed `success` with 63 current news rows through Akshare
  Eastmoney/Sina global sources; `jarvis_t_plus_one` occurrence
  `2026-05-29T08:00:00` recovered as scheduler run `147` without duplicating
  the already-sent `outbound_messages.id = 9`. Current `today-status` is
  intentionally still `warn`: 5 jobs are `success`, while hourly market/news
  remain `partial` because earlier same-day failures stay visible by design.
  Test evidence after the pass: `277 passed, 2 warnings`.

- Earlier Jarvis-first IA narrowing is closed, not the current active pause.
  `TASK-061` through `TASK-065` are complete: the AI provider boundary,
  expert/Jarvis prompt and evidence schemas, provider-backed orchestration,
  Jarvis confidence gates, and architecture/code-index synchronization are in
  place. `TASK-066`, `TASK-067`, `TASK-068`, and `TASK-069`
  are now complete: the first-level WebUI navigation exposes only 今日简报 /
  机会池 / 专家团 / 证据 / 设置, legacy technical routes remain direct/drill-down
  compatible, 今日简报 is organized around Jarvis daily decision questions,
  机会池 consolidates category/theme/fund/prediction discovery, and 证据 / 设置
  consolidate advanced model/data/system/communication detail. `TASK-070`
  acceptance is also complete, so the five-entry Jarvis IA round is accepted.

  The provider-based AI interaction layer milestone is closed, and `SPEC-012`
  now implements the agentic product shape for this round: system-owned
  scheduling plus a Codex agent runtime access layer. The system, not Codex,
  owns triggers, data readiness, persistence, audit, validation, and UI. Codex
  is invoked as a role-scoped runtime with project skills, role prompts,
  MCP/API tools, and structured output contracts. Experts complete or
  explicitly skip/fail T-day virtual investment actions before Jarvis runs the
  T+1 daily analysis.

- Data coverage has been expanded and ingestion channels have been hardened.
  The first productized research-flow slice is now in place through the run
  timeline, category navigation, and fund screening presets. The expert
  committee foundation has started with a persisted four-expert roster named
  with durable historical personas, structured style metadata, focus weights, risk limits, allowed asset categories,
  cash buffers, review cadence, lifecycle state, and one CNY 500,000 virtual
  portfolio per active expert. Experts can now produce one evidence-backed
  daily plan per date and simulate execution into those virtual portfolios.
  Expert scorecards, lifecycle reviews, retirement lessons, and replacement
  hiring are now persisted from virtual portfolio records. The expert
  committee is inspectable in WebUI through `/experts`, including active,
  probation, retired, plans, scorecards, reviews, and lessons. Expert roster,
  planning, portfolios, scoring, reviews, and lessons are now exposed to
  MCP/Agent workflows with task logs. The near-term product workbench polish
  pass through `TASK-031`/`TASK-032`/`TASK-033`/`TASK-035` is complete, and
  the phone communication phase through iMessage outbound delivery is already
  implemented through `TASK-042` through `TASK-046`. The final product target
  has been clarified as Jarvis: a top-level
  AI intelligent investment assistant that synthesizes system market
  information, prediction models, expert plans, expert scores, and expert
  current returns into a simple daily wealth-management brief. Jarvis now has
  a persisted daily-brief product model, safe persistence API, and deterministic
  synthesis engine that fills those records from stored market, model, expert,
  portfolio, task-log, and user-context evidence. Jarvis is now visible in
  WebUI through a first-screen `/jarvis` brief and dashboard entry with
  secondary evidence drill-down. Jarvis is also exposed to Agents through MCP
  tools for structured retrieval and generation. Expert AI analysis and Jarvis
  AI financial analysis are now explicit persisted orchestration steps with
  evidence packets, validation metadata, and task logs. WebUI market
  gain/loss semantics now follow Chinese market convention: red/up/上涨 for
  positive return-like values, green/down/下跌 for negative values, and muted
  flat markers for neutral values. The prediction page now groups repeated
  5/20/60 day horizon forecasts into one asset-level card per asset, with raw
  model rows kept as technical detail. The dashboard now opens with a Chinese
  daily brief and grouped run-health cards for ingest, features, market
  snapshot, forecast, backtest, advice, and monitoring, with failed/missing
  stages tied to impact and recovery hints. Table-heavy workbench pages now
  use progressive disclosure: `/backtests`, `/advice`, `/settings`, and
  `/logs` lead with summaries/cards/recovery guidance while raw rows and JSON
  stay available as secondary technical detail. Generic simulated portfolio
  tracking is now available through `portfolio create/list/trade/value` CLI
  commands and a `/portfolios` WebUI route with holdings, transactions,
  valuations, and an equity curve, all backed by stored prices.
  Communication now has a channel-neutral foundation with persisted
  recipients, adapter configs, outbound messages, allowlist/idempotency policy,
  dry-run sends, failure recording, and CLI inspection/configuration commands.
  The first iMessage adapter now sits behind that service boundary with
  AppleScript isolated in the adapter, setup health checks, explicit real-send
  support for allowlisted recipients, and permission/failure reporting. Mobile
  notification templates now turn persisted daily workflow, provider warning,
  expert plan, expert probation, and expert retirement evidence into concise
  opt-in phone messages routed through the same audited communication service.
  Communication is now inspectable in WebUI through `/communication`, with
  adapter health, iMessage preflight checks, masked allowlisted recipients,
  dry-run test sends, recent outbound statuses, and error summaries. Jarvis can
  now render and optionally send a concise phone summary from persisted daily
  brief evidence through the same idempotent allowlisted communication service.
  Safe inbound phone command design is now documented: iMessage remains
  outbound-only, while future inbound commands require a safer authenticated
  nonce-bound audit flow and are limited to non-trading operations.
  Daily advice now includes target-volatility allocation proposals built from
  stored volatility/drawdown metrics and bounded by active user max-equity and
  min-cash preferences; `/advice` shows the proposal and risk-metric evidence
  before raw JSON. Model monitoring now persists per-version health reports
  covering prediction score, risk score, benchmark excess, score drift, and
  prediction/backtest staleness; daily workflow writes monitoring task logs
  and `/backtests` surfaces degraded/warning states before raw rows.
  The expert overview has also been tightened so it shows compact expert
  cards, one multi-expert virtual return comparison curve, and no duplicate
  equity/benchmark or plan/execution table; plan details remain behind each
  expert drill-down. Fund benchmark scoring now uses stored same-bucket peer
  averages for funds when enough peer history exists, records explicit
  沪深300/unavailable fallback behavior, and persists benchmark
  identity/source on advice outcome scores. Default AKShare ingestion is now
  sequential and residential-network polite, with configurable delay/jitter,
  retry backoff diagnostics, incremental date ranges from local history, and
  task-log warnings for empty or likely throttled provider responses. Tushare
  Pro is now available as an explicit optional provider for users with
  credentials, while AKShare remains the free default provider and the schema
  stays provider-neutral. Market snapshots and macro observations now have a
  dedicated `/market` WebUI page, so the stored market regime and macro series
  used by advice and Jarvis can be inspected directly instead of only through
  dashboard/timeline context. A deterministic industry/theme classification
  layer now labels assets from stored code/name/type/fund-type fields, surfaces
  the label across category, data, fund, prediction, and market views, and lets
  fund screening filter by theme without adding an opaque external taxonomy.
  Theme labels are now also aggregated on a dedicated `/themes` configuration
  page, where users can compare theme-level coverage, recent return, drawdown,
  expected-return summaries, and representative assets. Capital-flow
  observations now have a provider-neutral persistence layer, explicit AKShare
  ingestion command, and `/market` WebUI section for latest inflow/outflow
  evidence and historical details. Daily advice and Jarvis now carry
  capital-flow evidence IDs and summaries when observations are available, with
  `/advice` and `/jarvis` linking back to `/market`.
  Public-fund holding reports now have provider-neutral persistence, an
  explicit `ingest fund-holdings` command, and a `/funds` holding-observation
  panel scoped to the current fund filter. The fund workbench now also
  aggregates those holdings into deterministic theme look-through exposure so
  users can compare what filtered funds actually own before reading raw rows.
  Daily advice now includes correlation risk-budget evidence derived from
  stored price history and target-volatility candidate assets, so allocation
  review covers approximate diversification and bucket risk contribution.

## Current Product Clarification

- "Codex automation" must no longer mean a Codex-owned daily scheduler.
  Scheduling belongs to this system.
- Codex app automations are not part of the operational refresh path. Market
  data and news updates are triggered by the system scheduler, run at least
  hourly where appropriate, and must be incremental补齐 rather than full量更新.
- Hourly refresh means bounded missing-window repair from persisted watermarks:
  news uses source/time/asset/theme indexes, market context uses changed scopes,
  derived news/features update only affected ranges, and providers enter
  deferred/backoff states when budgets are exceeded.
- The target product AI architecture is agentic:
  - system prepares data/model/news evidence and exposes APIs/MCP tools;
  - one Codex expert agent runs per active expert on T day;
  - expert agents submit validated virtual actions back through system APIs;
  - Jarvis runs at T+1 after expert T outcomes are available;
  - Jarvis uses system evidence plus expert actions/scores/current returns to
    produce the consumer daily brief.
- Existing `ai_providers` and deterministic synthesis remain useful fallback
  or validation surfaces, but they must not be confused with final
  expert/Jarvis agent runtime behavior.
- Runtime skill design is two-layered:
  - domain/function skills expose bounded capabilities such as market data,
    model evidence, news evidence, asset research, expert portfolio, virtual
    action, Jarvis synthesis, and output contracts;
  - expert and Jarvis role overview skills compose different skill bundles and
    different tool manifests for their respective runtime tasks.

## Last Completed

- `TASK-001`: Established Python project skeleton, SQLite schema, database
  initialization command, and baseline tests.
- `TASK-002`: Added AKShare MVP ingestion for one index, one ETF, and one public
  fund with normalized rows, ETF fallback, task logs, and tests.
- `TASK-003`: Added reproducible feature/risk metric calculation from stored
  prices with `features_v1` persistence, missing-gap validation, task logs, and
  tests.
- `TASK-004`: Added `baseline_mean_v1` forecasts, rolling backtests, score
  persistence, CLI commands, and future-leakage tests.
- `TASK-005`: Added daily advice generation from stored predictions/backtests,
  three risk-profile variants, allocation triggers, evidence links, compliance
  guardrails, task logs, CLI command, and tests.
- `TASK-006`: Added MCP-compatible tool schemas and JSON-callable tool
  implementations for asset, history, metrics, snapshot, forecast, backtest,
  and daily advice workflows.
- `TASK-007`: Added deterministic daily workflow command, success/failure task
  logs, dry-run tests, and the initial scheduled daily run setup. Current
  product direction supersedes any Codex-owned scheduling language: scheduling
  belongs to the system.
- `TASK-008`: Added local WebUI workbench with dashboard, data, funds,
  predictions, backtests, advice, and task-log pages, plus browser verification.
- `TASK-009`: Added baseline candidate calibration reports comparing
  `baseline_mean_v1` and `momentum_last_return_v1` across historical windows.
- `TASK-010`: Audited README MVP requirements against implementation evidence
  and created follow-up tasks for remaining material gaps.
- `TASK-011`: Added official MCP Python SDK stdio transport over the existing
  tool registry with transport smoke tests.
- `TASK-012`: Expanded the AKShare universe to 10 representative assets across
  indices, ETFs, public funds, and one individual A-share.
- `TASK-013`: Added AKShare fund info ingestion, persistence, MCP output, and
  WebUI fund metadata for tracked public funds.
- `TASK-014`: Added stored market environment snapshots, daily workflow
  integration, MCP/WebUI output, and advice evidence links.
- `TASK-015`: Added provider retry behavior and per-asset ingestion quality
  reports with warning metadata.
- `TASK-016`: Added real 沪深300 benchmark-relative backtest scoring and
  matured daily advice outcome scoring.
- `TASK-017`: Added historical calibration corpus workflow and verified a
  2023-2025 expanded-universe calibration report.
- `TASK-018`: Added FRED macro observation ingestion, persistence, CLI command,
  and market snapshot evidence integration.
- `TASK-019`: Added daily-advice history selection and focus-asset links to
  product data pages.
- `TASK-020`: Added dashboard database status and restart-time row-count health
  output.
- `TASK-021`: Added persisted user risk preferences, CLI/WebUI settings, and
  preference-aware daily advice generation.
- `TASK-027`: Expanded default data coverage to 63 assets and hardened
  research/full ingestion controls.
- `TASK-034`: Measured the AKShare full candidate universe at 23,952 assets,
  added resumable balanced full-ingestion batches, skipped existing assets,
  isolated fund detail and feature-history failures, and expanded the default
  database to 476 assets / 153,175 price rows.
- `TASK-028`: Added a WebUI research timeline that connects advice, market
  snapshots, prediction coverage, backtest evidence, task health, source links,
  and missing-stage recovery hints.
- `TASK-029`: Added product category navigation, dashboard category drill-in,
  category summaries, and a selected-asset-first `/data` view with the raw
  asset list moved into secondary technical details.
- `TASK-030`: Upgraded `/funds` into a practical screening workflow with
  metadata/metric filters, conservative/balanced/aggressive presets,
  suitability explanations, and product-language missing metadata states.
- `TASK-031`: Added shared WebUI market-value formatting so dashboard,
  predictions, funds, data/category tables, Jarvis metrics, and expert return
  views consistently show red/up/上涨 for positive values, green/down/下跌 for
  negative values, and neutral markers without reusing operational
  success/failure colors.
- `TASK-032`: Reworked `/predictions` into asset-level forecast cards that
  group 5/20/60 day horizons under one asset, show expected return, up
  probability, downside risk, confidence, and a horizon agreement label, while
  preserving raw prediction rows as secondary technical detail.
- `TASK-033`: Added a dashboard daily brief with stance, three reasons, watch
  condition, active risk settings, and grouped run-health cards for ingest,
  features, market snapshot, forecast, backtest, advice, and monitoring.
- `TASK-035`: Applied progressive disclosure to table-heavy WebUI pages so
  `/backtests`, `/advice`, `/settings`, and `/logs` start with user-facing
  summaries, evidence cards, risk-profile context, and recovery guidance while
  raw technical rows remain collapsed.
- `TASK-022`: Completed generic simulated portfolio tracking with CLI
  create/list/trade/value commands and `/portfolios` WebUI inspection for
  holdings, transactions, valuation history, and equity curve.
- `TASK-023`: Added target-volatility allocation proposals to daily advice
  using stored `features_daily` volatility/drawdown metrics, active user
  max-equity/min-cash constraints, structured evidence IDs, and a WebUI
  target-volatility panel on `/advice`.
- `TASK-024`: Added persisted model monitoring reports, `monitoring run` CLI,
  daily workflow monitoring task logs, and `/backtests` monitoring cards for
  score drift, stale inputs, benchmark excess, and degraded model health.
- `TASK-025`: Added an optional Tushare provider path with explicit
  `--provider tushare` selection, `--tushare-token`/environment token support,
  optional `.[tushare]` install extra, normalized index/stock/ETF/fund history,
  and provider-neutral source logging.
- `TASK-026`: Added fund peer benchmark scoring with shared benchmark
  selection, same-bucket fund peer averages, explicit 沪深300 fallback,
  backtest benchmark details, and persisted advice outcome benchmark
  identity/source.
- `TASK-027`: Added polite AKShare ingestion defaults with configurable
  provider delay/jitter/retry/backoff, request diagnostics, incremental
  per-asset history windows, skip-already-current behavior, and task-log
  warnings for empty or likely throttled provider responses.
- `TASK-042`: Added channel-neutral communication persistence and service
  boundary with recipients, adapter configs, outbound messages, dry-run send,
  allowlist enforcement, idempotency, failed-send recording, and CLI commands.
- `TASK-043`: Added the iMessage outbound adapter with testable AppleScript
  command construction, macOS/osascript setup verification, permission-required
  failure mapping, service-layer real-send adapter resolution, and
  `communication verify-setup` CLI support.
- `TASK-044`: Added safe mobile notification templates for daily success,
  daily failure, provider warnings, expert plan readiness, expert
  probation/warnings, and expert retirement/replacement; daily and expert
  workflows can now opt in to audited, idempotent, non-blocking notifications.
- `TASK-045`: Added communication inspection in CLI/WebUI, including
  `communication list-adapters`, `/communication`, iMessage preflight health,
  masked allowlisted recipients, WebUI dry-run testing, recent outbound
  messages, and error summaries.
- `TASK-046`: Added safe inbound phone command design in `ADR-006` and
  `SPEC-008`, deciding that iMessage stays outbound-only and any future inbound
  commands must be non-trading, allowlisted, authenticated, nonce-bound,
  confirmation-gated, replay-protected, and audited.
- `TASK-036`: Added persisted expert roster architecture with the four
  default active historical-name experts, structured configuration, lifecycle
  state, idempotent initialization, CLI inspection, and tests.
- `TASK-037`: Added shared simulated portfolio accounting and created one CNY
  500,000 virtual portfolio per active expert with cash ledger, positions,
  transactions, no-trade/unfilled records, and stored-price valuation.
- `TASK-038`: Added expert daily planning and simulated execution from stored
  predictions, features, market snapshots, focus weights, risk checks, and
  portfolio cash, with idempotent one-plan-per-expert-per-day persistence.
- `TASK-039`: Added expert scorecards, lifecycle reviews, structured lessons,
  warning/probation/retirement progression, and style-diverse replacement
  hiring that restores four active experts.
- `TASK-040`: Added `/experts` WebUI for expert roster, virtual portfolios,
  current capital/cash/return/drawdown/score, latest plans, lifecycle reviews,
  retired/probation states, equity/benchmark comparison, lessons, and
  secondary technical details.
- `TASK-041`: Added expert MCP/Agent tools for roster, plans, virtual
  portfolios, scoring, scorecards/reviews, lessons, daily planning, and
  scoring execution with task logs.
- `TASK-047`: Added Jarvis daily-brief persistence with idempotent
  `(brief_date, version)` records, focus directions, model/expert summaries,
  combined recommendation, risk warnings, evidence references,
  missing/stale-evidence metadata, query helpers, and safe-language validation.
- `TASK-048`: Added deterministic Jarvis synthesis from persisted market,
  model, backtest, expert plan, expert scorecard, virtual valuation, task-log,
  macro, and user-preference evidence, plus model/expert disagreement
  explanation, missing/stale-evidence warnings, CLI generation, and an explicit
  daily workflow flag.
- `TASK-049`: Added `/jarvis` and a dashboard Jarvis entry showing the latest
  first-screen brief with focus directions, stance, model summary, expert
  cards, scores/current returns/drawdowns, combined recommendation, risk
  warnings, evidence links, history, and secondary raw JSON.
- `TASK-050`: Added Jarvis MCP/Agent tools for retrieving latest or dated
  Jarvis briefs and generating new briefs from persisted evidence, with
  structured output and task logs through the FastMCP stdio server.
- `TASK-051`: Added a Jarvis phone summary template and optional
  `jarvis generate --notify-recipient-key` delivery path through the audited
  communication service, with dry-run rendering, safe research-support
  language, and idempotent duplicate prevention.
- `TASK-052`: Added shared AI analysis orchestration records, expert
  evidence-packet analysis before expert plans, expert-plan `ai_analysis_id`
  traceability, Jarvis AI analysis over market/model/expert/portfolio evidence,
  compliance/evidence validation, and task logs for both expert and Jarvis AI
  analysis runs.
- `TASK-053`: Added a `/market` WebUI route for market snapshots, macro
  observations, historical market/macro records, and a category drill-in link
  from "宏观/市场指标".
- `TASK-054`: Added deterministic industry/theme classification for assets and
  WebUI theme visibility/filtering across category, data, fund, prediction, and
  market pages.
- `TASK-055`: Added `/themes` theme allocation overview with theme-level
  counts, prediction coverage, return/drawdown/expected-return aggregates, and
  representative asset drill-down.
- `TASK-056`: Added capital-flow observations with provider-neutral
  persistence, AKShare normalization, `ingest capital-flow`, and `/market`
  funds-flow inspection.
- `TASK-057`: Connected capital-flow observations into daily advice, Jarvis
  synthesis, Jarvis AI-analysis evidence packets, and WebUI evidence links.
- `TASK-058`: Added public-fund holding ingestion and WebUI inspection with
  provider-neutral `fund_holdings`, AKShare normalization, CLI support, and
  latest holding observations on `/funds`.
- `TASK-059`: Added filtered fund-holding theme look-through on `/funds`, using
  persisted holdings plus deterministic theme labels to show exposure weight,
  fund count, holding count, latest report period, and representative holdings
  before raw holding rows.
- `TASK-060`: Added correlation risk-budget evidence to daily advice and
  `/advice`, including pairwise correlation summary, bucket risk contribution,
  per-asset risk scores, evidence asset IDs, and explicit insufficient-history
  states.
- `TASK-061`: Added the bounded AI provider adapter contract with
  request/response/config dataclasses, environment-based config discovery,
  fake-provider dry runs, deterministic fallback metadata, and
  `investment-forecasting ai provider-check`.
- `TASK-066`: Replaced the WebUI first-level navigation with the five Jarvis
  consumer entries 今日简报, 机会池, 专家团, 证据, 设置, while preserving legacy
  technical routes for direct links, evidence drill-down, tests, and agents.
- `TASK-067`: Reworked `/` into the default Jarvis 今日简报 decision surface,
  organized around 今天怎么看, 为什么, 能不能信, 关注哪些资产, 专家是否一致, and
  风险边界/观察条件, with data freshness, run health, focus assets, expert
  consensus, risk warnings, and technical evidence moved into secondary links
  or collapsed sections.
- `TASK-068`: Added `/opportunities` as a 机会池 flow that consolidates product
  categories, theme summaries, fund candidates, holding look-through, and
  asset-level prediction cards behind product-type and risk-profile filters.
- `TASK-069`: Added `/evidence` for model predictions, backtests/model health,
  market/macro/capital-flow evidence, data coverage, and collapsed raw rows;
  expanded `/settings` to include risk preferences, notification/communication
  health, data update state, system health, and task-log guidance.
- `TASK-070`: Accepted the Jarvis consumer IA round after verifying the
  rendered nav has exactly five entries, the default page answers the six
  Jarvis daily decision questions, old technical pages remain secondary/direct,
  project memory matches route ownership, and WebUI/Jarvis tests pass.

## Current Constraints

- MCP stdio transport is implemented with the official Python SDK. SSE or
  streamable HTTP can be enabled later if needed.
- The core local MVP loop is implemented and verified, including live FRED
  macro ingestion after adding a portable `certifi` CA bundle.
- MVP should start with AKShare and SQLite.
- Investment advice must remain research support and must include risk and
  uncertainty.
- The Jarvis consumer IA is a standing product constraint. First-level WebUI
  navigation must remain exactly 今日简报, 机会池, 专家团, 证据, 设置 unless a future
  product-review task and ADR update `ADR-007`.
- User-facing product chrome should present Jarvis as the assistant. Avoid
  reverting primary copy to developer-workbench framing.
- Technical pages and labels such as 预测, 回测评分, 任务日志, 数据与曲线, 市场指标,
  and 研究时间线 must stay as drill-downs under 机会池, 证据, 设置, or direct
  agent links.
- Residential broadband access to AKShare-backed public data should be treated
  as low-frequency personal research only; future ingestion work must minimize
  temporary ban or anti-bot risk with rate limits, jitter, incremental updates,
  and clear throttling diagnostics.

## Open Issues

- Some deeper research pages can still be made more decision-oriented, but the
  main table-heavy WebUI pages now expose summaries/cards/recovery guidance
  before raw technical details.
- The latest IA review found one product-polish gap: primary chrome still uses
  "投资预测工作台" wording in places. Future UI polish should rename the visible
  product framing to Jarvis 理财助理 without changing navigation structure.
- Daily 08:00 scheduling must account for China market data availability: the
  morning run mainly uses previous trading-day data.
- Expert committee planning/execution work must reuse the new persisted expert
  roster plus existing advice, forecast, backtest, scoring, portfolio, daily
  workflow, MCP, and WebUI capabilities instead of creating a parallel
  investment engine.
- Phone communication must be opt-in, allowlisted, auditable, and safe.
  iMessage is the first adapter, but investment, expert, workflow, and WebUI
  logic must call a channel-neutral communication service instead of directly
  invoking Messages or AppleScript.
- iMessage is outbound-only for this architecture. Future inbound phone
  commands require `ADR-006` constraints: no trading, no private Messages
  history scraping, allowlist/authentication, nonce binding, confirmation,
  replay protection, and command audit before side effects.
- Jarvis must be the user-facing synthesis layer, not a parallel prediction
  engine. It must reuse stored market data, model predictions, backtests,
  expert plans, expert scorecards, expert virtual returns, and user
  preferences, and it must preserve risk warnings and evidence links.
- Real-LLM integration must reuse the existing AI provider adapter and
  `ai_analysis.py` prompt/schema contracts. Provider-backed and deterministic
  fallback records share the same persisted evidence/output/validation shape.
- Jarvis now confidence-gates stale, degraded, low-confidence, and outlier
  model signals. Gated predictions are watch-only context, not strong daily
  action directions.
- Expert performance maturity is surfaced when score or return evidence is
  sample-poor; Jarvis must keep treating expert returns as evidence, not proof.
- News evidence should be added as a searchable evidence service, not as bulk
  prompt context. Codex AI/Jarvis should retrieve news through explicit filters
  when needed and cite evidence IDs.
- Financial expert and CEO review approve the next product/engineering phase
  as Model Reliability Upgrade, not "stronger prediction". The goal is to
  improve ranking evidence, validation, model health, and Jarvis caution.
- `TASK-074` is complete: latest model predictions can now carry sidecar
  reliability metadata for cross-sectional rank, same-category rank,
  risk-adjusted score, validation state, degraded reason, and evidence IDs
  without breaking existing `model_predictions` consumers.
- `TASK-075` is complete: backtests now persist IC, Rank IC, bucket spread,
  asset-type/same-category validation, probability calibration, validation
  policy, and insufficient/degraded validation status; monitoring, MCP, and
  `/backtests` expose those reliability signals.
- `TASK-076` is complete: the model layer now has an interpretable candidate
  pool with `momentum_reversal_v1` and `risk_adjusted_factor_v1` alongside
  `baseline_mean_v1`. Forecast, backtest, calibration, CLI, and MCP paths can
  compare multiple model versions, write the same rank/risk-adjusted
  reliability sidecar, and keep candidates contextual instead of promoting
  them to Jarvis-primary by default.
- `TASK-077` is complete: experts and Jarvis now consume the same
  `model_evidence_packet_v1` shape built from model predictions plus
  reliability sidecar fields. Expert plans persist that packet, include
  style-specific weighting guidance, and downgrade degraded, negative-Rank-IC,
  or negative-bucket-spread model signals to watch-only context instead of
  strong buy/rebalance language.
- `TASK-078` is complete: Jarvis now acts as a model risk officer by adding
  explicit gate reasons, `model_risk_summary`, excluded horizons, and degraded
  model-family explanations for stale, unvalidated, degraded, weak-Rank-IC,
  weak-bucket, low-confidence, outlier, and model-disagreement signals. Phone
  summaries, MCP output, and `/jarvis` surface those reasons while keeping raw
  evidence visible under 证据.
- `TASK-079` is complete: model promotion/demotion governance now records
  explicit states, promotion gates, demotion reasons, Jarvis-primary
  eligibility, and product-review requirements in calibration/monitoring
  outputs. Phase decision: `baseline_mean_v1` remains the primary model;
  `momentum_reversal_v1` and `risk_adjusted_factor_v1` remain contextual and
  are currently marked degraded in local monitoring evidence.
- `TASK-080` is complete: the system-owned Codex runtime access contract now
  has persisted `agent_runs` and `agent_tool_calls`, serializable
  `codex_agent_runtime_v1` launch request/runtime policy/result shapes,
  fake-adapter prepare/start/poll/cancel/collect behavior, service helpers,
  and `agent-runs list` CLI inspection. This established the runtime boundary
  and audit model that `TASK-081` now extends with local Codex CLI execution
  and role manifests.
- `TASK-081` is complete: local Codex CLI runtime integration now has
  `CodexCliRuntimeAdapter`, project-local artifacts under
  `data/agent_runtime/runs/<agent_run_id>/`, non-interactive `codex exec`
  command construction with `--ask-for-approval never` and
  `--sandbox workspace-write`, pid/command/path metadata persisted to
  `agent_runs`, `agent-runs codex-readiness`, and `agent-runs codex-smoke`.
  The adapter uses the locally configured Codex model by default because the
  ChatGPT-authenticated CLI rejected the hard-coded `gpt-5-codex` model during
  smoke testing. Expert/Jarvis role manifests, submission envelope tools,
  validation preview, and `agent_tool_calls` audit are now in place.
- `TASK-082` through `TASK-084` are complete: project domain/function skills,
  expert and Jarvis overview skills, prompt rendering, strict output schemas,
  expert T-day local Codex execution, artifact clearing on rerun, audited
  submission envelopes, expert plan/action persistence with `agent_run_id`
  evidence links, Jarvis T+1 readiness gates, and Jarvis brief persistence with
  producing agent-run/readiness evidence are now in place.
- `TASK-086` through `TASK-089` are complete, with the 2026-05-26 operational
  follow-up folded into the active implementation: scheduler tables, fixed job
  definitions, CLI inspection/manual run commands, incremental watermarks,
  provider budgets/backoff, scheduler health surfaces, task-log summaries, and
  `scheduler install-cron` are now implemented. The current sync timing is:
  news and market context every two hours; price/NAV post-close at `17:30`;
  features at `18:10`; model/advice preparation at `18:40`; experts at `20:00`
  on T; and Jarvis daily brief plus phone notification at `08:00` on T+1.

## Next Steps

1. Product review for the completed `SPEC-013` scheduler slice, especially
   whether provider execution should remain plan-only by default or be enabled
   for selected jobs.
2. Stop for product review before changing primary model status; current
   primary remains `baseline_mean_v1`.
3. Before any WebUI implementation, state which of the five Jarvis entries owns
   the change and verify `ADR-007` remains satisfied.
4. Do not add another LLM/provider integration path; expert/Jarvis product
   reasoning should continue through the `agent_runtime` access layer while
   `ai_providers` remains fallback/simple bounded analysis.

## Last Completed

- `TASK-084` added Jarvis T+1 readiness gates and local Codex runtime execution
  that persists Jarvis briefs with `agent_run_id`, target evidence date, and
  expert readiness metadata.
- `TASK-083` connected expert local Codex artifacts to validated expert
  plan/action persistence, including skipped/failed `no_trade` handling and
  artifact clearing for idempotent reruns.
- `TASK-082` added domain/function skill docs, expert/Jarvis overview skills,
  prompt rendering, and strict expert/Jarvis output schemas.
- `TASK-080` added the Codex runtime access contract, `agent_runs` /
  `agent_tool_calls` audit persistence, fake adapter, runtime service helpers,
  and CLI inspection.
- `TASK-081` added local Codex CLI runtime hookup with readiness/smoke checks,
  project-local run artifacts, non-interactive `codex exec` command
  construction, role manifests, agent-aware MCP/API submission envelopes, and
  a passing real local Codex smoke run.
- `TASK-079` added model promotion/demotion governance and documented that
  `baseline_mean_v1` remains primary while candidate models stay contextual.
- `TASK-078` extended Jarvis confidence gates into explicit model-risk-officer
  summaries across daily synthesis, phone summary, MCP output, and `/jarvis`.
- `TASK-077` added shared model evidence packets for experts and Jarvis, made
  expert planning reliability-aware, and added watch-only handling for degraded
  model evidence.
- `TASK-076` added deterministic interpretable candidate models,
  multi-model forecast/backtest/CLI/MCP execution, reliability sidecar refresh
  for candidates, and contextual candidate comparison without primary
  promotion.
- `TASK-075` added financial validation metrics, recorded embargo policy,
  validation status, model-monitoring warnings, MCP validation summary, and
  `/backtests` reliability display.
- `TASK-074` added prediction reliability metadata through
  `model_prediction_reliability`, deterministic rank/risk-adjusted refresh
  after forecasts, WebUI/MCP evidence exposure, and legacy migration coverage.
- `TASK-065` synchronized architecture, code index, status, SPEC-009, and task
  notes for the completed AI interaction layer milestone.
- `TASK-064` added Jarvis confidence gates and expert maturity wording so
  extreme low-confidence forecasts are downgraded to watch-only signals.
- `TASK-063` wired provider-backed AI orchestration through expert planning,
  Jarvis synthesis, task logs, and MCP provider/fallback status.
- `TASK-062` froze expert/Jarvis prompt and evidence schema contracts, including
  explicit news retrieval policy and unsupported news evidence validation.
- `TASK-073` added bounded `search_news_evidence` retrieval and MCP exposure
  with filters for source, time, asset, theme, event type, sentiment, keyword,
  dedupe, and sort. Results include evidence IDs, bounded excerpts, links,
  tags, match reasons, and audit references without raw provider dumps.
- `TASK-072` added deterministic news links/tags/features: asset code/name
  links, theme keyword/channel links, event type tags, directional sentiment
  tags, auditable reasons/confidence, and leakage-safe aggregate feature
  windows by asset/theme.
- `TASK-071` added the provider-neutral `news_items` store, bounded
  `ingest news` CLI, optional Tushare `news` adapter support, task-log counts,
  duplicate handling, and tests. News content is still not injected into
  expert/Jarvis prompts; retrieval/indexing remains in `TASK-072` and
  `TASK-073`.

Do not continue provider-backed industry taxonomy, bond/fund holding depth,
automatic rebalancing, covariance optimization, additional experts, inbound
phone commands, broad UI expansion, transformer/foundation time-series models,
or reinforcement learning until `TASK-074` through `TASK-079` are reviewed.

## Next Phase Acceptance Gate

- The left navigation exposes only 今日简报, 机会池, 专家团, 证据, 设置.
- The default page is Jarvis 今日简报, not a generic developer dashboard.
- 总览 / 研究时间线 / 每日建议 no longer compete as separate primary user
  destinations.
- 产品分类 / 数据与曲线 / 基金筛选 / 预测 are reachable through 机会池 or evidence
  drill-down, not first-level navigation.
- 回测评分 / 任务日志 are reachable through 证据 or 设置 / 系统健康, not first-level
  navigation.
- `/jarvis` or the default route clearly answers: 今天怎么看, 为什么, 能不能信,
  关注什么, 专家是否一致, 风险边界是什么.
- Existing direct routes may remain for compatibility and agents, but consumer
  navigation must not expose the old 11-entry structure.
- Tests cover navigation labels, default route content, opportunity-pool
  entry, evidence/settings consolidation links, and absence of old primary nav
  items.
- `ARCHITECTURE.md` and `CODE_INDEX.md` are updated in the same change set as
  implementation, before the phase is considered done.
- News evidence is retrievable by source, datetime range, asset/theme, event
  type, sentiment, keyword, and max result count; AI prompts do not receive
  unbounded news content by default.
- Candidate models remain candidate/contextual until promotion gates prove
  stable improvement over `baseline_mean_v1`.
- Jarvis daily brief prefers relative ranking, calibrated probability, and
  risk-adjusted language over large point-return claims.
- Model optimization succeeds when Jarvis can explain why it should not trust
  a tempting signal.

## Round Evaluation

- Date: 2026-05-24
- Scope: `TASK-062` through `TASK-065` AI interaction layer closeout.
- Judge: `python3 -m pytest tests/test_ai_providers.py tests/test_experts.py tests/test_jarvis.py tests/test_mcp_tools.py tests/test_daily_workflow.py -q`
  and `python3 -m pytest tests/test_jarvis.py tests/test_web_app.py tests/test_communication.py tests/test_mcp_tools.py -q`.
- Score: 94/100
- Reasoning: The provider boundary now has versioned expert/Jarvis prompt and
  schema contracts, explicit news retrieval policy, fake-provider success in
  expert and Jarvis orchestration, deterministic fallback metadata, MCP
  provider/fallback status, Jarvis confidence gates for stale/degraded/outlier
  signals, and expert-maturity wording. Live provider SDK calls remain outside
  scope; the fake provider is the current test harness for provider-backed
  orchestration.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-061` AI provider adapter contract.
- Judge: `python3 -m pytest tests/test_ai_providers.py tests/test_experts.py tests/test_jarvis.py -q`
  and `investment-forecasting ai provider-check` dry-run behavior.
- Score: 93/100
- Reasoning: The AI interaction layer now has a single bounded provider
  boundary with environment config, fake-provider success, missing config and
  missing credential fallback, forced error/timeout fallback, CLI inspection,
  and persisted provider/fallback metadata on AI analysis records. Live
  provider SDK integration and prompt/schema freezing remain intentionally
  deferred to `TASK-062` and `TASK-063`.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-060` correlation risk-budget advice.
- Judge: `python3 -m pytest tests/test_advice.py tests/test_web_app.py -q`.
- Score: 92/100
- Reasoning: Daily advice now persists `allocation_json.risk_budget` and
  evidence IDs from stored price history, while `/advice` surfaces a
  correlation risk-budget panel and evidence chip before raw JSON. The
  implementation intentionally remains descriptive and dependency-free; a full
  covariance optimizer and automatic rebalancing remain future work.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-059` fund holding theme look-through.
- Judge: `python3 -m pytest tests/test_web_app.py tests/test_fund_holdings.py tests/test_db.py -q`
  plus `/funds` smoke check after WebUI restart.
- Score: 94/100
- Reasoning: `/funds` now turns latest persisted holding rows into a
  filter-scoped theme exposure summary before the raw holding table. Theme
  labels reuse deterministic classification and prefer linked asset fields
  when available. This closes the first look-through usability gap without
  adding an opaque taxonomy or implying suitability.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-058` fund holdings ingestion and WebUI.
- Judge: `python3 -m pytest tests/test_fund_holdings.py tests/test_web_app.py tests/test_db.py`
  and `python3 -m investment_forecasting.cli ingest fund-holdings --help`.
- Score: 93/100
- Reasoning: The README基金持仓 gap now has a durable first slice:
  `fund_holdings` persists quarterly stock holdings with normalized weight,
  shares, market value, report period, and source fields; the ingestion command
  can fetch tracked funds explicitly; `/funds` exposes latest observations
  alongside screening results. Remaining lift is bond holdings, broader live
  provider reliability, and look-through risk/theme aggregation.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-057` capital-flow evidence synthesis.
- Judge: `python3 -m pytest tests/test_advice.py tests/test_jarvis.py tests/test_web_app.py tests/test_capital_flow.py`.
- Score: 93/100
- Reasoning: Capital-flow observations now participate in the research
  evidence chain instead of remaining a standalone table. Daily advice stores
  `capital_flow_ids` and a structured flow summary; Jarvis collects flow rows,
  includes them in model summary and source evidence, records missing/stale
  flow state, and carries IDs into Jarvis AI-analysis packets. Remaining lift
  is broader sector/fund-flow provider coverage and real data availability.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-056` capital-flow observations.
- Judge: `python3 -m pytest tests/test_capital_flow.py tests/test_web_app.py tests/test_db.py`
  and `python3 -m investment_forecasting.cli ingest capital-flow --help`.
- Score: 93/100
- Reasoning: The README资金流 gap now has a durable first slice: normalized
  capital-flow rows are persisted idempotently, AKShare money-flow fields are
  hidden behind the provider adapter, and `/market` shows latest inflow/outflow
  evidence beside market and macro context. Remaining work is richer
  sector/fund-flow coverage and using this evidence in advice/Jarvis synthesis.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-055` theme allocation overview.
- Judge: `python3 -m pytest tests/test_web_app.py`.
- Score: 94/100
- Reasoning: Theme classification now has a portfolio-research surface instead
  of only per-asset labels. `/themes` aggregates stored assets by theme,
  displays coverage and risk/return summaries, and links representative assets
  back to `/data`. This advances industry configuration while leaving future
  provider-backed taxonomy, holdings, and capital-flow ingestion open.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-054` industry and theme classification.
- Judge: `python3 -m pytest tests/test_classification.py tests/test_web_app.py`.
- Score: 93/100
- Reasoning: Assets now receive deterministic theme labels with explicit
  keyword reasons, and those labels are visible in key research views. Fund
  screening can filter by theme, closing the first industry-classification gap
  without adding a paid taxonomy or schema migration. Future work remains real
  provider-backed industry tables, fund holdings, and capital-flow ingestion.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-053` market and macro indicator page.
- Judge: `python3 -m pytest tests/test_web_app.py`.
- Score: 94/100
- Reasoning: WebUI now has a dedicated `/market` route for latest market
  snapshot metrics, latest macro observations, and historical technical detail.
  The product-category "宏观/市场指标" drill-in now links to that page instead of
  showing a future-work placeholder. Future improvement is richer China-native
  macro and capital-flow series once a stable free source is selected.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-025` optional Tushare provider expansion.
- Judge: `python3 -m pytest tests/test_tushare_provider.py tests/test_akshare_ingestion.py`.
- Score: 92/100
- Reasoning: Tushare is now an explicit optional provider with token-only
  activation, optional SDK extra, normalized index/stock/ETF/fund history, and
  provider-neutral persistence through existing `assets` and `price_daily`
  tables. Default AKShare ingestion remains unchanged for users without
  credentials.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-027` provider access polite ingestion.
- Judge: `python3 -m pytest tests/test_akshare_ingestion.py tests/test_daily_workflow.py`
  and `python3 -m investment_forecasting.cli ingest mvp --help`.
- Score: 93/100
- Reasoning: AKShare access now has configurable delay/jitter, retry attempts,
  exponential backoff caps, request diagnostics, and likely throttling warning
  detection. Ingestion resumes from local history per asset, skips already
  current ranges, records incremental metadata in data-quality reports, and
  writes task-log JSON with provider request/retry settings and warnings.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-024` model monitoring and drift detection.
- Judge: `python3 -m pytest tests/test_monitoring.py tests/test_daily_workflow.py tests/test_web_app.py tests/test_db.py`
  and `python3 -m pytest`.
- Score: 92/100
- Reasoning: The system now persists per-model monitoring reports with
  prediction score, risk score, benchmark excess, overall score, score drift,
  stale prediction/backtest days, structured warnings, and ok/warning/degraded
  status. Daily workflow writes `model_monitoring` task logs, CLI can generate
  reports on demand, and `/backtests` surfaces degraded/warning states before
  technical rows. Future improvement is richer multi-version comparison once
  more model families are promoted.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-023` target-volatility allocation.
- Judge: `python3 -m pytest tests/test_advice.py tests/test_web_app.py` and
  `python3 -m pytest`.
- Score: 92/100
- Reasoning: Daily advice now embeds a target-volatility proposal backed by
  stored feature risk metrics, including source feature IDs, estimated
  annualized volatility, drawdown penalty, bounded equity/fixed-income/cash
  weights, and selected assets. Active user max-equity and min-cash settings
  constrain the proposal, and `/advice` exposes it before raw JSON. Remaining
  future work is richer asset-class classification and covariance-aware
  optimization once more stable histories are available.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-046` safe inbound phone command design.
- Judge: `ADR-006`, `SPEC-008`, `ARCHITECTURE.md`, and
  `rg -n "Messages history|phone-originated|execute investment actions" src tests`.
- Score: 94/100
- Reasoning: The design explicitly keeps iMessage outbound-only, limits future
  inbound commands to non-trading operational requests, forbids live execution
  and private Messages scraping, and defines allowlist, authentication,
  freshness, nonce, confirmation, replay-protection, and audit requirements
  before any future implementation task can add an execution path.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-051` Jarvis phone summary template.
- Judge: `python3 -m pytest tests/test_communication.py tests/test_jarvis.py`
  and `python3 -m pytest`.
- Score: 93/100
- Reasoning: Jarvis daily briefs can now render concise phone summaries with
  focus, stance, model signal, expert signal, risk warning, and `/jarvis`
  inspection hint. Delivery uses the existing communication service, recipient
  allowlist, dry-run support, outbound audit records, and
  `mobile:jarvis_daily_summary:{date}:{version}` idempotency key; notification
  failure does not fail Jarvis brief generation.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-045` communication WebUI and CLI inspection.
- Judge: `python3 -m pytest tests/test_communication.py tests/test_web_app.py`
  and `python3 -m pytest`.
- Score: 92/100
- Reasoning: Users can now inspect adapter setup, iMessage preflight health,
  masked allowlisted recipients, recent outbound statuses/errors, and trigger a
  WebUI dry-run test without real phone delivery. CLI inspection now includes
  adapter listing, while existing recipient/message/setup/test-send commands
  remain unchanged.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-044` mobile notification templates.
- Judge: `python3 -m pytest tests/test_communication.py tests/test_daily_workflow.py tests/test_experts.py tests/test_expert_scoring.py`.
- Score: 93/100
- Reasoning: Daily, provider, expert plan, probation, and retirement templates
  now render from persisted evidence, include research-support or virtual
  simulation wording, avoid raw JSON, and use deterministic idempotency keys.
  Optional notification hooks are non-blocking and reuse the communication
  service for dry-run, allowlist, policy, and outbound audit records.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-043` iMessage outbound adapter.
- Judge: `python3 -m pytest tests/test_communication.py`.
- Score: 92/100
- Reasoning: Real iMessage sending is now isolated behind the communication
  adapter boundary, dry-run remains non-invasive, setup health checks cover
  configuration, allowlist, macOS, and `osascript`, and tests cover AppleScript
  construction plus sent/permission-required adapter outcomes without requiring
  a real Messages account.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-042` communication adapter architecture.
- Judge: `python3 -m pytest tests/test_communication.py tests/test_db.py`.
- Score: 91/100
- Reasoning: The communication layer now has durable recipients, adapter
  configs, outbound messages, idempotency keys, structured statuses/errors,
  dry-run support, allowlist enforcement, and CLI inspection/configuration.
  Actual iMessage sending remains correctly isolated for `TASK-043`.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-031` red/green market semantics.
- Judge: `python3 -m pytest tests/test_web_app.py`.
- Score: 92/100
- Reasoning: WebUI now uses shared market-value formatting with Chinese market
  color convention and non-color arrows/text. Dashboard recommendations,
  prediction tables, fund screening, category/data tables, Jarvis metrics, and
  expert return surfaces all use the shared helper, while operational task
  states keep separate ok/warn/bad styles.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-052` AI analysis orchestration for experts and Jarvis.
- Judge: `python3 -m pytest tests/test_db.py tests/test_experts.py tests/test_jarvis.py`
  and `python3 -m pytest tests/test_mcp_tools.py tests/test_mcp_server.py tests/test_daily_workflow.py tests/test_web_app.py`.
- Score: 91/100
- Reasoning: Each active expert now persists one evidence-backed AI analysis
  per date before plan finalization, and expert plans reference that analysis.
  Jarvis daily briefs now reference expert AI analyses plus expert plans,
  model forecasts, scorecards, and virtual valuations, then persist a Jarvis AI
  analysis separating system facts, model interpretation, expert views,
  expert performance, final synthesis, and risk boundaries. Remaining lift is
  replacing the deterministic analysis source with a real model adapter when
  credentials, prompts, and review policy are ready.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-050` Jarvis MCP and Agent workflow.
- Judge: `python3 -m pytest tests/test_mcp_tools.py tests/test_mcp_server.py`.
- Score: 91/100
- Reasoning: Agents can now retrieve and generate Jarvis daily briefs through
  structured MCP tools. Outputs include focus directions, model summary,
  expert summaries with current returns, risk warnings, evidence references,
  and missing/stale evidence. Generation writes `jarvis_brief_generation` task
  logs and is exposed through the FastMCP stdio server. Remaining Jarvis work
  is phone summary rendering and explicit AI-analysis orchestration.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-049` Jarvis WebUI first-screen experience.
- Judge: `python3 -m pytest tests/test_web_app.py`.
- Score: 91/100
- Reasoning: `/jarvis` now gives the user a non-technical first screen for the
  persisted Jarvis brief: focus directions, stance, combined recommendation,
  model summary, disagreement explanation, one card per expert, risk warnings,
  evidence links, history, and secondary raw JSON. The next missing surface is
  MCP/Agent access and later phone summaries.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-048` Jarvis synthesis engine.
- Judge: `python3 -m pytest tests/test_jarvis.py tests/test_daily_workflow.py`
  and real database `jarvis generate` smoke run.
- Score: 91/100
- Reasoning: Jarvis now generates a persisted daily brief from stored market,
  model, backtest, expert, portfolio, task-log, macro, and preference evidence.
  The output includes model forecasts, every active expert's stance/score/current
  return, disagreement explanation, missing/stale evidence warnings, and safe
  risk language. Remaining value is making it the first visible WebUI
  experience and later MCP/phone access.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-047` Jarvis product model and persistence.
- Judge: `python3 -m pytest tests/test_jarvis.py tests/test_db.py`.
- Score: 90/100
- Reasoning: Jarvis now has a durable SQLite product record with idempotent
  reruns, traceable evidence references, missing/stale evidence metadata, and
  safe-language validation before persistence. The remaining product value is
  in `TASK-048` synthesis and `TASK-049` first-screen WebUI, not the storage
  foundation.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-041` expert Agent workflow and MCP integration.
- Judge: `python3 -m pytest tests/test_mcp_tools.py tests/test_mcp_server.py`.
- Score: 92/100
- Reasoning: Expert committee operations are now available through structured
  MCP tools and the FastMCP stdio server. Agents can inspect experts, plans,
  virtual portfolios, scorecards, reviews, and lessons, and can trigger expert
  planning/scoring without direct SQL edits. Planning and scoring write task
  logs. Remaining expert polish is richer WebUI charts and future automation
  scheduling, not core accessibility.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-040` expert committee WebUI.
- Judge: `python3 -m pytest tests/test_web_app.py`.
- Score: 91/100
- Reasoning: `/experts` now makes expert status inspectable without reading raw
  tables first: lifecycle state, style, current virtual capital, cash, return,
  drawdown, score, latest plan/execution, review rationale, lessons, and
  technical score/review details are all visible. Remaining expert integration
  belongs to MCP/Agent workflow exposure.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-039` expert scoring, retirement, and replacement hiring.
- Judge: `python3 -m pytest tests/test_expert_scoring.py tests/test_experts.py
  tests/test_portfolio.py tests/test_db.py` and real database `experts score`
  smoke run.
- Score: 90/100
- Reasoning: Scorecards are now reproducible from persisted virtual valuations,
  transactions, and plans. Lifecycle review requires maturity, moves weak
  experts through warn/probation before retirement, writes structured lessons,
  and creates a style-diverse replacement with a virtual portfolio to restore
  four active experts. The live database currently has immature scorecards
  because no valuation history exists yet, so no expert is punished.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-038` expert daily planning and simulated execution.
- Judge: Expert planning tests and real database CLI execution for
  `experts run-plans --date 2026-05-23`.
- Score: 90/100
- Reasoning: Each active expert can now produce at most one stored plan per
  date, with action/no-trade, target asset/amount, rationale, evidence links,
  risk checks, warnings, and execution status. Executions reuse virtual
  portfolio accounting, so buys update cash/positions and no-trade decisions
  are persisted. Remaining maturity is scoring, lifecycle review, and WebUI.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-037` expert virtual portfolio foundation.
- Judge: `python3 -m pytest tests/test_portfolio.py tests/test_db.py` and
  real database CLI bootstrap for expert portfolios.
- Score: 91/100
- Reasoning: Each active expert now has an independent CNY 500,000 virtual
  portfolio on the shared simulated-accounting path. The system can record
  filled buy/sell orders, no-trade decisions, unfilled missing-price orders,
  cash ledger entries, positions, and daily valuations from stored prices.
  Remaining value comes from `TASK-038` daily expert planning and execution.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-036` expert architecture and roster model.
- Judge: Expert spec/task audit, `python3 -m pytest tests/test_experts.py
  tests/test_db.py`, and CLI smoke initialization.
- Score: 92/100
- Reasoning: The expert committee is now grounded in persisted structured
  records instead of UI-only personas. Four active experts can be initialized
  idempotently and queried by lifecycle state. Remaining expert value depends
  on `TASK-037` virtual portfolios and later plan/execution/scoring loops.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-030` fund screening filters and presets.
- Judge: `python3 -m pytest`, WebUI `/funds` smoke check, and route/content
  review.
- Score: 93/100
- Reasoning: The fund page now supports practical screening by metadata,
  risk/return metrics, fee completeness, market state, and risk-profile
  presets. Results explain why a fund appears and whether data is incomplete,
  reducing raw-table friction. Remaining product polish is visual semantics and
  asset-level forecast presentation.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-029` product category navigation.
- Judge: `python3 -m pytest`, WebUI route smoke checks, and route/content
  review.
- Score: 92/100
- Reasoning: The workbench now supports product-first browsing through
  user-facing categories, dashboard drill-in, category summaries, peer links,
  and a `/data` page that starts with selected-asset context instead of raw rows.
  Remaining category depth belongs in `TASK-030`, where fund filters and presets
  should make the category views more actionable.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-028` product timeline and run history.
- Judge: `python3 -m pytest`, WebUI route smoke check, and route/content review.
- Score: 93/100
- Reasoning: The workbench now has a dedicated research timeline and dashboard
  entry point that connect advice, market snapshots, predictions, backtests, and
  task health into date-based run history. Missing stages have explicit recovery
  hints and rows link back to source evidence pages. Remaining polish belongs to
  the next productization tasks: categories, filters, market semantics, and
  asset-level forecast cards.

## Round Evaluation

- Date: 2026-05-23
- Scope: Product progress review and next-phase planning after `TASK-021` and
  `TASK-027`.
- Judge: Browser inspection of dashboard, settings, funds, predictions, advice,
  and logs plus review of `repo/STATUS.md`, `repo/INDEX.md`, and product
  acceptance documentation.
- Score: 88/100
- Reasoning: The product now has broader data, fresher predictions, market
  snapshots, active risk preferences, and preference-aware advice. The next
  bottleneck is product experience: the UI still relies on raw tables and
  repeated lists, so the next phase should prioritize timeline, categories,
  filters, market color semantics, asset-level prediction grouping, and
  dashboard/run-health summaries before adding deeper portfolio optimization.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-027` data expansion and channel hardening.
- Judge: `python3 -m pytest`, live AKShare/FRED ingestion, row-count audit, and
  WebUI restart health output.
- Score: 94/100
- Reasoning: The default database now has materially broader coverage and all
  core derived artifacts were recomputed. `research` ingestion can continue on
  individual failures, and `full` ingestion can cap per type to avoid one asset
  class dominating a staged pull. Remaining depth comes from more provider
  diversity and portfolio-level evaluation.
6. `TASK-027`: Add polite provider access controls for residential-network-safe
   ingestion.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-021` user risk preferences.
- Judge: `python3 -m pytest`, CLI preference smoke test, and WebUI settings
  rendering.
- Score: 92/100
- Reasoning: The roadmap backlog is now translated into concrete tasks, and the
  first personalization task is implemented end to end: persistence, CLI,
  WebUI, and advice generation all use the active preference. Remaining product
  depth comes from portfolio tracking and allocation optimization.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-020` data status and service health.
- Judge: `python3 -m pytest`, `scripts/restart_web.sh`, and HTTP check of
  dashboard content.
- Score: 93/100
- Reasoning: The dashboard now shows the active database path, key row counts,
  latest data dates, and empty-database guidance. The restart script prints
  row-count health after the service is up, making DB_PATH/data mixups visible
  immediately.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-019` advice history and product links.
- Judge: `python3 -m pytest` plus HTTP smoke against local WebUI route
  `/advice`.
- Score: 94/100
- Reasoning: The WebUI now supports selecting historical advice by id, shows a
  history table, and links focus asset cards to `/data?asset_id=...` for the
  corresponding product curve/history page. Tests cover both behaviors and an
  HTTP smoke followed a real focus link to a product page.

## Round Evaluation

- Date: 2026-05-23
- Scope: Project memory bootstrap only.
- Judge: Manual self-check because no independent LLM judge tool is configured
  for this repo.
- Score: 86/100
- Reasoning: The repo now has goals, architecture, roadmap, specs, tasks,
  acceptance criteria, and write-back rules. The main remaining risk is that
  implementation commands and framework choices are intentionally deferred to
  `TASK-001`.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-001` Python skeleton and SQLite schema.
- Judge: `python3 -m pytest` plus manual inspection of the initialization
  command and schema constraints.
- Score: 90/100
- Reasoning: The repo now has install, database initialization, and test
  commands; all README/SPEC-001 core tables exist with primary keys and
  idempotent uniqueness constraints; tests cover schema creation and asset
  upsert/query. Remaining work belongs to `TASK-002`: AKShare adapters, tracked
  universe, provider failure logs, and normalized ingestion.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-002` AKShare MVP ingestion.
- Judge: `python3 -m pytest` plus live command
  `investment-forecasting ingest mvp --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --start-date 20240520 --end-date 20240522`.
- Score: 91/100
- Reasoning: Ingestion now writes one index, one ETF, and one public fund into
  SQLite through normalized internal fields; duplicate writes are idempotent;
  provider failures write `task_logs`; ETF ingestion falls back from Eastmoney
  to Sina when needed. Remaining work belongs to `TASK-003`: derived features,
  risk metrics, and richer data quality checks.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-003` feature and risk metrics.
- Judge: `python3 -m pytest` plus live command
  `investment-forecasting features calculate --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --start-date 20240520 --end-date 20240522`.
- Score: 90/100
- Reasoning: Feature calculation now reads only stored SQLite prices, computes
  returns, volatility, drawdown, Sharpe, Calmar, win rate, momentum, and a
  simple market state where history permits, persists rows with `features_v1`,
  records task logs, rejects large missing-date gaps, and is idempotent. The
  remaining quant work belongs to `TASK-004`: baseline forecasts, rolling
  backtests, and score persistence.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-004` baseline forecasts, rolling backtests, and scoring.
- Judge: `python3 -m pytest` plus sample commands
  `investment-forecasting forecast run --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --horizons 5,20,60`
  and
  `investment-forecasting backtest run --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --horizons 1 --lookback-days 2`.
- Score: 89/100
- Reasoning: The system now writes latest baseline forecasts for 5/20/60 day
  horizons, records rolling backtest runs/results, stores direction/error/risk
  and overall scores, and has tests that explicitly verify no future rows enter
  prediction history. Remaining work belongs to `TASK-005`: converting
  structured forecasts and historical scores into daily advice with risk
  variants and compliance language.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-005` daily advice generator.
- Judge: `python3 -m pytest` plus smoke command
  `investment-forecasting advice generate --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --date 20260523`.
- Score: 90/100
- Reasoning: The system now generates a traceable `daily_advice` row from
  stored `model_predictions` and `backtest_runs`, includes aggressive,
  balanced, and conservative variants with allocation ranges and add/reduce
  triggers, records assumptions and warnings, rejects prohibited certainty
  language, and logs failures. Remaining work belongs to `TASK-006`: exposing
  these structured capabilities to AI through MCP tools.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-006` MCP-compatible tools.
- Judge: `python3 -m pytest` plus smoke commands
  `investment-forecasting mcp list-tools` and
  `investment-forecasting mcp call get_market_snapshot --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --args '{}'`.
- Score: 88/100
- Reasoning: The system now exposes all SPEC-004 MVP tool names with stable
  JSON schemas, service-backed implementations, structured success/error
  envelopes, and CLI calls that AI agents can consume. The full stdio/network
  MCP transport remains deferred to a thin wrapper over this registry. Remaining
  historical work belonged to `TASK-007`: system-owned daily workflow
  automation.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-007` system-owned daily workflow automation.
- Judge: `python3 -m pytest`, smoke command
  `investment-forecasting daily run --db /tmp/investment_forecasting_task002_live_fallback.sqlite3 --date 20260523 --start-date 20240520 --end-date 20240522 --horizons 1 --lookback-days 2 --skip-ingest`,
  and Codex app automation creation result.
- Score: 90/100
- Reasoning: The system now has a deterministic `daily run` command that
  executes ingestion, feature calculation, forecasts, backtests, and advice
  generation, is safe to rerun against existing data, and records top-level
  success/failure task logs. Historical Codex app scheduling was an early
  convenience, but current product direction assigns scheduling to this
  system and uses Codex only as a role-scoped runtime.
  Remaining work belongs to `TASK-008`: WebUI workbench.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-008` WebUI workbench.
- Judge: `python3 -m pytest`, local server smoke checks, and Playwright desktop
  and mobile screenshots.
- Score: 90/100
- Reasoning: The system now has a local workbench server with dashboard, data,
  funds, predictions, backtests, daily advice, and task-log pages. The UI
  surfaces risk, confidence, model versions, evidence, stale/missing states, and
  job failures without marketing framing. Playwright verified desktop and
  mobile rendering with no console errors or invalid layout boxes. Remaining
  work belongs to `TASK-009`: model calibration enhancements.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-009` model calibration enhancement.
- Judge: `python3 -m pytest` plus smoke command
  `investment-forecasting calibration run --db /tmp/investment_forecasting_calibration_smoke.sqlite3 --date 20260523 --horizons 2 --lookback-days 10`.
- Score: 88/100
- Reasoning: The system now records `model_calibration_reports` comparing
  simple candidate versions across available historical windows, includes
  out-of-sample scores, risk hit rate, return error, stability, promotion
  rationale, and an explainable promoted model version. No ML dependency was
  introduced. Further calibration quality requires a larger real historical
  universe and more market regimes.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-010` README completion audit and gap plan.
- Judge: Manual requirement-to-evidence audit plus `python3 -m pytest`.
- Score: 92/100
- Reasoning: The project now has an explicit audit mapping README requirements
  to current evidence, partial coverage, and missing work. Follow-up tasks
  `TASK-011` through `TASK-017` cover every material remaining gap identified
  by the audit. The overall README goal remains active because those gaps are
  not yet closed.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-011` MCP stdio transport.
- Judge: `python3 -m pytest` including a stdio MCP client smoke test.
- Score: 92/100
- Reasoning: The project now uses the official MCP Python SDK to expose the
  existing eight tool registry entries through stdio transport. Tests verify
  `list_tools`, a read tool, a workflow tool, and structured error payloads
  through an actual MCP client/server subprocess. Remaining README gaps now
  move to `TASK-012`: broader AKShare universe coverage.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-012` broader AKShare universe.
- Judge: `python3 -m pytest` plus live smoke command
  `investment-forecasting ingest mvp --db /tmp/investment_forecasting_task012_expanded_fallback.sqlite3 --start-date 20240520 --end-date 20240522`.
- Score: 91/100
- Reasoning: The tracked universe now covers representative indices, ETFs,
  public funds, and an individual A-share. Live smoke wrote 30 rows across 10
  assets and tests cover universe composition, stock normalization, and stock
  fallback. Remaining README data gaps are fund metadata, macro/environment,
  quality/retry, benchmark scoring, and broader historical calibration.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-013` fund info ingestion.
- Judge: `python3 -m pytest` plus live smoke command
  `investment-forecasting ingest mvp --db /tmp/investment_forecasting_task013_fund_info.sqlite3 --start-date 20240520 --end-date 20240522`.
- Score: 91/100
- Reasoning: The system now populates `fund_info` for tracked public funds,
  including fund type, manager, scale, fee proxy, benchmark/strategy/objective,
  and stage-return JSON where AKShare provides it. MCP fund metrics and the
  WebUI fund page surface the metadata. Remaining README gaps move to market
  environment data, reliability/quality, benchmark scoring, and larger
  calibration windows.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-014` market environment data.
- Judge: `python3 -m pytest` plus smoke commands over the expanded universe
  from 2024-04-01 through 2024-05-22.
- Score: 91/100
- Reasoning: The system now stores and surfaces market environment proxies for
  index trend, breadth, liquidity heat, stock-bond comparison, and sentiment.
  The daily workflow calculates snapshots, MCP/WebUI expose them, and daily
  advice links to the snapshot evidence. Remaining README gaps are provider
  quality/retry/cache, benchmark/advice outcome scoring, and larger historical
  calibration.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-015` data quality, retry, and cache metadata.
- Judge: `python3 -m pytest` plus live smoke command
  `investment-forecasting ingest mvp --db /tmp/investment_forecasting_task015_quality.sqlite3 --start-date 20240520 --end-date 20240522`.
- Score: 90/100
- Reasoning: Provider calls now use deterministic retry, existing fallbacks
  remain available, ingestion writes per-asset data-quality reports, and
  workflow/task logs retain partial progress and actionable errors. Full
  point-in-time rollback snapshots remain future enhancement, but MVP
  inspectability and recoverability are materially improved. Remaining README
  gaps are benchmark/advice outcome scoring and larger historical calibration.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-016` benchmark and advice outcome scoring.
- Judge: `python3 -m pytest` plus smoke command
  `investment-forecasting advice score-outcomes --db /tmp/investment_forecasting_task014_market.sqlite3 --horizon-days 5`.
- Score: 91/100
- Reasoning: Backtests now use real stored 沪深300 benchmark returns when
  aligned, and matured advice records can be scored without future leakage once
  outcome observations exist. Remaining README gap is larger multi-regime
  historical calibration.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-017` historical calibration corpus.
- Judge: `python3 -m pytest` plus smoke command
  `investment-forecasting calibration corpus --db /tmp/investment_forecasting_task017_corpus.sqlite3 --start-date 20230101 --end-date 20251231 --date 20260523 --horizons 5,20,60 --lookback-days 60 --skip-ingest`.
- Score: 90/100
- Reasoning: The system now supports an end-to-end historical calibration
  corpus workflow and produced a real three-window 2023-2025 expanded-universe
  calibration report. Benchmark excess and drawdown control are included in
  aggregate model comparison metrics. The only remaining scope question is
  whether README's macro-data wording requires true external macro series for
  the current MVP or can be satisfied by the implemented market-proxy snapshot.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-018` external macro data provider.
- Judge: `python3 -m pytest` plus live FRED smoke command
  `investment-forecasting ingest macro --db /tmp/investment_forecasting_task018_macro.sqlite3 --start-date 20240520 --end-date 20240524 --series DGS10,T10YIE`.
- Score: 92/100
- Reasoning: The repo now has idempotent `macro_observations` persistence, a
  FRED CSV provider, CLI ingestion, market snapshot evidence integration, and
  tests covering ingestion and snapshot behavior. Live FRED validation wrote 10
  observations after the provider was updated to use `certifi` for TLS CA
  resolution. Remaining enhancements are broader Chinese macro coverage and
  richer fund-peer benchmarks.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-040` expert overview duplicate equity/benchmark cleanup.
- Judge: `python3 -m pytest tests/test_web_app.py`.
- Score: 94/100
- Reasoning: `/experts` now labels the overview curve as "专家收益对比",
  removes residual raw scorecard/review queries from the overview render path,
  and tests assert that the overview has no table, benchmark fields, or the
  old "权益曲线与基准" block. The previous overview-level latest-plan table was
  removed so per-expert plans, return curves, benchmark context, and
  reflections are inspected through detail pages.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-040` expert detail duplicate valuation-table cleanup.
- Judge: `python3 -m pytest tests/test_web_app.py`.
- Score: 95/100
- Reasoning: Expert detail pages now keep return visualization in a single
  "收益曲线" section and no longer append a duplicate valuation table beneath
  the curve. Asset totals, invested capital, cash, valuation events, plans,
  reasons, analysis, and reflections remain available through the profile,
  full timeline, plan/execution, and analysis sections.

## Round Evaluation

- Date: 2026-05-23
- Scope: `TASK-026` fund peer benchmark scoring.
- Judge: `python3 -m pytest tests/test_backtest.py tests/test_advice_scoring.py tests/test_db.py`.
- Score: 94/100
- Reasoning: Backtests now select fund peer-average benchmarks from same-bucket
  stored funds before falling back to 沪深300, and result details record
  benchmark identity, source, peer count, and fallback reason. Matured advice
  outcome scoring persists `benchmark_identity` and `benchmark_source` so the
  chosen comparison can be audited.
