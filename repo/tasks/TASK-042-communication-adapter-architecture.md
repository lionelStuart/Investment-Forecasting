# TASK-042: Communication Adapter Architecture

## Status

pending

## Purpose

Create the channel-neutral communication foundation that will connect the local
Mac research system to the user's phone without hardcoding iMessage into
investment, expert, daily workflow, or WebUI logic.

## Scope

- Add communication persistence for recipients, adapter configuration,
  outbound messages, idempotency keys, status, timestamps, and errors.
- Add a communication service interface with dry-run support.
- Add delivery policy concepts: enabled flag, allowlist, severity, quiet hours,
  rate limits, and retry limit.
- Add tests for allowlist rejection, dry-run, idempotency, and failed send
  recording.
- Update architecture and code index.

## Non-Scope

- No actual iMessage sending yet.
- No inbound phone command parsing.
- No live trading or real-money execution.

## Files Likely To Change

- `src/investment_forecasting/migrations/001_init.sql`
- `src/investment_forecasting/db.py`
- `src/investment_forecasting/communication/`
- `src/investment_forecasting/cli.py`
- `tests/test_communication.py`
- `repo/ARCHITECTURE.md`
- `repo/CODE_INDEX.md`

## Acceptance Criteria

- Communication records can be created and queried.
- A service can render a dry-run outbound message without sending.
- Recipient allowlist is enforced before adapter execution.
- Duplicate idempotency keys do not send duplicate messages.
- Failed sends persist structured error status.

## Depends On

- `SPEC-008`
- `ADR-004`
