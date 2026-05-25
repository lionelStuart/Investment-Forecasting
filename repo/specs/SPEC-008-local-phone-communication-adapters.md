# SPEC-008: Local Mac To Phone Communication Adapters

## Status

draft

## Summary

Add a local communication layer that lets the Mac-hosted investment research
system send controlled messages to the user's phone. The first adapter is
iMessage through the local macOS Messages app. The architecture must remain
adapter-based so future channels can be added without rewriting investment,
expert, workflow, or WebUI logic.

The initial goal is not autonomous trading by phone. It is reliable delivery of
research summaries, run-health alerts, expert-plan updates, and explicit review
prompts from the local Mac to an allowlisted phone identity.

## Product Goals

- Let the local Mac notify the user's phone when daily research, expert plans,
  failures, or important risk changes need attention.
- Keep communication separate from investment logic through a stable adapter
  interface.
- Start with iMessage because it can bridge the local Mac and iPhone without
  adding a third-party messaging vendor.
- Persist every outbound communication attempt, result, template, payload
  summary, and error for audit.
- Make phone communication opt-in, allowlisted, rate-limited, and safe.

## Core Concepts

- `Communication Adapter`: A channel implementation such as iMessage, email,
  SMS, push notification, or future app bridge.
- `Message Recipient`: A configured target identity, such as a phone number,
  Apple ID, or contact alias. Recipients must be allowlisted.
- `Message Template`: A structured template for daily summary, alert, expert
  plan, scorecard warning, retirement review, or recovery prompt.
- `Outbound Message`: A persisted send request with channel, recipient,
  rendered body, status, idempotency key, timestamps, and error detail.
- `Delivery Policy`: Rate limits, quiet hours, severity thresholds, retry
  limits, and redaction rules.
- `Inbound Command`: A future optional phone-originated instruction. First
  implementation should prefer outbound-only notifications; inbound commands
  require explicit security and confirmation gates.
- `Command Nonce`: A short-lived single-use token that binds a phone command to
  one outbound prompt or local WebUI confirmation.
- `Command Audit Record`: A persisted record of a parsed inbound command,
  validation result, confirmation state, execution status, and any error.

## Requirements

### Adapter Architecture

- Communication must use a channel-neutral service boundary.
- Business modules should request a message through a communication service,
  not call `osascript`, Messages, SMTP, or any channel API directly.
- The adapter result must be structured: sent, skipped, dry-run, failed,
  permission-required, recipient-not-allowed, or rate-limited.
- Every send attempt must write an auditable row or task log.
- Adapters must support dry-run mode for tests and local development.

### iMessage First Adapter

- The first adapter should send through the local macOS Messages app.
- The adapter must require explicit configuration before sending:
  allowlisted recipient, account/service identifier if needed, and enabled flag.
- The adapter must detect common local blockers:
  Messages app not available, account not signed in, Automation/TCC permission
  missing, recipient missing, or AppleScript execution failure.
- The adapter must not silently fall back to another recipient or unconfigured
  channel.
- The adapter must expose a clear setup and verification command before daily
  workflows depend on it.

### Safety

- Messages must not contain guaranteed-return, capital-protection, or certain
  buy/sell language.
- Messages must identify outputs as research support or virtual simulation when
  they include advice or expert plans.
- Sensitive payloads should be summarized, not dumped as raw JSON.
- Sending should respect quiet hours and rate limits.
- Outbound messages should be deduplicated by idempotency key so reruns do not
  spam the phone.
- Initial implementation should be outbound-only. Any inbound command support
  must require an allowlist, command parser, confirmation flow, and audit log.

### Inbound Command Design

- iMessage is approved for outbound notifications only. It is not an approved
  inbound command transport for this system because macOS Messages history is
  private, broad, brittle to parse safely, and does not provide strong
  application-level authentication or nonce guarantees.
- Future inbound commands must use a safer purpose-built channel, such as a
  local WebUI confirmation flow or future app bridge, before any execution
  path is added.
- Allowed future command families are limited to non-trading operations:
  acknowledgement of a warning, request to regenerate a Jarvis report with
  existing settings, status/report resend, pause/resume non-critical
  notifications, and local WebUI follow-up/reminder creation.
