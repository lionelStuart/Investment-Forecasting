from __future__ import annotations

import json

import pytest

from investment_forecasting.cli import main
from investment_forecasting.data.news import (
    NewsIngestionError,
    build_news_feature,
    ingest_news,
    normalize_news_row,
    search_news_evidence,
)
from investment_forecasting.db import connect, init_db, upsert_asset


class FakeNewsProvider:
    source = "fake_news"

    def __init__(self) -> None:
        self.calls = []

    def news(self, *, source: str, start_datetime: str, end_datetime: str):
        self.calls.append({"source": source, "start_datetime": start_datetime, "end_datetime": end_datetime})
        return [
            {
                "id": "n1",
                "datetime": "20260523 09:30:00",
                "title": "贵州茅台盘中异动",
                "content": "白酒板块成交活跃，市场关注消费修复。",
                "channels": ["财经", "市场"],
                "url": "https://example.test/news/1",
            },
            {
                "id": "n1",
                "datetime": "20260523 09:30:00",
                "title": "贵州茅台盘中异动",
                "content": "白酒板块成交活跃，市场关注消费修复。",
                "channels": ["财经", "市场"],
                "url": "https://example.test/news/1",
            },
            {
                "datetime": "20260523 09:30:00",
                "title": "贵州茅台盘中异动",
                "content": "白酒板块成交活跃，市场关注消费修复。",
                "channels": "财经,市场",
                "url": "https://example.test/news/1",
            },
        ]


class IndexingNewsProvider:
    source = "fake_news"

    def news(self, *, source: str, start_datetime: str, end_datetime: str):
        return [
            {
                "id": "good",
                "datetime": "20260523 09:30:00",
                "title": "600519 贵州茅台获消费政策支持",
                "content": "白酒板块需求修复，北向资金净流入，市场认为消费行业景气回暖。",
                "channels": ["财经", "白酒"],
            },
            {
                "id": "bad",
                "datetime": "20260523 11:30:00",
                "title": "光伏企业出现违约风险",
                "content": "新能源板块下跌，市场担忧流动性风险和亏损扩大。",
                "channels": ["风险", "新能源"],
            },
        ]


class EastmoneyStockNewsProvider:
    source = "akshare"

    def news(self, *, source: str, start_datetime: str, end_datetime: str):
        return [
            {
                "id": "em-000001",
                "datetime": "20260523 09:30:00",
                "title": "平安银行000001.SZ)：一季度净利润增长",
                "content": "平安银行000001.SZ)发布季报，并提及招商银行600036资金流入。",
                "channels": ["证券时报网", "000001", "平安银行"],
            },
            {
                "id": "em-irrelevant",
                "datetime": "20260523 09:35:00",
                "title": "上证50ETF成交额放大",
                "content": "上证50指数000001近期成交活跃，跟踪指数出现波动。",
                "channels": ["证券时报网", "000001", "平安银行"],
            },
        ]


def test_ingest_news_persists_provider_neutral_rows_and_deduplicates(tmp_path):
    db_path = tmp_path / "news.sqlite3"
    provider = FakeNewsProvider()

    first = ingest_news(
        db_path,
        provider=provider,
        source="sina",
        start_datetime="20260523 09:00:00",
        end_datetime="20260523 10:00:00",
    )
    second = ingest_news(
        db_path,
        provider=provider,
        source="sina",
        start_datetime="20260523 09:00:00",
        end_datetime="20260523 10:00:00",
    )

    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM news_items").fetchall()
        log = conn.execute("SELECT status, message FROM task_logs WHERE task_name = 'news_ingestion' ORDER BY id DESC LIMIT 1").fetchone()

    assert first == {"fetched_count": 3, "inserted_count": 1, "duplicate_count": 2, "skipped_count": 0}
    assert second == {"fetched_count": 3, "inserted_count": 0, "duplicate_count": 3, "skipped_count": 0}
    assert len(rows) == 1
    assert rows[0]["provider"] == "fake_news"
    assert rows[0]["source"] == "sina"
    assert rows[0]["provider_news_id"] == "n1"
    assert rows[0]["published_at"] == "2026-05-23 09:30:00"
    assert rows[0]["content_hash"]
    assert json.loads(rows[0]["channels_json"]) == ["财经", "市场"]
    assert log["status"] == "success"
    assert '"inserted_count": 0' in log["message"]


