from __future__ import annotations

import sqlite3
from datetime import datetime
from uuid import uuid4


class NewsRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list(self, *, symbol: str | None = None, exchange: str | None = None, limit: int = 100) -> list[dict]:
        """List news items, optionally filtered by symbol/exchange."""
        query = """
            SELECT news_id, symbol, exchange, published_at, title, summary,
                   source_site, url, keywords_json, saved, quality, ingested_at
            FROM news_items
            WHERE 1=1
        """
        params = []

        if symbol:
            query += " AND symbol=?"
            params.append(symbol)

        if exchange:
            query += " AND exchange=?"
            params.append(exchange)

        query += " ORDER BY published_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()

        import json

        return [
            {
                "news_id": r[0],
                "symbol": r[1],
                "exchange": r[2],
                "published_at": r[3],
                "title": r[4],
                "summary": r[5],
                "source_site": r[6],
                "url": r[7],
                "keywords": json.loads(r[8]) if r[8] else [],
                "saved": bool(r[9]),
                "quality": r[10],
                "ingested_at": r[11],
            }
            for r in rows
        ]

    def save_news(self, news_id: str, saved: bool = True) -> None:
        """Mark a news item as saved (bookmarked)."""
        with self._conn:
            self._conn.execute(
                "UPDATE news_items SET saved=? WHERE news_id=?",
                (1 if saved else 0, news_id),
            )

    def create_mock_news(self, symbol: str, exchange: str, count: int = 10) -> None:
        """Create mock news items for demonstration purposes."""
        import random

        now = datetime.now()
        news_titles = [
            f"{symbol} 发布重要公告",
            f"{symbol} 业绩预告超预期",
            f"{symbol} 获得重大合同",
            f"{symbol} 高管增持股份",
            f"{symbol} 行业景气度提升",
            f"{symbol} 技术创新获突破",
            f"{symbol} 市场占有率提升",
            f"{symbol} 战略合作达成",
            f"{symbol} 新产品上市",
            f"{symbol} 股价异动原因",
        ]

        for i in range(count):
            news_id = str(uuid4())
            published_at = (now.timestamp() - i * 3600)
            published_at = datetime.fromtimestamp(published_at).isoformat(timespec="seconds")
            title = random.choice(news_titles)
            summary = f"详细描述 {title} 的相关信息，内容包括业务影响、市场前景等。"
            source_site = random.choice(["东方财富", "证券时报", "上海证券报", "中国证券报"])
            url = f"https://example.com/news/{news_id}"
            keywords = random.sample(["业绩", "公告", "合作", "技术", "市场", "投资"], k=3)

            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO news_items(
                        news_id, symbol, exchange, published_at, title, summary,
                        source_site, url, keywords_json, saved, quality, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        news_id,
                        symbol,
                        exchange,
                        published_at,
                        title,
                        summary,
                        source_site,
                        url,
                        str(keywords).replace("'", '"'),
                        0,
                        "OK",
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
