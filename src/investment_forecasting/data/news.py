from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from investment_forecasting.data.classification import THEME_KEYWORDS, THEME_LABELS
from investment_forecasting.db import (
    complete_task_log,
    connect,
    init_db,
    start_task_log,
    upsert_news_feature_daily,
    upsert_news_item,
    upsert_news_item_link,
    upsert_news_item_tag,
)


MAX_NEWS_WINDOW_DAYS = 31
DEFAULT_EXCERPT_LENGTH = 500
SEARCH_EXCERPT_LENGTH = 240
MAX_SEARCH_RESULTS = 50
NEWS_INDEX_SOURCE = "deterministic_news_index_v1"
NEWS_FEATURE_SOURCE = "deterministic_news_feature_v1"


EVENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "policy": ("政策", "支持", "补贴", "会议", "发改委", "财政部", "央行", "国务院"),
    "earnings": ("业绩", "财报", "营收", "利润", "净利润", "预告", "增长"),
    "regulation": ("监管", "处罚", "问询", "调查", "整改", "限制"),
    "macro": ("宏观", "cpi", "pmi", "利率", "汇率", "通胀", "就业", "经济"),
    "risk_event": ("风险", "违约", "暴雷", "停牌", "退市", "下修", "亏损", "诉讼"),
    "liquidity": ("资金", "流动性", "净流入", "净流出", "成交", "融资", "北向"),
    "industry_trend": ("板块", "行业", "景气", "趋势", "需求", "供给", "价格"),
    "company_event": ("公司", "公告", "并购", "回购", "减持", "增持", "订单", "中标"),
}

POSITIVE_KEYWORDS = ("利好", "上涨", "增长", "修复", "支持", "回暖", "净流入", "突破", "超预期", "增持")
NEGATIVE_KEYWORDS = ("利空", "下跌", "监管", "处罚", "风险", "回落", "净流出", "亏损", "暴雷", "违约", "停牌", "退市")


class NewsIngestionError(RuntimeError):
    """Raised when news evidence cannot be ingested into the local store."""


def ingest_news(
    db_path: str | Path,
    *,
    provider: Any,
    source: str,
    start_datetime: str,
    end_datetime: str,
    max_items: int = 500,
) -> dict[str, int]:
    source = str(source or "").strip()
    if not source:
        raise NewsIngestionError("news ingestion requires --source")
    if max_items <= 0:
        raise NewsIngestionError("--max-items must be positive")

    start = parse_news_datetime(start_datetime)
    end = parse_news_datetime(end_datetime)
    if end < start:
        raise NewsIngestionError("--end-datetime must be after --start-datetime")
    if (end - start).days > MAX_NEWS_WINDOW_DAYS:
        raise NewsIngestionError(f"news ingestion window must be {MAX_NEWS_WINDOW_DAYS} days or less")

    init_db(db_path)
    with connect(db_path) as conn:
        log_id = start_task_log(
            conn,
            "news_ingestion",
            start.date().isoformat(),
            json.dumps(
                {
                    "provider": getattr(provider, "source", provider.__class__.__name__),
                    "source": source,
                    "start_datetime": start_datetime,
                    "end_datetime": end_datetime,
                    "max_items": max_items,
                },
                ensure_ascii=False,
            ),
        )
        try:
            raw_rows = list(provider.news(source=source, start_datetime=start_datetime, end_datetime=end_datetime))
            inserted = 0
            duplicates = 0
            for row in raw_rows[:max_items]:
                news_item_id, was_inserted = upsert_news_item(
                    conn,
                    normalize_news_row(row, provider=getattr(provider, "source", provider.__class__.__name__), source=source),
                )
                index_news_item(conn, news_item_id)
                if was_inserted:
                    inserted += 1
                else:
                    duplicates += 1
            skipped = max(0, len(raw_rows) - max_items)
            summary = {
                "fetched_count": len(raw_rows),
                "inserted_count": inserted,
                "duplicate_count": duplicates,
                "skipped_count": skipped,
            }
            complete_task_log(conn, log_id, "success", json.dumps(summary, ensure_ascii=False))
            return summary
        except Exception as exc:
            complete_task_log(conn, log_id, "failed", error=str(exc))
            if isinstance(exc, NewsIngestionError):
                raise
            raise NewsIngestionError(f"News provider failed for source:{source}: {exc}") from exc


