# Index

## Specs

| ID | File | Status | Tags | Depends On |
| --- | --- | --- | --- | --- |
| SPEC-001 | `specs/SPEC-001-data-foundation.md` | draft | data, sqlite, akshare | - |
| SPEC-002 | `specs/SPEC-002-quant-forecast-backtest.md` | draft | features, forecast, backtest, scoring | SPEC-001 |
| SPEC-003 | `specs/SPEC-003-advice-generation.md` | draft | advice, risk-profiles, compliance | SPEC-001, SPEC-002 |
| SPEC-004 | `specs/SPEC-004-mcp-service.md` | draft | mcp, tools, json | SPEC-001, SPEC-002, SPEC-003 |
| SPEC-005 | `specs/SPEC-005-daily-automation.md` | draft | scheduler, codex, logs | SPEC-001, SPEC-002, SPEC-003, SPEC-004 |
| SPEC-006 | `specs/SPEC-006-webui-workbench.md` | draft | webui, dashboard, inspection | SPEC-001, SPEC-002, SPEC-003 |
| SPEC-007 | `specs/SPEC-007-expert-committee-virtual-investing.md` | draft | experts, virtual-portfolio, scoring, lifecycle | SPEC-001, SPEC-002, SPEC-003, SPEC-006 |
| SPEC-008 | `specs/SPEC-008-local-phone-communication-adapters.md` | draft | communication, imessage, adapters, notifications | SPEC-003, SPEC-005, SPEC-006, SPEC-007 |
| SPEC-009 | `specs/SPEC-009-jarvis-ai-investment-assistant.md` | draft | jarvis, assistant, synthesis, daily-brief | SPEC-002, SPEC-003, SPEC-006, SPEC-007, SPEC-008 |
| SPEC-010 | `specs/SPEC-010-news-evidence-retrieval.md` | draft | news, evidence, retrieval, mcp, tushare | SPEC-001, SPEC-004, SPEC-009 |
| SPEC-011 | `specs/SPEC-011-model-reliability-upgrade.md` | draft | model, reliability, validation, ranking, jarvis | SPEC-002, SPEC-009, SPEC-010 |
| SPEC-012 | `specs/SPEC-012-codex-agent-runtime-orchestration.md` | draft | codex-runtime, agents, experts, jarvis, scheduler, mcp | SPEC-004, SPEC-007, SPEC-009, SPEC-010, SPEC-011 |
| SPEC-013 | `specs/SPEC-013-system-scheduler-incremental-updates.md` | draft | scheduler, incremental, hourly, watermarks, provider-backoff | SPEC-001, SPEC-005, SPEC-010, SPEC-012 |
| SPEC-014 | `specs/SPEC-014-ytd-forecast-replay-model-tuning.md` | draft | model, replay, ytd, accuracy, confidence, tuning | SPEC-002, SPEC-011 |
| SPEC-015 | `specs/SPEC-015-model-applicability-shadow-routing.md` | draft | model, applicability, shadow-routing, governance, confidence | SPEC-014, SPEC-011 |

## Tasks

