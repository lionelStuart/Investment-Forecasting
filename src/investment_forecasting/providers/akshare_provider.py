from __future__ import annotations

import json
import os
import random
import subprocess
import time
from collections.abc import Iterator
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode


class ProviderDataError(RuntimeError):
    """Raised when provider data cannot be normalized safely."""


@dataclass(frozen=True)
class RetryConfig:
    attempts: int = 2
    fallback_to_direct: bool = True
    fallback_to_local_proxy: bool = True
    backoff_base_seconds: float = 0.5
    max_backoff_seconds: float = 5.0


@dataclass(frozen=True)
class ProviderAccessPolicy:
    min_delay_seconds: float = 0.25
    jitter_seconds: float = 0.25


@dataclass
class ProviderRequestStats:
    request_count: int = 0
    retry_count: int = 0
    labels: list[str] | None = None
    network_profiles: list[str] | None = None
    throttling_warnings: list[str] | None = None

    def __post_init__(self) -> None:
        self.labels = [] if self.labels is None else self.labels
        self.network_profiles = [] if self.network_profiles is None else self.network_profiles
        self.throttling_warnings = [] if self.throttling_warnings is None else self.throttling_warnings

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_count": self.request_count,
            "retry_count": self.retry_count,
            "labels": list(self.labels or []),
            "network_profiles": list(self.network_profiles or []),
            "throttling_warnings": list(self.throttling_warnings or []),
        }


