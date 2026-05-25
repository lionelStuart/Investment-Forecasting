# Roadmap

## Milestones

### M0: Project Memory Bootstrap

- Scope: Create gstack project-system files, specs, tasks, and initial status.
- Exit Criteria: Agents can start from `AGENT.md`/`repo/AGENTS.md`, find the
  active task, and follow specs with acceptance criteria.

### M1: Local Data Foundation

- Scope: Python project skeleton, SQLite schema, migrations, repository layer,
  AKShare data ingestion, cache/retry, and data quality checks.
- Exit Criteria: A repeatable command initializes SQLite and imports a small
  tracked universe of indices, ETFs, and funds with test coverage.

### M2: Quantitative Baseline

- Scope: Feature calculation, risk metrics, baseline forecasts, rolling
  backtests, and prediction/advice scoring.
- Exit Criteria: The system can produce reproducible 5/20/60-day baseline
  forecasts and historical scores without future leakage.

### M3: AI Integration And Daily Advice

- Scope: MCP tools, daily advice generator, system-owned daily scheduling, and
  task logs.
- Exit Criteria: AI agents can call MCP tools, trigger advice generation, and
  retrieve stored daily advice with risk-profile variants.

### M4: WebUI Workbench

- Scope: Dashboard, data, fund, prediction, backtest, daily advice, and task log
  views.
- Exit Criteria: A user can inspect current advice, supporting data, historical
  scores, and job status in the browser.

### M5: Model Calibration Enhancements

- Scope: Multi-period historical calibration, model version comparisons, and
  optional machine-learning baselines.
- Exit Criteria: More complex models must demonstrate sample-out improvement or
  better risk control than simple baselines.

### M6: Productized Research Experience

- Scope: Timeline, daily brief, product category navigation, category-aware
  screening, red/green market semantics, asset-level prediction cards, and
  grouped run-health summaries.
- Exit Criteria: A user can follow the daily research flow from brief to
  timeline to product categories, market/macro indicators, and evidence
  without scanning raw tables first, including deterministic industry/theme
  labels and theme-level allocation summaries before a full external taxonomy
  is available.

### M7: Expert Committee Virtual Investing

- Scope: Four parallel virtual experts with durable persona names, distinct investment styles,
  initial capital, daily plans, simulated execution, portfolio valuation,
  scorecards, retirement reviews, lessons, replacement hiring, WebUI inspection,
  CLI/MCP operations, and task logs.
- Exit Criteria: A user can compare four active experts' plans, positions,
  returns, risk, scores, failures, lessons, and replacement decisions using
  persisted virtual portfolios and stored evidence.

### M8: Local Phone Communication

- Scope: Adapter-based local-to-phone communication from the Mac workbench,
  starting with iMessage outbound notifications, setup verification, delivery
  policies, message logs, daily/expert templates, WebUI/CLI inspection, and a
  future inbound-command safety design.
- Exit Criteria: The Mac can send opt-in, allowlisted, auditable iMessage
  notifications for daily research and expert events without coupling
  investment logic to a specific channel or breaking workflows when delivery
  fails.

### M9: Jarvis AI Investment Assistant

- Scope: Top-level Jarvis assistant, persisted daily brief, synthesis engine,
  first-screen WebUI, MCP/Agent workflow, and phone-summary template.
- Exit Criteria: A user can open Jarvis and immediately see today's focus
  directions, one-line stance, model predictions, every expert's forecast,
  score, current virtual return, and risk warnings without scanning raw model
  or expert tables.

### M10: AI Interaction Layer Minimum Viable Closure

- Scope: Replace the current deterministic AI-analysis source with a bounded,
  adapter-based AI interaction layer for expert independent analysis and Jarvis
  daily financial analysis. Keep structured evidence packets, persisted
  outputs, validation gates, deterministic fallback, and WebUI/MCP traceability
  intact.
- Exit Criteria: One configured AI provider can generate structured expert and
  Jarvis analyses from stored evidence packets in a dry-run-safe workflow;
  invalid or unsupported model output is rejected; Jarvis applies confidence
  gates to extreme forecasts; `/jarvis` shows whether the analysis came from
  the real AI provider or deterministic fallback; all new architecture and code
  index entries are updated. Stop the iteration here unless a fresh product
  review creates the next milestone.

