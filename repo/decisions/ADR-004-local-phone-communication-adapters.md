# ADR-004: Local Phone Communication Uses Channel Adapters

## Status

accepted

## Context

The project needs to connect the local Mac research system with the user's
phone. The first requested channel is iMessage. Directly embedding iMessage
calls in daily workflow, advice, expert, or WebUI code would make later channel
changes expensive and would blur safety boundaries.

## Decision

Phone communication will use a channel-adapter architecture. Core investment,
advice, expert, and workflow modules request outbound messages through a
communication service. Channel adapters implement delivery. The first adapter
is iMessage on macOS through the local Messages app.

All sends must be opt-in, allowlisted, rate-limited, idempotent where practical,
and auditable. Communication failures must be visible but must not break core
research computation.

## Consequences

- iMessage can be used first while preserving a path to SMS, email, push, or
  other channels.
- macOS permission and Messages-account issues are isolated inside the adapter.
- Research outputs remain traceable and safe; channel code does not invent
  investment advice.
- Future inbound phone commands need a separate security design before
  implementation.
