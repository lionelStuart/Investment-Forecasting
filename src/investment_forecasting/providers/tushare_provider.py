from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from investment_forecasting.providers.akshare_provider import ProviderDataError


@dataclass(frozen=True)
class TushareRetryConfig:
    attempts: int = 2
    fallback_to_direct: bool = True
    fallback_to_local_proxy: bool = True
    backoff_base_seconds: float = 0.5
    max_backoff_seconds: float = 5.0


class TushareProvider:
    source = "tushare"

    def __init__(
        self,
        ts_module: Any | None = None,
        token: str | None = None,
        capital_flow_lookback_days: int = 180,
        retry_config: TushareRetryConfig | None = None,
        sleep_func: Any | None = None,
    ) -> None:
        self.token = token or os.environ.get("TUSHARE_TOKEN") or os.environ.get("TS_TOKEN")
        self.capital_flow_lookback_days = capital_flow_lookback_days
        self.retry_config = retry_config or TushareRetryConfig()
        self._sleep = sleep_func or time.sleep
        self.network_profiles: list[str] = []
        if not self.token:
            raise ProviderDataError("Tushare provider requires TUSHARE_TOKEN or --tushare-token; AKShare remains the default free provider.")
        if ts_module is None:
            try:
                import tushare as ts_module
            except ImportError as exc:
                raise ProviderDataError("Tushare provider requires optional package `tushare`; install the project with the tushare extra.") from exc
        self.ts = ts_module
        self.pro = ts_module.pro_api(self.token)

    def diagnostics(self) -> dict[str, Any]:
        return {
            "provider": self.source,
            "credential_source": "token_present",
            "network_profiles": list(self.network_profiles),
        }

    def history(self, asset: Any, start_date: str, end_date: str) -> list[dict[str, Any]]:
        ts_code = _ts_code(asset.code, asset.asset_type)
        if asset.asset_type == "index":
            raw = self.pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            rows = [_normalize_market_row(row) for row in _records(raw)]
        elif asset.asset_type == "stock":
            raw = self.ts.pro_bar(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                adj="qfq",
                asset="E",
                api=self.pro,
            )
            rows = [_normalize_market_row(row) for row in _records(raw)]
        elif asset.asset_type == "etf":
            raw = self.pro.fund_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            rows = [_normalize_market_row(row) for row in _records(raw)]
        elif asset.asset_type == "fund":
            raw = self.pro.fund_nav(ts_code=ts_code, start_date=start_date, end_date=end_date)
            rows = [_normalize_fund_nav_row(row) for row in _records(raw)]
        else:
            raise ProviderDataError(f"Unsupported Tushare asset type: {asset.asset_type}")
        rows = [row for row in rows if _date_text(start_date) <= row["trade_date"] <= _date_text(end_date)]
        if not rows:
            raise ProviderDataError(f"Tushare returned no history for {asset.asset_type}:{asset.code}")
        return sorted(rows, key=lambda row: row["trade_date"])

    def asset_universe(self, asset_types: tuple[str, ...] = ("stock", "etf", "fund")) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        if "stock" in asset_types:
            assets.extend(self._stock_universe())
        if "fund" in asset_types or "etf" in asset_types:
            assets.extend(self._fund_universe(asset_types))
        return assets

    def stock_capital_flow(self, code: str) -> list[dict[str, Any]]:
        normalized_code = str(code).zfill(6)
        ts_code = _ts_code(normalized_code, "stock")
        start_date, end_date = _recent_date_range(self.capital_flow_lookback_days)
        try:
            moneyflow_rows = _records(self.pro.moneyflow(ts_code=ts_code, start_date=start_date, end_date=end_date))
        except Exception as exc:
            try:
                ths_rows = _records(self.pro.moneyflow_ths(ts_code=ts_code, start_date=start_date, end_date=end_date))
            except Exception as fallback_exc:
                raise ProviderDataError(
                    f"Tushare moneyflow fetch failed for stock:{normalized_code}: {exc}; "
                    f"moneyflow_ths fallback failed: {fallback_exc}"
                ) from fallback_exc
            if not ths_rows:
                raise ProviderDataError(f"Tushare returned no moneyflow_ths fallback rows for stock:{normalized_code}") from exc
            return sorted((_normalize_ths_moneyflow_row(row, normalized_code) for row in ths_rows), key=lambda row: row["flow_date"])
        if not moneyflow_rows:
            ths_rows = _records(self.pro.moneyflow_ths(ts_code=ts_code, start_date=start_date, end_date=end_date))
            if not ths_rows:
                raise ProviderDataError(f"Tushare returned no moneyflow rows for stock:{normalized_code}")
            return sorted((_normalize_ths_moneyflow_row(row, normalized_code) for row in ths_rows), key=lambda row: row["flow_date"])

        ths_by_date: dict[str, dict[str, Any]] = {}
        try:
            ths_rows = _records(self.pro.moneyflow_ths(ts_code=ts_code, start_date=start_date, end_date=end_date))
            ths_by_date = {_date_text(row.get("trade_date")): row for row in ths_rows if row.get("trade_date")}
        except Exception:
            ths_by_date = {}

        return sorted(
            [_normalize_moneyflow_row(row, ths_by_date.get(_date_text(row.get("trade_date"))), normalized_code) for row in moneyflow_rows],
            key=lambda row: row["flow_date"],
        )

    def market_capital_flow(self) -> list[dict[str, Any]]:
        start_date, end_date = _recent_date_range(self.capital_flow_lookback_days)
        try:
            rows = _records(self.pro.moneyflow_mkt_dc(start_date=start_date, end_date=end_date))
            if rows:
                deduped = {_date_text(row.get("trade_date")): row for row in rows if row.get("trade_date")}
                return sorted((_normalize_market_dc_moneyflow_row(row) for row in deduped.values()), key=lambda row: row["flow_date"])
        except Exception:
            pass

        rows = []
        for chunk_start, chunk_end in _date_chunks(start_date, end_date, max_days=250):
            try:
                rows.extend(_records(self.pro.moneyflow_hsgt(start_date=chunk_start, end_date=chunk_end)))
            except Exception as exc:
                raise ProviderDataError(f"Tushare moneyflow_mkt_dc and moneyflow_hsgt fetch failed: {exc}") from exc
        if not rows:
            raise ProviderDataError("Tushare returned no moneyflow_mkt_dc or moneyflow_hsgt rows")
        deduped = {_date_text(row.get("trade_date")): row for row in rows if row.get("trade_date")}
        return sorted((_normalize_hsgt_moneyflow_row(row) for row in deduped.values()), key=lambda row: row["flow_date"])

    def news(self, *, source: str, start_datetime: str, end_datetime: str) -> list[dict[str, Any]]:
        return _records(
            self._with_network_profiles(
                f"news fetch failed for source:{source}",
                lambda: self.pro.news(
                    src=source,
                    start_date=_news_datetime_param(start_datetime),
                    end_date=_news_datetime_param(end_datetime),
                ),
            )
        )

    def _with_network_profiles(self, label: str, fetch: Any) -> Any:
        errors = []
        last_error: Exception | None = None
        for profile_name, proxy_env in _network_profiles(self.retry_config):
            self.network_profiles.append(profile_name)
            with _temporary_proxy_env(proxy_env):
                for attempt_index in range(max(1, self.retry_config.attempts)):
                    try:
                        return fetch()
                    except Exception as exc:
                        last_error = exc
                        if attempt_index < max(1, self.retry_config.attempts) - 1:
                            self._sleep(_backoff_seconds(self.retry_config, attempt_index))
                errors.append(f"{profile_name}: {_redact_token(str(last_error), self.token)}")
        raise ProviderDataError(f"Tushare {label} after {self.retry_config.attempts} attempt(s) across {len(errors)} network profile(s): {' | '.join(errors)}")

    def _stock_universe(self) -> list[dict[str, Any]]:
        rows = _records(self.pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name"))
        return [
            {
                "code": str(row.get("symbol") or "").zfill(6),
                "name": str(row.get("name") or row.get("symbol") or ""),
                "asset_type": "stock",
                "market": "CN",
                "provider_symbol": row.get("ts_code"),
            }
            for row in rows
            if row.get("symbol")
        ]

    def _fund_universe(self, asset_types: tuple[str, ...]) -> list[dict[str, Any]]:
        rows = _records(self.pro.fund_basic(market="E", fields="ts_code,symbol,name,fund_type"))
        assets = []
        for row in rows:
            code = str(row.get("symbol") or "").zfill(6)
            if not code:
                continue
            fund_type = str(row.get("fund_type") or "")
            asset_type = "etf" if "ETF" in fund_type.upper() else "fund"
            if asset_type not in asset_types:
                continue
            assets.append(
                {
                    "code": code,
                    "name": str(row.get("name") or code),
                    "asset_type": asset_type,
                    "market": "CN",
                    "provider_symbol": row.get("ts_code"),
                }
            )
        return assets


def _normalize_market_row(row: dict[str, Any]) -> dict[str, Any]:
    close = _number(row.get("close"))
    return {
        "trade_date": _date_text(row.get("trade_date")),
        "open": _number(row.get("open")),
        "high": _number(row.get("high")),
        "low": _number(row.get("low")),
        "close": close,
        "volume": _number(row.get("vol") or row.get("volume")),
        "amount": _number(row.get("amount")),
        "pct_change": _number(row.get("pct_chg") or row.get("pct_change")),
        "adjusted_close": close,
        "nav": None,
        "accumulated_nav": None,
        "raw_payload": None,
    }


def _normalize_fund_nav_row(row: dict[str, Any]) -> dict[str, Any]:
    nav = _number(row.get("unit_nav") or row.get("nav") or row.get("close"))
    return {
        "trade_date": _date_text(row.get("nav_date") or row.get("trade_date")),
        "open": None,
        "high": None,
        "low": None,
        "close": nav,
        "volume": None,
        "amount": None,
        "pct_change": _number(row.get("pct_chg") or row.get("pct_change")),
        "adjusted_close": None,
        "nav": nav,
        "accumulated_nav": _number(row.get("accum_nav") or row.get("accumulated_nav")),
        "raw_payload": None,
    }


def _normalize_moneyflow_row(row: dict[str, Any], ths_row: dict[str, Any] | None, code: str) -> dict[str, Any]:
    small = _amount_wan_delta(row, "buy_sm_amount", "sell_sm_amount")
    medium = _amount_wan_delta(row, "buy_md_amount", "sell_md_amount")
    large = _amount_wan_delta(row, "buy_lg_amount", "sell_lg_amount")
    super_large = _amount_wan_delta(row, "buy_elg_amount", "sell_elg_amount")
    main = _amount_wan(row.get("net_mf_amount"))
    return {
        "flow_date": _date_text(row.get("trade_date")),
        "scope": "stock",
        "subject_code": code,
        "subject_name": str((ths_row or {}).get("name") or code),
        "asset_id": None,
        "close": _number((ths_row or {}).get("latest")),
        "pct_change": _pct((ths_row or {}).get("pct_change")),
        "main_net_inflow": main,
        "main_net_inflow_pct": None,
        "super_large_net_inflow": super_large,
        "super_large_net_inflow_pct": None,
        "large_net_inflow": large,
        "large_net_inflow_pct": _pct((ths_row or {}).get("buy_lg_amount_rate")),
        "medium_net_inflow": medium,
        "medium_net_inflow_pct": _pct((ths_row or {}).get("buy_md_amount_rate")),
        "small_net_inflow": small,
        "small_net_inflow_pct": _pct((ths_row or {}).get("buy_sm_amount_rate")),
        "raw_payload": json.dumps({"moneyflow": row, "moneyflow_ths": ths_row}, ensure_ascii=False, default=str),
        "source": "tushare",
    }


def _normalize_ths_moneyflow_row(row: dict[str, Any], code: str) -> dict[str, Any]:
    return {
        "flow_date": _date_text(row.get("trade_date")),
        "scope": "stock",
        "subject_code": code,
        "subject_name": str(row.get("name") or code),
        "asset_id": None,
        "close": _number(row.get("latest")),
        "pct_change": _pct(row.get("pct_change")),
        "main_net_inflow": _amount_wan(row.get("net_amount")),
        "main_net_inflow_pct": None,
        "super_large_net_inflow": None,
        "super_large_net_inflow_pct": None,
        "large_net_inflow": _amount_wan(row.get("buy_lg_amount")),
        "large_net_inflow_pct": _pct(row.get("buy_lg_amount_rate")),
        "medium_net_inflow": _amount_wan(row.get("buy_md_amount")),
        "medium_net_inflow_pct": _pct(row.get("buy_md_amount_rate")),
        "small_net_inflow": _amount_wan(row.get("buy_sm_amount")),
        "small_net_inflow_pct": _pct(row.get("buy_sm_amount_rate")),
        "raw_payload": json.dumps({"moneyflow_ths": row, "fallback": "moneyflow_ths"}, ensure_ascii=False, default=str),
        "source": "tushare",
    }


def _normalize_market_dc_moneyflow_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "flow_date": _date_text(row.get("trade_date")),
        "scope": "market",
        "subject_code": "CN_A",
        "subject_name": "A股大盘资金流",
        "asset_id": None,
        "close": _number(row.get("close_sh")),
        "pct_change": _pct(row.get("pct_change_sh")),
        "main_net_inflow": _number(row.get("net_amount")),
        "main_net_inflow_pct": _pct(row.get("net_amount_rate")),
        "super_large_net_inflow": _number(row.get("buy_elg_amount")),
        "super_large_net_inflow_pct": _pct(row.get("buy_elg_amount_rate")),
        "large_net_inflow": _number(row.get("buy_lg_amount")),
        "large_net_inflow_pct": _pct(row.get("buy_lg_amount_rate")),
        "medium_net_inflow": _number(row.get("buy_md_amount")),
        "medium_net_inflow_pct": _pct(row.get("buy_md_amount_rate")),
        "small_net_inflow": _number(row.get("buy_sm_amount")),
        "small_net_inflow_pct": _pct(row.get("buy_sm_amount_rate")),
        "raw_payload": json.dumps({"moneyflow_mkt_dc": row}, ensure_ascii=False, default=str),
        "source": "tushare",
    }


