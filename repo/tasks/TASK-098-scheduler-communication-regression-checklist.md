# TASK-098: Scheduler And Communication Regression Checklist

## Status

active-operational-watch

## Current Acceptance State

As of 2026-05-29, the D1/D2/D3 regression defects have been fixed and converted
from strict expected failures to normal passing tests. The authoritative
evidence is recorded in:

- `repo/audits/TASK-098-CHECKLIST-TEST-COVERAGE-2026-05-28.md`

Latest automated evidence:

- Sequential recovery/freshness fix on 2026-05-29:
  `python3 -m pytest` -> `277 passed, 2 warnings`.
- Jarvis/short-message recovery fix on 2026-05-29:
  `python3 -m pytest -q` -> `269 passed, 3 xfailed`.
- Interface recovery fix on 2026-05-29:
  `python3 -m pytest -q` -> `267 passed, 3 xfailed`.
- Targeted scheduler/communication/agent/WebUI/Jarvis/experts set:
  `116 passed, 3 xfailed`.
- Minimum checklist set:
  `119 passed, 2 xfailed`.
- Full suite:
  `262 passed, 3 xfailed`.
- `git diff --check`: clean.
- Secret/phone scan outside `data/`, `.git`, and SQLite files: no real
  provider token found; matches are env var names, placeholders, test numbers,
  and numeric finance fixtures.

Acceptance is blocked, not complete, for these reasons:

- D1 fixed: `scheduler today-status` now evaluates each due scheduled
  occurrence, keeps same-day failures visible, and records recovered
  occurrences separately.
- D2 fixed: Jarvis capital-flow summaries now include `stale`, `age_days`, and
  `status = degraded` when the latest observation is older than the freshness
  threshold.
- D3 fixed: new expert plans now include capital-flow freshness/degradation
  evidence in `evidence_json`.
- Real iMessage receipt still requires human/device confirmation before
  claiming the user received a phone notification.
- Full green daily status is intentionally not claimed for 2026-05-29 because
  same-day historical market/news failures remain visible as `partial` even
  after later successful recovery runs.

Market/news interface recovery evidence on 2026-05-29:

- `news_hourly_incremental` was rerun against
  `data/investment_forecasting.sqlite3` and completed `success` as scheduler run
  `114`; the bounded Sina window used the Tushare provider, fetched 0 rows for
  the short current window, and recorded no provider/network error.
- `market_context_intraday` was rerun against
  `data/investment_forecasting.sqlite3` and completed `success` as scheduler run
  `120`; because the latest AKShare/Eastmoney failure was newer than the latest
  AKShare success, the scheduler skipped the primary market-context provider and
  used Tushare as a market-level fallback, writing 5 capital-flow rows.
- A later market/data green-path repair fixed two remaining fallback gaps:
  Tushare price fallback now matches the installed `tushare 1.4.29` API
  signature and uses `fund_daily` for ETF prices, while market-context stock
  subjects can fall back to Tushare moneyflow. Operational proof:
  `market_context_intraday` run `136` completed `success`, wrote 105
  capital-flow rows across 21 subjects, and recorded `failed_subjects = 0`.
  Full suite after this repair: `271 passed, 3 xfailed`.
- Price/NAV recovery on 2026-05-29 completed as scheduler run `143`,
  `success`, with 159 written price rows, Tushare ETF fallback, one explicit
  no-history failure for `stock:000004`, and 156 current-day fund NAV rows
  marked pending instead of failed.
- News recovery on 2026-05-29 completed as scheduler run `146`, `success`,
  inserting 63 current news rows through `eastmoney_global` and `sina_global`
  while Tushare `sina` returned zero rows for the window.
- Manual verification interruptions while investigating the wrapper path were
  explicitly marked failed/interrupted in scheduler runs `115` through `119` so
  they remain visible as operator test artifacts instead of stale running jobs.

Jarvis and short-message recovery evidence on 2026-05-29:

- Root cause: `jarvis_t_plus_one` scheduler run `110` deferred because the
  target evidence date `2026-05-28` had only three completed expert runs; the
  `sang_hongyang` expert Codex run had timed out and was stored as
  `cancelled`, which kept Jarvis readiness in `pending`.
- Runtime fix: artifact timeouts now persist `agent_runs.status = timed_out`
  instead of leaving a timeout as `cancelled`, and successful recovered runs
  clear stale `failure_reason` text so completed records do not look failed in
  later audits.
- Operational recovery: `sang_hongyang` was rerun with a longer timeout and
  completed as `agent_runs.id = 30`, persisting `expert_plans.id = 27`.
