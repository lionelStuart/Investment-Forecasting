from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any


@dataclass(frozen=True)
class BenchmarkSelection:
    benchmark_return: float | None
    identity: str
    source: str
    asset_id: int | None = None
    peer_count: int = 0
    fallback_reason: str | None = None

    def details(self) -> dict[str, Any]:
        return {
            "benchmark_return": self.benchmark_return,
            "benchmark_identity": self.identity,
            "benchmark_source": self.source,
            "benchmark_asset_id": self.asset_id,
            "benchmark_peer_count": self.peer_count,
            "benchmark_fallback_reason": self.fallback_reason,
        }


def select_asset_benchmark(conn: Any, asset_id: int, start_date: str, end_date: str) -> BenchmarkSelection:
    asset = conn.execute("SELECT id, code, name, asset_type FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if asset is None:
        return BenchmarkSelection(None, "unavailable:missing_asset", "unavailable", fallback_reason="asset_not_found")
    actual_return = _asset_return(conn, asset_id, start_date, end_date)
    if asset["code"] == "000300" and asset["asset_type"] == "index":
        return BenchmarkSelection(actual_return, "self:000300", "self", asset_id=asset_id)
    if asset["asset_type"] == "fund":
        peer = _fund_peer_benchmark(conn, asset, start_date, end_date)
        if peer.benchmark_return is not None:
            return peer
        hs300 = _hs300_benchmark(conn, start_date, end_date)
        if hs300.benchmark_return is not None:
            return BenchmarkSelection(
                hs300.benchmark_return,
                hs300.identity,
                "fallback:hs300",
                asset_id=hs300.asset_id,
                fallback_reason=peer.fallback_reason or "insufficient_fund_peers",
            )
        return peer
    return _hs300_benchmark(conn, start_date, end_date)


def select_equal_weight_benchmark(
    conn: Any, asset_ids: list[int], start_date: str, end_date: str
) -> BenchmarkSelection:
    selections = [select_asset_benchmark(conn, asset_id, start_date, end_date) for asset_id in asset_ids]
    available = [item for item in selections if item.benchmark_return is not None]
    if not available:
        return BenchmarkSelection(None, "unavailable:no_benchmark_history", "unavailable")
    sources = sorted({item.source for item in available})
    return BenchmarkSelection(
        mean(float(item.benchmark_return) for item in available if item.benchmark_return is not None),
        f"equal_weight:{','.join(sources)}",
        "equal_weight_selected_benchmarks",
        peer_count=sum(item.peer_count for item in available),
        fallback_reason=None if len(available) == len(selections) else "partial_benchmark_coverage",
    )


def _fund_peer_benchmark(conn: Any, asset: Any, start_date: str, end_date: str, min_peers: int = 2) -> BenchmarkSelection:
    fund_info = conn.execute(
        "SELECT fund_type, benchmark FROM fund_info WHERE asset_id = ? ORDER BY updated_at DESC, id DESC LIMIT 1",
        (asset["id"],),
    ).fetchone()
    bucket = _fund_bucket(fund_info["fund_type"] if fund_info else None)
    peers = conn.execute(
        """
        SELECT a.id, a.code, a.name, fi.fund_type
        FROM assets a
        JOIN fund_info fi ON fi.asset_id = a.id
        WHERE a.asset_type = 'fund'
          AND a.id != ?
          AND a.status = 'active'
        ORDER BY a.id
        """,
        (asset["id"],),
    ).fetchall()
    peer_returns = []
    for peer in peers:
        if _fund_bucket(peer["fund_type"]) != bucket:
            continue
        peer_return = _asset_return(conn, int(peer["id"]), start_date, end_date)
        if peer_return is not None:
            peer_returns.append(peer_return)
    if len(peer_returns) < min_peers:
        return BenchmarkSelection(
            None,
            f"fund_peer:{bucket}:unavailable",
            "fund_peer_average",
            peer_count=len(peer_returns),
            fallback_reason=f"need_{min_peers}_peers",
        )
    return BenchmarkSelection(
        mean(peer_returns),
        f"fund_peer:{bucket}:n={len(peer_returns)}",
        "fund_peer_average",
        peer_count=len(peer_returns),
    )


def _hs300_benchmark(conn: Any, start_date: str, end_date: str) -> BenchmarkSelection:
    row = conn.execute("SELECT id FROM assets WHERE code = '000300' AND asset_type = 'index' ORDER BY id LIMIT 1").fetchone()
    if row is None:
        return BenchmarkSelection(None, "hs300:unavailable", "hs300", fallback_reason="missing_hs300_asset")
    benchmark_return = _asset_return(conn, int(row["id"]), start_date, end_date)
    if benchmark_return is None:
        return BenchmarkSelection(None, "hs300:unavailable", "hs300", asset_id=int(row["id"]), fallback_reason="missing_hs300_prices")
    return BenchmarkSelection(benchmark_return, "index:000300", "hs300", asset_id=int(row["id"]))


def _asset_return(conn: Any, asset_id: int, start_date: str, end_date: str) -> float | None:
    prices = conn.execute(
        """
        SELECT trade_date, COALESCE(adjusted_close, close, nav) AS value
        FROM price_daily
        WHERE asset_id = ? AND trade_date IN (?, ?)
          AND COALESCE(adjusted_close, close, nav) IS NOT NULL
        """,
        (asset_id, start_date, end_date),
    ).fetchall()
    by_date = {price["trade_date"]: float(price["value"]) for price in prices}
    if start_date not in by_date or end_date not in by_date:
        return None
    return (by_date[end_date] / by_date[start_date]) - 1.0


def _fund_bucket(fund_type: str | None) -> str:
    value = (fund_type or "").lower()
    if "股票" in value or "偏股" in value:
        return "equity_fund"
    if "混合" in value:
        return "hybrid_fund"
    if "债" in value:
        return "bond_fund"
    if "货币" in value or "现金" in value:
        return "cash_fund"
    if "指数" in value or "index" in value:
        return "index_fund"
    if "qdii" in value:
        return "qdii_fund"
    if "fof" in value:
        return "fof_fund"
    return "fund"
