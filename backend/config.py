"""Central configuration. All values are optional; sensible free-mode defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "").strip()
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = _int("PORT", 8000)
    max_search_results: int = _int("MAX_SEARCH_RESULTS", 10)
    max_pages_to_read: int = _int("MAX_PAGES_TO_READ", 6)
    request_timeout: int = _int("REQUEST_TIMEOUT", 10)
    cache_ttl_seconds: int = _int("CACHE_TTL_SECONDS", 900)
    enable_critic_retry: bool = _bool("ENABLE_CRITIC_RETRY", True)
    max_retry: int = _int("MAX_RETRY", 1)

    @property
    def tavily_enabled(self) -> bool:
        return bool(self.tavily_api_key)


settings = Settings()
