# SPEC-012: Codex Agent Runtime Orchestration

## Status

draft

## Goal

Define the real product AI shape for Jarvis and the expert committee:
the Investment Forecasting system owns data, APIs, persistence, scheduling,
audit, validation, and UI. Codex is not the scheduler and not a passive
provider call. Codex is an agent runtime that the system invokes at specific
business moments with project skills, role prompts, and bounded MCP/API tools.

Each expert committee member must behave as an agentic virtual investor with
its own mandate, prompt, skill context, portfolio state, and allowed tools.
Jarvis must behave as a higher-level agent that uses the same system tools plus
the completed expert outputs to produce the next-day daily investment brief.

## Product Shape

The product contains three distinct layers:

- System layer:
  - owns scheduled triggers;
  - ingests data;
  - runs models and reliability checks;
  - exposes stable MCP/API tools;
  - persists expert actions, Jarvis briefs, task logs, and audit records;
  - validates safety, evidence links, and output schemas.
- Codex runtime access layer:
  - starts a Codex agent run for a specific role and task;
  - injects the appropriate project skill and role prompt;
  - provides tool access through MCP/API only;
  - collects structured output;
  - writes or submits output back through system APIs.
- Agent role layer:
  - expert agents each reason in their own style and produce daily virtual
    investment actions;
  - Jarvis agent synthesizes market, model, news, task-health, and completed
    expert evidence into a T+1 daily brief.

The current daily Codex automation is not the target product shape. It may be
replaced or bypassed by system-owned scheduling that invokes the Codex runtime
through an explicit access layer.

## Scheduling Semantics

Scheduling belongs to the Investment Forecasting system.

Minimum MVP schedule:

1. T day system preparation
   - update market data, features, model predictions, model reliability, news
     indexes, task health, and user preferences;
   - expose all prepared evidence through MCP/API tools.
2. T day expert actions
   - invoke one Codex agent run per active expert;
   - each expert reads only allowed system tools and its own portfolio,
     mandate, scorecard, lessons, and candidate evidence;
   - each expert submits one structured virtual plan/action for T;
   - the system validates and records the plan, simulated execution, and task
     log.
3. T+1 Jarvis analysis
   - invoke Jarvis after T expert actions and simulated execution records are
     available;
   - Jarvis reads system market/model/news evidence, expert plans, expert
     actions, expert scorecards, virtual returns, and task health;
   - Jarvis produces the T+1 day-level investment brief;
   - the system validates and persists the brief, then renders WebUI and
     optional phone summaries from persisted output.

Jarvis must not run before the expert committee has either completed T actions
or recorded explicit skipped/failed states for each required active expert.

## Required MCP/API Capability Groups

The system must provide stable tools for Codex agents. Tools should be grouped
by capability rather than by UI page.

Read tools:

- market snapshot, macro observations, capital-flow evidence, task health;
- asset list, asset history, fund metrics, theme/category summaries;
- model predictions, reliability packets, backtests, model governance state;
- searchable news evidence with source/time/asset/theme/event/sentiment
  filters;
- expert roster, mandate, current portfolio, latest valuation, scorecard,
  lessons, and prior plans;
- Jarvis historical briefs and prior risk warnings.

Action/submission tools:

- submit expert analysis draft;
- submit expert virtual plan/action;
- record expert skipped/failed action with reason;
- submit Jarvis analysis draft;
- submit Jarvis daily brief;
- request validation preview for an expert or Jarvis output before final
  persistence.

Operational tools:

- start/complete agent run audit record;
- list pending expert runs for a date;
- list Jarvis readiness for T+1;
- return allowed tool manifest for a role.

No agent may write directly to SQLite, shell out to mutate investment records,
or bypass system validation.

## Runtime Interaction Protocol

The runtime protocol is system-initiated and role-scoped. It is not a chat
session protocol and not a Codex-owned schedule.

### Runtime Adapter Boundary

`agent_runtime` must expose an adapter interface that can be implemented by a
real Codex launcher or a deterministic test double.

Minimum adapter operations:

- `prepare_run(request) -> AgentRunHandle`
  - creates or resolves the persisted `agent_runs` row;
  - renders the role prompt;
  - resolves the role overview skill and domain/function skill bundle;
  - resolves the allowed MCP/API tool manifest;
  - writes an immutable launch request snapshot for audit.
- `start_run(agent_run_id) -> AgentRunHandle`
  - marks the run as running;
  - launches or simulates the Codex runtime;
  - records runtime/session metadata when available.
- `poll_run(agent_run_id) -> AgentRunStatus`
  - returns current status, heartbeat, token/runtime metadata when available,
    and last observed error.
- `cancel_run(agent_run_id, reason) -> AgentRunStatus`
  - marks the run cancelled or failed through system state;
  - does not rely on Codex to self-clean product records.