- Jarvis recovery: `run-jarvis-codex --date 2026-05-29
  --target-evidence-date 2026-05-28` completed as `agent_runs.id = 26`,
  persisted `jarvis_daily_briefs.id = 6`, and created
  `outbound_messages.id = 9`.
- Scheduler occurrence recovery: `jarvis_t_plus_one` was rerun for scheduled
  occurrence `2026-05-29T08:00:00` and completed as scheduler run `147`
  without duplicating the already-sent outbound message.
- Short-message evidence: `outbound_messages.id = 9` has
  `template_key = jarvis_daily_summary`, `status = sent`, `sent_at =
  2026-05-29 01:43:45`, `channel = imessage`, and `recipient_key =
  owner_phone`. Device-side receipt still needs human confirmation before this
  is marked accepted.

Do not mark this checklist fully accepted until real phone receipt is confirmed
and the remaining local operational watch items are resolved or explicitly
accepted: 2026-05-29 hourly market/news history is still `partial` by design
because same-day failures remain visible, and `stock:000004` still needs a
lifecycle/status decision after repeated no-history responses.

## Purpose

Keep scheduler, data incrementals, expert/Jarvis runtime, and phone
notification changes from passing review with hidden operational regressions.
Any large change touching these areas must explicitly check each item below.

## Scope

- LaunchAgent scheduler registration and runtime environment.
- Market price/NAV, capital-flow, and news incremental jobs.
- Expert T-day Codex runtime and Jarvis T+1 runtime.
- Jarvis daily brief and iMessage/phone notification delivery.
- WebUI/CLI task health visibility for missed, failed, deferred, and dry-run
  states.

## Required Acceptance Checklist

For every checked item, append evidence in this form:

```text
Evidence:
- Date:
- Command / DB query / WebUI route / screenshot:
- Result:
- Reviewer:
- Notes:
```

Severity rules:

- `P0`: Blocks acceptance. A regression can break the scheduled research and
  notification loop, expose secrets, or make the user believe stale/missing
  evidence is fresh.
- `P1`: Blocks release unless explicitly downgraded with a documented
  workaround and owner. A regression can degrade reliability, recovery, or
  operational visibility.
- `P2`: Should be fixed or tracked before closing the task. A regression creates
  documentation, polish, or secondary observability debt.

### LaunchAgent And Runtime Environment

- [ ] **P0** LaunchAgent points at the project DB and project root, not a temporary
  test path.
- [ ] **P0** LaunchAgent environment includes required runtime variables without
  exposing secrets in logs: `PYTHONPATH`, DB path, notification defaults,
  Codex binary, and provider credentials such as Tushare token.
- [ ] **P0** LaunchAgent and current shell environment are checked separately; a token
  present in the shell is not accepted as proof that scheduled jobs can see it.
- [ ] **P0** Provider credentials are validated by presence/length or setup status
  only; raw tokens must not be printed to logs, task output, screenshots, or
  documentation.
- [ ] **P0** Tests that install cron use a temporary LaunchAgents directory and cannot
  overwrite the real user LaunchAgent.
- [ ] **P1** Scheduler install/update tests assert the plist path, working directory,
  DB path, and injected environment without mutating the real user LaunchAgent.

### Scheduler Health And Visibility

- [ ] **P0** `scheduler today-status` shows expected, missed, failed, deferred, and
  completed jobs for the current date.
- [ ] **P0** `scheduler today-status` distinguishes `success`, `partial`, `failed`,
  `deferred`, and `missed`; historical failures from the same day remain visible
  even if a later manual rerun succeeds.
- [ ] **P0** Market/news/price failures are not hidden by later model/expert success;
  the overall status remains failed, partial, or degraded when upstream data
  failed earlier in the day.
- [ ] **P1** `task_logs`, `scheduler_runs`, `scheduler_watermarks`, and
  `provider_rate_limits` are all sufficient to explain what failed, what was
  skipped, what was deferred, and what data cursor advanced.
- [ ] **P1** WebUI status pages expose today's failed or missed jobs, not only the
  latest successful downstream model/advice result.

### Provider Budgets And Backoff

- [ ] **P0** Provider rate-limit accounting resets by hour/day even after provider
  failures; a failed price/NAV sync must not indefinitely block later market
  context jobs.
- [ ] **P0** Provider failure metadata preserves the previous count window
  (`last_success_at`) and records `last_failure_at`; failures must not overwrite
  the only timestamp used to reset hourly/daily budgets.
- [ ] **P1** Shared provider keys do not create accidental cross-job starvation:
  a heavy price/NAV job must not silently exhaust the market context job's
  budget without that state being visible.