class AkshareProvider:
    source = "akshare"

    def __init__(
        self,
        ak_module: Any | None = None,
        retry_config: RetryConfig | None = None,
        access_policy: ProviderAccessPolicy | None = None,
        sleep_func: Any | None = None,
        monotonic_func: Any | None = None,
        random_func: Any | None = None,
        curl_runner: Any | None = None,
    ) -> None:
        live_module = ak_module is None
        if ak_module is None:
            try:
                import akshare as ak_module
            except ImportError as exc:
                raise RuntimeError("AKShare is required for live ingestion. Install project dependencies.") from exc
        self.ak = ak_module
        self.retry_config = retry_config or RetryConfig()
        self.access_policy = access_policy or (ProviderAccessPolicy() if live_module else ProviderAccessPolicy(min_delay_seconds=0.0, jitter_seconds=0.0))
        self._sleep = sleep_func or time.sleep
        self._monotonic = monotonic_func or time.monotonic
        self._random = random_func or random.random
        self._curl_runner = curl_runner or _run_curl_json
        self._last_request_at: float | None = None
        self.stats = ProviderRequestStats()

    def diagnostics(self) -> dict[str, Any]:
        return {
            **self.stats.as_dict(),
            "min_delay_seconds": self.access_policy.min_delay_seconds,
            "jitter_seconds": self.access_policy.jitter_seconds,
            "attempts": self.retry_config.attempts,
            "backoff_base_seconds": self.retry_config.backoff_base_seconds,
            "max_backoff_seconds": self.retry_config.max_backoff_seconds,
        }

    def history(self, asset: Any, start_date: str, end_date: str) -> list[dict[str, Any]]:
        try:
            if asset.asset_type == "index":
                raw = self._with_retry(
                    f"index:{asset.code}",
                    lambda: self.ak.stock_zh_index_daily_tx(
                        symbol=asset.provider_symbol or asset.code,
                        start_date=start_date,
                        end_date=end_date,
                    ),
                )
            elif asset.asset_type == "stock":
                raw = self._stock_history(asset, start_date=start_date, end_date=end_date)
            elif asset.asset_type == "etf":
                raw = self._etf_history(asset, start_date=start_date, end_date=end_date)
            elif asset.asset_type == "fund":
                raw = self._with_retry(
                    f"fund:{asset.code}:history",
                    lambda: self.ak.fund_open_fund_info_em(symbol=asset.code, indicator="单位净值走势"),
                )
            else:
                raise ProviderDataError(f"Unsupported AKShare asset type: {asset.asset_type}")
        except ProviderDataError:
            raise
        except Exception as exc:
            raise ProviderDataError(
                f"AKShare fetch failed for {asset.asset_type}:{asset.code} after "
                f"{self.retry_config.attempts} attempt(s): {exc}. "
                "If network access is blocked, retry with the local proxy from AGENTS.md."
            ) from exc

        records = normalize_price_rows(raw, asset_type=asset.asset_type)
        records = [
            record
            for record in records
            if _date_text(start_date) <= record["trade_date"] <= _date_text(end_date)
        ]
        if not records:
            raise ProviderDataError(f"AKShare returned no history for {asset.asset_type}:{asset.code}")
        return records

    def asset_universe(self, asset_types: tuple[str, ...] = ("stock", "etf", "fund")) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        if "stock" in asset_types:
            assets.extend(self._stock_universe())
        if "etf" in asset_types:
            assets.extend(self._etf_universe())
        if "fund" in asset_types:
            assets.extend(self._fund_universe())
        return assets

    def news(self, *, source: str, start_datetime: str, end_datetime: str) -> list[dict[str, Any]]:
        if source == "eastmoney_global":
            raw = self._with_retry("news:eastmoney_global", lambda: self.ak.stock_info_global_em())
            rows = [
                {
                    "id": str(_value(row, "链接", "url") or _value(row, "标题") or ""),
                    "title": str(_value(row, "标题") or ""),
                    "content": str(_value(row, "摘要", "内容") or _value(row, "标题") or ""),
                    "published_at": str(_value(row, "发布时间", "时间") or ""),
                    "url": str(_value(row, "链接", "url") or ""),
                }
                for row in _records(raw)
            ]
        elif source == "sina_global":
            raw = self._with_retry("news:sina_global", lambda: self.ak.stock_info_global_sina())
            rows = [
                {
                    "id": str(_value(row, "时间") or "") + ":" + str(_value(row, "内容") or "")[:40],
                    "title": str(_value(row, "内容") or "")[:80],
                    "content": str(_value(row, "内容") or ""),
                    "published_at": str(_value(row, "时间") or ""),
                    "url": "",
                }
                for row in _records(raw)
            ]
        else:
            raise ProviderDataError(f"Unsupported AKShare news source: {source}")
        return [row for row in rows if _within_news_window(row.get("published_at"), start_datetime, end_datetime)]

    def _stock_universe(self) -> list[dict[str, Any]]:
        try:
            raw = self._with_retry("stock:universe:spot_em", lambda: self.ak.stock_zh_a_spot_em())
        except ProviderDataError:
            raw = self._with_retry("stock:universe:code_name", lambda: self.ak.stock_info_a_code_name())
        assets = []
        for row in _records(raw):
            raw_code = _value(row, "代码", "code")
            if raw_code is None:
                continue
            code = str(raw_code).zfill(6)
            name = str(_value(row, "名称", "name") or code)
            assets.append(
                {
                    "code": code,
                    "name": name,
                    "asset_type": "stock",
                    "market": "CN",
                    "provider_symbol": _provider_symbol(code),
                }
            )
        return assets

    def _etf_universe(self) -> list[dict[str, Any]]:
        raw = self._with_retry("etf:universe", lambda: self.ak.fund_etf_spot_em())
        assets = []
        for row in _records(raw):
            raw_code = _value(row, "代码", "基金代码", "code")
            if raw_code is None:
                continue
            code = str(raw_code).zfill(6)
            name = str(_value(row, "名称", "基金简称", "name") or code)
            assets.append(
                {
                    "code": code,
                    "name": name,
                    "asset_type": "etf",
                    "market": "CN",
                    "provider_symbol": _provider_symbol(code),
                }
            )
        return assets

    def _fund_universe(self) -> list[dict[str, Any]]:
        raw = self._with_retry("fund:universe", lambda: self.ak.fund_open_fund_rank_em(symbol="全部"))
        assets = []
        for row in _records(raw):
            raw_code = _value(row, "基金代码", "代码", "code")
            if raw_code is None:
                continue
            code = str(raw_code).zfill(6)
            name = str(_value(row, "基金简称", "名称", "name") or code)
            assets.append({"code": code, "name": name, "asset_type": "fund", "market": "CN", "provider_symbol": None})
        return assets

    def _etf_history(self, asset: Any, start_date: str, end_date: str) -> Any:
        try:
            return self._with_retry(
                f"etf:{asset.code}:eastmoney",
                lambda: self.ak.fund_etf_hist_em(
                    symbol=asset.code,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq",
                ),
            )
        except Exception:
            if not getattr(asset, "provider_symbol", None):
                raise
            return self._with_retry(
                f"etf:{asset.code}:sina",
                lambda: self.ak.fund_etf_hist_sina(symbol=asset.provider_symbol),
            )

    def _stock_history(self, asset: Any, start_date: str, end_date: str) -> Any:
        try:
            return self._with_retry(
                f"stock:{asset.code}:eastmoney",
                lambda: self.ak.stock_zh_a_hist(
                    symbol=asset.code,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq",
                ),
            )
        except Exception:
            if not getattr(asset, "provider_symbol", None):
                raise
            return self._with_retry(
                f"stock:{asset.code}:daily",
                lambda: self.ak.stock_zh_a_daily(
                    symbol=asset.provider_symbol,
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq",
                ),
            )

    def fund_info(self, asset: Any) -> dict[str, Any]:
        if asset.asset_type != "fund":
            raise ProviderDataError(f"fund_info only supports funds, got {asset.asset_type}")
        try:
            basic = self._with_retry(
                f"fund:{asset.code}:basic",
                lambda: self.ak.fund_individual_basic_info_xq(symbol=asset.code),
            )
            rank = self._with_retry("fund:rank", lambda: self.ak.fund_open_fund_rank_em(symbol="全部"))
        except Exception as exc:
            raise ProviderDataError(f"AKShare fund info fetch failed for fund:{asset.code}: {exc}") from exc
        return normalize_fund_info(basic, rank, code=asset.code)

    def fund_stock_holdings(self, code: str, year: str) -> list[dict[str, Any]]:
        normalized_code = str(code).zfill(6)
        try:
            raw = self._with_retry(
                f"fund:{normalized_code}:stock_holdings:{year}",
                lambda: self.ak.fund_portfolio_hold_em(symbol=normalized_code, date=str(year)),
            )
        except Exception as exc:
            raise ProviderDataError(f"AKShare fund holdings fetch failed for fund:{normalized_code}: {exc}") from exc
        return normalize_fund_stock_holding_rows(raw, fund_code=normalized_code)

    def stock_capital_flow(self, code: str) -> list[dict[str, Any]]:
        normalized_code = str(code).zfill(6)
        market = _fund_flow_market(normalized_code)
        try:
            raw = self._with_retry(
                f"stock:{normalized_code}:capital_flow",
                lambda: self.ak.stock_individual_fund_flow(stock=normalized_code, market=market),
            )
        except Exception as exc:
            try:
                raw = self._eastmoney_capital_flow(
                    label=f"stock:{normalized_code}:capital_flow:curl",
                    secid=f"{_eastmoney_market_id(market)}.{normalized_code}",
                    market_scope="stock",
                )
            except Exception as fallback_exc:
                raise ProviderDataError(
                    f"AKShare capital flow fetch failed for stock:{normalized_code}: {exc}; "
                    f"curl fallback failed: {fallback_exc}"
                ) from fallback_exc
        return normalize_capital_flow_rows(raw, scope="stock", subject_code=normalized_code, subject_name=normalized_code)

    def market_capital_flow(self) -> list[dict[str, Any]]:
        try:
            raw = self._with_retry("market:capital_flow", lambda: self.ak.stock_market_fund_flow())
        except Exception as exc:
            try:
                raw = self._eastmoney_capital_flow(
                    label="market:capital_flow:curl",
                    secid="1.000001",
                    secid2="0.399001",
                    market_scope="market",
                )
            except Exception as fallback_exc:
                raise ProviderDataError(
                    f"AKShare market capital flow fetch failed: {exc}; curl fallback failed: {fallback_exc}"
                ) from fallback_exc
        return normalize_capital_flow_rows(raw, scope="market", subject_code="CN_A", subject_name="A股市场")

    def _eastmoney_capital_flow(
        self,
        *,
        label: str,
        secid: str,
        market_scope: str,
        secid2: str | None = None,
    ) -> list[dict[str, Any]]:
        self._apply_rate_limit()
        self.stats.request_count += 1
        self.stats.labels.append(label)
        self.stats.network_profiles.append("curl_fallback")
        payload = self._curl_runner(_eastmoney_capital_flow_url(secid=secid, secid2=secid2))
        rows = _eastmoney_capital_flow_records(payload, market_scope=market_scope)
        if not rows:
            raise ProviderDataError(f"Eastmoney returned no capital flow rows for {secid}")
        return rows

    def _with_retry(self, label: str, fetch: Any) -> Any:
        last_error: Exception | None = None
        errors = []
        for profile_name, proxy_env in _network_profiles(self.retry_config):
            self.stats.network_profiles.append(profile_name)
            with _temporary_proxy_env(proxy_env):
                for attempt_index in range(max(1, self.retry_config.attempts)):
                    try:
                        self._apply_rate_limit()
                        self.stats.request_count += 1
                        self.stats.labels.append(label)
                        return fetch()
                    except Exception as exc:
                        last_error = exc
                        if attempt_index < max(1, self.retry_config.attempts) - 1:
                            self.stats.retry_count += 1
                            if _looks_like_throttling(exc):
                                self.stats.throttling_warnings.append(f"{label}: likely throttling or anti-bot response: {exc}")
                            self._sleep(_backoff_seconds(self.retry_config, attempt_index))
                errors.append(f"{profile_name}: {last_error}")
        raise ProviderDataError(
            f"{label} failed after {self.retry_config.attempts} attempt(s) across "
            f"{len(errors)} network profile(s): {' | '.join(errors)}"
        )

    def _apply_rate_limit(self) -> None:
        min_delay = max(0.0, self.access_policy.min_delay_seconds)
        jitter = max(0.0, self.access_policy.jitter_seconds)
        target_delay = min_delay + (self._random() * jitter if jitter else 0.0)
        now = self._monotonic()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            if elapsed < target_delay:
                self._sleep(target_delay - elapsed)
                now = self._monotonic()
        self._last_request_at = now


