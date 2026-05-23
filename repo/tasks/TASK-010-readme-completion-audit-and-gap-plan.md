# TASK-010: README Completion Audit And Gap Plan

## Status

completed

## Source

`README.md`

## Goal

Audit the current implementation against the README MVP goals, identify
unproven or incomplete requirements, and create follow-up tasks for the
remaining gaps.

## Required Context

- `README.md`
- `repo/PROJECT.md`
- `repo/STATUS.md`
- `repo/INDEX.md`
- Completed `TASK-001` through `TASK-009`

## Modify Scope

- Project memory files.
- New task files for concrete remaining gaps.
- Documentation of current evidence and missing evidence.

## Forbidden

- Do not mark the overall goal complete from broad summaries alone.
- Do not treat tests as evidence for README requirements they do not cover.
- Do not hide deferred work such as MCP transport, broader data coverage, or
  richer historical samples.

## Acceptance

- README requirements are mapped to current evidence, incomplete work, or
  missing verification.
- Follow-up tasks exist for every material README gap.
- `STATUS.md` and `INDEX.md` reflect the next concrete task.
- The audit distinguishes MVP-complete evidence from future enhancement work.

## Test Plan

- Inspect current files, commands, and test outputs.
- Run the project test suite.
- Verify new task links exist in `INDEX.md`.

## Progress

- [x] Planned
- [x] Implemented
- [x] Validated
- [x] Written back

## Result

Completed on 2026-05-23.

- Added `repo/audits/README-MVP-COMPLETION-2026-05-23.md`.
- Mapped README requirements to current evidence, partial coverage, and missing
  implementation/verification.
- Confirmed the current implementation is a working vertical MVP slice, but not
  enough to mark the full README goal complete.
- Added follow-up tasks:
  - `TASK-011`: MCP stdio transport.
  - `TASK-012`: Broader AKShare universe.
  - `TASK-013`: Fund info ingestion.
  - `TASK-014`: Market environment data.
  - `TASK-015`: Data quality, retry, and cache.
  - `TASK-016`: Benchmark and advice outcome scoring.
  - `TASK-017`: Historical calibration corpus.
- Validation passed with `python3 -m pytest`.

## Follow-Ups

- Expected follow-up tasks may include MCP transport hardening, broader data
  universe ingestion, richer macro/sentiment data, and calibration with larger
  historical windows.
