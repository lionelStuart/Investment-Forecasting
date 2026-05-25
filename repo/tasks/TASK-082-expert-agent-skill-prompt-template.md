# TASK-082: Domain Skill Library And Expert Overview Prompt MVP

## Status

completed

## Purpose

Create the project-level domain/function skill library and the expert role
overview skill. This turns each persisted expert into an agentic virtual
investor with its own mandate, style, risk constraints, portfolio context,
allowed domain capabilities, allowed tools, and structured output schema.

## Scope

- Add domain/function skill docs for bounded system capabilities:
  - `repo/skills/investment-market-data-skill/SKILL.md`;
  - `repo/skills/investment-model-evidence-skill/SKILL.md`;
  - `repo/skills/investment-news-evidence-skill/SKILL.md`;
  - `repo/skills/investment-asset-research-skill/SKILL.md`;
  - `repo/skills/investment-expert-portfolio-skill/SKILL.md`;
  - `repo/skills/investment-virtual-action-skill/SKILL.md`;
  - `repo/skills/investment-agent-output-contract/SKILL.md`.
- Add `repo/skills/investment-expert-agent/SKILL.md` as the expert overview
  skill that composes only expert-safe domain/function skills.
- Add a prompt-template builder for one expert/date/agent-run context.
- Inject expert identity, style, focus weights, risk limits, allowed asset
  categories, current portfolio, latest scorecard, prior plan, and lessons.
- Inject allowed skill bundle, allowed tool manifest, and output schema.
- Require explicit evidence IDs and optional news evidence IDs.
- Require exactly one output outcome: plan/action or skipped/failed reason.
- Add tests that render prompts for the four default experts without missing
  required fields.

## Non-Scope

- No live Codex execution.
- No Jarvis overview skill or prompt template.
- No new expert roster.
- No change to virtual execution rules.

## Files Likely To Change

- `repo/skills/investment-*-skill/SKILL.md`
- `repo/skills/investment-expert-agent/SKILL.md`
- `src/investment_forecasting/agent_runtime/prompts.py`
- `src/investment_forecasting/experts/roster.py`
- `tests/test_agent_runtime.py`

## Implementation Checklist

- Define domain/function skills as capability docs, not role entry points.
- Define a stable expert prompt template with:
  - role;
  - mandate;
  - included skill bundle;
  - evidence policy;
  - required tool-use checklist;
  - safety constraints;
  - output schema;
  - stop conditions.
- Render one prompt per expert from persisted fields, not hardcoded prose only.
- Add shared output contract references so prompt and validation stay aligned.
- Ensure expert overview skill excludes Jarvis synthesis and any Jarvis-only
  submission tools.
- Ensure prompts do not include bulk news dumps.

## Acceptance Criteria

- Domain/function skills exist and are visibly distinct from the expert
  overview skill.
- Four default experts can each render a complete prompt with unique style
  context.
- Expert prompt includes the expert allowed skill bundle.
- Prompt contains tool-use policy and forbids direct SQLite/WebUI scraping.
- Prompt requires evidence IDs for any prediction/news/model claims.
- Prompt requires virtual research-only language and no guaranteed returns.
- Tests snapshot or assert the required template sections.

## Test Plan

- `python3 -m pytest tests/test_agent_runtime.py tests/test_experts.py -q`

## Depends On

- `TASK-080`
- `TASK-081`

## Completion Notes

- Added project domain/function skills plus `investment-expert-agent`.
- Added `agent_runtime/prompts.py` with expert prompt rendering and output
  schema.
- Verified all default experts render prompts with role manifest, tool policy,
  evidence policy, and research-only constraints.
