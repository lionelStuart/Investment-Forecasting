# TASK-098 Checklist Test Coverage Audit - 2026-05-28

## Scope

This audit reviews the `TASK-098` P0/P1/P2 checklist against current
implementation and tests. The goal of this pass is to add unit and
module-integration coverage first, without changing production logic. Any
suspected logic defect is recorded here instead of being fixed in the same
pass.

## Test Coverage Added

Verification updated: 2026-05-29 Asia/Shanghai.

- 2026-05-29 sequential defect-repair pass:
  - D1 fixed: `scheduler today-status` now evaluates status by due scheduled
    occurrence, filters operator-interrupted manual probes, preserves same-day
    failures, and records `recovered_count` when an explicit scheduled
    occurrence is successfully rerun.
  - D2 fixed: Jarvis capital-flow summaries now mark stale evidence as
    `status = degraded` and include `stale` plus `age_days`.
  - D3 fixed: expert plan evidence now includes capital-flow freshness and
    degradation state for new plans.
  - Operational recovery evidence: `price_nav_post_close` scheduler run `143`
    completed `success`, `news_hourly_incremental` run `146` completed
    `success`, and `jarvis_t_plus_one` scheduled occurrence
    `2026-05-29T08:00:00` recovered as run `147` without duplicating
    `outbound_messages.id = 9`.
  - Full suite after this pass: `277 passed, 2 warnings`.

- 2026-05-29 interface recovery fix:
  - `TushareProvider.news()` now retries across environment, direct, and local
    `127.0.0.1:7890` proxy profiles, records which profiles were attempted,
    and redacts token values from diagnostics/errors.
  - `market_context_intraday` can bypass an unrecovered or backoff-active
    AKShare/Eastmoney market-context provider when Tushare credentials are
    available, using Tushare for market-level capital-flow recovery instead of
    blocking the whole job.
  - Market-context scheduler results now record per-subject provider source,
    subject errors, failed subject count, and provider request counts by the
    actual provider used.
  - Real DB recovery evidence: `news_hourly_incremental` scheduler run `114`
    completed `success`; `market_context_intraday` scheduler run `120`
    completed `success` with `provider_by_subject.market:market = tushare` and
    5 written capital-flow rows.
  - Full suite after the fix: `267 passed, 3 xfailed`.

- 2026-05-29 Jarvis/short-message recovery fix:
  - Expert Codex artifact timeouts now persist `timed_out` as the terminal
    status instead of leaving timeout cancellations as `cancelled`, so Jarvis
    readiness no longer waits forever on a timed-out expert run.
  - Successful recovered agent runs clear stale `failure_reason` fields, which
    keeps completed Jarvis/expert rows from carrying old timeout/readiness
    messages.
  - Operational DB evidence: `sang_hongyang` recovered as expert
    `agent_runs.id = 30` and `expert_plans.id = 27`; Jarvis recovered as
    `agent_runs.id = 26`, `jarvis_daily_briefs.id = 6`, and
    `outbound_messages.id = 9`.
  - `outbound_messages.id = 9` is `jarvis_daily_summary`, `status = sent`,
    `sent_at = 2026-05-29 01:43:45`, `channel = imessage`,
    `recipient_key = owner_phone`.
  - Full suite after the fix: `269 passed, 3 xfailed`.

- `tests/test_scheduler.py`
  - Verifies `scheduler install-cron` writes a unified LaunchAgent into a
    caller-provided temporary LaunchAgents directory.
  - Verifies LaunchAgent `WorkingDirectory`, `ProgramArguments --db`,
    `PYTHONPATH`, project DB path, notification defaults, Codex binary, and
    provider token environment injection.
  - Verifies the `install-cron` result object does not expose the injected fake
    provider token.
  - Verifies a scheduled `news_hourly_incremental` runtime with no Tushare
    token records a failed run, provider backoff, and `last_failure_at`
    metadata as a configuration/environment propagation failure.
  - Verifies provider hourly and daily budget exhaustion produce distinct
    deferred reasons.
  - Verifies `market_context_intraday` surfaces shared `akshare` budget
    starvation after `price_nav_post_close` consumes the provider budget.
  - Verifies same-day scheduler health keeps earlier failures visible and
    records recovery after an explicit scheduled-occurrence rerun.
  - Verifies no-history price/NAV failures leave asset status plus
    per-asset watermark metadata for lifecycle/status review.
  - Verifies `scheduler_status` exposes failed, deferred, and skipped latest
    runs alongside watermark cursors and provider backoff metadata.
