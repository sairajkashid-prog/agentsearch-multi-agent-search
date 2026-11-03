"""DuckDuckGo search - no API key.

Strategy: try the lightweight `lite.duckduckgo.com` endpoint first (works well
from servers), then fall back to `html.duckduckgo.com`. Both are public HTML
endpoints; we parse them with BeautifulSoup. If DDG blocks/rate-limits us, the
SearchAgent automatically falls back to Wikipedia.
"""
from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from ..models import SearchResult
from .base import ProviderError, SearchProvider, clean_snippet, client, request_with_retry


def _resolve_ddg_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return href


class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"

    async def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        errors: list[str] = []
        async with client() as http:
            for url in ("https://lite.duckduckgo.com/lite/", "https://html.duckduckgo.com/html/"):
                try:
                    resp = await request_with_retry(http, "GET", url, params={"q": query}, retries=1)
                    if resp.status_code in (202, 403, 429):
                        errors.append(f"{url} -> HTTP {resp.status_code} (blocked)")
                        continue
                    resp.raise_for_status()
                    results = self._parse(resp.text, limit)
                    if results:
                        return results
                    errors.append(f"{url} -> 0 results")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{url} -> {exc}")
        raise ProviderError("DuckDuckGo failed: " + " | ".join(errors))

    def _parse(self, html: str, limit: int) -> list[SearchResult]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[SearchResult] = []
        seen: set[str] = set()

        # --- lite layout: <a class="result-link"> then snippet in next row ---
        for a in soup.select("a.result-link"):
            href = _resolve_ddg_url(a.get("href", ""))
            title = a.get_text(" ", strip=True)
            if not href or not title or href in seen:
                continue
            snippet = ""
            tr = a.find_parent("tr")
            if tr is not None:
                nxt = tr.find_next_sibling("tr")
                if nxt is not None:
                    td = nxt.select_one("td.result-snippet")
                    if td is not None:
                        snippet = td.get_text(" ", strip=True)
            seen.add(href)
            out.append(SearchResult(title=title, url=href,
                                    snippet=clean_snippet(snippet), provider=self.name))
            if len(out) >= limit:
                return out

        # --- html layout ---
        for res in soup.select("div.result, div.web-result"):
            a = res.select_one("a.result__a")
            if a is None:
                continue
            href = _resolve_ddg_url(a.get("href", ""))
            title = a.get_text(" ", strip=True)
            if not href or href in seen:
                continue
            sn = res.select_one(".result__snippet")
            snippet = sn.get_text(" ", strip=True) if sn else ""
            seen.add(href)
            out.append(SearchResult(title=title, url=href,
                                    snippet=clean_snippet(snippet), provider=self.name))
            if len(out) >= limit:
                break
        return out
