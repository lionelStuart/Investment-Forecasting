# TASK-051: Jarvis Phone Summary Template

## Status

completed

## Purpose

Send a concise Jarvis daily summary to the user's phone through the
communication adapter layer after communication infrastructure exists.

## Scope

- Add a Jarvis phone template with:
  - today's focus direction;
  - one-line stance;
  - model signal;
  - expert consensus/disagreement;
  - top risk warning;
  - WebUI link or local inspection hint.
- Use communication service idempotency and allowlist policy.
- Add dry-run rendering and tests.

## Non-Scope

- No direct iMessage calls from Jarvis code.
- No phone-originated commands.
- No real-money execution.

## Files Likely To Change

- `src/investment_forecasting/communication/templates.py`
- `src/investment_forecasting/jarvis/`
- `tests/test_communication.py`
- `tests/test_jarvis.py`

## Acceptance Criteria

- Jarvis phone summary can be rendered in dry-run.
- Template uses safe research-support language.
- Sending uses communication service and does not bypass adapter policy.
- Duplicate daily sends are prevented by idempotency key.

## Depends On

- `TASK-043`
- `TASK-044`
- `TASK-048`

## Implementation Notes

- Added `render_jarvis_daily_summary` in the shared communication template
  layer so Jarvis phone summaries use the same channel-neutral, allowlisted,
  audited send path as daily workflow and expert notifications.
- The template includes today's focus direction, one-line stance, model signal,
  expert consensus/disagreement, top risk warning, and a `/jarvis` inspection
  hint.
- `jarvis generate` and the Jarvis Codex scheduled task now read
  `INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY`,
  `INVESTMENT_FORECASTING_NOTIFICATION_CHANNEL`, and
  `INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN` as default notification
  configuration. CLI flags can still override the defaults.
- Jarvis brief generation and phone-summary sending remain separate functions;
  the Jarvis task composes them as sequential steps after the brief is
  persisted.
- Jarvis notification failures are reported in the generated brief response but
  do not fail brief generation.
- Idempotency key `mobile:jarvis_daily_summary:{brief_date}:{version}` prevents
  duplicate daily phone summaries for the same Jarvis brief version.

## Verification

- `python3 -m pytest tests/test_communication.py tests/test_jarvis.py`
- `python3 -m pytest`
- CLI smoke:
  `investment-forecasting jarvis generate --db /tmp/jarvis-phone-smoke.sqlite3 --date 20260523 --notify-recipient-key owner_phone --notification-dry-run`
- `scripts/restart_web.sh`