- `tests/test_tushare_provider.py`
  - Verifies Tushare diagnostics report credential presence without exposing
    token values and that DNS/provider news failures stay distinct from missing
    credential failures after a token is present.
  - Verifies Tushare news retries through the local proxy profile when direct
    network access fails and restores the caller's original proxy environment.
- `tests/test_akshare_ingestion.py`
  - Verifies Eastmoney curl fallback errors preserve both direct/no-proxy and
    local-proxy profile names in the provider error detail.
- `tests/test_communication.py`
  - Verifies enabled communication adapter defaults to real send when
    `dry_run_default = 0` and no per-send dry-run override is supplied.
  - Verifies `dry_run -> sent` retry still preserves `sent` idempotency and
    blocks later duplicate sends.
  - Strengthens weekly Jarvis summary assertions for coverage dates, daily
    brief count, missing evidence count, stale evidence count, and latest
    stance.
  - Verifies daily success/failure, provider warning, expert lifecycle/plan,
    Jarvis daily, and Jarvis weekly notification templates preserve safety
    language and do not expose raw payloads or phone numbers.
  - Verifies a failed weekly notification remains visible in
    `outbound_messages` after a later daily notification succeeds.
- `tests/test_agent_runtime.py`
  - Verifies Jarvis upstream readiness remains degraded when a required
    upstream scheduler chain has a same-day failed run before a later success.
- `tests/test_jarvis.py`
  - Verifies stale capital-flow observations are persisted in Jarvis
    `stale_evidence`, retain their latest evidence date, and trigger stale
    evidence risk language.
  - Verifies stale capital-flow summaries are marked `degraded` instead of
    silently `available`.
  - Verifies Jarvis brief persistence can succeed while phone notification
    fails separately, with the failed outbound message visible in
    `outbound_messages`.
- `tests/test_experts.py`
  - Verifies expert plan evidence packets carry capital-flow
    freshness/degradation state.
- `tests/test_web_app.py`
  - Verifies the communication WebUI surfaces `dry_run`, `sent`, `failed`, and
    `permission_required` outbound states, recent error details, `sent_at`, and
    masked recipient addresses without exposing the raw phone number.
  - Verifies the settings/system-health WebUI surfaces scheduler `failed`,
    `deferred`, and `missed` states with provider/backoff reasons and task-log
    errors.

Targeted command:

```bash
python3 -m pytest tests/test_scheduler.py tests/test_communication.py tests/test_agent_runtime.py tests/test_web_app.py tests/test_jarvis.py tests/test_experts.py -q
```

Result:

```text
116 passed, 3 xfailed
```

Provider diagnostics command:

```bash
python3 -m pytest tests/test_tushare_provider.py tests/test_akshare_ingestion.py tests/test_scheduler.py -q
```

Result:

```text
62 passed, 1 xfailed
```

Checklist minimum command:

```bash
python3 -m pytest tests/test_scheduler.py tests/test_communication.py tests/test_jarvis.py tests/test_agent_runtime.py tests/test_web_app.py tests/test_news_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py -q
```

Result:

```text
119 passed, 2 xfailed
```

Full command:

```bash
python3 -m pytest -q
```

Result:

```text
262 passed, 3 xfailed
```

Hygiene checks:

```bash
git diff --check
rg -n "TOKEN|TUSHARE|TS_TOKEN|[0-9]{11}" . -g '!data/**' -g '!.git/**' -g '!*.sqlite3' -g '!*.sqlite3-*'
```

Result:

- `git diff --check`: clean.
- Secret/phone scan: no real provider token found; matches are environment
  variable names, documented placeholders, numeric finance fixtures, and test
  recipient fixtures. Local-only paths such as `data/` and SQLite files remain
  excluded.

## P0 Checklist Review

