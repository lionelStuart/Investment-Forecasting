# Tushare Interface Index

Source: `https://tushare.pro/document/2`, checked 2026-05-24.

Use this as a curated starting index. If a data need is not listed here, open
the root interface catalog and search the page directly.

## Current Project Priority Interfaces

| Need | Interface doc | Typical API | Notes |
| --- | --- | --- | --- |
| Trading calendar | `doc_id=26` 各交易所交易日历 | `trade_cal` | Use for open days and efficient date batching. |
| Stock list | `doc_id=25` 股票列表 | `stock_basic` | Basic A-share universe. |
| Stock daily bars | `doc_id=27` 历史日线 | `daily` or `pro_bar` | Use explicit fields; `pro_bar` can handle adjustment. |
| ETF daily bars | `doc_id=127` ETF日线行情 | interface page specific | Use for ETF prices; confirm params/fields. |
| ETF basic info | `doc_id=385` ETF基本信息 | interface page specific | Use for ETF metadata. |
| Index basic info | `doc_id=94` 指数基本信息 | `index_basic` | Index universe and metadata. |
| Index daily bars | `doc_id=95` 指数日线行情 | `index_daily` | Existing provider uses this for index history. |
| Index historical minutes | `doc_id=419` 指数历史分钟 | `idx_mins` | Permission-gated minute data; single-call row limits apply. |
| Fund list | `doc_id=19` 基金列表 | `fund_basic` | Existing provider uses this for fund/ETF discovery. |
| Fund NAV | `doc_id=119` 基金净值 | `fund_nav` | Existing provider uses this for public fund history. |
| Fund holdings | `doc_id=121` 基金持仓 | `fund_portfolio` or page-specific | Confirm API name on page before use. |
| Stock money flow | `doc_id=170` 个股资金流向 | `moneyflow` | Existing provider uses this and THS fallback. |
| THS stock money flow | `doc_id=348` 个股资金流向（THS） | `moneyflow_ths` | Existing fallback for individual stock flows. |
| DC market flow | `doc_id=345` 大盘资金流向（DC） | `moneyflow_mkt_dc` | Existing market flow path. |
| HSGT flow | `doc_id=47` 沪深港通资金流向 | `moneyflow_hsgt` | Existing market-flow fallback. |
| News flash | `doc_id=143` 新闻快讯（短讯） | `news` | Permission-gated; evidence retrieval only. |
| Long news | `doc_id=195` 新闻通讯（长篇） | page-specific | Use for richer text evidence when permission exists. |
| Listed-company announcement | `doc_id=176` 上市公司公告 | page-specific | Use for company evidence; not default prompt stuffing. |
| Policy corpus | `doc_id=406` 国家政策库 | page-specific | Macro/policy evidence. |
| Brokerage research reports | `doc_id=415` 券商研究报告 | page-specific | Permission-gated research corpus. |
| GDP | `doc_id=227` 国内生产总值（GDP） | page-specific | Macro feature candidates. |
| CPI | `doc_id=228` 居民消费价格指数（CPI） | page-specific | Macro feature candidates. |
| PPI | `doc_id=245` 工业生产者出厂价格指数（PPI） | page-specific | Macro feature candidates. |
| PMI | `doc_id=325` 采购经理指数（PMI） | page-specific | Macro feature candidates. |
| Shibor | `doc_id=149` Shibor利率 | page-specific | Liquidity/rate context. |
| LPR | `doc_id=151` LPR贷款基础利率 | page-specific | Domestic rate context. |
| US treasury curve | `doc_id=219` 国债收益率曲线利率 | page-specific | International macro/rate context. |

`page-specific` means do not guess the API name from this index. Open the
interface page and copy the current API name, params, fields, limits, and
permissions from the official page.

## Category Map

### Stocks

| Category | Doc |
| --- | --- |
| 股票数据 | `https://tushare.pro/document/2?doc_id=14` |
| 基础数据 | `https://tushare.pro/document/2?doc_id=24` |
| 股票列表 | `https://tushare.pro/document/2?doc_id=25` |
| 交易日历 | `https://tushare.pro/document/2?doc_id=26` |
| 行情数据 | `https://tushare.pro/document/2?doc_id=15` |
| 历史日线 | `https://tushare.pro/document/2?doc_id=27` |
| 历史分钟 | `https://tushare.pro/document/2?doc_id=370` |
| 复权行情 | `https://tushare.pro/document/2?doc_id=146` |
| 每日指标 | `https://tushare.pro/document/2?doc_id=32` |
| 财务数据 | `https://tushare.pro/document/2?doc_id=16` |
| 利润表 | `https://tushare.pro/document/2?doc_id=33` |
| 资产负债表 | `https://tushare.pro/document/2?doc_id=36` |
| 现金流量表 | `https://tushare.pro/document/2?doc_id=44` |
| 财务指标数据 | `https://tushare.pro/document/2?doc_id=79` |
| 参考数据 | `https://tushare.pro/document/2?doc_id=17` |
| 特色数据 | `https://tushare.pro/document/2?doc_id=291` |
| 两融及转融通 | `https://tushare.pro/document/2?doc_id=330` |
| 资金流向数据 | `https://tushare.pro/document/2?doc_id=342` |
| 打板专题数据 | `https://tushare.pro/document/2?doc_id=346` |

