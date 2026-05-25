---
name: investment-virtual-action-skill
description: Expert-only virtual action submission policy.
---

# Investment Virtual Action Skill

Each expert agent must return exactly one outcome for the target date:
`plan_action`, `skipped`, or `failed`.

Completed action proposals must include action, target, reason, analysis,
reflection, risk note, and evidence IDs. The system validates and persists
actions; the agent must not write to SQLite or trade real money.