| Area | Current Test Evidence | Status |
| --- | --- | --- |
| LaunchAgent project root/DB/env | `test_scheduler_install_cron_writes_unified_launch_agent` | Covered |
| Shell env vs scheduled env distinction | LaunchAgent plist env is parsed separately from process behavior; scheduled news runtime missing-token failure is recorded independently | Covered for unit/runtime-path evidence |
| Secret/token non-printing | Fake token is asserted only inside temp plist content; `install-cron` result and provider diagnostics do not expose token values | Covered for tests/diagnostics |
| Cron tests cannot mutate real plist | Temp `launch_agents_dir` asserted | Covered |
| Today status expected/missed/failed/deferred/completed | `test_scheduler_today_status_marks_missed_failed_and_not_yet_due` plus existing scheduler tests | Covered |
| Same-day historical failure remains visible after manual success | `test_scheduler_today_status_keeps_same_day_failure_visible_after_manual_success` | Covered |
| Provider budget reset and failure metadata | Existing `test_provider_failure_preserves_count_window_for_later_reset` | Covered |
| News token vs provider/network failure | `test_news_scheduler_missing_tushare_token_is_recorded_as_runtime_configuration_failure`, `test_tushare_provider_requires_explicit_token`, and `test_tushare_provider_reports_token_presence_without_exposing_token_and_keeps_network_failure_distinct` | Covered |
| Manual news rerun result visibility | Operational checklist item; not unit-covered without provider fixture expansion | Gap |
| Price/NAV continues after one asset failure | `test_price_nav_incremental_continues_after_one_asset_failure` | Covered |
| Partial price/NAV metadata | Same test verifies `failed_assets`, `errors_by_asset`, `written_price_rows` | Covered |
| Price rerun followed by features/model | `test_scheduler_pipeline_runs_real_outputs_before_expert_and_jarvis` | Covered |
| Market context failure/deferred distinction | `test_market_context_fails_when_provider_returns_no_rows`, new budget-reason test | Covered |
| Expert T-day readiness | Existing scheduler/agent-runtime readiness tests | Covered |
| Jarvis T+1 expert terminal gate | Existing `jarvis_agent_readiness` and scheduler agent tests | Covered |
| Jarvis upstream freshness/failure state | New `test_jarvis_readiness_keeps_same_day_upstream_failures_visible` | Covered |
| Communication default real send | New communication test | Covered |
| Dry-run retry to real send | Existing and strengthened communication tests | Covered |
| Outbound terminal status and `sent_at` | Existing communication tests | Covered |
| Jarvis brief and phone notification decoupled in same flow | `test_generate_jarvis_brief_can_send_phone_summary_dry_run` and `test_generate_jarvis_brief_keeps_failed_notification_visible_without_failing_brief` | Covered for dry-run and failed-notification paths; real device receipt remains manual |
| Real iMessage delivery manually verified | Requires human/device confirmation | Manual gap |
| Weekly report distinct template and retry policy | Weekly template/idempotency test plus failed-weekly visibility test | Covered for template/CLI/send visibility, not scheduler |
| Git/privacy hygiene | Must be run before commit; not a product unit test | Manual gate |
| Recovery/backfill order | Pipeline test covers order; real operational backfill remains manual evidence | Partial |

## P1/P2 Checklist Review

| Area | Current Test Evidence | Status |
| --- | --- | --- |
| Scheduler status explains failures/skips/deferred/cursors | `test_scheduler_status_explains_failed_deferred_skipped_cursors_and_provider_state` | Covered |
| WebUI exposes failed/missed jobs | `test_settings_page_surfaces_scheduler_failed_deferred_and_missed_states` | Covered |
| Shared provider starvation visibility | `test_market_context_surfaces_price_nav_provider_budget_starvation` | Covered |
| Backoff clear reason/operator notes | Backoff recovery tested; operator-note requirement is documentation/ops gap | Partial |
| Network proxy attempt details | `test_eastmoney_curl_fallback_error_records_direct_and_local_proxy_profiles` covers direct/no-proxy and local-proxy provider error details | Partial |
| Repeated no-history lifecycle/status review | `test_price_nav_no_history_failures_leave_lifecycle_review_evidence` proves per-asset status and watermark metadata are available for review; actual asset lifecycle change remains an operator/product decision | Partial |
| Stale capital-flow evidence treated as degraded by experts/Jarvis | `test_jarvis_brief_marks_stale_capital_flow_summary_as_degraded` and `test_expert_plan_evidence_marks_stale_capital_flow_as_degraded` | Covered |
| Agent run artifacts and submission result | Existing agent-runtime tests cover artifacts, prompts, submission, plan evidence | Covered |
| WebUI communication states | `test_communication_page_surfaces_terminal_statuses_and_recent_errors`; scheduler deferred/missed visibility is covered by the settings/system-health WebUI test | Covered for WebUI visibility |
| Notification template compliance language | `test_notification_templates_preserve_safety_language_and_hide_raw_payloads` covers daily, provider, expert, Jarvis daily, and Jarvis weekly templates | Covered |
| Local-only operational data called out | This report lists current local-only artifacts and staging exclusions | Covered for report hygiene |

## Defects Recorded Before Logic Changes

