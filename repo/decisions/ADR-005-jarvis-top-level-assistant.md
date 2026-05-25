# ADR-005: Jarvis Is The Top-Level Investment Assistant

## Status

accepted

## Context

The system now contains several evidence-producing subsystems: market
information, model prediction and backtest scoring, daily advice, expert
virtual investing, and planned phone communication. Without a top-level
assistant, users still need to inspect multiple pages to answer the practical
daily question: what should I watch today and how should I interpret risk?

## Decision

The final user-facing product will be an AI investment assistant named Jarvis.
Jarvis is a synthesis layer. It consumes persisted market data, model
predictions, model quality, expert plans, expert scorecards, expert virtual
returns, and user preferences, then produces a simple daily
wealth-management brief.

Jarvis must be evidence-backed, persisted, auditable, and safe. It does not
replace market/model/expert systems and does not create unsupported investment
claims. It is the product layer that explains those systems in plain language.

## Consequences

- Future UX work should converge toward a Jarvis-first experience.
- Market/model/expert pages remain evidence drill-downs, not the primary user
  journey.
- Daily workflow should eventually produce Jarvis after all source evidence is
  available.
- Phone notifications should use Jarvis summaries rather than raw model rows or
  expert logs.
