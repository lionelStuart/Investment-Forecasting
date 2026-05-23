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

## Decisions

| ID | File | Status | Scope |
| --- | --- | --- | --- |
| ADR-001 | `decisions/ADR-001-mvp-local-first-akshare-sqlite.md` | accepted | MVP architecture |
| ADR-002 | `decisions/ADR-002-official-mcp-python-sdk.md` | accepted | MCP transport |

## Learnings

| ID | File | Topic | Trigger |
| --- | --- | --- | --- |

## Skills

| ID | File | Applies To |
| --- | --- | --- |