### M11: Jarvis Consumer Information Architecture

- Scope: Reorganize the WebUI from 11 module-oriented workbench entries into
  five user-journey entries: 今日简报, 机会池, 专家团, 证据, 设置. Keep existing
  technical routes and raw evidence available as drill-downs, but remove them
  from first-level consumer navigation.
- Exit Criteria: A non-technical user can start from Jarvis 今日简报, understand
  today's conclusion, inspect opportunities, compare expert views, open
  evidence only when needed, and adjust settings/system health without seeing
  developer-oriented pages in the primary nav. The old 11-entry workbench
  navigation is gone from the default UI.
- Standing Rule: This milestone is not closed merely as an implementation
  task; it becomes an ongoing product constraint recorded in `ADR-007`.
  Future roadmap items must preserve the five-entry IA unless a new
  product-review milestone changes it.

### M12: News Evidence Retrieval MVP

- Scope: Add optional Tushare news-flash ingestion, provider-neutral news
  persistence, source/time/asset/theme/event/sentiment indexes, deterministic
  aggregate features, and a bounded `search_news_evidence` retrieval tool for
  Codex AI/Jarvis.
- Exit Criteria: Codex AI can retrieve relevant news by source, date range,
  asset, theme, event type, sentiment, and keyword; results include evidence
  IDs, timestamps, excerpts, tags, and match reasons; prompts do not receive
  unbounded news dumps; news features are time-safe and optional.

### M13: Model Reliability Upgrade

- Status: Completed through `TASK-074` to `TASK-079`; product review should
  happen before changing the primary model away from `baseline_mean_v1`.
- Scope: Reframe forecasting from point-return prediction to model reliability:
  cross-sectional ranking, financial-grade validation, interpretable candidate
  models, shared model evidence packets, expert multi-model review, Jarvis
  model-risk gates, and model promotion/demotion governance.
- Exit Criteria: Jarvis can explain which model signals are usable, weak,
  stale, degraded, or watch-only; candidate models are compared against
  `baseline_mean_v1` with IC/Rank IC/bucket-spread/same-category metrics; no
  model becomes primary without explicit promotion evidence.

### M14: System-Scheduled Codex Agent Runtime

- Status: Completed through `TASK-080` to `TASK-084`: runtime access, audit
  tables, fake/local Codex CLI adapters, project-local artifacts,
  readiness/smoke commands, role manifests, agent tool-call audit,
  domain/function skills, expert prompt rendering, expert T-day execution, and
  Jarvis T+1 readiness/brief persistence are in place.
- Scope: Replace the ambiguous "Codex automation" product wording with a
  system-owned scheduling and Codex runtime access layer. The system prepares
  data/model/news evidence, invokes one role-scoped Codex agent per active
  expert for T-day virtual actions, records outputs through MCP/API
  submission tools, then invokes Jarvis at T+1 after expert actions are
  complete or explicitly skipped/failed.
- Exit Criteria: Expert and Jarvis runs are auditable `agent_runs`; role-scoped
  tool manifests prevent direct database/WebUI/shell mutation; domain/function
  skills are separated by capability; expert and Jarvis each have different
  role overview skills and skill bundles; `codex_agent_runtime_v1` defines
  launch request/result/status and adapter actions; expert T actions complete
  before Jarvis T+1 readiness passes; Jarvis briefs link to the producing
  agent run and clearly report incomplete expert evidence.

### M15: System Scheduler And Incremental Updates

- Status: Complete for the MVP slice. `TASK-085` removed Codex automation from
  the operational refresh path, and `TASK-086` through `TASK-089` added
  persisted scheduler jobs/runs/watermarks, provider backoff state, fixed sync
  timing, scheduler CLI commands, incremental work planning, provider
  request-budget/backoff enforcement, and CLI/WebUI/MCP health surfaces.
- Scope: Remove Codex app automation from the operational update path and
  implement a system-owned scheduler for hourly incremental data/news updates.
  Jobs use watermarks, bounded windows, provider request caps, backoff, and
  readiness gates so the system fills gaps without repeatedly fetching full
  history or pressuring provider interfaces.