def test_ingest_news_rejects_unbounded_windows(tmp_path):
    with pytest.raises(NewsIngestionError, match="31 days or less"):
        ingest_news(
            tmp_path / "news.sqlite3",
            provider=FakeNewsProvider(),
            source="sina",
            start_datetime="20260101 00:00:00",
            end_datetime="20260301 00:00:00",
        )


def test_normalize_news_row_accepts_tushare_style_fields():
    row = normalize_news_row(
        {
            "datetime": "20260523093000",
            "title": "政策利好科技成长",
            "content": "监管部门发布支持科技创新的政策。",
            "src": "wallstreetcn",
            "url": "https://example.test/news/2",
        },
        provider="tushare",
        source="wallstreetcn",
    )

    assert row["published_at"] == "2026-05-23 09:30:00"
    assert row["content_excerpt"] == "监管部门发布支持科技创新的政策。"
    assert json.loads(row["channels_json"]) == ["wallstreetcn"]


def test_ingest_news_cli_requires_tushare_credentials_gracefully(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TS_TOKEN", raising=False)

    result = main(
        [
            "ingest",
            "news",
            "--db",
            str(tmp_path / "news.sqlite3"),
            "--source",
            "sina",
            "--start-datetime",
            "20260523 09:00:00",
            "--end-datetime",
            "20260523 10:00:00",
        ]
    )

    assert result == 1
    assert "News ingestion failed" in capsys.readouterr().err


def test_ingest_news_indexes_asset_theme_event_and_sentiment(tmp_path):
    db_path = init_db(tmp_path / "news.sqlite3")
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": "600519",
                "name": "贵州茅台",
                "asset_type": "stock",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "manual",
            },
        )

    summary = ingest_news(
        db_path,
        provider=IndexingNewsProvider(),
        source="sina",
        start_datetime="20260523 09:00:00",
        end_datetime="20260523 12:00:00",
    )

    with connect(db_path) as conn:
        asset_links = conn.execute(
            """
            SELECT nl.*, ni.title
            FROM news_item_links nl
            JOIN news_items ni ON ni.id = nl.news_item_id
            WHERE nl.asset_id = ?
            ORDER BY nl.link_type
            """,
            (asset_id,),
        ).fetchall()
        theme_links = conn.execute("SELECT theme_key, theme_label, reason FROM news_item_links WHERE theme_key IS NOT NULL").fetchall()
        tags = conn.execute(
            """
            SELECT ni.title, nt.tag_type, nt.tag_value, nt.reason
            FROM news_item_tags nt
            JOIN news_items ni ON ni.id = nt.news_item_id
            ORDER BY ni.provider_news_id, nt.tag_type
            """
        ).fetchall()

    assert summary["inserted_count"] == 2
    assert {row["link_type"] for row in asset_links} == {"asset_code"}
    assert any(row["theme_key"] == "consumer" and row["theme_label"] == "消费" for row in theme_links)
    assert any(row["theme_key"] == "new_energy" for row in theme_links)
    assert ("600519 贵州茅台获消费政策支持", "event_type", "policy") in {
        (row["title"], row["tag_type"], row["tag_value"]) for row in tags
    }
    assert ("600519 贵州茅台获消费政策支持", "sentiment", "positive") in {
        (row["title"], row["tag_type"], row["tag_value"]) for row in tags
    }
    assert ("光伏企业出现违约风险", "event_type", "liquidity") not in {
        (row["title"], row["tag_type"], row["tag_value"]) for row in tags
    }
    assert ("光伏企业出现违约风险", "sentiment", "negative") in {
        (row["title"], row["tag_type"], row["tag_value"]) for row in tags
    }


