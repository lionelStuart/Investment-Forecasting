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
