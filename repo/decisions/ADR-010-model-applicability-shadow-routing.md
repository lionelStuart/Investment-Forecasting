# ADR-010: Model Applicability And Shadow Routing

## Status

accepted

## Context

The 2026 replay and CEO review show that a single global model score is not
enough for safe model optimization. A model can be useful for one horizon,
asset scope, or output purpose while being harmful for another.

Current evidence says:

- 5-day routing should not replace the fixed baseline.
- 20-day routing may be useful, but only as conservative shadow evidence.
- 20-day same-type ranking is weak or negative.
- Raw confidence is too easy to misread as prediction certainty.

## Decision

Adopt a model applicability and shadow-routing governance architecture.

The system will:

- persist model-health metrics by context;
- derive context-specific model roles;
- run routing changes in shadow before any production use;
- disable same-type ranking when same-type Rank IC or bucket spread is
  non-positive;
- treat confidence as evidence quality, not success probability;
- keep production defaults unchanged during the next implementation phase.

## Consequences

- Model optimization becomes slower but more durable.
- Shadow results can be reviewed without affecting operational predictions.
- Future product surfaces can consume explicit model roles instead of inferring
  meaning from raw scores.
- Candidate models cannot quietly expand from allocation bias to same-type
  ranking or primary forecast without evidence.

## Guardrails

- No expert, Jarvis, advice, phone, WebUI, or portfolio behavior may change in
  the next phase.
- No operational `model_predictions` overwrite.
- No promotion from one replay sample.
- No strong confidence language until calibrated tiers show stable realized
  separation.

## Related

- `SPEC-014`
- `SPEC-015`
- `TASK-093` through `TASK-097`
