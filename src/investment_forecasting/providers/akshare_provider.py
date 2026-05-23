from __future__ import annotations

import json
import os
from collections.abc import Iterator
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any


class ProviderDataError(RuntimeError):
    """Raised when provider data cannot be normalized safely."""


@dataclass(frozen=True)
class RetryConfig:
    attempts: int = 2
    fallback_to_direct: bool = True
    fallback_to_local_proxy: bool = True


class AkshareProvider:
    source = "akshare"

    def __init__(self, ak_module: Any | None = None, retry_config: RetryConfig | None = None) -> None:
        if ak_module is None:
            try:
                import akshare as ak_module
            except ImportError as exc:
                raise RuntimeError("AKShare is required for live ingestion. Install project dependencies.") from exc
        self.ak = ak_module
        self.retry_config = retry_config or RetryConfig()

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

    def _with_retry(self, label: str, fetch: Any) -> Any:
        last_error: Exception | None = None
        errors = []
        for profile_name, proxy_env in _network_profiles(self.retry_config):
            with _temporary_proxy_env(proxy_env):
                for _ in range(max(1, self.retry_config.attempts)):
                    try:
                        return fetch()
                    except Exception as exc:
                        last_error = exc
                errors.append(f"{profile_name}: {last_error}")
        raise ProviderDataError(
            f"{label} failed after {self.retry_config.attempts} attempt(s) across "
            f"{len(errors)} network profile(s): {' | '.join(errors)}"
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


def _find_rank_row(raw_rank: Any, code: str) -> Mapping[str, Any]:
    for row in _records(raw_rank):
        if str(_value(row, "基金代码", "code")) == code:
            return row
    return {}


def _provider_symbol(code: str) -> str:
    prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    return f"{prefix}{code}"


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
