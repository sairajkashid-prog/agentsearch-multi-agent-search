"""SearchAgent: parallel search across multiple providers with automatic fallback."""
from __future__ import annotations

import asyncio
import copy
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..config import settings
from ..core.cache import TTLCache
from ..core.ranking import credibility
from ..core.text import content_tokens
from ..models import Plan, SearchResult
from ..providers import BingRSSProvider, DuckDuckGoProvider, ProviderError, TavilyProvider, WikipediaProvider
from .base import BaseAgent

_cache = TTLCache(ttl=settings.cache_ttl_seconds, maxsize=512)
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                   "utm_content", "gclid", "fbclid", "ref", "source"}


def canonical_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
        if p.scheme not in {"http", "https"}:
            return ""
        host = p.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        query = urlencode([(k, v) for k, v in parse_qsl(p.query) if k.lower() not in TRACKING_PARAMS])
        path = p.path.rstrip("/") or "/"
        return urlunparse((p.scheme, host, path, p.params, query, ""))
    except Exception:
        return ""


class SearchAgent(BaseAgent):
    name = "search"
    role = "Web Searcher"
    emoji = "🔎"

    def __init__(self, emit=None):
        super().__init__(emit)
        self.tavily = TavilyProvider()
        self.ddg = DuckDuckGoProvider()
        self.bing = BingRSSProvider()

    async def run(self, plan: Plan, depth: str = "standard",
                  exclude_urls: set[str] | None = None) -> list[SearchResult]:
        await self.start("Searching the web for sources…")
        exclude_urls = exclude_urls or set()
        limit = {"quick": 6, "standard": settings.max_search_results,
                 "deep": settings.max_search_results + 4}.get(depth, settings.max_search_results)
        per_query = max(3, limit // max(1, len(plan.subqueries)))
        wiki = WikipediaProvider(lang="en")

        primary = self.tavily if self.tavily.available() else self.ddg
        await self.log(f"Primary provider: {primary.name}" +
                       (" (API key configured)" if primary.name == "tavily" else " (free, no key)"),
                       {"provider": primary.name})

        sem = asyncio.Semaphore(3)

        async def fetch_one(subquery: str) -> list[SearchResult]:
            async with sem:
                cache_key = f"{primary.name}:{subquery}:{per_query}"
                cached = _cache.get(cache_key)
                if cached is not None:
                    await self.log(f"Cache hit: “{subquery}”", {"subquery": subquery, "cache": True})
                    return copy.deepcopy(cached)
                try:
                    results = await primary.search(subquery, per_query)
                    if results:
                        _cache.set(cache_key, copy.deepcopy(results))
                        await self.log(f"{primary.name}: “{subquery}” → {len(results)} results",
                                       {"subquery": subquery, "provider": primary.name, "count": len(results)})
                        return results
                    raise ProviderError("0 results")
                except Exception as exc:  # noqa: BLE001
                    await self.log(f"{primary.name} failed for “{subquery}”: {exc}. Trying fallbacks…",
                                   {"subquery": subquery, "error": str(exc)})
                    for fallback in (wiki, self.bing):
                        try:
                            results = await fallback.search(subquery, max(3, per_query - 1))
                            if results:
                                _cache.set(cache_key, copy.deepcopy(results))
                                await self.log(f"{fallback.name}: “{subquery}” → {len(results)} results",
                                               {"subquery": subquery, "provider": fallback.name, "count": len(results)})
                                return results
                        except Exception as exc2:  # noqa: BLE001
                            await self.log(f"{fallback.name} fallback failed: {exc2}", {"error": str(exc2)})
                    await self.fail(f"All providers failed for “{subquery}”")
                    return []

        batches = await asyncio.gather(*(fetch_one(sq) for sq in plan.subqueries))
        merged: list[SearchResult] = []
        seen: set[str] = set(exclude_urls)
        for batch in batches:
            for r in batch:
                curl = canonical_url(r.url)
                if not curl or curl in seen:
                    continue
                seen.add(curl)
                r.url = curl
                merged.append(r)

        # Add Wikipedia as a supplement for encyclopedic queries.
        if plan.intent in {"definition", "fact", "general", "list"} and primary.name != "wikipedia":
            try:
                extra = await wiki.search(plan.query, 3)
                for r in extra:
                    curl = canonical_url(r.url)
                    if curl and curl not in seen:
                        seen.add(curl)
                        r.url = curl
                        merged.append(r)
                if extra:
                    await self.log(f"Wikipedia supplement: +{len(extra)} encyclopedia sources")
            except Exception:
                pass

        q_tokens = set(content_tokens(plan.query + " " + " ".join(plan.keywords)))
        for r in merged:
            overlap = len(q_tokens & set(content_tokens(r.title + " " + r.snippet)))
            encyclo_boost = 0.0
            if plan.intent in {"definition", "fact", "general", "list"} and (
                    r.provider == "wikipedia" or "wikipedia.org" in r.url or "britannica.com" in r.url):
                encyclo_boost = 1.0
            title_l = r.title.lower()
            list_penalty = 0.0
            if plan.intent in {"definition", "fact", "general"} and title_l.startswith(
                    ("list of", "timeline of", "glossary", "index of", "outline of")):
                list_penalty = 1.2
            title_overlap = len(q_tokens & set(content_tokens(r.title))) / max(1, len(q_tokens))
            r.score = round(r.score + credibility(r.url) * 0.6 + overlap * 0.15 +
                            encyclo_boost + title_overlap * 1.5 - list_penalty, 4)
        merged.sort(key=lambda r: r.score, reverse=True)
        merged = merged[:limit]

        providers = sorted({r.provider for r in merged})
        await self.done(f"{len(merged)} unique sources found ({', '.join(providers) or 'none'})",
                        {"count": len(merged), "providers": providers,
                         "results": [r.to_dict() for r in merged[:12]]})
        return merged
