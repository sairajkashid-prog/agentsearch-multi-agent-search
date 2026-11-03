"""API tests with mocked network calls (fast and deterministic)."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import Document, SearchResult


@pytest.fixture()
def client(monkeypatch, tmp_path):
    # Use a temporary database so real history is not affected.
    import backend.storage as storage
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")

    # Mock Search + Reader so unit tests do not use the real network.
    async def fake_search(self, plan, depth="standard", exclude_urls=None):
        return [
            SearchResult(title="Python (programming language)", url="https://en.wikipedia.org/wiki/Python_(programming_language)",
                         snippet="Python is a high-level programming language.", provider="wikipedia"),
            SearchResult(title="Welcome to Python.org", url="https://www.python.org/",
                         snippet="The official home of the Python Programming Language.", provider="duckduckgo"),
        ]

    async def fake_reader(self, results, depth="standard"):
        return [
            Document(url=results[0].url, title=results[0].title,
                     text=("Python is a high-level, general-purpose programming language. "
                           "Its design philosophy emphasizes code readability with the use of significant indentation. "
                           "Python is dynamically typed and garbage-collected. "
                           "It supports multiple programming paradigms including structured, object-oriented and functional programming."),
                     provider="wikipedia", fetch_ok=True),
        ]

    from backend.agents.search import SearchAgent
    from backend.agents.reader import ReaderAgent
    monkeypatch.setattr(SearchAgent, "run", fake_search)
    monkeypatch.setattr(ReaderAgent, "run", fake_reader)

    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_search_json(client):
    r = client.post("/api/search", json={"query": "What is Python?", "depth": "quick"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer"]["markdown"]
    assert data["sources"]
    assert data["stats"]["mode"] in {"free-no-key", "tavily+free-fallback"}


def test_search_sse(client):
    with client.stream("GET", "/api/search?q=What%20is%20Python%3F&depth=quick") as r:
        assert r.status_code == 200
        types = []
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                types.append(ev["type"])
                if ev["type"] == "done":
                    break
        assert "agent_start" in types
        assert "result" in types
        assert types[-1] == "done"


def test_history(client):
    client.post("/api/search", json={"query": "What is Python?", "depth": "quick"})
    r = client.get("/api/history")
    assert r.status_code == 200
    runs = r.json()["runs"]
    assert len(runs) >= 1
    rid = runs[0]["id"]
    r2 = client.get(f"/api/history/{rid}")
    assert r2.status_code == 200
    assert r2.json()["result"]["query"] == "What is Python?"
    r3 = client.delete("/api/history")
    assert r3.json()["status"] == "cleared"


def test_validation(client):
    r = client.post("/api/search", json={"query": "x", "depth": "quick"})
    assert r.status_code == 422
    r = client.post("/api/search", json={"query": "valid query", "depth": "invalid"})
    assert r.status_code == 422