def _normalize_hsgt_moneyflow_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "flow_date": _date_text(row.get("trade_date")),
        "scope": "market",
        "subject_code": "CN_HSGT",
        "subject_name": "沪深港通资金流",
        "asset_id": None,
        "close": None,
        "pct_change": None,
        "main_net_inflow": _amount_million(row.get("north_money")),
        "main_net_inflow_pct": None,
        "super_large_net_inflow": _amount_million(row.get("south_money")),
        "super_large_net_inflow_pct": None,
        "large_net_inflow": _amount_million(row.get("hgt")),
        "large_net_inflow_pct": None,
        "medium_net_inflow": _amount_million(row.get("sgt")),
        "medium_net_inflow_pct": None,
        "small_net_inflow": None,
        "small_net_inflow_pct": None,
        "raw_payload": json.dumps(row, ensure_ascii=False, default=str),
        "source": "tushare",
    }


def _ts_code(code: str, asset_type: str) -> str:
    if "." in code:
        return code.upper()
    suffix = "SH" if code.startswith(("5", "6", "9")) or (asset_type == "index" and code.startswith("0")) else "SZ"
    return f"{code.zfill(6)}.{suffix}"


def _date_text(value: Any) -> str:
    text = str(value or "")
    if "-" in text:
        return text
    if len(text) == 8:
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    raise ProviderDataError("Missing required date column in provider response")


