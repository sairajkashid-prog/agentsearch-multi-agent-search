"""Provider parsing + fallback tests (offline, synthetic HTML/XML)."""
import pytest

from backend.agents.search import canonical_url
from backend.providers.base import clean_snippet
from backend.providers.duckduckgo import DuckDuckGoProvider

DDG_LITE_HTML = """
<table>
<tr><td>1.</td><td><a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.python.org%2F">Python.org</a></td></tr>
<tr><td></td><td class="result-snippet">Official Python website.</td></tr>
<tr><td>2.</td><td><a class="result-link" href="https://docs.python.org/3/">Python Docs</a></td></tr>
<tr><td></td><td class="result-snippet">Documentation.</td></tr>
</table>
"""

DDG_HTML = """
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FPython">Python - Wikipedia</a>
  <a class="result__snippet">Python is a programming language.</a>
</div>
"""


def test_ddg_lite_parse():
    results = DuckDuckGoProvider()._parse(DDG_LITE_HTML, 5)
    assert len(results) == 2
    assert results[0].url == "https://www.python.org/"
    assert results[0].title == "Python.org"
    assert "Official" in results[0].snippet


def test_ddg_html_parse():
    results = DuckDuckGoProvider()._parse(DDG_HTML, 5)
    assert len(results) == 1
    assert results[0].url == "https://en.wikipedia.org/wiki/Python"
    assert results[0].provider == "duckduckgo"


def test_canonical_url_strips_tracking():
    u = "https://www.example.com/path/?utm_source=x&id=5&fbclid=y#frag"
    assert canonical_url(u) == "https://example.com/path?id=5"


def test_canonical_url_rejects_non_http():
    assert canonical_url("ftp://example.com/file") == ""
    assert canonical_url("javascript:alert(1)") == ""


def test_clean_snippet():
    assert clean_snippet("<b>Hello</b>   world", 100) == "Hello world"
    long = "word " * 100
    assert len(clean_snippet(long, 50)) <= 51


@pytest.mark.asyncio
async def test_search_fallback_chain(monkeypatch):
    """Primary fail -> Wikipedia fail -> Bing success."""
    from backend.agents.search import SearchAgent
    from backend.models import Plan, SearchResult
    from backend.providers import ProviderError

    agent = SearchAgent()

    async def fail_primary(query, limit=8):
        raise ProviderError("blocked")

    async def fail_wiki(query, limit=5):
        raise ProviderError("429")

    async def ok_bing(query, limit=8):
        return [SearchResult(title="Bing Result", url="https://example.com/a",
                             snippet="ok", provider="bing-rss")]

    monkeypatch.setattr(agent.ddg, "search", fail_primary)
    monkeypatch.setattr(agent.tavily, "available", lambda: False)
    monkeypatch.setattr("backend.agents.search.WikipediaProvider.search", fail_wiki)
    monkeypatch.setattr(agent.bing, "search", ok_bing)

    plan = Plan(query="test query", intent="general", language="en",
                keywords=["test"], subqueries=["test query"], entities=["test"])
    results = await agent.run(plan, "quick")
    assert len(results) == 1
    assert results[0].provider == "bing-rss"