| ID | File | Status | Spec | Depends On |
| --- | --- | --- | --- | --- |
| TASK-000 | `tasks/TASK-000-bootstrap-project-memory.md` | completed | PROJECT | - |
| TASK-001 | `tasks/TASK-001-python-skeleton-sqlite-schema.md` | completed | SPEC-001 | TASK-000 |
| TASK-002 | `tasks/TASK-002-akshare-ingestion.md` | completed | SPEC-001 | TASK-001 |
| TASK-003 | `tasks/TASK-003-feature-risk-metrics.md` | completed | SPEC-002 | TASK-002 |
| TASK-004 | `tasks/TASK-004-baseline-forecast-backtest-scoring.md` | completed | SPEC-002 | TASK-003 |
| TASK-005 | `tasks/TASK-005-daily-advice-generator.md` | completed | SPEC-003 | TASK-004 |
| TASK-006 | `tasks/TASK-006-mcp-tools.md` | completed | SPEC-004 | TASK-005 |
| TASK-007 | `tasks/TASK-007-daily-codex-automation.md` | completed | SPEC-005 | TASK-006 |
| TASK-008 | `tasks/TASK-008-webui-workbench.md` | completed | SPEC-006 | TASK-005 |
| TASK-009 | `tasks/TASK-009-model-calibration-enhancement.md` | completed | SPEC-002 | TASK-004 |
| TASK-010 | `tasks/TASK-010-readme-completion-audit-and-gap-plan.md` | completed | README | TASK-001..TASK-009 |
| TASK-011 | `tasks/TASK-011-mcp-stdio-transport.md` | completed | SPEC-004 | TASK-006, TASK-010 |
| TASK-012 | `tasks/TASK-012-broader-akshare-universe.md` | completed | SPEC-001 | TASK-002, TASK-010 |
| TASK-013 | `tasks/TASK-013-fund-info-ingestion.md` | completed | SPEC-001 | TASK-002, TASK-010 |
| TASK-014 | `tasks/TASK-014-market-environment-data.md` | completed | SPEC-001 | TASK-003, TASK-010 |
| TASK-015 | `tasks/TASK-015-data-quality-retry-cache.md` | completed | SPEC-001, SPEC-005 | TASK-002, TASK-007, TASK-010 |
| TASK-016 | `tasks/TASK-016-benchmark-advice-outcome-scoring.md` | completed | SPEC-002, SPEC-003 | TASK-004, TASK-005, TASK-010 |
| TASK-017 | `tasks/TASK-017-historical-calibration-corpus.md` | completed | SPEC-002 | TASK-009, TASK-012, TASK-010 |
| TASK-018 | `tasks/TASK-018-external-macro-data-provider.md` | completed | SPEC-001 | TASK-014, TASK-010 |
| TASK-019 | `tasks/TASK-019-advice-history-product-links.md` | completed | SPEC-006 | TASK-008, TASK-005 |
| TASK-020 | `tasks/TASK-020-data-status-and-service-health.md` | completed | SPEC-006, SPEC-005 | TASK-008, TASK-019 |
| TASK-021 | `tasks/TASK-021-user-risk-preferences.md` | completed | SPEC-003, SPEC-006 | TASK-005, TASK-008, TASK-020 |
| TASK-022 | `tasks/TASK-022-simulated-portfolio-tracking.md` | completed | ROADMAP | TASK-021 |
| TASK-023 | `tasks/TASK-023-target-volatility-allocation.md` | completed | ROADMAP | TASK-021, TASK-022 |
| TASK-024 | `tasks/TASK-024-model-monitoring-drift.md` | completed | ROADMAP | TASK-016, TASK-017 |
| TASK-025 | `tasks/TASK-025-provider-expansion-tushare.md` | completed | ROADMAP | TASK-015 |
| TASK-026 | `tasks/TASK-026-fund-peer-benchmark-scoring.md` | completed | ROADMAP | TASK-016 |
| TASK-027 | `tasks/TASK-027-data-expansion-and-channel-hardening.md` | completed | SPEC-001 | TASK-015, TASK-020 |
| TASK-027 | `tasks/TASK-027-provider-access-polite-ingestion.md` | completed | SPEC-001, SPEC-005 | TASK-015, TASK-025 |
| TASK-028 | `tasks/TASK-028-product-timeline-run-history.md` | completed | SPEC-006 | TASK-019, TASK-020, TASK-021 |
| TASK-029 | `tasks/TASK-029-product-category-navigation.md` | completed | SPEC-006 | TASK-027, TASK-028 |
| TASK-030 | `tasks/TASK-030-fund-screening-filters-presets.md` | completed | SPEC-006 | TASK-013, TASK-021, TASK-029 |
| TASK-031 | `tasks/TASK-031-red-green-market-semantics.md` | completed | SPEC-006 | TASK-008 |
| TASK-032 | `tasks/TASK-032-asset-level-prediction-cards.md` | completed | SPEC-006 | TASK-004, TASK-027, TASK-031 |
| TASK-033 | `tasks/TASK-033-dashboard-brief-run-health.md` | completed | SPEC-006, SPEC-005 | TASK-020, TASK-021, TASK-028, TASK-031 |
| TASK-034 | `tasks/TASK-034-full-asset-scale-ingestion.md` | completed | SPEC-001, SPEC-002 | TASK-027 |
| TASK-035 | `tasks/TASK-035-progressive-disclosure-technical-tables.md` | completed | SPEC-006 | TASK-029, TASK-030, TASK-032, TASK-033 |
| TASK-036 | `tasks/TASK-036-expert-architecture-roster-model.md` | completed | SPEC-007 | TASK-021, TASK-030 |
| TASK-037 | `tasks/TASK-037-expert-virtual-portfolio-foundation.md` | completed | SPEC-007, ROADMAP | TASK-022, TASK-036 |
| TASK-038 | `tasks/TASK-038-expert-daily-planning-execution.md` | completed | SPEC-007 | TASK-032, TASK-033, TASK-036, TASK-037 |
| TASK-039 | `tasks/TASK-039-expert-scoring-retirement-hiring.md` | completed | SPEC-007 | TASK-024, TASK-037, TASK-038 |
| TASK-040 | `tasks/TASK-040-expert-committee-webui.md` | completed | SPEC-007, SPEC-006 | TASK-035, TASK-036, TASK-037, TASK-038, TASK-039 |
| TASK-041 | `tasks/TASK-041-expert-agent-workflow-mcp.md` | completed | SPEC-007, SPEC-004, SPEC-005 | TASK-036, TASK-038, TASK-039 |
| TASK-042 | `tasks/TASK-042-communication-adapter-architecture.md` | completed | SPEC-008 | TASK-007, TASK-020 |
| TASK-043 | `tasks/TASK-043-imessage-outbound-adapter.md` | completed | SPEC-008 | TASK-042 |
| TASK-044 | `tasks/TASK-044-mobile-notification-templates.md` | completed | SPEC-008 | TASK-033, TASK-038, TASK-042, TASK-043 |
| TASK-045 | `tasks/TASK-045-communication-webui-cli.md` | completed | SPEC-008, SPEC-006 | TASK-035, TASK-042, TASK-043 |
| TASK-046 | `tasks/TASK-046-safe-inbound-phone-command-design.md` | completed | SPEC-008 | TASK-043 |
| TASK-047 | `tasks/TASK-047-jarvis-product-model-persistence.md` | completed | SPEC-009 | TASK-036, TASK-041 |
| TASK-048 | `tasks/TASK-048-jarvis-synthesis-engine.md` | completed | SPEC-009 | TASK-032, TASK-033, TASK-038, TASK-039, TASK-047 |
| TASK-049 | `tasks/TASK-049-jarvis-webui-first-screen.md` | completed | SPEC-009, SPEC-006 | TASK-035, TASK-040, TASK-047, TASK-048 |
| TASK-050 | `tasks/TASK-050-jarvis-mcp-agent-workflow.md` | completed | SPEC-009, SPEC-004 | TASK-041, TASK-048 |
| TASK-051 | `tasks/TASK-051-jarvis-phone-summary-template.md` | completed | SPEC-009, SPEC-008 | TASK-043, TASK-044, TASK-048 |
| TASK-052 | `tasks/TASK-052-ai-analysis-orchestration.md` | completed | SPEC-007, SPEC-009 | TASK-038, TASK-041, TASK-047, TASK-048 |
| TASK-053 | `tasks/TASK-053-market-macro-indicator-page.md` | completed | SPEC-006 | TASK-014, TASK-018, TASK-029 |
| TASK-054 | `tasks/TASK-054-industry-theme-classification.md` | completed | SPEC-001, SPEC-006 | TASK-029, TASK-030, TASK-053 |
| TASK-055 | `tasks/TASK-055-theme-allocation-overview.md` | completed | SPEC-006 | TASK-054, TASK-032 |
| TASK-056 | `tasks/TASK-056-capital-flow-observations.md` | completed | SPEC-001, SPEC-006 | TASK-053, TASK-055 |
| TASK-057 | `tasks/TASK-057-capital-flow-evidence-synthesis.md` | completed | SPEC-003, SPEC-009 | TASK-056, TASK-048, TASK-052 |
| TASK-058 | `tasks/TASK-058-fund-holdings-ingestion-webui.md` | completed | SPEC-001, SPEC-006 | TASK-013, TASK-030, TASK-054 |
| TASK-059 | `tasks/TASK-059-fund-holding-theme-lookthrough.md` | completed | SPEC-006 | TASK-054, TASK-058 |
| TASK-060 | `tasks/TASK-060-correlation-risk-budget-advice.md` | completed | SPEC-003, SPEC-006 | TASK-021, TASK-023 |
| TASK-061 | `tasks/TASK-061-ai-provider-adapter-contract.md` | completed | SPEC-009 | TASK-052, TASK-060 |
| TASK-062 | `tasks/TASK-062-ai-prompt-evidence-schema-freeze.md` | completed | SPEC-009 | TASK-061, TASK-073 |
| TASK-063 | `tasks/TASK-063-provider-backed-ai-orchestration.md` | completed | SPEC-009 | TASK-061, TASK-062 |
| TASK-064 | `tasks/TASK-064-jarvis-confidence-gates.md` | completed | SPEC-009, SPEC-006 | TASK-063 |
| TASK-065 | `tasks/TASK-065-architecture-code-index-sync.md` | completed | ARCHITECTURE, CODE_INDEX | TASK-061, TASK-062, TASK-063, TASK-064 |
| TASK-066 | `tasks/TASK-066-jarvis-five-entry-navigation.md` | completed | SPEC-006 | TASK-061 |
| TASK-067 | `tasks/TASK-067-today-brief-consolidation.md` | completed | SPEC-006, SPEC-009 | TASK-066 |
| TASK-068 | `tasks/TASK-068-opportunity-pool-consolidation.md` | completed | SPEC-006 | TASK-066 |
| TASK-069 | `tasks/TASK-069-evidence-settings-consolidation.md` | completed | SPEC-006 | TASK-066 |
| TASK-070 | `tasks/TASK-070-consumer-ia-acceptance-and-docs.md` | completed | SPEC-006, ARCHITECTURE, CODE_INDEX | TASK-066, TASK-067, TASK-068, TASK-069 |
| TASK-071 | `tasks/TASK-071-news-evidence-persistence-ingestion.md` | completed | SPEC-010, SPEC-001 | TASK-061 |
| TASK-072 | `tasks/TASK-072-news-indexing-linking-features.md` | completed | SPEC-010 | TASK-071 |
| TASK-073 | `tasks/TASK-073-news-evidence-search-mcp.md` | completed | SPEC-010, SPEC-004, SPEC-009 | TASK-071, TASK-072 |
| TASK-074 | `tasks/TASK-074-prediction-target-model-output-redesign.md` | completed | SPEC-011, SPEC-002 | TASK-073 |
| TASK-075 | `tasks/TASK-075-financial-validation-upgrade.md` | completed | SPEC-011, SPEC-002 | TASK-074 |
| TASK-076 | `tasks/TASK-076-interpretable-candidate-model-pool.md` | completed | SPEC-011, SPEC-002 | TASK-075 |
| TASK-077 | `tasks/TASK-077-model-evidence-packet-expert-review.md` | completed | SPEC-011, SPEC-007, SPEC-009 | TASK-076 |
| TASK-078 | `tasks/TASK-078-jarvis-model-risk-officer-gates.md` | completed | SPEC-011, SPEC-009 | TASK-077 |
| TASK-079 | `tasks/TASK-079-model-promotion-demotion-governance.md` | completed | SPEC-011 | TASK-078 |
| TASK-080 | `tasks/TASK-080-codex-runtime-access-contract.md` | completed | SPEC-012 | ADR-008 |
| TASK-081 | `tasks/TASK-081-role-scoped-mcp-api-tool-manifest.md` | completed | SPEC-012, SPEC-004 | TASK-080 |
| TASK-082 | `tasks/TASK-082-expert-agent-skill-prompt-template.md` | completed | SPEC-012, SPEC-007 | TASK-080, TASK-081 |
| TASK-083 | `tasks/TASK-083-expert-daily-agent-execution-workflow.md` | completed | SPEC-012, SPEC-007 | TASK-082 |
| TASK-084 | `tasks/TASK-084-jarvis-t-plus-one-agent-workflow.md` | completed | SPEC-012, SPEC-009 | TASK-083 |
| TASK-085 | `tasks/TASK-085-remove-codex-automation-scheduler-migration.md` | completed | SPEC-013 | ADR-009 |
| TASK-086 | `tasks/TASK-086-system-scheduler-persistence-cli.md` | completed | SPEC-013 | TASK-085 |
| TASK-087 | `tasks/TASK-087-incremental-watermarks-news-market-features.md` | completed | SPEC-013 | TASK-086 |
| TASK-088 | `tasks/TASK-088-provider-rate-limit-backoff-policy.md` | completed | SPEC-013 | TASK-087 |
| TASK-089 | `tasks/TASK-089-hourly-scheduler-orchestration-health.md` | completed | SPEC-013 | TASK-088 |
| TASK-090 | `tasks/TASK-090-ytd-forecast-replay-corpus.md` | completed | SPEC-014 | TASK-079 |
| TASK-091 | `tasks/TASK-091-replay-scoring-diagnostics.md` | completed | SPEC-014 | TASK-090 |
| TASK-092 | `tasks/TASK-092-model-tuning-recommendation-report.md` | completed | SPEC-014 | TASK-091 |
| TASK-093 | `tasks/TASK-093-model-health-fact-layer.md` | completed | SPEC-015 | TASK-092 |
| TASK-094 | `tasks/TASK-094-model-applicability-profiles.md` | completed | SPEC-015 | TASK-093 |
| TASK-095 | `tasks/TASK-095-20d-shadow-router.md` | completed | SPEC-015 | TASK-094 |
| TASK-096 | `tasks/TASK-096-confidence-calibration-labels.md` | completed | SPEC-015 | TASK-094 |
| TASK-097 | `tasks/TASK-097-monthly-model-governance-summary.md` | completed | SPEC-015 | TASK-095, TASK-096 |

