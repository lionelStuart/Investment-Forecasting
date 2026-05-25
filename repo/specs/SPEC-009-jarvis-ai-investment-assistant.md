# SPEC-009: Jarvis AI Investment Assistant

## Status

draft

Implementation through `TASK-065` is accepted for the local provider-boundary
milestone: expert/Jarvis prompt schemas are versioned, provider-backed
orchestration is wired through the shared adapter, deterministic fallback is
auditable, Jarvis confidence gates are persisted and surfaced, and future
provider work must reuse `investment_forecasting.ai_providers`.

## Summary

The final product goal is an AI investment assistant named Jarvis. Jarvis is
the user-facing intelligence layer above the market information system,
prediction model system, and expert committee system.

Jarvis does not invent market facts. It gathers system-level market data,
model predictions, backtest/model quality, expert plans, expert scores, and
expert virtual returns, then synthesizes a simple daily wealth-management
brief. The output should be easy enough for a non-technical user to understand:
what to watch today, what the models forecast, what each expert thinks, how
each expert is performing, and what risk boundaries matter.

## Product Goal

Jarvis should answer the daily question:

> 今天我应该关注什么方向，为什么，模型怎么看，专家怎么看，哪些专家最近做得好或做得差，我应该如何理解风险？

The answer must be concise, traceable, and safe. It is research support, not a
guaranteed return or direct real-money trading instruction.

## System Inputs

Jarvis must synthesize these evidence sources:

- System market information:
  - market snapshots;
  - macro observations;
  - capital-flow observations as auxiliary liquidity/crowding evidence;
  - retrievable news evidence when the AI requests asset/theme/date-specific
    context through the news evidence tool;
  - data freshness and task health;
  - provider/data warnings.
- Prediction model system:
  - latest model predictions by asset and horizon;
  - confidence, expected return, downside risk, up probability;
  - backtest/model quality scores and degraded states.
- Expert system:
  - expert style and mandate;
  - daily expert plan and whether the expert traded or stayed in cash;
  - expert forecast/stance;
  - current virtual capital, return, drawdown, score, and lifecycle state;
  - expert lessons, warnings, probation, retirement, and replacement context.
- User context:
  - active risk profile;
  - investment horizon;
  - max equity/min cash constraints;
  - communication preference when enabled.

## Jarvis Daily Advice Shape

Each daily Jarvis output should include:

1. `今日关注方向`
   - 1 to 3 plain-language directions, such as defensive cash, ETF rotation,
     AI/software ETF watch, dividend/fixed-income watch, or broad-market
     recovery confirmation.

2. `一句话结论`
   - A simple stance such as `偏防守，等待确认`, `均衡观察`, or `小幅进攻但控制回撤`.

3. `模型预测`
   - Key model forecasts by horizon.
   - Confidence and downside risk.
   - Model quality or degraded-state warning.

4. `专家观点`
   - One summary row/card per active expert.
   - Expert style, today's action, target direction, evidence, confidence,
     score, current return, drawdown, and whether the expert is active,
     warning, probation, or retired.

5. `综合建议`
   - A simple interpretation that combines market state, model evidence, and
     expert behavior.
   - It should include what to watch, what not to overreact to, and what would
     change the stance.

6. `风险与边界`
   - Explicit risk warning, data freshness warning, and uncertainty note.
   - No capital-protection or guaranteed-return language.

7. `证据入口`
   - Links or references back to market snapshot, predictions, backtests,
     capital-flow observations, expert plans, scorecards, and task logs.

## Jarvis AI Analysis

- Jarvis should run a daily AI financial analysis after system market data,
  model predictions, expert AI analyses, expert plans, expert scorecards, and
  virtual portfolio returns are available.
- The AI analysis must consume structured evidence packets, not raw database
  dumps.
- The output must be persisted as structured fields plus plain-language text:
  focus directions, model interpretation, expert consensus, expert
  disagreement, risk boundaries, watch triggers, and user-facing daily
  recommendation.
- The persisted Jarvis daily brief must reference the expert AI analysis IDs
  reviewed and the Jarvis AI analysis ID generated for the same brief.
- Jarvis may challenge experts when their plans conflict with model quality,
  stale data, or poor recent performance.
- Jarvis must clearly distinguish:
  - system market facts;
  - model forecasts;
  - each expert's independent analysis;
  - each expert's score/current return;
  - Jarvis's final synthesis.
- Jarvis AI analysis must pass compliance and evidence-link checks before it is
  shown in WebUI, MCP, or phone summaries.

## AI Interaction Layer Requirements

- Real AI interaction must enter through an explicit provider adapter. Expert,
  Jarvis, WebUI, workflow, MCP, and communication modules must not call an LLM
  SDK directly.
- The provider receives only bounded evidence packets built from persisted
  system records. It must not receive raw database dumps or hidden prompt-only
  state.
- Provider output must be structured JSON that conforms to the existing
  expert/Jarvis analysis output shape before it can be saved.
- The system must preserve deterministic fallback. Missing credentials,
  provider timeout, malformed JSON, unsupported claims, unsafe language, or
  validation failure must produce an auditable fallback result instead of
  blocking the daily research workflow.
- `ai_analysis_records.source`, `version`, `status`, `validation_json`, and
  task logs must make it clear whether a record came from a real provider or
  fallback.