- Exit Criteria: No active Codex automation is required for refresh; scheduler
  jobs and runs are persisted; hourly news/data jobs update only missing
  windows; provider throttling creates backoff/deferred states; CLI/WebUI/MCP
  surfaces show freshness, watermarks, request budgets, and failures.

### M16: YTD Model Accuracy And Confidence Replay Audit

- Status: Planned through `SPEC-014` and `TASK-090` through `TASK-092`.
- Scope: Re-run current-year daily predictions from already stored historical
  data, persist a separate replay corpus, score only matured prediction
  windows, diagnose model/horizon/asset-group failures, and produce ranked
  model tuning recommendations for accuracy and confidence calibration. This
  phase is strictly model-layer validation; it does not evaluate expert
  committee predictions, Jarvis daily conclusions, investment advice, or
  portfolio outcomes.
- Exit Criteria: A local command can replay 2026 year-to-date predictions
  without network calls or production prediction overwrite; matured predictions
  are scored with direction/rank/risk/benchmark/calibration metrics; pending
  horizons are separated from failures; CLI exposes the latest replay report
  and tuning recommendations; no expert/Jarvis/advice surface changes in this
  phase.

## Backlog Themes

- Tushare Pro enhancement provider.
- Macro and overseas indicators.
- Portfolio optimization and target-volatility allocation.
- Simulated portfolio tracking.
- Expert committee virtual investing with expert styles, virtual execution,
  scoring, retirement, lessons, and replacement hiring.
- Local Mac to phone communication adapters, starting with iMessage.
- Jarvis AI investment assistant as the final user-facing synthesis layer.
- Jarvis consumer information architecture: five task-based primary entries
  instead of module-based workbench navigation.
- AI interaction layer for expert independent analysis and Jarvis daily
  financial analysis, bounded by evidence packets and validation.
- News evidence retrieval: optional Tushare news ingestion, indexed searchable
  evidence, and MCP/Codex AI retrieval tools before news enters Jarvis
  reasoning.
- Model reliability upgrade: rank-based targets, financial validation,
  interpretable candidate models, model evidence packets, and Jarvis model-risk
  gates.
- System-scheduled Codex agent runtime: role-scoped expert/Jarvis Codex runs
  launched by system triggers, using project skills, MCP/API tools, audited
  tool calls, and validated structured submissions.
- System scheduler and incremental updates: hourly bounded news/data refresh,
  per-source watermarks, provider budgets/backoff, and health surfaces without
  Codex app automation.
- YTD model accuracy and confidence replay audit: rebuild this year's daily
  model prediction evidence from stored local data, score matured outcomes,
  and turn accuracy/confidence diagnostics into testable tuning experiments.
- User risk profiles and investment horizon settings.
- Model monitoring and drift detection.
- Productized WebUI flow: timeline, category-first screening, red/green market
  semantics, and asset-level forecast cards.
- Provider access politeness: rate limits, jitter, incremental updates, and
  throttling diagnostics so residential broadband ingestion avoids unnecessary
  temporary ban or anti-bot risk.

## Development Goals From Current Roadmap

1. Personalization: persist active user risk preference and investment horizon,
   then apply them to daily advice and WebUI controls.
2. Productized Research Flow: add timeline, daily brief, product categories,
   fund filters, red/green market semantics, and asset-level prediction cards
   so expanded data becomes usable before adding more advanced portfolio logic.
   Market snapshots and macro observations now also have a dedicated `/market`
   inspection page.
3. Portfolio Tracking: completed for the generic simulated portfolio foundation
   with stored portfolios, positions, transactions, daily valuation, CLI
   operations, and `/portfolios` inspection.
4. Allocation Engine: completed the first target-volatility allocation proposal
   path, bounded by user max-equity/min-cash constraints and backed by stored
   feature risk metrics. Daily advice now also includes correlation
   risk-budget evidence from stored prices so users can inspect approximate
   bucket risk contribution and diversification before raw JSON.
5. Model Monitoring: completed first model-version health reports with score
   drift, stale input checks, benchmark excess, daily workflow logs, and WebUI
   degraded-state cards.
