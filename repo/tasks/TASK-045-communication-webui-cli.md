# TASK-045: Communication WebUI And CLI Inspection

## Status

completed

## Purpose

Make local-to-phone communication inspectable and operable without editing
SQLite directly.

## Scope

- Add CLI commands for listing adapters, recipients, setup health, recent
  messages, and dry-run/real test sends.
- Add a WebUI section or route for communication status.
- Show iMessage adapter health, last send status, recent errors, quiet-hour
  policy, and allowlisted recipient summary.
- Keep sensitive recipient values masked in UI where practical.

## Non-Scope

- No contact management beyond explicit allowlist configuration.
- No inbound command UI.

## Files Likely To Change

- `src/investment_forecasting/cli.py`
- `src/investment_forecasting/web/app.py`
- `tests/test_web_app.py`
- `tests/test_communication.py`

## Acceptance Criteria

- User can inspect whether iMessage communication is configured and healthy.
- Recent outbound messages show status and error summary.
- Dry-run test is available without sending a real phone message.
- UI does not expose raw payloads or unmasked sensitive recipient data as the
  primary experience.

## Completion Notes

- Added `communication list-adapters` CLI inspection over persisted adapter
  configs.
- Added `/communication` WebUI route and nav entry with:
  - communication status summary;
  - iMessage adapter setup/preflight health;
  - allowlisted recipient summary with masked addresses;
  - WebUI dry-run test form that records a `dry_run` outbound message without
    invoking Messages;
  - recent outbound messages, recent error cards, and secondary technical
    details without raw payloads as the primary view.
- Reused the channel-neutral communication service for WebUI dry-run sends, so
  allowlist, idempotency, policy, and outbound audit behavior stay consistent.

## Verification

- `python3 -m pytest tests/test_communication.py tests/test_web_app.py`
- `python3 -m pytest`

## Depends On

- `TASK-042`
- `TASK-043`
- `TASK-035`