def _backoff_seconds(retry_config: RetryConfig, attempt_index: int) -> float:
    base = max(0.0, retry_config.backoff_base_seconds)
    return min(max(0.0, retry_config.max_backoff_seconds), base * (2**attempt_index))


def _looks_like_throttling(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "429",
            "403",
            "anti",
            "captcha",
            "forbidden",
            "too many",
            "too frequent",
            "rate limit",
            "temporarily blocked",
            "访问过于频繁",
            "禁止访问",
            "限流",
            "验证码",
        )
    )


def normalize_price_rows(raw_rows: Any, asset_type: str) -> list[dict[str, Any]]:
    rows = _records(raw_rows)
    if not rows:
        return []

    normalized = []
    for row in rows:
        trade_date = _value(row, "trade_date", "date", "日期", "净值日期")
        if trade_date is None:
            raise ProviderDataError("Missing required date column in provider response")

        if asset_type == "fund":
            normalized.append(
                {
                    "trade_date": _date_text(trade_date),
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": _number(_value(row, "单位净值", "nav", "close")),
                    "volume": None,
                    "amount": None,
                    "pct_change": _number(_value(row, "日增长率", "涨跌幅", "pct_change")),
                    "adjusted_close": None,
                    "nav": _number(_value(row, "单位净值", "nav")),
                    "accumulated_nav": _number(_value(row, "累计净值", "accumulated_nav")),
                    "raw_payload": None,
                }
            )
            continue

        close = _number(_value(row, "close", "收盘", "收盘价"))
        normalized.append(
            {
                "trade_date": _date_text(trade_date),
                "open": _number(_value(row, "open", "开盘", "开盘价")),
                "high": _number(_value(row, "high", "最高", "最高价")),
                "low": _number(_value(row, "low", "最低", "最低价")),
                "close": close,
                "volume": _number(_value(row, "volume", "成交量")),
                "amount": _number(_value(row, "amount", "成交额")),
                "pct_change": _number(_value(row, "pct_change", "涨跌幅")),
                "adjusted_close": close,
                "nav": None,
                "accumulated_nav": None,
                "raw_payload": None,
            }
        )
    return normalized