6. Provider Expansion: completed optional Tushare Pro provider selection for
   users with credentials while keeping AKShare as the free default. Richer
   Chinese macro enhancements remain future work. Fund-peer benchmark scoring
   now uses stored same-bucket peer averages with explicit 沪深300 fallback.
   A first deterministic industry/theme classification layer is complete.
   Capital-flow observations now have a provider-neutral table, AKShare
   ingestion command, `/market` inspection surface, and advice/Jarvis evidence
   links. Fund-holding observations now have a provider-neutral table, AKShare
   ingestion command, `/funds` inspection surface, and a deterministic
   theme-level look-through exposure summary for the current fund filter; true
   provider-backed industry tables and deeper bond/sector analytics remain
   future enhancements. `/themes` now aggregates theme-level coverage,
   risk/return, and representative assets for allocation research.
7. Polite Ingestion: completed for the default AKShare path with sequential
   provider calls, configurable delay/jitter, retry backoff diagnostics,
   incremental history ranges, and task-log throttling/empty-response warnings.
8. Expert Committee: completed the persisted expert roster, virtual
   portfolios, daily plans, scoring/retirement/hiring loop, and WebUI/MCP
   inspection.
9. Local Phone Communication: completed the channel-neutral communication
   service, iMessage outbound adapter, safe message templates, WebUI/CLI setup
   inspection, and future inbound-command design. iMessage remains outbound
   only.
10. Jarvis Assistant: completed the persisted brief, deterministic synthesis,
    WebUI, MCP, phone summary, and deterministic AI-analysis orchestration.
    The remaining product gap is real provider-backed AI interaction behind
    the existing evidence and validation contract.
11. Jarvis Consumer IA: before continuing deeper AI implementation, make the
    product structure match the intended assistant experience. Collapse the
    first-level navigation to 今日简报 / 机会池 / 专家团 / 证据 / 设置, and move
    timeline, raw predictions, backtests, technical data, and task logs into
    secondary tabs or details.
12. News Evidence Retrieval MVP: before freezing the Jarvis/expert prompt
    schema, add a searchable news evidence layer so AI can retrieve relevant
    news on demand instead of receiving raw news in every prompt.
13. AI Interaction Layer Closure: implement only the smallest real AI-provider
    path needed for expert and Jarvis analyses. Do not add new market-data
    providers, new optimization engines, new experts, live trading, inbound
    phone commands, or broad UI redesign in this milestone. The work is done
    when `TASK-061` through `TASK-065` pass their acceptance criteria and a
    product review confirms Jarvis can display a provider-backed daily brief
    with evidence links, confidence gates, fallback status, and safe language.
14. Model Reliability Upgrade: use `TASK-074` through `TASK-079` to make model
    evidence more honest and measurable. Success means Jarvis can reject a
    tempting signal with clear reasons, not that the system promises higher
    returns.
15. Codex Agent Runtime: use `TASK-080` through `TASK-084` to implement the
    actual product AI shape. The system owns scheduling and invokes Codex as a
    runtime for role-specific tasks. Experts run first on T day and persist
    virtual actions; Jarvis runs on T+1 only after expert outcomes are complete
    or explicitly skipped/failed. This slice is complete; future work should
    improve tool-rich multi-turn evidence gathering rather than reopening the
    runtime boundary.
16. System Scheduler: use `TASK-085` through `TASK-089` to replace Codex app
    automation with system-owned hourly incremental updates. Success means
    data/news freshness improves through watermarks and provider-safety policy,
    not through repeated full-history calls. MVP scheduler implementation is
    complete; product should next decide which provider jobs may switch from
    planned execution to live provider execution by default.
17. YTD Model Accuracy And Confidence Replay Audit: use `TASK-090` through
    `TASK-092` to rebuild this year's daily model prediction record from local
    historical data, score only matured outcomes, and produce concrete model
    tuning directions. Success means the team can say which horizons, model
    versions, asset groups, and regimes are accurate, inaccurate,
    overconfident, underconfident, or insufficient-sample before changing any
    algorithm defaults. Expert/Jarvis/advice prediction evaluation is outside
    this phase.
