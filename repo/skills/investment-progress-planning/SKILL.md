---
name: investment-progress-planning
description: Use for the Investment Forecasting project when asked to inspect the current code and WebUI progress, compare implementation against product goals, then update roadmap, goals, design direction, specs, and task breakdowns. Triggers on requests like "查看当前项目进展", "更新产品路线", "梳理目标/设计/需求拆分", or "plan next Investment Forecasting work".
---

# Investment Progress Planning

Use this skill only inside `/Users/wonderwall/project/Investment-Forecasting`.
It turns a project-progress review into durable project-memory updates.

## Load Order

Follow `repo/AGENTS.md` first. For this skill, read:

1. `repo/PROJECT.md`
2. `repo/STATUS.md`
3. `repo/INDEX.md`
4. `repo/ROADMAP.md`
5. Relevant `repo/specs/` and `repo/tasks/` files for the area being planned
6. Relevant implementation files under `src/investment_forecasting/`
7. Relevant tests under `tests/`

Do not read every markdown file by default. Start broad, then narrow from the
current focus, pending tasks, and changed product surface.

## Progress Audit

Build a concise evidence map before editing docs:

- Product state: summarize goals, current focus, last completed task, next
  pending tasks, and open constraints from project memory.
- Code state: inspect package modules, CLI commands, database schema, workflows,
  MCP tools, and provider boundaries relevant to the requested planning scope.
- UI state: inspect `src/investment_forecasting/web/app.py`, tests that cover
  WebUI routes, and if useful run or restart the local WebUI with
  `scripts/restart_web.sh`.
- Verification state: check recent test expectations and run the smallest
  meaningful command, normally `python3 -m pytest` for planning changes that
  touch task/spec status.
- Gap state: identify mismatch between implemented behavior, documented
  roadmap, UI experience, acceptance criteria, and next task ordering.

If network access or downloads fail, retry once with the proxy variables from
`repo/AGENTS.md`.

## Planning Updates

Update only the durable project-memory files needed by the audit:

- `repo/PROJECT.md`: product goals, users, constraints, terminology, or default
  commands when the product definition changed.
- `repo/ROADMAP.md`: milestones, backlog themes, development goals, sequencing,
  and product/design priorities.
- `repo/STATUS.md`: current focus, last completed work, open issues, next steps,
  and round evaluation.
- `repo/INDEX.md`: task/spec/status/skill index rows.
- `repo/specs/`: acceptance criteria and behavioral requirements.
- `repo/tasks/`: concrete implementation slices with scope, files, test plan,
  dependencies, and done criteria.
- `repo/decisions/`: durable architecture/provider/storage choices.
- `repo/learnings/`: reusable debugging facts or project-specific discoveries.
- `repo/skills/`: reusable project workflows like this one.

Keep docs synchronized. If a task is added, update both `repo/INDEX.md` and
`repo/STATUS.md`. If a spec changes acceptance behavior, update linked tasks.

## Task Breakdown Shape

When creating or revising tasks, use the existing task file style. Each task
should have:

- Purpose and user/product value.
- Scope and non-scope.
- Files likely to change.
- Implementation checklist.
- Acceptance criteria.
- Test plan.
- Dependencies and follow-up notes.

Prefer thin vertical slices that can be implemented and verified in one coding
round. Preserve investment-safety constraints: no guaranteed returns, no
capital-protection claims, and every advice/product planning feature must keep
evidence, assumptions, uncertainty, and risk warnings traceable.

## UI Review Lens

The WebUI is an operating workbench, not a marketing site. When planning UI
work, prioritize:

- Fast inspection of current advice, data freshness, and model health.
- Clear traceability from advice to assets, forecasts, backtests, assumptions,
  and task logs.
- Portfolio/risk controls that match user preferences and investment horizon.
- Dense but readable operational layouts, stable navigation, empty states, and
  mobile-safe tables/cards.
- Explicit stale-data, provider-failure, and uncertainty states.

## Codex Skill Loading Notes

Codex discovers skills from the session skill roots. For this machine, personal
skills are loaded from `/Users/wonderwall/.codex/skills`; project skills can be
made discoverable by symlinking a project skill directory into that root.

Each skill needs a `SKILL.md` with YAML frontmatter containing `name` and
`description`. Codex always sees that metadata and loads the body only when the
skill is triggered explicitly or by description matching. Optional
`agents/openai.yaml` provides UI metadata.

## End State

Finish with:

- A short summary of what was audited.
- The documentation/planning files updated.
- Any tests or smoke checks run.
- The next recommended implementation task.