### ETF, Index, Fund

| Category | Doc |
| --- | --- |
| ETF专题 | `https://tushare.pro/document/2?doc_id=384` |
| ETF基本信息 | `https://tushare.pro/document/2?doc_id=385` |
| ETF跟踪指数 | `https://tushare.pro/document/2?doc_id=386` |
| ETF历史分钟 | `https://tushare.pro/document/2?doc_id=387` |
| ETF日线行情 | `https://tushare.pro/document/2?doc_id=127` |
| ETF份额规模 | `https://tushare.pro/document/2?doc_id=408` |
| 指数专题 | `https://tushare.pro/document/2?doc_id=93` |
| 指数基本信息 | `https://tushare.pro/document/2?doc_id=94` |
| 指数日线行情 | `https://tushare.pro/document/2?doc_id=95` |
| 指数历史分钟 | `https://tushare.pro/document/2?doc_id=419` |
| 指数成分和权重 | `https://tushare.pro/document/2?doc_id=96` |
| 申万行业分类 | `https://tushare.pro/document/2?doc_id=181` |
| 申万行业指数日行情 | `https://tushare.pro/document/2?doc_id=327` |
| 公募基金 | `https://tushare.pro/document/2?doc_id=18` |
| 基金列表 | `https://tushare.pro/document/2?doc_id=19` |
| 基金规模 | `https://tushare.pro/document/2?doc_id=207` |
| 基金净值 | `https://tushare.pro/document/2?doc_id=119` |
| 基金分红 | `https://tushare.pro/document/2?doc_id=120` |
| 基金持仓 | `https://tushare.pro/document/2?doc_id=121` |

### Futures, Options, Bonds, FX, HK, US

| Category | Doc |
| --- | --- |
| 期货数据 | `https://tushare.pro/document/2?doc_id=134` |
| 期货交易日历 | `https://tushare.pro/document/2?doc_id=467` |
| 期货日线行情 | `https://tushare.pro/document/2?doc_id=138` |
| 期货历史分钟行情 | `https://tushare.pro/document/2?doc_id=313` |
| 期权数据 | `https://tushare.pro/document/2?doc_id=157` |
| 期权日线行情 | `https://tushare.pro/document/2?doc_id=159` |
| 债券专题 | `https://tushare.pro/document/2?doc_id=184` |
| 可转债基础信息 | `https://tushare.pro/document/2?doc_id=185` |
| 可转债行情 | `https://tushare.pro/document/2?doc_id=187` |
| 国债收益率曲线 | `https://tushare.pro/document/2?doc_id=201` |
| 外汇数据 | `https://tushare.pro/document/2?doc_id=177` |
| 外汇日线行情 | `https://tushare.pro/document/2?doc_id=179` |
| 港股数据 | `https://tushare.pro/document/2?doc_id=190` |
| 港股日线行情 | `https://tushare.pro/document/2?doc_id=192` |
| 美股数据 | `https://tushare.pro/document/2?doc_id=251` |
| 美股日线行情 | `https://tushare.pro/document/2?doc_id=254` |

### Macro, News, Wealth Management

| Category | Doc |
| --- | --- |
| 宏观经济 | `https://tushare.pro/document/2?doc_id=147` |
| 国内宏观 | `https://tushare.pro/document/2?doc_id=224` |
| 中国经济数据发布日程 | `https://tushare.pro/document/2?doc_id=461` |
| 利率数据 | `https://tushare.pro/document/2?doc_id=148` |
| 国民经济 | `https://tushare.pro/document/2?doc_id=225` |
| 价格指数 | `https://tushare.pro/document/2?doc_id=226` |
| 金融 | `https://tushare.pro/document/2?doc_id=240` |
| 社会融资 | `https://tushare.pro/document/2?doc_id=309` |
| 景气度 | `https://tushare.pro/document/2?doc_id=324` |
| 国际宏观 | `https://tushare.pro/document/2?doc_id=217` |
| 大模型语料专题数据 | `https://tushare.pro/document/2?doc_id=142` |
| 国家政策库 | `https://tushare.pro/document/2?doc_id=406` |
| 券商研究报告 | `https://tushare.pro/document/2?doc_id=415` |
| 新闻快讯（短讯） | `https://tushare.pro/document/2?doc_id=143` |
| 新闻通讯（长篇） | `https://tushare.pro/document/2?doc_id=195` |
| 上市公司公告 | `https://tushare.pro/document/2?doc_id=176` |
| 财富管理 | `https://tushare.pro/document/2?doc_id=263` |
| 基金销售行业数据 | `https://tushare.pro/document/2?doc_id=264` |

## Fallback Search Patterns

Use these when the curated index is not enough:

```text
site:tushare.pro/document/2 Tushare 股票 日线
site:tushare.pro/document/2 Tushare fund_nav
site:tushare.pro/document/2 Tushare 新闻快讯
site:tushare.pro/document/2 Tushare moneyflow
site:tushare.pro/document/2 Tushare <api_name>
site:tushare.pro/document/2 <中文接口名>
```

Then open the exact `doc_id` page and extract the current API signature.
