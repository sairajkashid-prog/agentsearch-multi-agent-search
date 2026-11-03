"""Agent unit tests (offline, using synthetic data)."""
import pytest

from backend.agents.planner import PlannerAgent
from backend.agents.ranker import RankerAgent, chunk_document
from backend.agents.synthesizer import SynthesizerAgent
from backend.agents.critic import CriticAgent
from backend.models import Document, Passage, Plan, SearchResult, Source


@pytest.mark.asyncio
async def test_planner_definition():
    p = await PlannerAgent().run("What is quantum computing?", "standard")
    assert p.intent == "definition"
    assert p.language == "en"
    assert len(p.subqueries) >= 1
    assert "quantum" in p.keywords


@pytest.mark.asyncio
async def test_planner_comparison():
    p = await PlannerAgent().run("Python vs JavaScript for beginners", "deep")
    assert p.intent == "comparison"
    assert len(p.subqueries) == 3


@pytest.mark.asyncio
async def test_planner_fact():
    p = await PlannerAgent().run("What is the capital of France?", "quick")
    assert p.language == "en"
    assert p.intent in {"definition", "fact"}


def test_chunk_document():
    text = "\n".join([f"Paragraph number {i} with enough words to be meaningful. " * 3 for i in range(6)])
    chunks = chunk_document(text)
    assert len(chunks) >= 2
    assert all(len(c) <= 950 for c in chunks)


@pytest.mark.asyncio
async def test_ranker_and_synthesizer_pipeline():
    plan = Plan(query="What is Python programming language", intent="definition",
                language="en", keywords=["python", "programming", "language"],
                subqueries=["What is Python programming language"])
    docs = [
        Document(url="https://en.wikipedia.org/wiki/Python", title="Python",
                 text=("Python is a high-level, general-purpose programming language. "
                       "Its design philosophy emphasizes code readability with the use of significant indentation. "
                       "Python is dynamically typed and garbage-collected. "
                       "It supports multiple programming paradigms, including structured, object-oriented and functional programming."),
                 provider="wikipedia", fetch_ok=True),
        Document(url="https://example.com/banana", title="Banana",
                 text="Bananas are yellow fruits that grow in tropical climates. They are rich in potassium.",
                 provider="duckduckgo", fetch_ok=True),
    ]
    results = [SearchResult(title=d.title, url=d.url, snippet=d.text[:150], provider=d.provider) for d in docs]
    passages, sources = await RankerAgent().run(plan, docs, results)
    assert passages, "Ranker should produce passages"
    assert passages[0].doc_url == "https://en.wikipedia.org/wiki/Python"
    answer = await SynthesizerAgent().run(plan, passages, sources)
    assert "[1]" in answer.markdown or "[2]" in answer.markdown
    assert answer.cited_source_ids
    critique = await CriticAgent().run(plan, answer, sources, passages, allow_retry=False)
    assert 0 < critique.confidence <= 1
    assert critique.coverage > 0.5


@pytest.mark.asyncio
async def test_synthesizer_no_evidence():
    plan = Plan(query="test", intent="general", language="en", keywords=["test"], subqueries=["test"])
    answer = await SynthesizerAgent().run(plan, [], [])
    assert answer.confidence <= 0.1
    assert answer.cited_source_ids == []
