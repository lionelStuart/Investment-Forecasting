# ADR-003: Expert Committee Uses Persisted Virtual Experts

## Status

accepted

## Context

The product needs several parallel investment experts with different styles,
preferences, and model focus. These experts must design investment plans, invest
virtual capital, accumulate return history, be scored, learn from failure, and
be retired or replaced.

This could be implemented as ephemeral LLM personas, but that would make
results hard to audit, score, compare, or reproduce.

## Decision

Expert behavior will be modeled as persisted structured records first. LLM or
Agent prose may help generate plan explanations, but the durable system of
record is SQLite:

- expert roster and lifecycle state;
- style/focus/risk configuration;
- virtual portfolios and transactions;
- daily expert plans and evidence links;
- scorecards, reviews, lessons, retirement, and hiring decisions.

Daily expert execution must use existing stored data, forecasts, backtests,
market snapshots, advice records, prices, and simulated portfolio mechanics.
Expert modules may add specialized policy logic, but they must not bypass
existing persistence, risk, scoring, or no-future-leakage constraints.

## Consequences

- Expert comparisons can be reproduced and audited.
- The WebUI can show plans, positions, returns, warnings, retirements, and
  lessons from persisted facts.
- The system can later expose expert operations through CLI or MCP without
  inventing a parallel state store.
- Implementation requires schema and service work before any polished expert
  UI or autonomous multi-agent orchestration.
