"""Optional Tavily provider (used only when TAVILY_API_KEY is set).

Tavily returns LLM-ready clean results. Free tier available at tavily.com.
Docs: https://docs.tavily.com/documentation/api-reference/endpoint/search
"""
from __future__ import annotations

from ..config import settings
from ..models import SearchResult
from .base import ProviderError, SearchProvider, clean_snippet, client, request_with_retry


class TavilyProvider(SearchProvider):
    name = "tavily"
    requires_key = True

    def available(self) -> bool:
        return settings.tavily_enabled

    async def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        if not self.available():
            raise ProviderError("TAVILY_API_KEY not configured")
        payload = {
            "query": query,
            "max_results": limit,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        try:
            async with client(timeout=15) as http:
                resp = await request_with_retry(
                    http, "POST", "https://api.tavily.com/search",
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
                    retries=1,
                )
                if resp.status_code == 401:
                    raise ProviderError("Tavily: invalid API key (401)")
                resp.raise_for_status()
                data = resp.json()
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"Tavily request failed: {exc}") from exc

        out: list[SearchResult] = []
        for item in data.get("results", []):
            url = item.get("url", "")
            if not url:
                continue
            out.append(SearchResult(
                title=item.get("title") or url,
                url=url,
                snippet=clean_snippet(item.get("content", ""), 500),
                provider=self.name,
                score=float(item.get("score", 0.0) or 0.0),
            ))
        return out
