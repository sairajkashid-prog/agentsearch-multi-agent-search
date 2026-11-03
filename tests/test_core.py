"""Unit tests for core NLP/IR utilities."""
from backend.core.text import content_tokens, detect_language, keywords, sentences, tokenize
from backend.core.ranking import bm25_scores, credibility
from backend.core.cache import TTLCache


def test_tokenize_english():
    assert tokenize("Hello, World! Python 3.13") == ["hello", "world", "python", "3.13"]


def test_content_tokens_removes_stopwords():
    toks = content_tokens("What is the capital of India?")
    assert "what" not in toks and "the" not in toks
    assert "capital" in toks and "india" in toks


def test_keywords():
    kws = keywords("machine learning machine learning deep learning")
    assert kws[0] == "learning"  # most frequent token
    assert "machine" in kws and "deep" in kws


def test_sentences():
    ss = sentences("This is sentence one. This is sentence two! This is sentence three?")
    assert len(ss) >= 2


def test_detect_language():
    assert detect_language("What is quantum computing") == "en"
    assert detect_language("") == "en"


def test_bm25_relevance_order():
    q = content_tokens("python programming language")
    docs = [
        content_tokens("Python is a programming language."),
        content_tokens("Bananas are yellow fruits."),
        content_tokens("The python snake is large."),
    ]
    scores = bm25_scores(q, docs)
    assert scores[0] > scores[1]


def test_credibility():
    assert credibility("https://en.wikipedia.org/wiki/Python") > 0.85
    assert credibility("https://nasa.gov/artemis") > 0.9
    assert credibility("https://random-blog.example.com/post") < 0.8


def test_ttl_cache():
    c = TTLCache(ttl=60)
    c.set("k", 42)
    assert c.get("k") == 42
    assert c.get("missing") is None
    c.clear()
    assert len(c) == 0