- Forbidden command families include live trading, real-money buy/sell/rebalance
  or transfer, risk-limit or user-preference changes without local WebUI
  confirmation, model/expert promotion changes, recipient/allowlist changes,
  safety/audit disabling, arbitrary shell/SQL/Python/AppleScript/MCP/agent
  execution, private Messages history scraping, and broad contact discovery.
- Every future inbound command must pass:
  - sender allowlist check;
  - channel and device trust check;
  - command parser whitelist;
  - short freshness window;
  - single-use nonce or challenge binding;
  - rate limit;
  - explicit confirmation for any side effect beyond acknowledgement;
  - persisted command audit before execution.
- The command audit record must include sender key, channel, raw command
  summary, normalized command type, nonce hash, received timestamp, validation
  status, confirmation status, execution status, linked outbound message or
  prompt, and structured error details.
- Inbound command failure must be fail-closed and must never change investment
  state, communication allowlists, safety settings, or local execution
  permissions.

### Use Cases

- Daily workflow completed: send a concise market stance, top watch condition,
  and link/path back to WebUI.
- Daily workflow failed: send failed stage, user-facing impact, and recovery
  command.
- Expert plan ready: send four expert stances and whether each expert traded
  or stayed in cash.
- Expert warning/retirement: send score, drawdown, failure lesson, and
  replacement status.
- Data provider blocked: send throttling/provider warning and next retry
  guidance.
- Notification templates must render from stored evidence and route through the
  channel-neutral communication service so idempotency, allowlist, dry-run, and
  send audit behavior stay consistent across daily and expert workflows.
- Jarvis daily summaries should use the same template and service path,
  rendering only concise focus, stance, model, expert, risk, and local WebUI
  inspection hints from persisted Jarvis evidence.

### WebUI And CLI

- WebUI should expose communication status, last sent messages, and adapter
  setup health. Recipient identities should be masked in primary UI surfaces,
  and raw payloads should stay out of the primary experience.
- CLI should support:
  - listing adapters;
  - verifying iMessage setup, including a config/allowlist-only mode for CI or
    local checks that should not probe Messages;
  - sending a dry-run test message;
  - sending a real allowlisted test message after explicit configuration;
  - inspecting recent outbound messages.

### Agent Workflow

- Before implementing a communication feature, inspect existing daily workflow,
  task logs, advice, expert, WebUI, CLI, and MCP capabilities.
- Prefer message templates built from existing view-model or summary helpers.
- Do not add channel-specific calls inside investment, expert, or WebUI
  business logic.

## Non-Goals

- No live trading or real-money execution from a phone message.
- No scraping private Messages history by default.
- No broad contact discovery.
- No inbound iMessage parsing for command execution in the current
  architecture.
- No unprompted sending to arbitrary phone numbers or Apple IDs.
- No dependency on iMessage for core research computation; communication
  failure must not break data, forecast, advice, or expert workflows.

## Acceptance Criteria

- A channel-neutral communication service boundary exists.
- iMessage adapter can be configured, verified, dry-run, and used for an
  allowlisted recipient.
- Outbound message attempts are persisted or task-logged with status and error.
- Daily workflow can optionally trigger communication without failing the whole
  research run when sending fails.
- Messages use safe research-support language and avoid raw JSON.
- Safe inbound command design exists before implementation. The design must
  identify allowed commands, forbidden commands, authentication, allowlist,
  confirmation, replay protection, audit requirements, and adapter constraints.
- iMessage remains outbound-only unless a later ADR/task replaces this decision
  with a safer validated inbound transport.
- Tests cover dry-run, allowlist rejection, idempotency, adapter failure, and
  template rendering.

## Related Tasks

- `TASK-042`: Communication adapter architecture and persistence.
- `TASK-043`: iMessage adapter setup and outbound send.
- `TASK-044`: Daily workflow and expert notification templates.
- `TASK-045`: Communication WebUI, CLI inspection, and setup health.
- `TASK-046`: Safe inbound command design for future phone replies.
- `TASK-051`: Jarvis phone summary template.