- `collect_result(agent_run_id) -> AgentRunResult`
  - reads the submitted system record, or in fallback mode reads a structured
    artifact for validation and system submission.

The real launcher is allowed to vary by environment, but every launcher must
conform to this adapter contract. The first implementation may be a local
process or Codex CLI/app bridge; tests must use a fake adapter.

### Launch Request

Each Codex runtime launch request must be serializable JSON. Required fields:

```json
{
  "protocol_version": "codex_agent_runtime_v1",
  "agent_run_id": 123,
  "role_type": "expert",
  "role_key": "bai_gui",
  "run_date": "2026-05-24",
  "target_evidence_date": "2026-05-24",
  "trigger_reason": "daily_expert_action",
  "overview_skill": "investment-expert-agent",
  "skill_bundle": [
    "investment-market-data-skill",
    "investment-model-evidence-skill",
    "investment-news-evidence-skill",
    "investment-asset-research-skill",
    "investment-expert-portfolio-skill",
    "investment-virtual-action-skill",
    "investment-agent-output-contract"
  ],
  "prompt_ref": {
    "kind": "persisted",
    "prompt_hash": "sha256:...",
    "prompt_snapshot_id": 456
  },
  "tool_manifest_ref": {
    "kind": "inline_or_persisted",
    "manifest_hash": "sha256:..."
  },
  "output_contract": {
    "schema_version": "expert_agent_output_v1",
    "submission_tool": "submit_expert_virtual_action"
  },
  "runtime_policy": {
    "timeout_seconds": 900,
    "max_tool_calls": 40,
    "max_retries": 1,
    "require_submission_tool": true
  }
}
```

For Jarvis, `role_type` must be `jarvis`, `role_key` must be `jarvis`,
`run_date` must be T+1, `target_evidence_date` must be T, and the overview
skill must be `jarvis-daily-agent`.

### Runtime Tool Contract

Codex receives tool access only through the role-scoped MCP/API manifest.

Every tool call made during a runtime run must include:

- `agent_run_id`;
- `role_type`;
- `role_key`;
- tool arguments;
- idempotency key for submission tools;
- optional `evidence_scope` when reading date/asset/model/news data.

The system must reject tool calls when:

- `agent_run_id` is missing or not running;
- the tool is not listed in the role manifest;
- the call attempts to access a future date beyond the run's evidence scope;
- the role attempts a submission reserved for another role;
- the call exceeds runtime policy limits.

### Submission Protocol

Preferred MVP mode: Codex must submit output by calling the appropriate
submission tool.

Expert successful submission:

- `submit_expert_analysis_draft`;
- then `submit_expert_virtual_action`, or one combined submission tool if the
  implementation keeps analysis and action atomic.

Expert non-success submission:

- `record_expert_skipped_action`; or
- `record_expert_failed_action`.

Jarvis successful submission:

- `submit_jarvis_analysis_draft`;
- then `submit_jarvis_daily_brief`, or one combined submission tool if the
  implementation keeps analysis and brief persistence atomic.

Fallback mode: if the selected Codex launcher cannot call MCP/API tools
directly, it may write one structured JSON artifact. The system must then read
that artifact, validate it, submit it through the same service-layer validators,
and mark the run `completed_via_artifact`. Artifact fallback is not allowed to
write database rows directly or skip validation.

### Response And Result Shape

`AgentRunResult` must be system-derived, not merely whatever Codex printed.

Minimum result fields:

```json
{
  "agent_run_id": 123,
  "status": "completed",
  "role_type": "expert",
  "role_key": "bai_gui",
  "run_date": "2026-05-24",
  "target_evidence_date": "2026-05-24",
  "submission_mode": "tool",
  "submitted_record_type": "expert_plan",
  "submitted_record_id": 789,
  "ai_analysis_id": 456,
  "validation_status": "passed",
  "tool_call_count": 18,
  "runtime_metadata": {
    "adapter": "fake",
    "session_id": "test-session"
  },
  "error": null
}
```

Jarvis results must link to `jarvis_daily_brief.id` and the producing
`ai_analysis_records.id` when available.

### State Machine

Allowed `agent_runs.status` values:

- `pending`: run record exists but runtime has not started;
- `running`: runtime has been launched;
- `submitted`: runtime called a submission tool, pending validation/finalization;
- `completed`: submitted output passed validation and was persisted;
- `completed_via_artifact`: structured artifact passed validation and was
  persisted by the system;
- `skipped`: role intentionally produced a no-run/skipped outcome accepted by
  the system;
- `validation_failed`: output was received but failed schema, evidence, safety,
  readiness, or risk validation;
- `failed`: runtime or system error prevented usable output;
- `cancelled`: system cancelled the run before completion;
- `timed_out`: runtime exceeded configured timeout.

