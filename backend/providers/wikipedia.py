"""Wikipedia search via the public MediaWiki API - no key, very reliable.

Uses the `generator=search` + `prop=extracts` combination to get titles, URLs,
and plain-text intro extracts in a single request. English Wikipedia is used by
default for this English-first project.
"""
from __future__ import annotations

from urllib.parse import quote

from ..models import SearchResult
from .base import (WIKI_USER_AGENT, ProviderError, SearchProvider, clean_snippet,
                     client, request_with_retry)


class WikipediaProvider(SearchProvider):
    name = "wikipedia"

    def __init__(self, lang: str = "en"):
        self.lang = lang or "en"

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        api = f"https://{self.lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": limit,
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "format": "json",
            "formatversion": 2,
        }
        try:
            async with client() as http:
                resp = await request_with_retry(http, "GET", api, params=params,
                                                headers={"User-Agent": WIKI_USER_AGENT}, retries=2)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"Wikipedia request failed: {exc}") from exc

        pages = data.get("query", {}).get("pages", [])
        pages = sorted(pages, key=lambda p: p.get("index", 999))
        out: list[SearchResult] = []
        for page in pages:
            title = page.get("title", "")
            extract = (page.get("extract") or "").strip()
            if not title:
                continue
            url = f"https://{self.lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
            out.append(SearchResult(
                title=title, url=url,
                snippet=clean_snippet(extract, 500) if extract else "",
                provider=self.name,
            ))
        return out
