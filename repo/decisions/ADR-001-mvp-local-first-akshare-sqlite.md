# ADR-001: MVP Local-First AKShare And SQLite

## Status

accepted

## Context

The README and pre-research docs define a first MVP that should be reliable,
reproducible, auditable, and easy to run locally. The project needs market and
fund data quickly, persistent historical records, daily advice generation, and
AI/MCP access before more advanced infrastructure is justified.

## Decision

Use AKShare as the primary MVP data source and SQLite as the local persistence
layer. Keep provider access behind adapters so Tushare Pro, BaoStock, or macro
providers can be introduced later without changing quant, MCP, or WebUI logic.

## Consequences

- Local development can start without paid API credentials.
- Data quality, retry, validation, and cache behavior must be implemented
  because AKShare-backed upstream endpoints can change or fail.
- SQLite is enough for MVP but schema and repository boundaries should avoid
  blocking a future PostgreSQL or DuckDB migration.