def index_news_evidence(db_path: str | Path) -> dict[str, int]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute("SELECT id FROM news_items ORDER BY published_at, id").fetchall()
        linked = 0
        tagged = 0
        for row in rows:
            result = index_news_item(conn, int(row["id"]))
            linked += result["link_count"]
            tagged += result["tag_count"]
        return {"news_count": len(rows), "link_count": linked, "tag_count": tagged}


def search_news_evidence(db_path: str | Path, **filters: Any) -> dict[str, Any]:
    init_db(db_path)
    max_results = min(MAX_SEARCH_RESULTS, max(1, int(filters.get("max_results") or 10)))
    start_datetime = filters.get("start_datetime")
    end_datetime = filters.get("end_datetime")
    source = _list_filter(filters.get("source") or filters.get("sources"))
    asset_id = filters.get("asset_id")
    asset_code = _optional_text(filters.get("asset_code"))
    theme = _optional_text(filters.get("theme") or filters.get("theme_key"))
    event_type = _optional_text(filters.get("event_type"))
    sentiment = _optional_text(filters.get("sentiment"))
    keyword = _optional_text(filters.get("keyword"))
    sort = filters.get("sort", "recency")
    dedupe = filters.get("dedupe", "content_hash")

    start_text = parse_news_datetime(start_datetime).strftime("%Y-%m-%d %H:%M:%S") if start_datetime else None
    end_text = parse_news_datetime(end_datetime).strftime("%Y-%m-%d %H:%M:%S") if end_datetime else None
    _validate_search_bounds(
        source=source,
        start_text=start_text,
        end_text=end_text,
        asset_id=asset_id,
        asset_code=asset_code,
        theme=theme,
        event_type=event_type,
        sentiment=sentiment,
        keyword=keyword,
    )

    with connect(db_path) as conn:
        resolved_asset_id = _resolve_asset_id(conn, asset_id=asset_id, asset_code=asset_code)
        if theme and theme not in THEME_LABELS:
            raise NewsIngestionError(f"unknown news theme filter: {theme}")
        where = ["1 = 1"]
        params: list[Any] = []
        if source:
            where.append(f"ni.source IN ({','.join('?' for _ in source)})")
            params.extend(source)
        if start_text:
            where.append("ni.published_at >= ?")
            params.append(start_text)
        if end_text:
            where.append("ni.published_at <= ?")
            params.append(end_text)
        if keyword:
            where.append("(ni.title LIKE ? OR ni.content_excerpt LIKE ? OR COALESCE(ni.content, '') LIKE ?)")
            params.extend([f"%{keyword}%"] * 3)
        if resolved_asset_id is not None:
            where.append("EXISTS (SELECT 1 FROM news_item_links nl WHERE nl.news_item_id = ni.id AND nl.asset_id = ?)")
            params.append(resolved_asset_id)
        if theme:
            where.append("EXISTS (SELECT 1 FROM news_item_links nl WHERE nl.news_item_id = ni.id AND nl.theme_key = ?)")
            params.append(theme)
        if event_type:
            where.append("EXISTS (SELECT 1 FROM news_item_tags nt WHERE nt.news_item_id = ni.id AND nt.tag_type = 'event_type' AND nt.tag_value = ?)")
            params.append(event_type)
        if sentiment:
            where.append("EXISTS (SELECT 1 FROM news_item_tags nt WHERE nt.news_item_id = ni.id AND nt.tag_type = 'sentiment' AND nt.tag_value = ?)")
            params.append(sentiment)
        order_by = _search_order_by(sort)
        rows = conn.execute(
            f"""
            SELECT ni.*
            FROM news_items ni
            WHERE {" AND ".join(where)}
            {order_by}
            LIMIT ?
            """,
            [*params, max_results * 3 if dedupe == "content_hash" else max_results],
        ).fetchall()
        deduped = _dedupe_news_rows(rows, dedupe)[:max_results]
        links = _search_links(conn, [int(row["id"]) for row in deduped])
        tags = _search_tags(conn, [int(row["id"]) for row in deduped])

    results = [_search_result(row, links.get(int(row["id"]), []), tags.get(int(row["id"]), [])) for row in deduped]
    return {
        "query": {
            "source": source,
            "start_datetime": start_text,
            "end_datetime": end_text,
            "asset_id": resolved_asset_id,
            "asset_code": asset_code,
            "theme": theme,
            "event_type": event_type,
            "sentiment": sentiment,
            "keyword": keyword,
            "max_results": max_results,
            "dedupe": dedupe,
            "sort": sort,
        },
        "count": len(results),
        "results": results,
        "bounded": True,
        "investment_advice": "News evidence is context only and is not direct buy/sell advice.",
    }