- [ ] **P1** Backoff is cleared only when the failure has been understood or the
  recovery run is intentional; the reason for clearing or waiting out backoff is
  recorded in the operator notes or task output.

### News Incremental Chain

- [ ] **P0** Tushare-backed news jobs prove token presence and distinguish credential
  failures from DNS/network/provider failures.
- [ ] **P0** `Tushare provider requires TUSHARE_TOKEN` is treated as an environment
  propagation/configuration failure, not as a provider outage.
- [ ] **P1** DNS or connection failures against `api.waditu.com` are treated as
  network/provider failures, not credential failures, after token presence is
  confirmed in the scheduled runtime.
- [ ] **P0** A manual `news_hourly_incremental` rerun succeeds or records a concrete
  provider/network error before the news chain is considered recovered.
- [ ] **P1** A successful news rerun advances the `news_hourly_incremental/source:sina`
  watermark and does not hide earlier same-day failed windows.

### Market Price/NAV Chain

- [ ] **P1** Market/news network failures include enough detail to identify direct,
  environment proxy, and local proxy attempts when applicable.
- [ ] **P1** DNS or TLS failures for Sina/AKShare endpoints such as
  `finance.sina.com.cn` are recorded as network/provider failures with the
  attempted profile, not collapsed into a generic scheduler failure.
- [ ] **P0** `price_nav_post_close` continues after a single stale or unsupported asset
  returns no history; one asset such as `stock:000004` must not fail the whole
  price/NAV batch.
- [ ] **P0** Partial price/NAV success records `failed_assets`, `errors_by_asset`,
  `written_price_rows`, and per-asset watermarks so bad assets can be fixed
  without blocking good assets.
- [ ] **P0** Any price/NAV rerun that writes new rows is followed by `features_post_close`
  and `model_post_close` reruns before downstream advice/expert/Jarvis output is
  considered fresh.
- [ ] **P1** Assets with repeated no-history failures are reviewed for lifecycle/status
  correctness instead of being allowed to fail every scheduled run forever.

### Market Context And Capital Flow Chain

- [ ] **P0** `market_context_intraday` failures against Eastmoney/AKShare capital-flow
  endpoints are visible separately from price/NAV failures.
- [ ] **P0** `market_context_intraday` deferred states identify whether the cause is
  active backoff, hourly budget exhaustion, daily budget exhaustion, or missing
  subjects.
- [ ] **P0** A market context rerun after budget/backoff recovery either writes
  capital-flow rows or records an explicit provider/no-row error.
- [ ] **P1** Jarvis and experts treat stale or failed capital-flow evidence as degraded
  evidence, not as a silent success.

### Expert And Jarvis Runtime

- [ ] **P0** Expert T-day jobs run only after market/model evidence readiness is
  satisfied or record a clear deferred reason.
- [ ] **P0** Jarvis T+1 jobs run only after expert T-day runs are terminal and record
  the evidence date they used.
- [ ] **P0** Jarvis daily brief persistence and AI analysis task logs both succeed or
  expose their failure separately.
- [ ] **P0** Jarvis T+1 output records whether each upstream data chain was fresh,
  failed, partial, or deferred at synthesis time.
- [ ] **P1** Codex runtime runs preserve `agent_run_id`, artifact paths, target evidence
  date, and submission result for both expert and Jarvis jobs.

### Communication And Phone Notification

- [ ] **P0** Default notification behavior is real send, not dry-run, when adapter and
  recipient configuration are enabled.
- [ ] **P0** A historical `dry_run` outbound message with the same idempotency key can
  be retried as a real send; a historical `sent` message still blocks duplicate
  sends.
- [ ] **P0** `outbound_messages` has a terminal status, `sent_at` for real sends, and
  a clear error for failed or permission-required sends.
- [ ] **P1** The WebUI communication/status surfaces make dry-run, sent, failed,
  deferred, and missed states visible enough for daily operation.
- [ ] **P0** Jarvis daily brief generation and phone notification are logically
  decoupled but verified in the same scheduled flow: brief success alone is not
  enough if the notification stayed `dry_run`, `failed`, or `permission_required`.
- [ ] **P0** A resend after `dry_run` updates the original outbound row with
  `retry_count`, `sent_at`, and `retried_from_dry_run` behavior instead of
  creating a silent duplicate.
- [ ] **P0** Real iMessage delivery is manually verified before claiming the
  consumer received the message; evidence includes `outbound_messages.status =
  'sent'`, `sent_at`, and human confirmation or a concrete permission/provider
  error.
