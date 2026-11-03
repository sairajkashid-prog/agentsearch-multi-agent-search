"""Bing RSS search - free, no API key. Last-resort fallback provider.

Bing exposes a public RSS endpoint (`&format=rss`) that returns clean XML
results. We use it only when DuckDuckGo and Wikipedia both fail/rate-limit.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ..models import SearchResult
from .base import ProviderError, SearchProvider, clean_snippet, client, request_with_retry


class BingRSSProvider(SearchProvider):
    name = "bing-rss"

    async def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        try:
            async with client() as http:
                resp = await request_with_retry(
                    http, "GET", "https://www.bing.com/search",
                    params={"q": query, "format": "rss", "count": limit},
                    retries=2,
                )
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"Bing RSS failed: {exc}") from exc

        out: list[SearchResult] = []
        seen: set[str] = set()
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            if not link or link in seen:
                continue
            seen.add(link)
            out.append(SearchResult(title=title or link, url=link,
                                    snippet=clean_snippet(desc, 400), provider=self.name))
            if len(out) >= limit:
                break
        return out