def normalize_fund_info(raw_basic: Any, raw_rank: Any | None, code: str) -> dict[str, Any]:
    basic_rows = _records(raw_basic)
    if not basic_rows:
        raise ProviderDataError(f"AKShare returned no fund basic info for {code}")
    basic = {}
    for row in basic_rows:
        item = _value(row, "item", "项目")
        value = _value(row, "value", "值")
        if item is not None:
            basic[str(item)] = None if value is None else str(value)

    if basic.get("基金代码") and basic["基金代码"] != code:
        raise ProviderDataError(f"Fund basic info code mismatch: expected {code}, got {basic['基金代码']}")

    rank_row = _find_rank_row(raw_rank, code) if raw_rank is not None else {}
    stage_returns = {
        "date": _value(rank_row, "日期"),
        "return_1w": _number(_value(rank_row, "近1周")),
        "return_1m": _number(_value(rank_row, "近1月")),
        "return_3m": _number(_value(rank_row, "近3月")),
        "return_6m": _number(_value(rank_row, "近6月")),
        "return_1y": _number(_value(rank_row, "近1年")),
        "return_2y": _number(_value(rank_row, "近2年")),
        "return_3y": _number(_value(rank_row, "近3年")),
        "return_ytd": _number(_value(rank_row, "今年来")),
        "return_since_inception": _number(_value(rank_row, "成立来")),
    }

    raw_payload = {"basic": basic, "rank": dict(rank_row) if rank_row else None}
    return {
        "fund_type": basic.get("基金类型"),
        "fund_company": basic.get("基金公司"),
        "manager": basic.get("基金经理"),
        "custodian": basic.get("托管银行"),
        "management_fee": None,
        "custody_fee": None,
        "purchase_fee": _number(_value(rank_row, "手续费")),
        "scale": _scale_yi(basic.get("最新规模")),
        "inception_date": basic.get("成立时间"),
        "benchmark": basic.get("业绩比较基准"),
        "strategy": basic.get("投资策略"),
        "objective": basic.get("投资目标"),
        "stage_returns_json": json.dumps(stage_returns, ensure_ascii=False, default=str),
        "raw_payload": json.dumps(raw_payload, ensure_ascii=False, default=str),
    }