### D1 - Same-Day Scheduler Daily Failure Can Be Hidden By Later Success

Status: fixed on 2026-05-29. Severity: P0.

Evidence:

- Converted regression test:
  `tests/test_scheduler.py::test_scheduler_today_status_keeps_same_day_failure_visible_after_manual_success`
- Current behavior keeps same-day failures visible, records recovered
  occurrences separately, and filters operator-interrupted manual probes from
  normal daily status.

Why it matters:

- `TASK-098` requires same-day historical failures to remain visible after
  manual recovery.
- Operators need to know both "recovered now" and "failed earlier today".

Fix implemented:

- Today-status aggregation now evaluates each due scheduled occurrence and
  preserves `success_count`, `failed_count`, and `recovered_count` separately.

### D2 - Stale Capital-Flow Evidence Is Still Summarized As Available

Status: fixed on 2026-05-29. Severity: P1.

Evidence:

- Passing tests:
  `tests/test_jarvis.py::test_jarvis_brief_records_stale_capital_flow_as_evidence_risk`
  `tests/test_jarvis.py::test_jarvis_brief_marks_stale_capital_flow_summary_as_degraded`
- Current behavior records stale capital-flow evidence in both
  `stale_evidence` and `model_summary.capital_flow`, with
  `status = degraded`, `stale = true`, and `age_days`.

Why it matters:

- `TASK-098` requires Jarvis and experts to treat stale or failed capital-flow
  evidence as degraded evidence, not as a silent success.
- Operators reading the structured synthesis payload may trust
  `capital_flow.status = available` without noticing the separate stale list.

Fix implemented:

- `_capital_flow_summary` now receives the target date and derives freshness
  state directly from the latest capital-flow observation date.

### D3 - Expert Evidence Packets Do Not Carry Capital-Flow Freshness State

Status: fixed on 2026-05-29. Severity: P1.

Evidence:

- Converted regression test:
  `tests/test_experts.py::test_expert_plan_evidence_marks_stale_capital_flow_as_degraded`
- Current expert plan evidence records `capital_flow` freshness/degradation
  state for newly generated plans.

Why it matters:

- `TASK-098` requires experts, not only Jarvis, to treat stale or failed
  capital-flow evidence as degraded evidence.
- Expert plans can currently look complete from `evidence_json` while omitting
  the market-context freshness signal.

Fix implemented:

- Expert planning now adds a bounded capital-flow evidence summary with latest
  date, status, stale flag, age, and observation count.

## Remaining Test Work

- Broaden WebUI tests later if new status surfaces are added; current settings
  and communication pages now have direct TASK-098 state visibility coverage.
- Expand provider diagnostic tests if an environment-proxy profile is added;
  current coverage proves Tushare credential vs provider/network distinction
  and Eastmoney direct/no-proxy plus local-proxy error detail.
- Extend no-history review from metadata evidence to an explicit operator
  workflow or lifecycle/status decision if repeated failures continue.
- Add manual operational evidence for real iMessage receipt when claiming user
  phone delivery.
- Add scheduler-level weekly notification flow coverage if/when weekly sending
  becomes a scheduled job rather than a CLI/template workflow.

## Completion Blockers

D1/D2/D3 are fixed. The remaining checklist blockers are operational/manual
acceptance items rather than strict xfail defects:

| Blocker | Severity | Current Evidence | Required Before Completion |
| --- | --- | --- | --- |
| Real iMessage receipt | P0 manual | Unit tests cover dry-run, failed-send, idempotency, masking, and adapter behavior only | Human/device confirmation of a real `sent` message and receipt |
| 2026-05-29 same-day partial history | P1 operational | `today-status` now shows 5 success items and 2 partial hourly items after recovery | Operator acceptance that earlier same-day news/market failures remain visible by design |
| `stock:000004` no-history | P1 operational | `price_nav_post_close` run `143` succeeded while recording the no-history asset separately | Product/operator lifecycle/status decision for repeated no-history assets |

## Local-Only Artifacts

Current `git status --short` shows local-only runtime/research data that must
not be staged for a PR:

- `data/`
- `research/model_tuning_2026/model_tuning_research.sqlite3`

The privacy scan was intentionally run with `data/`, `.git`, and SQLite files
excluded. These paths are operational local state, not source/test fixtures.

## Acceptance Note

The sequential repair pass changed production logic and converted D1/D2/D3 into
normal passing regression tests. Current automated evidence is `277 passed, 2
warnings`; remaining acceptance work is manual/operational.