def test_eastmoney_stock_news_disambiguates_same_code_to_stock(tmp_path):
    db_path = init_db(tmp_path / "news.sqlite3")
    with connect(db_path) as conn:
        stock_id = upsert_asset(
            conn,
            {
                "code": "000001",
                "name": "平安银行",
                "asset_type": "stock",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "manual",
            },
        )
        upsert_asset(
            conn,
            {
                "code": "000001",
                "name": "上证指数",
                "asset_type": "index",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "manual",
            },
        )
        upsert_asset(
            conn,
            {
                "code": "000001",
                "name": "华夏成长混合",
                "asset_type": "fund",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "manual",
            },
        )
        mentioned_id = upsert_asset(
            conn,
            {
                "code": "600036",
                "name": "招商银行",
                "asset_type": "stock",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "manual",
            },
        )

    summary = ingest_news(
        db_path,
        provider=EastmoneyStockNewsProvider(),
        source="eastmoney_stock_news",
        start_datetime="20260523 09:00:00",
        end_datetime="20260523 10:00:00",
    )

    with connect(db_path) as conn:
        links = conn.execute(
            """
            SELECT a.id, a.code, a.name, a.asset_type, nl.confidence, nl.reason
            FROM news_item_links nl
            JOIN assets a ON a.id = nl.asset_id
            ORDER BY nl.confidence DESC, a.id
            """
        ).fetchall()

    assert summary["inserted_count"] == 2
    assert {(row["id"], row["asset_type"]) for row in links} == {
        (stock_id, "stock"),
        (mentioned_id, "stock"),
    }
    assert any(row["id"] == stock_id and "确认来源股票" in row["reason"] and row["confidence"] == 0.99 for row in links)
    assert any(row["id"] == mentioned_id and "正文提及股票代码" in row["reason"] for row in links)


def test_news_feature_window_excludes_future_news(tmp_path):
    db_path = init_db(tmp_path / "news.sqlite3")
    with connect(db_path) as conn:
        asset_id = upsert_asset(
            conn,
            {
                "code": "600519",
                "name": "贵州茅台",
                "asset_type": "stock",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "manual",
            },
        )
    ingest_news(
        db_path,
        provider=IndexingNewsProvider(),
        source="sina",
        start_datetime="20260523 09:00:00",
        end_datetime="20260523 12:00:00",
    )

    with connect(db_path) as conn:
        before_future = build_news_feature(
            conn,
            scope_type="asset",
            scope_key=str(asset_id),
            feature_date="2026-05-23",
            window_start="20260523 09:00:00",
            window_end="20260523 10:00:00",
        )
        full_window = build_news_feature(
            conn,
            scope_type="theme",
            scope_key="new_energy",
            feature_date="2026-05-23",
            window_start="20260523 09:00:00",
            window_end="20260523 12:00:00",
        )
        persisted = conn.execute("SELECT * FROM news_feature_daily ORDER BY id").fetchall()

    assert before_future["news_count"] == 1
    assert before_future["positive_count"] == 1
    assert json.loads(before_future["evidence_ids_json"])
    assert full_window["news_count"] == 1
    assert full_window["negative_count"] == 1
    assert len(persisted) == 2


def test_search_news_evidence_filters_and_bounds_output(tmp_path):
    db_path = init_db(tmp_path / "news.sqlite3")
    with connect(db_path) as conn:
        upsert_asset(
            conn,
            {
                "code": "600519",
                "name": "贵州茅台",
                "asset_type": "stock",
                "market": "CN",
                "currency": "CNY",
                "status": "active",
                "source": "manual",
            },
        )
    ingest_news(
        db_path,
        provider=IndexingNewsProvider(),
        source="sina",
        start_datetime="20260523 09:00:00",
        end_datetime="20260523 12:00:00",
    )

    response = search_news_evidence(
        db_path,
        asset_code="600519",
        sentiment="positive",
        keyword="政策",
        max_results=5,
    )
    theme_response = search_news_evidence(
        db_path,
        source="sina",
        start_datetime="20260523 11:00:00",
        end_datetime="20260523 12:00:00",
        theme="new_energy",
        event_type="risk_event",
        sentiment="negative",
    )

    assert response["count"] == 1
    result = response["results"][0]
    assert result["evidence_id"]
    assert result["sentiment"] == "positive"
    assert result["event_type"] == "policy"
    assert result["links"][0]["asset"]["code"] == "600519"
    assert result["match_reasons"]
    assert "raw_payload" not in result
    assert result["audit"]["raw_payload_available"] is True
    assert theme_response["count"] == 1
    assert theme_response["results"][0]["title"] == "光伏企业出现违约风险"


def test_search_news_evidence_rejects_broad_unfiltered_dump(tmp_path):
    with pytest.raises(NewsIngestionError, match="requires"):
        search_news_evidence(tmp_path / "empty.sqlite3")