def _date_param(value: date) -> str:
    return value.strftime("%Y%m%d")


def _news_datetime_param(value: str) -> str:
    text = str(value or "").strip()
    digits = "".join(char for char in text if char.isdigit())
    if len(digits) >= 14:
        return f"{digits[:8]} {digits[8:10]}:{digits[10:12]}:{digits[12:14]}"
    if len(digits) == 8:
        return f"{digits} 00:00:00"
    raise ProviderDataError(f"Invalid Tushare news datetime: {value}")


def _recent_date_range(days: int) -> tuple[str, str]:
    today = date.today()
    start = today - timedelta(days=max(1, int(days)))
    return _date_param(start), _date_param(today)


def _parse_date_param(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def _date_chunks(start_date: str, end_date: str, max_days: int) -> list[tuple[str, str]]:
    start = _parse_date_param(start_date)
    end = _parse_date_param(end_date)
    chunks = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=max(1, max_days) - 1), end)
        chunks.append((_date_param(current), _date_param(chunk_end)))
        current = chunk_end + timedelta(days=1)
    return chunks


def _amount_wan_delta(row: dict[str, Any], buy_key: str, sell_key: str) -> float | None:
    buy = _number(row.get(buy_key))
    sell = _number(row.get(sell_key))
    if buy is None and sell is None:
        return None
    return ((buy or 0.0) - (sell or 0.0)) * 10_000.0


def _amount_wan(value: Any) -> float | None:
    number = _number(value)
    return None if number is None else number * 10_000.0


def _amount_million(value: Any) -> float | None:
    number = _number(value)
    return None if number is None else number * 1_000_000.0


def _pct(value: Any) -> float | None:
    number = _number(value)
    return None if number is None else number / 100.0


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ProviderDataError(f"Invalid numeric value from Tushare: {value}") from exc


def _records(raw_rows: Any) -> list[dict[str, Any]]:
    if hasattr(raw_rows, "to_dict"):
        return list(raw_rows.to_dict(orient="records"))
    return [dict(row) for row in raw_rows or []]


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


def _network_profiles(retry_config: TushareRetryConfig) -> list[tuple[str, dict[str, str | None]]]:
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


def _backoff_seconds(retry_config: TushareRetryConfig, attempt_index: int) -> float:
    base = max(0.0, retry_config.backoff_base_seconds)
    return min(max(0.0, retry_config.max_backoff_seconds), base * (2**attempt_index))


def _redact_token(text: str, token: str | None) -> str:
    if token:
        return text.replace(token, "[redacted]")
    return text
