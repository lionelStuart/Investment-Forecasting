# Project Agent Protocol

## Purpose

Use this repository as the source of truth for project context, active work, and
durable decisions for the Investment Forecasting system.

## Mandatory Read Order

Read in this order before implementation:

1. `PROJECT.md`
2. `STATUS.md`
3. `INDEX.md`
4. The active task in `tasks/`
5. The task-linked spec in `specs/`
6. Only the architecture, decision, or skill files referenced by that task or spec

Do not read every markdown file by default.

## Execution Rules

Follow this loop for every non-trivial development round:

1. Read the active task and required context.
2. Inspect existing code capabilities before designing new code. Prefer
   extending current modules, helpers, schemas, and tests over adding parallel
   implementations.
3. Produce or confirm a small design plan before editing. The plan must state
   reused code paths, touched modules, expected data flow, test coverage, and
   deployment/restart impact.
   For WebUI work, the plan must also state which Jarvis primary entry owns the
   change: 今日简报, 机会池, 专家团, 证据, or 设置.
4. Evaluate whether the change affects architecture, module boundaries, schema,
   public commands, WebUI routes, MCP tools, or automation. If yes, update the
   relevant design docs as part of the task.
5. Modify only the scoped files listed by the task or justified by the design
   plan.
6. Run the task test plan.
7. Restart or deploy the local service when the task changes runtime behavior.
8. Update the task progress, `STATUS.md`, and `INDEX.md`.
9. Record decisions, learnings, or reusable skills when durable context changes.

## Constraints

- Do not work without a task unless the repository is being bootstrapped.
- Do not modify unrelated files.
- Do not add a new module, route, command, table, task family, or abstraction
  before checking whether existing code already provides the capability.
- Do not add a new first-level WebUI navigation item. The consumer product
  navigation is fixed to 今日简报, 机会池, 专家团, 证据, 设置 unless a product-review
  task and ADR explicitly change it.
- Do not turn technical routes such as timeline, predictions, backtests, data,
  logs, market, funds, or raw settings into primary consumer navigation. They
  must stay under 机会池, 证据, 设置, or direct technical links.
- User-facing UI copy should present the product as Jarvis 理财助理. Avoid
  making "投资预测工作台" or similar developer-workbench language the primary
  brand or first-screen framing.
- Avoid code growth through duplicate helpers, ad hoc SQL, route-specific
  formatting, or one-off view logic when a shared local pattern exists.
- Do not introduce a new dependency, framework, data vendor, or storage engine
  without an ADR in `decisions/`.
- Do not output capital protection, guaranteed return, or certain-profit claims.
- All generated advice must be traceable to stored data, model output,
  backtest evidence, assumptions, and risk warnings.
- Expert committee features must remain virtual research simulations. Before
  implementing expert plans, scoring, retirement, or replacement hiring, inspect
  existing advice, forecast, backtest, portfolio, daily workflow, MCP, WebUI,
  and task-log capabilities and reuse them where possible.
- Phone communication features must use the communication adapter layer. Do not
  call iMessage, AppleScript, Messages, SMS, email, or push APIs directly from
  investment, expert, daily workflow, or WebUI logic. Sends must be opt-in,
  allowlisted, idempotent where practical, rate-limited, auditable, and safe.
  Actual iMessage/AppleScript execution must stay isolated in
  `src/investment_forecasting/communication/imessage.py`.
- Jarvis features must be built as the top-level synthesis layer over existing
  market, model, advice, expert, portfolio, user-preference, task-log, and
  communication capabilities. Do not create a separate unsupported prediction
  engine or hide source evidence behind opaque prose.
- Codex runtime work must follow `SPEC-012` and `ADR-008`: the system owns
  scheduling, readiness, persistence, audit, validation, and UI. Codex is only
  a role-scoped runtime invoked by the system with project skills, generated
  prompts, allowed MCP/API tools, and structured output contracts.
- Runtime implementation must follow `codex_agent_runtime_v1`: prepare, start,
  poll, cancel, and collect result through an adapter boundary. Prefer
  tool-based submission back into system APIs; artifact fallback is allowed
  only when the system validates and persists the artifact through the same
  service validators.
- Scheduler work must follow `SPEC-013` and `ADR-009`: the system owns hourly
  incremental updates, watermarks, provider request budgets, and backoff.
  Codex app automation must not be used for data/news refresh.
- Do not schedule full-history ingestion. Hourly jobs must compute missing
  windows from stored watermarks, cap request sizes, skip current assets/scopes,
  and defer politely when provider backoff is active.
- Model replay/tuning work must follow `SPEC-014`: use stored local history
  only, replay each prediction with point-in-time inputs, persist replay rows
  separately from operational `model_predictions`, score only matured horizons,
  and produce model accuracy/confidence tuning recommendations before changing
  model defaults. Do not include expert committee predictions, Jarvis
  conclusions, investment advice, MCP/WebUI surfaces, or portfolio outcomes in
  this phase.
- Do not confuse Codex scheduled script automation, `ai_providers` provider
  calls, and Codex agent runtime. Expert/Jarvis product reasoning is intended
  to be agentic through the runtime access layer, while provider calls are only
  fallback or simpler bounded analysis surfaces.
- Do not expose one giant all-purpose project skill to every role. System
  capabilities must be documented as domain/function skills, then composed by
  separate expert and Jarvis role overview skills with different allowed skill
  bundles and tool manifests.
- Expert agent runs happen before Jarvis: active experts must complete or
  explicitly skip/fail their T-day virtual investment actions before Jarvis can
  run the T+1 daily investment analysis.
- Codex agents must not write SQLite directly, scrape WebUI pages as evidence,
  call shell commands to mutate product state, bypass system validation, or use
  tools outside their role-scoped manifest.
- Jarvis UI features must preserve the daily decision journey: 今天怎么看,
  为什么, 能不能信, 关注哪些资产, 专家是否一致, 风险边界是什么.
- When network access or downloads fail, agents may retry with:
  `https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890 all_proxy=socks5://127.0.0.1:7890`.

## Mandatory End-Of-Task Update

After implementation, update all applicable files:

1. The active task's progress and result
2. `STATUS.md`
3. `INDEX.md` task status
4. `ARCHITECTURE.md` if boundaries, data flow, modules, runtime surfaces, or
   deployment shape changed
5. `CODE_INDEX.md` if files, commands, routes, tables, or key entry points were
   added, removed, renamed, or materially repurposed
6. The linked spec if behavior or acceptance changed
7. `decisions/` if a durable technical choice was made
8. `learnings/` if a new problem or debugging fact was discovered
9. `skills/` if the learning became a reusable procedure
10. Restart the background WebUI service with `scripts/restart_web.sh` so the
   local app is serving the latest completed task.