def index_news_item(conn: Any, news_item_id: int) -> dict[str, int]:
    item = conn.execute("SELECT * FROM news_items WHERE id = ?", (news_item_id,)).fetchone()
    if item is None:
        raise NewsIngestionError(f"news item not found: {news_item_id}")
    conn.execute("DELETE FROM news_item_links WHERE news_item_id = ? AND source = ?", (news_item_id, NEWS_INDEX_SOURCE))
    conn.execute("DELETE FROM news_item_tags WHERE news_item_id = ? AND source = ?", (news_item_id, NEWS_INDEX_SOURCE))
    text = _news_text(item)
    links = _asset_links(conn, item, text) + _theme_links(item, text)
    tags = _event_tags(item, text) + [_sentiment_tag(item, text)]
    for link in links:
        upsert_news_item_link(conn, link)
    for tag in tags:
        upsert_news_item_tag(conn, tag)
    return {"link_count": len(links), "tag_count": len(tags)}


def build_news_feature(
    conn: Any,
    *,
    scope_type: str,
    scope_key: str,
    feature_date: str,
    window_start: str,
    window_end: str,
) -> dict[str, Any]:
    if scope_type not in {"asset", "theme"}:
        raise NewsIngestionError("news feature scope_type must be asset or theme")
    end = parse_news_datetime(window_end)
    where = ["ni.published_at >= ?", "ni.published_at <= ?"]
    params: list[Any] = [parse_news_datetime(window_start).strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")]
    if scope_type == "asset":
        where.append("nl.asset_id = ?")
        params.append(int(scope_key))
    else:
        where.append("nl.theme_key = ?")
        params.append(scope_key)
    rows = conn.execute(
        f"""
        SELECT DISTINCT ni.id, ni.source, ni.published_at,
               st.tag_value AS sentiment,
               et.tag_value AS event_type
        FROM news_items ni
        JOIN news_item_links nl ON nl.news_item_id = ni.id
        LEFT JOIN news_item_tags st ON st.news_item_id = ni.id AND st.tag_type = 'sentiment'
        LEFT JOIN news_item_tags et ON et.news_item_id = ni.id AND et.tag_type = 'event_type'
        WHERE {" AND ".join(where)}
        ORDER BY ni.published_at DESC, ni.id DESC
        """,
        params,
    ).fetchall()
    evidence_ids = [int(row["id"]) for row in rows]
    sentiment_score = 0.0
    freshness_total = 0.0
    for row in rows:
        age_days = max(0.0, (end - parse_news_datetime(row["published_at"])).total_seconds() / 86400.0)
        freshness = 1.0 / (1.0 + age_days)
        sentiment_score += _sentiment_value(row["sentiment"]) * freshness
        freshness_total += freshness
    feature = {
        "feature_date": feature_date,
        "scope_type": scope_type,
        "scope_key": str(scope_key),
        "window_start": parse_news_datetime(window_start).strftime("%Y-%m-%d %H:%M:%S"),
        "window_end": end.strftime("%Y-%m-%d %H:%M:%S"),
        "news_count": len(rows),
        "source_count": len({row["source"] for row in rows}),
        "positive_count": sum(1 for row in rows if row["sentiment"] == "positive"),
        "negative_count": sum(1 for row in rows if row["sentiment"] == "negative"),
        "neutral_count": sum(1 for row in rows if row["sentiment"] in {"neutral", "unknown", None}),
        "risk_event_count": sum(1 for row in rows if row["event_type"] == "risk_event"),
        "policy_count": sum(1 for row in rows if row["event_type"] == "policy"),
        "freshness_weighted_sentiment": sentiment_score / freshness_total if freshness_total else 0.0,
        "evidence_ids_json": json.dumps(evidence_ids, ensure_ascii=False),
        "source": NEWS_FEATURE_SOURCE,
    }
    upsert_news_feature_daily(conn, feature)
    return feature


def normalize_news_row(row: dict[str, Any], *, provider: str, source: str) -> dict[str, Any]:
    title = _required_text(row, ("title", "news_title", "headline"))
    published_at = parse_news_datetime(
        row.get("published_at")
        or row.get("datetime")
        or row.get("time")
        or row.get("pub_time")
        or row.get("pubdate")
        or row.get("date")
    ).strftime("%Y-%m-%d %H:%M:%S")
    content = _text(row.get("content") or row.get("body") or row.get("summary") or row.get("desc") or title)
    content_excerpt = _excerpt(content)
    channels = _channels(row.get("channels") or row.get("channel") or row.get("src") or row.get("source"))
    provider_news_id = _optional_text(row.get("provider_news_id") or row.get("news_id") or row.get("id") or row.get("uuid"))
    url = _optional_text(row.get("url") or row.get("link"))
    raw_payload = json.dumps(row, ensure_ascii=False, default=str, sort_keys=True)
    content_hash = hashlib.sha256(f"{source}|{published_at}|{title}|{content}".encode("utf-8")).hexdigest()
    return {
        "provider": str(provider),
        "source": source,
        "provider_news_id": provider_news_id,
        "published_at": published_at,
        "title": title,
        "content_excerpt": content_excerpt,
        "content": content,
        "channels_json": json.dumps(channels, ensure_ascii=False),
        "url": url,
        "content_hash": content_hash,
        "raw_payload": raw_payload,
    }


def parse_news_datetime(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise NewsIngestionError("news row is missing published datetime")
    compact = re.sub(r"\D", "", text)
    if len(compact) >= 14:
        return datetime.strptime(compact[:14], "%Y%m%d%H%M%S")
    if len(compact) == 8:
        return datetime.strptime(compact, "%Y%m%d")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    raise NewsIngestionError(f"invalid news datetime: {value}")


def _required_text(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _optional_text(row.get(key))
        if value:
            return value
    raise NewsIngestionError(f"news row is missing required text field: {'/'.join(keys)}")


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _excerpt(value: str) -> str:
    return _text(value)[:DEFAULT_EXCERPT_LENGTH]


def _channels(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [item for item in (_text(item) for item in value) if item]
    return [item for item in (_text(part) for part in re.split(r"[,，/|]", str(value))) if item]


def _news_text(item: Any) -> str:
    channels = " ".join(json.loads(item["channels_json"] or "[]"))
    return _text(f"{item['title']} {item['content_excerpt']} {item['content'] or ''} {channels}").lower()


def _news_body_text(item: Any) -> str:
    return _text(f"{item['title']} {item['content_excerpt']} {item['content'] or ''}").lower()


def _asset_links(conn: Any, item: Any, text: str) -> list[dict[str, Any]]:
    if item["source"] == "eastmoney_stock_news":
        return _eastmoney_stock_news_links(conn, item)

    links: list[dict[str, Any]] = []
    assets = conn.execute("SELECT id, code, name, asset_type FROM assets WHERE status = 'active' ORDER BY id").fetchall()
    for asset in assets:
        code = str(asset["code"] or "").lower()
        name = str(asset["name"] or "").lower()
        if code and code in text:
            links.append(_link(item["id"], f"asset:{asset['id']}", asset["id"], None, None, "asset_code", 0.95, f"正文包含资产代码 {asset['code']}"))
        elif name and len(name) >= 2 and name in text:
            links.append(_link(item["id"], f"asset:{asset['id']}", asset["id"], None, None, "asset_name", 0.85, f"正文包含资产名称 {asset['name']}"))
    return links


def _eastmoney_stock_news_links(conn: Any, item: Any) -> list[dict[str, Any]]:
    channels = json.loads(item["channels_json"] or "[]")
    source_code = _stock_code_from_channels(channels)
    body_text = _news_body_text(item)
    stock_assets = conn.execute(
        "SELECT id, code, name FROM assets WHERE status = 'active' AND asset_type = 'stock' ORDER BY id"
    ).fetchall()
    non_stock_assets = conn.execute(
        "SELECT code, name, asset_type FROM assets WHERE status = 'active' AND asset_type <> 'stock' ORDER BY id"
    ).fetchall()
    by_code = {str(asset["code"]).zfill(6): asset for asset in stock_assets}
    non_stock_by_code: dict[str, list[Any]] = {}
    for asset in non_stock_assets:
        non_stock_by_code.setdefault(str(asset["code"]).zfill(6), []).append(asset)
    links: list[dict[str, Any]] = []
    linked_asset_ids: set[int] = set()

    if source_code and source_code in by_code:
        asset = by_code[source_code]
        name = str(asset["name"] or "").lower()
        if (
            (source_code.lower() in body_text or _contains_name(body_text, name))
            and not _non_stock_same_code_context(body_text, stock_name=name, non_stock_assets=non_stock_by_code.get(source_code, []))
        ):
            linked_asset_ids.add(int(asset["id"]))
            links.append(
                _link(
                    item["id"],
                    f"asset:{asset['id']}",
                    asset["id"],
                    None,
                    None,
                    "asset_code",
                    0.99,
                    f"东方财富个股新闻标题/正文确认来源股票 {asset['code']}",
                )
            )

    for code, asset in by_code.items():
        if int(asset["id"]) in linked_asset_ids:
            continue
        name = str(asset["name"] or "").lower()
        if _non_stock_same_code_context(body_text, stock_name=name, non_stock_assets=non_stock_by_code.get(code, [])):
            continue
        if code.lower() in body_text:
            linked_asset_ids.add(int(asset["id"]))
            links.append(
                _link(
                    item["id"],
                    f"asset:{asset['id']}",
                    asset["id"],
                    None,
                    None,
                    "asset_code",
                    0.8,
                    f"正文提及股票代码 {asset['code']}",
                )
            )
        elif _contains_name(body_text, name):
            linked_asset_ids.add(int(asset["id"]))
            links.append(
                _link(
                    item["id"],
                    f"asset:{asset['id']}",
                    asset["id"],
                    None,
                    None,
                    "asset_name",
                    0.75,
                    f"正文提及股票名称 {asset['name']}",
                )
            )
    return links


def _non_stock_same_code_context(body_text: str, *, stock_name: str, non_stock_assets: list[Any]) -> bool:
    if _contains_name(body_text, stock_name):
        return False
    for asset in non_stock_assets:
        if _contains_name(body_text, str(asset["name"] or "").lower()):
            return True
    return False


def _contains_name(text: str, name: str) -> bool:
    name = _text(name).lower()
    if len(name) < 2:
        return False
    return name in text or name.replace(" ", "") in text.replace(" ", "")


def _stock_code_from_channels(channels: list[Any]) -> str | None:
    for value in channels:
        text = _text(value)
        if re.fullmatch(r"\d{6}", text):
            return text
    return None


def _theme_links(item: Any, text: str) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    channels = " ".join(json.loads(item["channels_json"] or "[]")).lower()
    for key, keywords in THEME_KEYWORDS:
        if key == "unknown":
            continue
        matched = next((keyword for keyword in keywords if keyword.lower() in text), None)
        if matched:
            links.append(_link(item["id"], f"theme:{key}", None, key, THEME_LABELS[key], "theme_keyword", 0.75, f"文本包含主题关键词“{matched}”"))
            continue
        channel_match = next((keyword for keyword in keywords if keyword.lower() in channels), None)
        if channel_match:
            links.append(_link(item["id"], f"theme:{key}", None, key, THEME_LABELS[key], "channel", 0.6, f"频道包含主题关键词“{channel_match}”"))
    return links


def _event_tags(item: Any, text: str) -> list[dict[str, Any]]:
    matches: list[tuple[str, str]] = []
    for event_type, keywords in EVENT_KEYWORDS.items():
        matched = next((keyword for keyword in keywords if keyword.lower() in text), None)
        if matched:
            matches.append((event_type, matched))
    if not matches:
        matches = [("unknown", "未命中事件关键词")]
    event_type, reason = matches[0]
    intensity = min(1.0, 0.45 + 0.12 * len(matches))
    return [
        _tag(
            item["id"],
            "event_type",
            event_type,
            intensity,
            1.0,
            0.75 if event_type != "unknown" else 0.4,
            f"事件关键词：{reason}",
        )
    ]


def _sentiment_tag(item: Any, text: str) -> dict[str, Any]:
    positives = [keyword for keyword in POSITIVE_KEYWORDS if keyword.lower() in text]
    negatives = [keyword for keyword in NEGATIVE_KEYWORDS if keyword.lower() in text]
    if positives and negatives:
        value = "mixed"
        reason = f"同时包含正向{positives[:2]}和负向{negatives[:2]}关键词"
        confidence = 0.65
    elif positives:
        value = "positive"
        reason = f"包含正向关键词：{positives[:3]}"
        confidence = 0.75
    elif negatives:
        value = "negative"
        reason = f"包含负向关键词：{negatives[:3]}"
        confidence = 0.75
    else:
        value = "neutral"
        reason = "未命中明确正/负向关键词"
        confidence = 0.5
    intensity = min(1.0, 0.4 + 0.1 * (len(positives) + len(negatives)))
    return _tag(item["id"], "sentiment", value, intensity, 1.0, confidence, reason)


def _link(
    news_item_id: int,
    link_key: str,
    asset_id: int | None,
    theme_key: str | None,
    theme_label: str | None,
    link_type: str,
    confidence: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "news_item_id": news_item_id,
        "link_key": link_key,
        "asset_id": asset_id,
        "theme_key": theme_key,
        "theme_label": theme_label,
        "link_type": link_type,
        "confidence": confidence,
        "reason": reason,
        "source": NEWS_INDEX_SOURCE,
    }


def _tag(
    news_item_id: int,
    tag_type: str,
    tag_value: str,
    intensity: float,
    freshness_score: float,
    confidence: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "news_item_id": news_item_id,
        "tag_type": tag_type,
        "tag_value": tag_value,
        "intensity": intensity,
        "freshness_score": freshness_score,
        "confidence": confidence,
        "reason": reason,
        "source": NEWS_INDEX_SOURCE,
    }


def _sentiment_value(value: Any) -> float:
    if value == "positive":
        return 1.0
    if value == "negative":
        return -1.0
    if value == "mixed":
        return 0.0
    return 0.0


def _list_filter(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [item for item in (_optional_text(part) for part in value) if item]
    return [item for item in (_optional_text(part) for part in str(value).split(",")) if item]


def _validate_search_bounds(**filters: Any) -> None:
    meaningful = any(
        filters[key]
        for key in ("source", "asset_id", "asset_code", "theme", "event_type", "sentiment", "keyword")
    )
    start_text = filters["start_text"]
    end_text = filters["end_text"]
    if start_text and end_text:
        start = parse_news_datetime(start_text)
        end = parse_news_datetime(end_text)
        if end < start:
            raise NewsIngestionError("news search end_datetime must be after start_datetime")
        if (end - start).days <= 7:
            meaningful = True
    if not meaningful:
        raise NewsIngestionError("news search requires a source, asset, theme, tag, keyword, or a <=7 day datetime window")


def _resolve_asset_id(conn: Any, *, asset_id: Any, asset_code: str | None) -> int | None:
    if asset_id not in (None, ""):
        row = conn.execute("SELECT id FROM assets WHERE id = ?", (int(asset_id),)).fetchone()
        if row is None:
            raise NewsIngestionError(f"unknown asset_id for news search: {asset_id}")
        return int(row["id"])
    if asset_code:
        row = conn.execute(
            "SELECT id FROM assets WHERE code = ? ORDER BY id LIMIT 1",
            (asset_code.zfill(6) if asset_code.isdigit() else asset_code,),
        ).fetchone()
        if row is None:
            raise NewsIngestionError(f"unknown asset_code for news search: {asset_code}")
        return int(row["id"])
    return None


def _search_order_by(sort: Any) -> str:
    if sort == "intensity":
        return """
        ORDER BY (
            SELECT MAX(intensity)
            FROM news_item_tags nt
            WHERE nt.news_item_id = ni.id
        ) DESC, ni.published_at DESC, ni.id DESC
        """
    if sort == "relevance":
        return """
        ORDER BY (
            SELECT MAX(confidence)
            FROM news_item_links nl
            WHERE nl.news_item_id = ni.id
        ) DESC, ni.published_at DESC, ni.id DESC
        """
    return "ORDER BY ni.published_at DESC, ni.id DESC"


def _dedupe_news_rows(rows: list[Any], mode: Any) -> list[Any]:
    if mode != "content_hash":
        return rows
    seen: set[str] = set()
    deduped = []
    for row in rows:
        key = str(row["content_hash"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _search_links(conn: Any, news_item_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not news_item_ids:
        return {}
    rows = conn.execute(
        f"""
        SELECT nl.*, a.code AS asset_code, a.name AS asset_name, a.asset_type
        FROM news_item_links nl
        LEFT JOIN assets a ON a.id = nl.asset_id
        WHERE nl.news_item_id IN ({','.join('?' for _ in news_item_ids)})
        ORDER BY nl.news_item_id, nl.confidence DESC, nl.id
        """,
        news_item_ids,
    ).fetchall()
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["news_item_id"]), []).append(
            {
                "link_type": row["link_type"],
                "confidence": row["confidence"],
                "reason": row["reason"],
                "asset": {
                    "id": row["asset_id"],
                    "code": row["asset_code"],
                    "name": row["asset_name"],
                    "asset_type": row["asset_type"],
                }
                if row["asset_id"]
                else None,
                "theme": {
                    "key": row["theme_key"],
                    "label": row["theme_label"],
                }
                if row["theme_key"]
                else None,
            }
        )
    return grouped


def _search_tags(conn: Any, news_item_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    if not news_item_ids:
        return {}
    rows = conn.execute(
        f"""
        SELECT *
        FROM news_item_tags
        WHERE news_item_id IN ({','.join('?' for _ in news_item_ids)})
        ORDER BY news_item_id, tag_type, confidence DESC, id
        """,
        news_item_ids,
    ).fetchall()
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["news_item_id"]), []).append(
            {
                "type": row["tag_type"],
                "value": row["tag_value"],
                "intensity": row["intensity"],
                "freshness_score": row["freshness_score"],
                "confidence": row["confidence"],
                "reason": row["reason"],
            }
        )
    return grouped


def _search_result(item: Any, links: list[dict[str, Any]], tags: list[dict[str, Any]]) -> dict[str, Any]:
    sentiment = next((tag for tag in tags if tag["type"] == "sentiment"), None)
    event_type = next((tag for tag in tags if tag["type"] == "event_type"), None)
    return {
        "evidence_id": int(item["id"]),
        "provider": item["provider"],
        "source": item["source"],
        "published_at": item["published_at"],
        "title": item["title"],
        "content_excerpt": _excerpt(item["content_excerpt"])[:SEARCH_EXCERPT_LENGTH],
        "channels": json.loads(item["channels_json"] or "[]"),
        "url": item["url"],
        "links": links,
        "tags": tags,
        "sentiment": sentiment["value"] if sentiment else None,
        "event_type": event_type["value"] if event_type else None,
        "intensity": max((tag["intensity"] for tag in tags), default=0.0),
        "match_reasons": [entry["reason"] for entry in links] + [tag["reason"] for tag in tags],
        "audit": {
            "news_item_id": int(item["id"]),
            "content_hash": item["content_hash"],
            "raw_payload_available": True,
        },
    }
