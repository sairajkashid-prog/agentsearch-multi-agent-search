"""ReaderAgent: fetches top web pages and extracts clean readable text.

- Parallel fetching with a semaphore
- HTML boilerplate removal (nav/script/footer)
- Clean Wikipedia plaintext extracts via the MediaWiki API
- Fail-safe: if a page cannot be fetched, the search snippet is used
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from ..config import settings
from ..core.cache import TTLCache
from ..core.ranking import is_probably_article
from ..core.text import normalize
from ..models import Document, SearchResult
from ..providers.base import WIKI_USER_AGENT, client, request_with_retry
from .base import BaseAgent

_cache = TTLCache(ttl=settings.cache_ttl_seconds, maxsize=256)
MAX_CHARS = 14000
MIN_CHARS = 200

BOILERPLATE_RE = re.compile(
    r"(cookie|subscribe|newsletter|sign up|log in|advertisement|all rights reserved|"
    r"privacy policy|terms of service|skip to content|share this|follow us)", re.I)


def extract_main_text(html: str) -> tuple[str, str]:
    """Return (title, main_text) using readability-style heuristics."""
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = normalize(soup.title.string)
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = normalize(og["content"])

    for tag in soup(["script", "style", "noscript", "nav", "footer", "header",
                     "aside", "form", "iframe", "svg", "button"]):
        tag.decompose()

    candidates = []
    for sel in ("article", "main", "[role=main]", ".post-content", ".entry-content",
                ".article-body", "#content", ".mw-parser-output"):
        candidates.extend(soup.select(sel))
    if not candidates and soup.body:
        candidates = [soup.body]

    best_text, best_score = "", -1.0
    for c in candidates:
        paras = [normalize(p.get_text(" ", strip=True)) for p in c.find_all(["p", "li"])]
        paras = [p for p in paras if len(p) > 40 and not BOILERPLATE_RE.search(p)]
        text = "\n".join(paras)
        if not text:
            continue
        link_text = sum(len(a.get_text(" ", strip=True)) for a in c.find_all("a"))
        density = link_text / max(1, len(text))
        score = len(text) * (1.0 - min(0.9, density))
        if score > best_score:
            best_score, best_text = score, text
    if not best_text and soup.body:
        best_text = normalize(soup.body.get_text(" ", strip=True))
    return title, best_text[:MAX_CHARS]


async def _wikipedia_extract(url: str, http) -> str:
    parsed = urlparse(url)
    title = unquote(parsed.path.split("/wiki/")[-1]).replace("_", " ")
    if not title:
        return ""
    lang = parsed.netloc.split(".")[0] or "en"
    api = f"https://{lang}.wikipedia.org/w/api.php"
    resp = await request_with_retry(http, "GET", api, params={
        "action": "query", "prop": "extracts", "explaintext": 1,
        "titles": title, "format": "json", "formatversion": 2,
    }, headers={"User-Agent": WIKI_USER_AGENT}, retries=2)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", [])
    extract = (pages[0].get("extract") or "") if pages else ""
    # Remove MediaWiki section heading lines such as "== History ==".
    lines = [ln for ln in extract.splitlines() if not re.match(r"^\s*=+.*=+\s*$", ln)]
    return "\n".join(lines)[:MAX_CHARS]


class ReaderAgent(BaseAgent):
    name = "reader"
    role = "Content Reader"
    emoji = "📖"

    async def run(self, results: list[SearchResult], depth: str = "standard") -> list[Document]:
        await self.start("Reading content from top pages…")
        n = {"quick": 3, "standard": settings.max_pages_to_read,
             "deep": settings.max_pages_to_read + 3}.get(depth, settings.max_pages_to_read)
        targets = [r for r in results if is_probably_article(r.url)][:n]
        sem = asyncio.Semaphore(4)

        async with client(timeout=settings.request_timeout) as http:
            async def fetch(r: SearchResult) -> Document:
                async with sem:
                    cached = _cache.get(r.url)
                    if cached is not None:
                        await self.log(f"Cache: {r.url}", {"url": r.url, "cache": True})
                        return cached
                    try:
                        if "wikipedia.org/wiki/" in r.url:
                            text = await _wikipedia_extract(r.url, http)
                            doc = Document(url=r.url, title=r.title, text=text,
                                           provider=r.provider, fetch_ok=bool(text))
                        else:
                            resp = await http.get(r.url)
                            resp.raise_for_status()
                            ctype = resp.headers.get("content-type", "")
                            if "html" not in ctype and "text" not in ctype:
                                raise ValueError(f"unsupported content-type {ctype}")
                            title, text = extract_main_text(resp.text)
                            doc = Document(url=r.url, title=title or r.title, text=text,
                                           provider=r.provider, fetch_ok=len(text) >= MIN_CHARS)
                        if not doc.fetch_ok:
                            doc.text = r.snippet or doc.text
                            doc.error = "thin content; snippet used"
                        _cache.set(r.url, doc)
                        await self.log(f"{'✓' if doc.fetch_ok else '△'} {r.title[:60]} ({len(doc.text)} chars)",
                                       {"url": r.url, "ok": doc.fetch_ok, "chars": len(doc.text)})
                        return doc
                    except Exception as exc:  # noqa: BLE001
                        await self.log(f"✗ {r.url} → {exc}; using snippet fallback", {"url": r.url, "error": str(exc)})
                        return Document(url=r.url, title=r.title, text=r.snippet or "",
                                        provider=r.provider, fetch_ok=False, error=str(exc))

            docs = await asyncio.gather(*(fetch(r) for r in targets))

        ok = sum(1 for d in docs if d.fetch_ok)
        await self.done(f"{ok}/{len(docs)} pages successfully read",
                        {"read": ok, "total": len(docs),
                         "docs": [{"url": d.url, "title": d.title, "chars": len(d.text), "ok": d.fetch_ok} for d in docs]})
        return docs
