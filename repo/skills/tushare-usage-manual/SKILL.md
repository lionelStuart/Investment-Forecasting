---
name: tushare-usage-manual
description: Use in the Investment Forecasting project when an agent needs to learn how to correctly use Tushare Pro, choose Tushare data interfaces, inspect official Tushare SDK/HTTP/API documentation, query market/news/macro/fund/stock data, or design/modify Tushare provider ingestion. Implements a three-layer fallback: official usage docs, interface-document index, then browser-based lookup.
---

# Tushare Usage Manual

Use this skill inside `/Users/wonderwall/project/Investment-Forecasting` when a
task needs Tushare data or Tushare usage instructions.

## Goal

Help the agent obtain the correct Tushare usage method through a layered
funnel:

1. Official usage docs: installation, token, SDK, HTTP API, permissions,
   update rules, and efficient fetching patterns.
2. Interface docs: find the specific API page, parameters, fields, limits,
   update frequency, and permission requirements.
3. Browser fallback: if the index is incomplete or stale, open/search Tushare
   docs directly and extract the current usage pattern from the page.

## Required References

Read references only as needed:

- `references/layered-manual.md`: the three-layer lookup workflow and project
  integration rules.
- `references/interface-index.md`: curated Tushare document index for common
  Investment Forecasting data needs.

## Project Integration Rules

- Prefer the existing provider boundary in
  `src/investment_forecasting/providers/tushare_provider.py` before writing new
  direct SDK calls.
- Keep AKShare as the default free provider; Tushare must stay explicit and
  optional through `--provider tushare`, `--tushare-token`, `TUSHARE_TOKEN`, or
  `TS_TOKEN`.
- Never commit tokens. Read them from CLI args or environment variables.
- Preserve provider-neutral persistence: normalize rows into existing tables
  and record `source='tushare'`.
- Treat Tushare permissions, points, per-interface limits, and frequency caps
  as runtime constraints. Fail gracefully with clear diagnostics.
- For news or language-corpus data, keep it as retrievable evidence; do not
  turn raw news into direct buy/sell advice.

## When Answering A Tushare Question

Return:

1. The selected Tushare interface or official doc page.
2. Why it matches the user need.
3. Required token/permission/points constraints.
4. Parameters and fields to request.
5. Python SDK and, if useful, HTTP JSON examples.
6. Project-specific integration advice: provider method, schema target, logs,
   tests, and graceful failure behavior.
7. Any uncertainty and the browser/doc page used to resolve it.

If the official docs cannot be loaded directly, retry once with:

```bash
export https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890 all_proxy=socks5://127.0.0.1:7890
```

Then use browser search/open as the final fallback.