Terminal states are `completed`, `completed_via_artifact`, `skipped`,
`validation_failed`, `failed`, `cancelled`, and `timed_out`.

Jarvis readiness may treat expert terminal states as complete only when they
are explicit and audited. Pending, running, or missing expert runs block Jarvis.

### Timeout, Retry, And Idempotency

- Expert agent runs should default to a bounded timeout such as 15 minutes in
  MVP.
- Jarvis agent runs should default to a bounded timeout such as 20 minutes in
  MVP.
- A timed-out run may be retried once by creating a new version or retry number
  for the same role/date/evidence date.
- Submission tools must be idempotent by `(agent_run_id, submission_type,
  idempotency_key)`.
- A completed run must not be overwritten by a retry unless a new version is
  created.

### Security And Privacy

- Runtime requests must not include raw database dumps.
- Runtime requests must not include secrets, provider tokens, iMessage
  addresses, or private communication payloads.
- Tool manifests must be generated server-side and cannot be expanded by the
  agent.
- Prompt snapshots and tool manifests should be hashed so a future audit can
  prove what the role was asked to do.

## Project Skill Requirements

The project must provide Codex-loadable skills that encode system-specific
behavior.

Skills must be layered. The project should not expose one giant all-purpose
skill to every role.

### Domain And Function Skills

Domain/function skills describe one bounded capability area and its allowed
MCP/API tools. They are reusable by expert and Jarvis role skills, but role
skills decide which ones are available for a run.

Minimum domain/function skills:

- `investment-market-data-skill`
  - market snapshots, macro observations, capital-flow observations, task
    freshness, and data-health interpretation.
- `investment-model-evidence-skill`
  - model predictions, reliability packets, backtests, model governance,
    confidence gates, and watch-only interpretation.
- `investment-news-evidence-skill`
  - bounded `search_news_evidence` usage, source/time/asset/theme/event/
    sentiment filters, evidence IDs, and no bulk news injection.
- `investment-asset-research-skill`
  - asset list, asset history, fund metrics, category/theme summaries, and
    opportunity-pool evidence reading.
- `investment-expert-portfolio-skill`
  - expert mandate, current virtual portfolio, holdings, cash, prior plans,
    latest valuation, scorecards, lifecycle state, and lessons.
- `investment-virtual-action-skill`
  - expert virtual plan/action submission, no_trade/skipped/failed outcomes,
    risk checks, cash/price constraints, and simulated execution boundaries.
- `investment-jarvis-synthesis-skill`
  - Jarvis-only synthesis of system facts, model evidence, expert outputs,
    expert performance, user preferences, watch triggers, and daily brief
    structure.
- `investment-agent-output-contract`
  - shared structured JSON fields, evidence IDs, compliance wording,
    validation failures, retry/fallback behavior, and forbidden claims.

### Role Overview Skills

Role overview skills are the only intended skill entry points for Codex agent
runs. They compose the relevant domain/function skills, load the role prompt,
declare the allowed tool manifest, and define the stop condition for the run.

Minimum role overview skills:

- `investment-expert-agent`
  - used by one expert at a time;
  - acts as the expert role overview skill;
  - composes only expert-safe domain/function skills, normally market data,
    model evidence, news evidence, asset research, expert portfolio, virtual
    action, and output contract;
  - loads the expert mandate, style, risk limits, current virtual portfolio,
    allowed tools, output schema, safety rules, and stop conditions;
  - requires evidence citations and explicit action/no-action rationale.
- `jarvis-daily-agent`
  - used by Jarvis at T+1;
  - acts as the Jarvis role overview skill;
  - composes Jarvis-safe domain/function skills, normally market data, model
    evidence, news evidence, asset research, expert portfolio read-only,
    Jarvis synthesis, and output contract;
  - loads the Jarvis synthesis role, available evidence groups, expert outputs,
    risk wording, output schema, and stop conditions;
  - requires separation of system facts, model evidence, expert views, Jarvis
    synthesis, watch triggers, and risk boundaries.

Skills must tell Codex to use MCP/API tools for evidence. They must not ask
Codex to scrape WebUI pages, query SQLite directly, or invent unavailable
market facts.

Domain/function skills must not grant capability by themselves. Capability is
granted only when a role overview skill and role-scoped tool manifest include
that skill for the current agent run.

## Expert Prompt Template Requirements

Each expert prompt must be generated from persisted expert fields and include:

- expert identity, style label, mandate, focus weights, risk budget, max
  drawdown tolerance, allowed asset categories, default cash buffer, and
  lifecycle state;
- current virtual cash, holdings, valuation, scorecard, prior action, and
  relevant lessons;