## Decisions

| ID | File | Status | Scope |
| --- | --- | --- | --- |
| ADR-001 | `decisions/ADR-001-mvp-local-first-akshare-sqlite.md` | accepted | MVP architecture |
| ADR-002 | `decisions/ADR-002-official-mcp-python-sdk.md` | accepted | MCP transport |
| ADR-003 | `decisions/ADR-003-expert-committee-virtual-investing.md` | accepted | Expert committee persistence and lifecycle |
| ADR-004 | `decisions/ADR-004-local-phone-communication-adapters.md` | accepted | Local phone communication adapters and iMessage first |
| ADR-005 | `decisions/ADR-005-jarvis-top-level-assistant.md` | accepted | Jarvis as the top-level investment assistant |
| ADR-006 | `decisions/ADR-006-safe-inbound-phone-commands.md` | accepted | Safe non-trading inbound phone command boundaries |
| ADR-007 | `decisions/ADR-007-jarvis-consumer-information-architecture.md` | accepted | Jarvis five-entry consumer information architecture |
| ADR-008 | `decisions/ADR-008-system-scheduled-codex-agent-runtime.md` | accepted | System-owned scheduling and Codex role agent runtime |
| ADR-009 | `decisions/ADR-009-system-owned-incremental-scheduler.md` | accepted | System-owned hourly incremental scheduler and provider safety |
| ADR-010 | `decisions/ADR-010-model-applicability-shadow-routing.md` | accepted | Context-specific model applicability and shadow routing |

## Architecture And Code Index

| File | Purpose |
| --- | --- |
| `ARCHITECTURE.md` | System boundaries, module ownership, architecture diagram, and architecture maintenance rules |
| `CODE_INDEX.md` | Runtime entry points, module/file map, WebUI routes, database areas, tests, and task surfaces |

## Learnings

| ID | File | Topic | Trigger |
| --- | --- | --- | --- |

## Skills

| ID | File | Applies To |
| --- | --- | --- |
| investment-progress-planning | `skills/investment-progress-planning/SKILL.md` | Inspect current code/WebUI progress, update roadmap/goals/design/specs/tasks |
| investment-evaluation-audit | `skills/investment-evaluation-audit/SKILL.md` | Inspect WebUI/database evidence, evaluate prediction quality, regressions, scoring, and design defects |
| tushare-usage-manual | `skills/tushare-usage-manual/SKILL.md` | Find official Tushare usage docs, interface docs, permissions, SDK/HTTP examples, and fallback lookup paths |
