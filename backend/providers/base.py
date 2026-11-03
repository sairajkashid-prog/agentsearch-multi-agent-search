"""Provider interface and shared HTTP helpers with retry/backoff."""
from __future__ import annotations

import abc
import asyncio
import random

import httpx

from ..models import SearchResult

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 AgentSearch/1.1"
)
# Descriptive User-Agent for Wikimedia policy compliance.
WIKI_USER_AGENT = "AgentSearch/1.1 (educational multi-agent search demo; +https://github.com/agentsearch) httpx"


class ProviderError(RuntimeError):
    """Raised when a provider fails (network, parse, rate-limit, etc.)."""


class SearchProvider(abc.ABC):
    name: str = "base"
    requires_key: bool = False

    @abc.abstractmethod
    async def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        ...

    def available(self) -> bool:
        return True


def client(timeout: float = 10.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
    )


def clean_snippet(text: str, max_len: int = 320) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len].rsplit(" ", 1)[0] + "…" if len(text) > max_len else text


async def request_with_retry(http: httpx.AsyncClient, method: str, url: str, *,
                             retries: int = 2, backoff: float = 1.2,
                             **kwargs) -> httpx.Response:
    """GET/POST with exponential backoff on 429/202/5xx (rate-limit friendly)."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await http.request(method, url, **kwargs)
            if resp.status_code in (429, 202, 503) and attempt < retries:
                wait = float(resp.headers.get("Retry-After", backoff * (2 ** attempt)))
                await asyncio.sleep(min(8.0, wait) + random.uniform(0, 0.4))
                continue
            return resp
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(backoff * (2 ** attempt) + random.uniform(0, 0.3))
                continue
            raise
    raise last_exc or RuntimeError("request failed")
