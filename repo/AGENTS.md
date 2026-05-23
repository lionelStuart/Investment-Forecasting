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
2. Produce or confirm a small plan.
3. Modify only the scoped files listed by the task.
4. Run the task test plan.
5. Update the task progress, `STATUS.md`, and `INDEX.md`.
6. Record decisions, learnings, or reusable skills when durable context changes.

## Constraints

- Do not work without a task unless the repository is being bootstrapped.
- Do not modify unrelated files.
- Do not introduce a new dependency, framework, data vendor, or storage engine
  without an ADR in `decisions/`.
- Do not output capital protection, guaranteed return, or certain-profit claims.
- All generated advice must be traceable to stored data, model output,
  backtest evidence, assumptions, and risk warnings.
- When network access or downloads fail, agents may retry with:
  `https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890 all_proxy=socks5://127.0.0.1:7890`.

## Mandatory End-Of-Task Update

After implementation, update all applicable files:

1. The active task's progress and result
2. `STATUS.md`
3. `INDEX.md` task status
4. The linked spec if behavior or acceptance changed
5. `decisions/` if a durable technical choice was made
6. `learnings/` if a new problem or debugging fact was discovered
7. `skills/` if the learning became a reusable procedure

