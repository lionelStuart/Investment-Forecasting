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
| TASK-022 | `tasks/TASK-022-simulated-portfolio-tracking.md` | pending | ROADMAP | TASK-021 |
| TASK-023 | `tasks/TASK-023-target-volatility-allocation.md` | pending | ROADMAP | TASK-021, TASK-022 |
| TASK-024 | `tasks/TASK-024-model-monitoring-drift.md` | pending | ROADMAP | TASK-016, TASK-017 |
| TASK-025 | `tasks/TASK-025-provider-expansion-tushare.md` | pending | ROADMAP | TASK-015 |
| TASK-026 | `tasks/TASK-026-fund-peer-benchmark-scoring.md` | pending | ROADMAP | TASK-016 |
| TASK-027 | `tasks/TASK-027-data-expansion-and-channel-hardening.md` | completed | SPEC-001 | TASK-015, TASK-020 |
| TASK-027 | `tasks/TASK-027-provider-access-polite-ingestion.md` | pending | SPEC-001, SPEC-005 | TASK-015, TASK-025 |
| TASK-028 | `tasks/TASK-028-product-timeline-run-history.md` | completed | SPEC-006 | TASK-019, TASK-020, TASK-021 |
| TASK-029 | `tasks/TASK-029-product-category-navigation.md` | completed | SPEC-006 | TASK-027, TASK-028 |
| TASK-030 | `tasks/TASK-030-fund-screening-filters-presets.md` | completed | SPEC-006 | TASK-013, TASK-021, TASK-029 |
| TASK-031 | `tasks/TASK-031-red-green-market-semantics.md` | pending | SPEC-006 | TASK-008 |
| TASK-032 | `tasks/TASK-032-asset-level-prediction-cards.md` | pending | SPEC-006 | TASK-004, TASK-027, TASK-031 |
| TASK-033 | `tasks/TASK-033-dashboard-brief-run-health.md` | pending | SPEC-006, SPEC-005 | TASK-020, TASK-021, TASK-028, TASK-031 |
| TASK-034 | `tasks/TASK-034-full-asset-scale-ingestion.md` | completed | SPEC-001, SPEC-002 | TASK-027 |
| TASK-035 | `tasks/TASK-035-progressive-disclosure-technical-tables.md` | pending | SPEC-006 | TASK-029, TASK-030, TASK-032, TASK-033 |
| TASK-036 | `tasks/TASK-036-expert-architecture-roster-model.md` | completed | SPEC-007 | TASK-021, TASK-030 |
| TASK-037 | `tasks/TASK-037-expert-virtual-portfolio-foundation.md` | completed | SPEC-007, ROADMAP | TASK-022, TASK-036 |
| TASK-038 | `tasks/TASK-038-expert-daily-planning-execution.md` | completed | SPEC-007 | TASK-032, TASK-033, TASK-036, TASK-037 |
| TASK-039 | `tasks/TASK-039-expert-scoring-retirement-hiring.md` | completed | SPEC-007 | TASK-024, TASK-037, TASK-038 |
| TASK-040 | `tasks/TASK-040-expert-committee-webui.md` | completed | SPEC-007, SPEC-006 | TASK-035, TASK-036, TASK-037, TASK-038, TASK-039 |
| TASK-041 | `tasks/TASK-041-expert-agent-workflow-mcp.md` | completed | SPEC-007, SPEC-004, SPEC-005 | TASK-036, TASK-038, TASK-039 |
| TASK-042 | `tasks/TASK-042-communication-adapter-architecture.md` | pending | SPEC-008 | TASK-007, TASK-020 |
| TASK-043 | `tasks/TASK-043-imessage-outbound-adapter.md` | pending | SPEC-008 | TASK-042 |
| TASK-044 | `tasks/TASK-044-mobile-notification-templates.md` | pending | SPEC-008 | TASK-033, TASK-038, TASK-042, TASK-043 |
| TASK-045 | `tasks/TASK-045-communication-webui-cli.md` | pending | SPEC-008, SPEC-006 | TASK-035, TASK-042, TASK-043 |
| TASK-046 | `tasks/TASK-046-safe-inbound-phone-command-design.md` | pending | SPEC-008 | TASK-043 |

## Decisions

| ID | File | Status | Scope |
| --- | --- | --- | --- |
| ADR-001 | `decisions/ADR-001-mvp-local-first-akshare-sqlite.md` | accepted | MVP architecture |
| ADR-002 | `decisions/ADR-002-official-mcp-python-sdk.md` | accepted | MCP transport |
| ADR-003 | `decisions/ADR-003-expert-committee-virtual-investing.md` | accepted | Expert committee persistence and lifecycle |
| ADR-004 | `decisions/ADR-004-local-phone-communication-adapters.md` | accepted | Local phone communication adapters and iMessage first |

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
