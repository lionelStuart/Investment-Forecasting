# Layered Tushare Lookup Manual

This reference explains how to obtain reliable Tushare usage instructions
without guessing.

## Layer 1: Official Usage Documentation

Start from `https://tushare.pro/document/1`.

Use these official pages first:

| Need | Doc | URL |
| --- | --- | --- |
| Register and get token | 获取token | `https://tushare.pro/document/1?doc_id=39` |
| General data call pattern | 调取数据 | `https://tushare.pro/document/1?doc_id=40` |
| HTTP JSON API | 通过HTTP获取数据 | `https://tushare.pro/document/1?doc_id=130` |
| Python SDK | 通过Python SDK获取 | `https://tushare.pro/document/1?doc_id=131` |
| Efficient fetching | 如何优雅撸数据 | `https://tushare.pro/document/1?doc_id=230` |
| Minute data caveats | 如何获取分钟数据 | `https://tushare.pro/document/1?doc_id=234` |
| Common failures | 常见问题整理 | `https://tushare.pro/document/1?doc_id=122` |
| Data update timing | 数据更新说明 | `https://tushare.pro/document/1?doc_id=108` |
| Points/frequency | 积分频次对应表 | `https://tushare.pro/document/1?doc_id=290` |
| Tushare MCP | Tushare MCP | `https://tushare.pro/document/1?doc_id=463` |

Use Layer 1 to answer:

- How to install `tushare`.
- How to set or pass `token`.
- Whether to use Python SDK or HTTP API.
- What frequency/points/permission constraints apply.
- How to fetch efficiently without excessive calls.
- How to interpret permission errors and empty results.

### Canonical Python SDK Pattern

```python
import os
import tushare as ts

token = os.environ["TUSHARE_TOKEN"]
pro = ts.pro_api(token)

df = pro.trade_cal(
    exchange="",
    start_date="20260101",
    end_date="20260131",
    fields="exchange,cal_date,is_open,pretrade_date",
)
```

Avoid hard-coding tokens. `ts.set_token(...)` is acceptable for local setup, but
project code should prefer environment variables or explicit CLI args.

### Canonical HTTP Pattern

```json
{
  "api_name": "trade_cal",
  "token": "YOUR_TOKEN",
  "params": {
    "exchange": "",
    "start_date": "20260101",
    "end_date": "20260131"
  },
  "fields": "exchange,cal_date,is_open,pretrade_date"
}
```

POST the JSON body to `http://api.tushare.pro`.

### Efficient Fetching Rule

For broad market daily data, prefer trade-date batches when the interface
supports them. Avoid looping every asset over long history unless the interface
requires per-symbol calls or the scope is intentionally small. Use incremental
date windows, rate limits, retry with backoff, jitter, and task-log diagnostics.

## Layer 2: Interface Documentation Index

Use `https://tushare.pro/document/2` and
`references/interface-index.md`.

For a specific data need:

1. Map the need to a category: stock, ETF, index, fund, futures, bonds, macro,
   news/language corpus, capital flow, theme/industry, financial statement.
2. Open the matching `doc_id` page.
3. Extract from the page:
   - API name;
   - required and optional input parameters;
   - output fields;
   - row limit;
   - points/permission requirements;
   - update frequency;
   - example code.
4. Build a minimal SDK call with explicit `fields`.
5. Add pagination/date-window/chunking if the interface has a row limit.

If the interface page says a permission is required, do not assume the token has
it. Add graceful failure behavior and diagnostics.

## Layer 3: Browser Fallback

Use this only when Layer 1 and Layer 2 do not answer the question or the docs
appear stale.

Browser fallback procedure:

1. Open the most likely page:
   - `https://tushare.pro/document/1`
   - `https://tushare.pro/document/2`
   - `https://tushare.pro/document/2?doc_id=DOC_ID`
2. Search page text for:
   - `接口：`, `接口名称`, `API`, `输入参数`, `输出参数`, `接口示例`,
     `数据说明`, `积分`, `权限`, `单次最大`, `调取说明`.
3. If the doc page is hard to parse, search the web with:
   - `site:tushare.pro/document/2 Tushare <data need>`
   - `site:tushare.pro/document/2 <Chinese interface name>`
   - `site:tushare.pro/document/2 <suspected api_name>`
4. Record the exact URL and date accessed in the answer or project docs.

If browsing or downloads fail, retry once with the local proxy variables from
`repo/AGENTS.md`.

## Project Implementation Pattern

For this repo:

- Add or modify behavior behind `TushareProvider`, not scattered direct calls.
- Normalize output into existing provider-neutral tables.
- Keep `source='tushare'`.
- Log provider selection, row counts, empty results, permission failures, and
  throttling/rate-limit signals.
- Add tests with fake Tushare modules rather than requiring live credentials.
- Keep Tushare optional in default workflows.

Existing project surfaces:

- Provider: `src/investment_forecasting/providers/tushare_provider.py`
- CLI selection: `investment-forecasting ingest ... --provider tushare`
- Token inputs: `--tushare-token`, `TUSHARE_TOKEN`, `TS_TOKEN`
- Tests: `tests/test_tushare_provider.py`,
  `tests/test_news_evidence.py`

## Error Handling Checklist

Handle separately:

- Missing token.
- Missing optional package `tushare`.
- Permission/points failures.
- Rate limits or throttling.
- Empty responses.
- Schema/field changes.
- Date format errors.
- Partial batch failure.

Do not silently treat permission failures as valid empty data.