def normalize_capital_flow_rows(
    raw_rows: Any,
    scope: str,
    subject_code: str,
    subject_name: str,
) -> list[dict[str, Any]]:
    normalized = []
    for row in _records(raw_rows):
        raw_date = _value(row, "日期", "交易日期", "date", "trade_date")
        if raw_date in (None, ""):
            continue
        flow_date = _date_text(raw_date)
        current_code = _value(row, "代码", "股票代码", "symbol", "code") or subject_code
        current_name = _value(row, "名称", "股票简称", "name") or subject_name
        normalized.append(
            {
                "flow_date": flow_date,
                "scope": scope,
                "subject_code": _capital_flow_subject_code(scope, current_code),
                "subject_name": str(current_name),
                "asset_id": None,
                "close": _number(_value(row, "收盘价", "最新价", "close")),
                "pct_change": _percent_ratio(_value(row, "涨跌幅", "pct_change")),
                "main_net_inflow": _number(_value(row, "主力净流入-净额", "主力净流入净额", "净额", "主力净额")),
                "main_net_inflow_pct": _percent_ratio(_value(row, "主力净流入-净占比", "主力净流入净占比", "净占比")),
                "super_large_net_inflow": _number(_value(row, "超大单净流入-净额", "超大单净额")),
                "super_large_net_inflow_pct": _percent_ratio(_value(row, "超大单净流入-净占比", "超大单净占比")),
                "large_net_inflow": _number(_value(row, "大单净流入-净额", "大单净额")),
                "large_net_inflow_pct": _percent_ratio(_value(row, "大单净流入-净占比", "大单净占比")),
                "medium_net_inflow": _number(_value(row, "中单净流入-净额", "中单净额")),
                "medium_net_inflow_pct": _percent_ratio(_value(row, "中单净流入-净占比", "中单净占比")),
                "small_net_inflow": _number(_value(row, "小单净流入-净额", "小单净额")),
                "small_net_inflow_pct": _percent_ratio(_value(row, "小单净流入-净占比", "小单净占比")),
                "raw_payload": json.dumps(dict(row), ensure_ascii=False, default=str),
            }
        )
    return normalized