- [ ] **P1** Daily, weekly, expert, failure, and provider-warning notification
  templates all preserve compliance language and do not contain raw JSON,
  unsafe certainty claims, unmasked secrets, or private phone numbers in logs.

### Weekly Report Notification

- [ ] **P0** `jarvis_weekly_summary` exists as a distinct template or workflow
  output and is not simulated by re-sending a daily summary with ambiguous copy.
- [ ] **P0** Weekly report send uses the same allowlist, adapter, rate-limit,
  idempotency, and `dry_run -> sent` retry rules as daily Jarvis summaries.
- [ ] **P0** Weekly report coverage dates, included daily brief count, missing
  evidence count, stale evidence count, and latest stance are visible in the
  message body or persisted payload.
- [ ] **P1** A failed weekly send remains visible in `outbound_messages` and
  does not get hidden by a later successful daily notification.
- [ ] **P1** Weekly report delivery is included in manual operational recovery
  after scheduler or communication changes.

### Local Secrets, Privacy, And Git Hygiene

- [ ] **P0** `git status --short` is reviewed before completion; private local
  files such as `data/`, SQLite databases, local model research DBs, screenshots
  with secrets, LaunchAgent plists, and runtime logs are not staged.
- [ ] **P0** Secret and phone-number scans are run outside `data/` and `.git`
  before commit, for example `rg -n "TOKEN|TUSHARE|TS_TOKEN|[0-9]{11}" . -g
  '!data/**' -g '!.git/**'`.
- [ ] **P0** User phone numbers, provider tokens, Apple IDs, API keys, and local
  proxy credentials are stored only in local DB/config/environment, never in
  repository docs, tests, fixtures, screenshots, or task logs intended for Git.
- [ ] **P1** CLI/WebUI displays mask phone numbers and credentials where
  practical; full values may only appear in local operator-only config outputs
  when explicitly requested.
- [ ] **P2** If local-only operational data is produced during validation, the
  final report calls it out so reviewers do not accidentally include it in a PR.

### Recovery And Backfill Order

- [ ] **P0** Recovery/backfill follows dependency order: news/market context and
  price/NAV first, then features, then model/advice, then expert T-day, then
  Jarvis T+1, then phone notification.
- [ ] **P0** Manual recovery runs use the same SQLite DB and runtime environment as the
  scheduler, unless the deviation is explicitly documented.
- [ ] **P1** After recovery, the latest data/advice dates are checked in DB status and
  WebUI; examples include `latest_advice`, `price_daily`, `features_daily`,
  `model_predictions`, `daily_advice`, and `outbound_messages`.
- [ ] **P1** Backend service is restarted after code or runtime behavior changes so the
  WebUI reflects the fixed scheduler/communication logic.
- [ ] **P1** Recovery notes distinguish "automated test passed", "manual dry-run
  passed", and "real provider / real phone delivery observed".

## Minimum Test Set

Run these before accepting related changes:

```bash
python3 -m pytest tests/test_scheduler.py tests/test_communication.py tests/test_jarvis.py tests/test_agent_runtime.py tests/test_web_app.py tests/test_news_evidence.py tests/test_mcp_tools.py tests/test_mcp_server.py -q
python3 -m pytest -q
```

Coverage audit:

- 2026-05-28:
  `repo/audits/TASK-098-CHECKLIST-TEST-COVERAGE-2026-05-28.md` records the
  current P0/P1/P2 unit and module-integration coverage, gaps, and the
  D1/D2/D3 defects that were fixed on 2026-05-29. Updated on 2026-05-29 with
  explicit WebUI communication status coverage, operational recovery evidence,
  and full-test evidence.

For targeted fixes, record the exact subset and why it is sufficient:

```text
Targeted test evidence:
- Changed surfaces:
- Tests run:
- Tests intentionally skipped:
- Reason skipped tests are safe:
- Follow-up owner/date if any:
```

For local operational verification, also run:

```bash
python3 -m investment_forecasting.cli scheduler today-status --db data/investment_forecasting.sqlite3
python3 -m investment_forecasting.cli scheduler run-job news_hourly_incremental --db data/investment_forecasting.sqlite3
python3 -m investment_forecasting.cli scheduler run-job market_context_intraday --db data/investment_forecasting.sqlite3
python3 -m investment_forecasting.cli scheduler run-job price_nav_post_close --db data/investment_forecasting.sqlite3
python3 -m investment_forecasting.cli scheduler run-job features_post_close --db data/investment_forecasting.sqlite3
python3 -m investment_forecasting.cli scheduler run-job model_post_close --db data/investment_forecasting.sqlite3
python3 -m investment_forecasting.cli scheduler run-job expert_t_day_agents --db data/investment_forecasting.sqlite3
python3 -m investment_forecasting.cli scheduler run-job jarvis_t_plus_one --db data/investment_forecasting.sqlite3
python3 -m investment_forecasting.cli communication verify-setup --db data/investment_forecasting.sqlite3 --recipient-key owner_phone
python3 -m investment_forecasting.cli communication list-messages --db data/investment_forecasting.sqlite3 --limit 10
```

