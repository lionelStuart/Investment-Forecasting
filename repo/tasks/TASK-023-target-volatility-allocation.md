# TASK-023: Target Volatility Allocation

## Status

pending

## Source

Updated `ROADMAP.md` backlog theme: portfolio optimization and
target-volatility allocation.

## Goal

Generate target-volatility allocation proposals bounded by active user
preferences and backed by stored risk metrics.

Expert committee tasks may reuse this allocation logic as one possible expert
style, but expert-specific plans must still record their own evidence, risk
checks, and virtual execution.

## Acceptance

- Allocation proposals use stored volatility/drawdown data.
- Proposals respect user max-equity and min-cash settings.
- Daily advice can reference the allocation proposal as structured evidence.
