from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    title: str
    link: str
    published: str
    source: str


class GoogleNewsRSS:
    """Free news headlines via Google News RSS (no API key)."""

    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=15.0, follow_redirects=True)
        self._owns = client is None

    def close(self) -> None:
        if self._owns:
            self._client.close()

    def __enter__(self) -> GoogleNewsRSS:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fetch(self, query: str, limit: int = 3) -> list[NewsItem]:
        url = (
            "https://news.google.com/rss/search?q="
            + quote_plus(query)
            + "&hl=en-IN&gl=IN&ceid=IN:en"
        )
        try:
            r = self._client.get(url)
            r.raise_for_status()
            root = ET.fromstring(r.text)
            items: list[NewsItem] = []
            for item in root.findall(".//item")[:limit]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub = item.findtext("pubDate", "")
                source = item.findtext("source", "")
                if title:
                    items.append(NewsItem(title=title, link=link, published=pub, source=source))
            return items
        except Exception as exc:
            logger.warning("News fetch failed for '%s': %s", query, exc)
            return []

    def fetch_for_symbols(self, symbols: list[str], limit_per: int = 2) -> dict[str, list[NewsItem]]:
        results: dict[str, list[NewsItem]] = {}
        for sym in symbols:
            results[sym] = self.fetch(f"{sym} stock India NSE", limit=limit_per)
        return results