- Prompts must require separation of system facts, model forecasts, expert
  independent analysis, expert score/current return, Jarvis synthesis, risk
  warnings, and watch triggers.
- Prompts must not receive all recent news by default. When news context is
  needed, the AI should call `search_news_evidence` with
  explicit filters such as asset, theme, source, date range, event type, and
  sentiment.
- Any news-based claim must cite returned `news_evidence_ids`; unsupported news
  evidence IDs are rejected before persistence or display.
- Jarvis must confidence-gate extreme model predictions. Low-confidence,
  stale, degraded, or outlier forecasts should be described as uncertain watch
  signals, not as strong daily recommendations.
- Jarvis must mark expert score/return evidence as immature when the stored
  evaluation window is too short.
- MCP Jarvis tools must expose provider/fallback status for the persisted
  Jarvis AI analysis so agents can explain whether a brief used provider-backed
  or deterministic fallback analysis.

## User Experience Requirements

- Jarvis must be the first-level product experience when the system is mature.
- Jarvis output should be "傻瓜式": useful without reading raw tables,
  model rows, JSON, or SQL-like fields.
- Detailed market/model/expert evidence should remain accessible as secondary
  drill-down.
- Jarvis should explain disagreement. If models and experts disagree, the user
  should see the conflict and why it matters.
- Jarvis should not overfit to the currently best-performing expert; expert
  returns are evidence, not a guarantee.
- Jarvis should be suitable for WebUI display and phone notification summary.

## Data And Persistence Requirements

- Jarvis daily outputs must be persisted with date, generated timestamp,
  model/version, summary fields, evidence links, and risk warnings.
- Jarvis must reference source evidence IDs instead of copying raw data blobs.
- Reruns for the same date should be idempotent or versioned.
- Jarvis must record when evidence is missing or stale.
- Jarvis AI analysis evidence packets should include capital-flow IDs/counts
  when observations are available and should not treat flow data as a certain
  return predictor.
- Jarvis may reference news evidence IDs returned by the retrieval tool, but
  news content should not be copied wholesale into persisted briefs. Store
  bounded excerpts, source timestamps, tags, and match reasons.

## Integration Requirements

- Daily workflow should eventually generate Jarvis after market snapshots,
  forecasts, backtests, advice, expert plans, and expert scorecards are
  available.
- Daily workflow should eventually run expert AI analysis first, then expert
  plans, then Jarvis AI analysis as the top-level synthesis.
- WebUI should provide a `/jarvis` route or dashboard-first Jarvis module.
- MCP/Agent tools should expose structured Jarvis daily advice.
- Communication templates should be able to send a short Jarvis phone summary
  through the communication adapter layer. The summary must render from the
  persisted Jarvis brief, use safe research-support language, include a local
  `/jarvis` inspection hint, and rely on communication-service idempotency and
  allowlist policy.

## Non-Goals

- Jarvis must not place real trades.
- Jarvis must not bypass expert, model, or market evidence.
- Jarvis must not hide uncertainty, data freshness problems, model degradation,
  or expert underperformance.
- Jarvis must not output a single opaque "buy/sell" instruction.
- The AI interaction layer must not add new data providers, new experts,
  automatic rebalancing, live trading, inbound phone commands, or a new WebUI
  redesign in the same milestone.

## Acceptance Criteria

- A Jarvis daily advice record can be generated from persisted market, model,
  expert, and user-context evidence.
- The daily output includes today's focus directions, model forecast summary,
  each active expert's stance, score, current return, and risk state.
- The daily output includes or links to each expert's independent AI analysis.
- The WebUI can show Jarvis as a simple first-screen brief with secondary
  evidence drill-down.
- Jarvis can explain model/expert disagreement.
- Jarvis can surface capital-flow evidence availability and link it back to
  `/market`.
- Jarvis phone summary can be rendered through communication templates after
  communication infrastructure exists.
- Tests verify missing evidence, stale data, expert disagreement, and safe
  language handling.
- A configured AI provider can generate expert and Jarvis analyses through an
  adapter while preserving deterministic fallback.
- Provider-backed and fallback analyses are distinguishable in persisted
  records, WebUI, task logs, and MCP output.
- Tests verify provider success, provider failure, malformed output,
  unsupported claims, fallback, confidence gating, and expert-maturity wording.
- News evidence is accessed through a retrieval tool and referenced by evidence
  IDs; it is not injected wholesale into every expert or Jarvis prompt.

## Related Tasks

- `TASK-047`: Jarvis product model and persistence.
- `TASK-048`: Jarvis synthesis engine.
- `TASK-049`: Jarvis WebUI first-screen experience.
- `TASK-050`: Jarvis MCP and Agent workflow.
- `TASK-051`: Jarvis phone summary template.
- `TASK-052`: AI analysis orchestration.
- `TASK-061`: AI provider adapter contract.
- `TASK-062`: AI prompt and evidence schema freeze.
- `TASK-063`: Provider-backed AI orchestration.
- `TASK-064`: Jarvis confidence gating and maturity wording.
- `TASK-065`: Architecture and code index synchronization.
- `TASK-071`: News evidence persistence and ingestion.
- `TASK-072`: News indexing, linking, and feature extraction.
- `TASK-073`: News evidence retrieval service and MCP tool.