def normalize_fund_stock_holding_rows(raw_rows: Any, fund_code: str) -> list[dict[str, Any]]:
    normalized = []
    for row in _records(raw_rows):
        holding_code = _value(row, "股票代码", "代码", "stock_code")
        if holding_code in (None, ""):
            continue
        quarter = _value(row, "季度", "报告期", "report_period")
        normalized.append(
            {
                "fund_code": str(fund_code).zfill(6),
                "report_period": str(quarter or ""),
                "holding_type": "stock",
                "holding_code": str(holding_code).zfill(6) if str(holding_code).isdigit() else str(holding_code),
                "holding_name": str(_value(row, "股票名称", "名称", "stock_name") or holding_code),
                "holding_asset_id": None,
                "weight_pct": _percent_ratio(_value(row, "占净值比例", "持仓占比", "weight_pct")),
                "shares": _ten_thousand_unit(_value(row, "持股数", "持股数量", "shares")),
                "market_value": _ten_thousand_unit(_value(row, "持仓市值", "市值", "market_value")),
                "rank": int(_number(_value(row, "序号", "排名", "rank")) or 0) or None,
                "raw_payload": json.dumps(dict(row), ensure_ascii=False, default=str),
            }
        )
    return normalized


def _find_rank_row(raw_rank: Any, code: str) -> Mapping[str, Any]:
    for row in _records(raw_rank):
        if str(_value(row, "基金代码", "code")) == code:
            return row
    return {}


def _provider_symbol(code: str) -> str:
    prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    return f"{prefix}{code}"


def _fund_flow_market(code: str) -> str:
    normalized_code = str(code).zfill(6)
    if normalized_code.startswith(("60", "68", "90")):
        return "sh"
    if normalized_code.startswith(("8", "4")):
        return "bj"
    return "sz"


def _eastmoney_market_id(market: str) -> str:
    return "1" if market == "sh" else "0"


def _eastmoney_capital_flow_url(*, secid: str, secid2: str | None = None) -> str:
    params = {
        "lmt": "0",
        "klt": "101",
        "secid": secid,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "ut": "b2884a393a59ad64002292a3e90d46a5",
        "_": str(int(time.time() * 1000)),
    }
    if secid2:
        params["secid2"] = secid2
    return f"https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?{urlencode(params)}"


def _run_curl_json(url: str) -> dict[str, Any]:
    base_command = [
        "curl",
        "-L",
        "--fail",
        "--silent",
        "--show-error",
        "--max-time",
        "20",
        "--compressed",
        "-H",
        "Accept: application/json,text/plain,*/*",
        "-H",
        "Referer: https://data.eastmoney.com/",
        "-A",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36",
    ]
    profiles = [
        ("curl_no_proxy", [*base_command, "--noproxy", "*", url], None),
        ("curl_local_proxy_127.0.0.1:7890", [*base_command, url], {**os.environ, **LOCAL_PROXY_ENV}),
    ]
    errors = []
    for profile_name, command, env in profiles:
        for attempt in range(3):
            try:
                result = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
            except FileNotFoundError as exc:
                raise ProviderDataError("curl is required for Eastmoney capital flow fallback") from exc
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or exc.stdout or str(exc)).strip()
                errors.append(f"{profile_name} attempt {attempt + 1}: {detail}")
                time.sleep(1 + attempt)
                continue
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError:
                errors.append(f"{profile_name} attempt {attempt + 1}: invalid JSON {result.stdout[:200]}")
                time.sleep(1 + attempt)
                continue
            if isinstance(payload, dict):
                return payload
            errors.append(f"{profile_name} attempt {attempt + 1}: response must be a JSON object")
    raise ProviderDataError(f"curl request failed: {' | '.join(errors)}")


