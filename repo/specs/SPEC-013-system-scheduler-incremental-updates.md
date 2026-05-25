# SPEC-013: System Scheduler And Incremental Updates

## Status

draft

## Goal

Replace Codex app automation with a system-owned scheduler that runs frequent,
polite, incremental data and news updates. The scheduler must update missing
or stale slices by watermark, not repeatedly fetch full history, so provider
interfaces are protected from unnecessary load and temporary bans.

## Product Requirement

The system must keep market evidence and news evidence fresh enough for expert
agents and Jarvis without depending on Codex as the scheduler.

Codex remains an agent runtime invoked by system workflows. It must not be the
mechanism that wakes up every hour to update data.

## Scheduling Model

The MVP scheduler should support:

- hourly incremental update jobs for data and news freshness;
- market-aware windows so trading-day work differs from weekend/holiday work;
- distinct job types for news, capital flow, prices, features, predictions,
  monitoring, expert agents, and Jarvis;
- persisted job definitions, run logs, watermarks, retry state, and provider
  backoff state;
- manual trigger commands that use the same scheduler service and safety
  policy as automatic runs.

Minimum recommended cadence:

- Every hour:
  - ingest bounded news windows since the last successful news watermark;
  - rebuild news links/tags/features only for changed news/date scopes;
  - refresh task/data health status.
- Trading hours or provider-supported intraday windows:
  - refresh bounded capital-flow observations and other lightweight market
    context when configured;
  - do not fetch full asset history.
- After expected market close data availability:
  - incrementally ingest prices/NAV only for assets whose latest stored date is
    behind the target trading date;
  - calculate features only for affected asset/date ranges;
  - run forecasts, reliability, backtests/monitoring, and advice only after
    required data freshness gates pass.
- T day evening:
  - trigger expert Codex agent runs only after T market/model evidence is ready
    or explicitly marked stale/degraded.
- T+1 morning:
  - trigger Jarvis Codex agent only after T expert actions are completed or
    explicitly skipped/failed.

Exact wall-clock times should be configurable because provider data availability
differs by source and network condition.

## Incremental Watermark Requirements

Each scheduled job must track its own incremental state.

MVP watermarks:

- `news`: last successful `published_at` or source window end per provider and
  source.
- `price_daily`: latest stored trade date per provider/source/asset.
- `features_daily`: latest calculated feature date per asset.
- `capital_flow_observations`: latest flow date per scope/subject/provider.
- `model_predictions`: latest prediction date per model/horizon.
- `news_feature_daily`: latest generated feature date per scope/key.

Jobs should compute the missing window from stored watermarks and cap the
request size. No hourly job may default to a broad full-history fetch.

## Provider Politeness Requirements

The scheduler must enforce provider safety centrally:

- per-provider concurrency limit, default 1 for AKShare/Tushare-style local
  calls;
- minimum delay and optional jitter between provider requests;
- exponential backoff after transient failures, empty suspicious responses, or
  likely throttling;
- per-job request cap;
- per-provider hourly/daily request budget;
- skip or defer jobs when backoff is active;
- task logs must explain whether a job updated, skipped, deferred, or failed.

If a provider appears throttled or blocked, the scheduler should stop that
provider's job family for the backoff window instead of retrying aggressively.

## Data Freshness Gates

Downstream work must be gated by evidence readiness:

- forecasts should not run when price/features are missing for the required
  target date unless the run is explicitly marked degraded;
- expert agents should see clear stale/degraded evidence status before acting;
- Jarvis should not run before expert actions are terminal;
- Jarvis must downgrade confidence when the latest hourly update failed or
  evidence is stale.

## CLI And Runtime Surfaces

Planned commands:

- `investment-forecasting scheduler install`
  - installs or enables the local system-owned scheduler.
- `investment-forecasting scheduler run-due`
  - runs all jobs due at the current time.
- `investment-forecasting scheduler run-job JOB_KEY`
  - manually triggers one job through the same policy path.
- `investment-forecasting scheduler list-jobs`
  - lists job definitions, cadence, enabled state, and next run time.
- `investment-forecasting scheduler status`
  - shows latest run status, watermarks, backoff, and provider budgets.

These commands are system commands. They are not Codex automations.

## Persistence Requirements

MVP tables or equivalent persisted state:

- `scheduler_jobs`
  - job key, job type, enabled flag, cadence, time window, provider key, policy
    JSON, next run time, and description.
- `scheduler_runs`
  - job key, scheduled time, started/finished time, status, updated counts,
    skipped/deferred reason, provider request counts, and error.
- `scheduler_watermarks`
  - job key, provider/source/scope keys, last successful cursor/date/datetime,
    last attempted cursor, and metadata.
- `provider_rate_limits`
  - provider key, backoff-until timestamp, hourly/daily counters, failure
    counters, and last failure reason.

Existing `task_logs` should still receive summarized entries so WebUI/system
health remains coherent.

## Codex Automation Removal

The old Codex app automation `investment-forecasting-daily-run` must be removed
from the operational path. Documentation may reference it only as historical
context or migration cleanup.

## Non-Goals

- No full-history hourly ingestion.
- No Codex-owned cron or heartbeat automation for data refresh.
- No live trading or brokerage action.
- No dependency on WebUI being open.
- No hidden provider retries outside the central policy.

## Acceptance Criteria

- No active Codex app automation is required for data/news updates.
- The system can list scheduler jobs and run due jobs manually.
- Hourly news update uses source-specific watermarks and bounded windows.
- Market data update uses per-asset/provider watermarks and skips already
  current assets.
- Provider policy enforces delay, jitter, request caps, and backoff.
- Task logs and scheduler run records show updated/skipped/deferred/failed
  outcomes.
- Tests prove hourly runs do not call full-history ingestion by default.
- Tests prove a throttled provider enters backoff and later jobs are deferred.

## Related Tasks

- `TASK-085`: Remove Codex automation and document scheduler migration.
- `TASK-086`: Scheduler persistence, job registry, and CLI.
- `TASK-087`: Incremental watermarks for news, market data, and features.
- `TASK-088`: Provider rate limit, backoff, and request-budget policy.
- `TASK-089`: Hourly scheduler orchestration, health UI, and acceptance.
