# TASK-043: iMessage Outbound Adapter

## Status

pending

## Purpose

Implement the first phone communication adapter using the local macOS Messages
app and iMessage, so the Mac can send opt-in research notifications to an
allowlisted phone identity.

## Scope

- Add an iMessage adapter behind the communication service interface.
- Send through the local macOS Messages app.
- Add setup verification that checks configuration, recipient allowlist, and
  common local blockers.
- Add CLI commands for dry-run test, setup health, and explicit real test send.
- Record sent, skipped, permission-required, recipient-not-allowed, and failed
  outcomes.

## Non-Scope

- No inbound reading of Messages history.
- No broad contact discovery.
- No sending to non-allowlisted recipients.
- No automatic investment execution from messages.

## Files Likely To Change

- `src/investment_forecasting/communication/imessage.py`
- `src/investment_forecasting/communication/service.py`
- `src/investment_forecasting/cli.py`
- `tests/test_communication.py`
- `repo/AGENTS.md`

## Acceptance Criteria

- iMessage adapter supports dry-run without invoking Messages.
- Real sends require explicit enabled configuration and allowlisted recipient.
- Adapter reports macOS/Messages permission or execution failures clearly.
- CLI can verify setup and send an allowlisted test message.
- Tests cover command construction or adapter boundary without requiring a real
  Messages account in CI.

## Depends On

- `TASK-042`