- required tool-use policy:
  - inspect model candidates and reliability packets;
  - inspect market/task freshness;
  - optionally search news evidence when asset/theme-specific context matters;
  - inspect current portfolio before proposing an action;
- output schema:
  - thesis;
  - selected and rejected candidates;
  - evidence IDs;
  - news evidence IDs if used;
  - proposed action: buy, sell, rebalance, hold, or no_trade;
  - target asset/weight/amount when applicable;
  - risk objections;
  - confidence;
  - stop condition if evidence is missing or stale.

The expert must submit exactly one action outcome for the run date: a valid
virtual plan/action, or a skipped/failed action with a structured reason.

## Jarvis Prompt Template Requirements

The Jarvis prompt must include:

- Jarvis role as the final consumer-facing investment assistant;
- T+1 run context and the T expert action date being reviewed;
- required system evidence groups:
  - market facts;
  - model predictions and reliability gates;
  - backtest/model governance;
  - news evidence retrieved through tools when relevant;
  - expert plans/actions;
  - expert scores, current returns, drawdowns, lifecycle states, and lessons;
  - data freshness and task health;
  - user risk preference and communication context;
- required output shape:
  - today's focus directions;
  - one-line stance;
  - model view;
  - expert consensus and disagreement;
  - expert score/current-return summary;
  - Jarvis synthesis;
  - watch triggers;
  - risk boundaries;
  - evidence references.

Jarvis must not hide expert failures, missing evidence, model degradation, or
stale data. If expert outputs are incomplete, Jarvis must say so and downgrade
confidence rather than fabricating consensus.

## Persistence And Audit Requirements

Agent runs must be first-class audited records.

MVP persistence should support:

- `agent_runs`
  - protocol version;
  - role type: expert or jarvis;
  - role key: expert key or jarvis;
  - run date;
  - target evidence date;
  - trigger reason;
  - status;
  - overview skill and skill bundle;
  - prompt hash/snapshot reference;
  - tool manifest hash/snapshot reference;
  - output schema version;
  - submission mode;
  - submitted record type and ID when completed;
  - Codex runtime/session metadata;
  - started/completed timestamps;
  - error/fallback reason.
- `agent_tool_calls`
  - agent run ID;
  - role type and role key;
  - tool name;
  - sanitized arguments;
  - status;
  - idempotency key when present;
  - referenced evidence IDs;
  - timestamps and error.
- links from expert plans and Jarvis briefs back to the agent run that produced
  them.

Existing `ai_analysis_records` can remain as the evidence-backed analysis
record, but it must not be the only runtime audit surface once Codex agent
runs are introduced.

## Validation Requirements

All agent outputs must pass system validation before they affect product
state:

- required fields and JSON schema;
- no unsupported prediction/news/model/expert evidence IDs;
- no certain-return, capital-protection, or real-money trade language;
- expert action respects mandate, risk limits, cash, price availability, and
  virtual execution rules;
- Jarvis brief references completed expert outputs or explicit skipped states;
- Jarvis T+1 readiness gate passes before final brief generation.

Validation failure should produce an auditable failed/skipped run and a clear
retry surface. It should not silently create a deterministic plan that appears
agentic.

## Non-Goals

- No live trading or brokerage execution.
- No Codex-owned scheduler.
- No direct SQLite writes by Codex.
- No WebUI scraping as an evidence source.
- No hidden prompt-only expert memory.
- No multi-agent chat room or open-ended debate loop in the MVP.
- No unlimited tool access; tools must be role-scoped.
- No guarantee that agentic reasoning improves returns.

## Acceptance Criteria

- The project documents distinguish system-owned scheduling from Codex runtime
  execution.
- A runtime access layer can launch or simulate one role-scoped Codex agent run
  with a skill, prompt, allowed tool manifest, and output schema.
- Domain/function skills are documented separately from expert and Jarvis role
  overview skills.
- Expert and Jarvis agent runs load different overview skills and different
  allowed skill/tool bundles.
- Each active expert can be represented as a pending/completed/failed agent run
  for a T date.
- The system blocks Jarvis T+1 execution until expert T runs are complete or
  explicitly skipped/failed.
- Expert output is persisted through system APIs and linked to the producing
  agent run.
- Jarvis output is persisted through system APIs and linked to the producing
  agent run.
- Tests cover schedule ordering, role-scoped tool manifests, output validation,
  audit records, and Jarvis readiness gates.

## Related Tasks

- `TASK-080`: Codex runtime access contract and agent-run audit model.
- `TASK-081`: Project MCP/API tool manifest for role-scoped agent execution.
- `TASK-082`: Domain/function skill library and expert overview prompt MVP.
- `TASK-083`: Expert daily agent execution workflow.
- `TASK-084`: Jarvis T+1 agent workflow and readiness gates.
