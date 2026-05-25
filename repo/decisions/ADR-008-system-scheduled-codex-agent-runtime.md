# ADR-008: System-Scheduled Codex Agent Runtime

## Status

accepted

## Context

The project previously used "Codex automation" language in two different ways:

- a daily scheduled job that runs local scripts; and
- the intended product shape where Codex acts as an agent runtime for expert
  committee members and Jarvis.

This ambiguity can send development in the wrong direction. The product target
is not simply a scheduled script and not merely an LLM provider call from
`ai_providers`. The target is a system-owned scheduler that invokes Codex
runtime runs at specific business moments with role prompts, project skills,
role-scoped tools, and validated structured outputs.

## Decision

The Investment Forecasting system owns scheduling, APIs, persistence, audit,
validation, UI, and communication.

Codex is introduced as an agent runtime access layer. It is invoked by the
system for a specific role and task, receives a project skill plus a generated
role prompt, uses only allowed MCP/API tools, and submits structured output
back through system APIs.

The expert committee and Jarvis must be agentic:

- Each active expert runs as its own Codex agent task on T day after system data
  and model evidence are prepared.
- Each expert produces exactly one daily virtual action outcome: a validated
  plan/action or an explicit skipped/failed action.
- Jarvis runs at T+1 after T expert outputs are complete or explicitly skipped.
- Jarvis uses the same system capabilities plus completed expert outputs to
  produce the consumer-facing daily investment brief.

The existing provider-adapter path remains a bounded fallback or simpler LLM
analysis path, but it is not the final product architecture for expert/Jarvis
reasoning.

## Consequences

- Documentation and roadmap must distinguish:
  - system scheduled tasks;
  - Codex runtime access layer;
  - role-scoped expert/Jarvis agent runs;
  - ordinary AI provider adapter calls.
- New work must not add route-specific LLM calls or direct Codex database
  writes.
- Agent runs need auditable persistence and tool-call records.
- MCP/API tools need role-scoped manifests and submission endpoints, not only
  read/generate convenience tools.
- Jarvis readiness must enforce ordering: T expert actions first, T+1 Jarvis
  synthesis second.
- WebUI can display agent status, but UI is not an evidence source for agents.

## Non-Goals

- Do not let Codex own the scheduler.
- Do not create an unbounded autonomous trading agent.
- Do not bypass simulated portfolio and validation services.
- Do not turn the expert committee into an open-ended multi-agent chat.
- Do not claim agentic output produces guaranteed returns.

## Follow-Up

- Implement `SPEC-012` through `TASK-080` to `TASK-084`.
- Update `ARCHITECTURE.md`, `CODE_INDEX.md`, `PROJECT.md`, `ROADMAP.md`,
  `STATUS.md`, and `INDEX.md` whenever the runtime access layer adds durable
  commands, modules, tools, tables, or skills.