Run these SQLite checks after operational recovery:

```bash
sqlite3 data/investment_forecasting.sqlite3 "SELECT MAX(published_at), COUNT(*) FROM news_items;"
sqlite3 data/investment_forecasting.sqlite3 "SELECT MAX(trade_date), COUNT(*) FROM price_daily;"
sqlite3 data/investment_forecasting.sqlite3 "SELECT MAX(feature_date), COUNT(*) FROM features_daily;"
sqlite3 data/investment_forecasting.sqlite3 "SELECT MAX(prediction_date), COUNT(*) FROM model_predictions;"
sqlite3 data/investment_forecasting.sqlite3 "SELECT MAX(advice_date), COUNT(*) FROM daily_advice;"
sqlite3 data/investment_forecasting.sqlite3 "SELECT MAX(brief_date), COUNT(*) FROM jarvis_daily_briefs;"
sqlite3 data/investment_forecasting.sqlite3 "SELECT template_key, status, sent_at, error FROM outbound_messages ORDER BY id DESC LIMIT 10;"
sqlite3 data/investment_forecasting.sqlite3 "SELECT job_key, status, error, metadata_json FROM scheduler_runs ORDER BY id DESC LIMIT 20;"
sqlite3 data/investment_forecasting.sqlite3 "SELECT provider_key, hourly_count, daily_count, backoff_until, last_failure_reason, metadata_json FROM provider_rate_limits;"
```

Run these Git/privacy checks before commit:

```bash
git status --short
rg -n "TOKEN|TUSHARE|TS_TOKEN|[0-9]{11}" . -g '!data/**' -g '!.git/**' -g '!*.sqlite3' -g '!*.sqlite3-*'
git diff --check
```

If real phone delivery is part of the acceptance claim, also record:

```text
Real delivery evidence:
- Message template:
- outbound_messages.id:
- status / sent_at:
- Recipient confirmation:
- If not received, exact permission/provider error:
```

## Regression Notes

- 2026-05-28: Real scheduler plist had once been overwritten by a test temp
  path; cron installation tests must never write to the real home LaunchAgents
  directory.
- 2026-05-28: Tushare token was available to the shell but not to the old
  LaunchAgent environment, causing early news jobs to fail as missing token.
- 2026-05-28: Later Tushare news failures were DNS/network failures against
  `api.waditu.com`, not credential failures.
- 2026-05-28: Manual `news_hourly_incremental` rerun proved the token was valid
  and the later issue was transient network/DNS or provider reachability.
- 2026-05-28: Sina/AKShare price/NAV endpoints failed with DNS/TLS/proxy
  profile errors; retry diagnostics must preserve which profile failed.
- 2026-05-28: `price_nav_post_close` originally failed the entire job on
  `stock:000004` returning no history; the accepted behavior is partial success
  with `errors_by_asset` and continued writes for other assets.
- 2026-05-28: After partial price/NAV recovery, the successful rerun wrote 603
  price/NAV rows while 26 no-history assets were recorded as local failures;
  downstream features and model jobs were rerun afterward.
- 2026-05-28: A Jarvis daily summary was persisted as `dry_run`; idempotency
  blocked later real send until `dry_run -> sent` retry was supported.
- 2026-05-28: AKShare price/NAV failure and provider budget accounting caused
  market context jobs to defer as budget exhausted; provider count windows must
  survive failures and reset correctly.
- 2026-05-28: `market_context_intraday` remained unhealthy after price/news
  recovery because Eastmoney/AKShare capital-flow requests had failed and later
  runs were deferred by provider budget/backoff; this chain must be verified
  independently.
- 2026-05-28: `scheduler today-status` can remain `bad` even after manual
  recovery because earlier same-day failures are intentionally visible. Reviewers
  must inspect both latest reruns and historical same-day failures.

## Pass/Fail Rule

A large change touching scheduler, market/news data, provider credentials,
expert/Jarvis runtime, or phone delivery cannot pass if any required checklist
item above is unverified. Mark each item with evidence from tests, CLI output,
DB rows, or WebUI screenshots. If an item is intentionally deferred, record the
reason and downgrade the change status instead of declaring the spec complete.