def _eastmoney_capital_flow_records(payload: Mapping[str, Any], *, market_scope: str) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    klines = data.get("klines")
    if not isinstance(klines, list):
        return []
    rows = []
    for item in klines:
        parts = str(item).split(",")
        if len(parts) < 13:
            continue
        base = {
            "日期": parts[0],
            "主力净流入-净额": parts[1],
            "小单净流入-净额": parts[2],
            "中单净流入-净额": parts[3],
            "大单净流入-净额": parts[4],
            "超大单净流入-净额": parts[5],
            "主力净流入-净占比": parts[6],
            "小单净流入-净占比": parts[7],
            "中单净流入-净占比": parts[8],
            "大单净流入-净占比": parts[9],
            "超大单净流入-净占比": parts[10],
        }
        if market_scope == "market":
            base.update(
                {
                    "上证-收盘价": parts[11],
                    "上证-涨跌幅": parts[12],
                    "深证-收盘价": parts[13] if len(parts) > 13 else None,
                    "深证-涨跌幅": parts[14] if len(parts) > 14 else None,
                }
            )
        else:
            base.update({"收盘价": parts[11], "涨跌幅": parts[12]})
        rows.append(base)
    return rows


def _capital_flow_subject_code(scope: str, value: Any) -> str:
    text = str(value).strip()
    if scope == "stock" and text.isdigit():
        return text.zfill(6)
    return text


PROXY_ENV_KEYS = (
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
)


LOCAL_PROXY_ENV = {
    "https_proxy": "http://127.0.0.1:7890",
    "http_proxy": "http://127.0.0.1:7890",
    "all_proxy": "socks5://127.0.0.1:7890",
    "HTTPS_PROXY": "http://127.0.0.1:7890",
    "HTTP_PROXY": "http://127.0.0.1:7890",
    "ALL_PROXY": "socks5://127.0.0.1:7890",
}


def _network_profiles(retry_config: RetryConfig) -> list[tuple[str, dict[str, str | None]]]:
    profiles: list[tuple[str, dict[str, str | None]]] = [("environment", {})]
    if retry_config.fallback_to_direct:
        profiles.append(("direct", {**{key: None for key in PROXY_ENV_KEYS}, "NO_PROXY": "*", "no_proxy": "*"}))
    if retry_config.fallback_to_local_proxy and not _is_local_proxy_env():
        profiles.append(("local_proxy_127.0.0.1:7890", LOCAL_PROXY_ENV))
    return profiles


def _is_local_proxy_env() -> bool:
    proxy_values = {os.environ.get(key, "") for key in PROXY_ENV_KEYS}
    return any("127.0.0.1:7890" in value or "localhost:7890" in value for value in proxy_values)


@contextmanager
def _temporary_proxy_env(proxy_env: dict[str, str | None]) -> Iterator[None]:
    original = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
    try:
        for key, value in proxy_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _records(raw_rows: Any) -> list[Mapping[str, Any]]:
    if hasattr(raw_rows, "to_dict"):
        return raw_rows.to_dict("records")
    if isinstance(raw_rows, Iterable) and not isinstance(raw_rows, (str, bytes, Mapping)):
        return list(raw_rows)
    raise ProviderDataError("Provider response must be a dataframe or iterable of mappings")


def _within_news_window(value: Any, start_datetime: str, end_datetime: str) -> bool:
    try:
        published = datetime.fromisoformat(str(value).replace(" ", "T"))
        start = datetime.fromisoformat(str(start_datetime).replace(" ", "T"))
        end = datetime.fromisoformat(str(end_datetime).replace(" ", "T"))
    except ValueError:
        return False
    return start <= published <= end


def _value(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    text = str(value).strip().replace("%", "")
    if text in {"", "-", "nan", "None"}:
        return None
    return float(text)


def _percent_ratio(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return number / 100 if abs(number) > 1 else number


def _ten_thousand_unit(value: Any) -> float | None:
    number = _number(value)
    return number * 10_000 if number is not None else None


def _scale_yi(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "-", "nan", "None", "<NA>"}:
        return None
    multiplier = 1.0
    if text.endswith("万"):
        multiplier = 0.0001
        text = text[:-1]
    elif text.endswith("亿"):
        text = text[:-1]
    return _number(text) * multiplier if _number(text) is not None else None


def _date_text(value: Any) -> str:
    if hasattr(value, "date"):
        return value.date().isoformat()
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text
