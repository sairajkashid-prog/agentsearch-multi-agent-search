# Project Report: AgentSearch — Multi-Agent Search Engine

## 1. Abstract

AgentSearch is an open-source, English-language, multi-agent search engine. It distributes a user query across six specialized agents and produces a grounded, cited answer. The system runs in 100% free mode by default and supports an optional Tavily API key for premium search. Answers are generated using extractive summarization, which keeps hallucination near zero. The backend uses FastAPI and Server-Sent Events, while the frontend provides a ChatGPT-style chat interface.

## 2. Problem Statement

Traditional search engines return links, requiring users to read and synthesize information themselves. LLM-based answer engines are powerful but often require paid API keys, carry hallucination risk, and provide opaque reasoning. A transparent, free, multi-agent system is needed that can:

- Plan a search strategy.
- Retrieve evidence from multiple sources.
- Rank the evidence.
- Write a cited answer.
- Audit its own quality.

## 3. Objectives

1. Provide a working search engine without mandatory API keys.
2. Use a multi-agent pipeline with clear separation of concerns.
3. Show live transparency through agent status and logs.
4. Produce source-cited answers.
5. Support a self-reflection/retry loop for low-confidence answers.
6. Provide an English, ChatGPT-style user interface.
7. Keep the codebase testable, dockerizable, and extensible.

## 4. Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| HTTP | httpx, BeautifulSoup4 |
| Search | DuckDuckGo, Wikipedia MediaWiki API, Bing RSS, optional Tavily |
| NLP/IR | Custom tokenizer, BM25, MMR, regex intent detection |
| Streaming | Server-Sent Events |
| Storage | SQLite |
| Frontend | HTML, CSS, vanilla JavaScript |
| Testing | pytest, pytest-asyncio, FastAPI TestClient |
| Deployment | Docker, docker-compose |

## 5. System Architecture

Pipeline:

```text
Planner -> Search -> Reader -> Ranker -> Synthesizer -> Critic
```

If the Critic reports low confidence, the Planner refines the query and the system runs another round. The EventBus converts agent activity into SSE events. SQLite stores each run and its event history.

## 6. Module Description

### 6.1 PlannerAgent

Detects intent, extracts keywords and entities, and generates subqueries. Supported intents include definition, comparison, how-to, news, list, fact, and general.

### 6.2 SearchAgent

Provider chain:

```text
Tavily (if configured) -> DuckDuckGo -> Wikipedia -> Bing RSS
```

Features:

- Parallel subquery search
- Canonical URL deduplication
- TTL cache
- Retry/backoff for rate limits
- Credibility pre-scoring
- Encyclopedia boost for definition/fact queries

### 6.3 ReaderAgent

Fetches top pages asynchronously, removes HTML boilerplate, and extracts readable text. Wikipedia pages use MediaWiki plaintext extracts. If a page fails, the search snippet is used as fallback.

### 6.4 RankerAgent

Splits documents into passages, scores them with BM25, applies credibility and title boosts, removes near-duplicates, and limits per-domain dominance.

### 6.5 SynthesizerAgent

Selects candidate sentences, scores them, applies MMR for diversity, chooses a strong lead sentence, and renders a cited markdown answer.

### 6.6 CriticAgent

Computes coverage, source diversity, citation integrity, average credibility, evidence strength, and confidence. Low confidence can trigger a retry.

### 6.7 Orchestrator

Sequences the pipeline, manages retry rounds, collects statistics, persists results, and emits final events.

### 6.8 API and Frontend

The API provides REST and SSE endpoints. The frontend provides a ChatGPT-style interface with sidebar history, chat messages, collapsible agent activity, cited answers, sources, and follow-up suggestions.

## 7. Testing

The automated test suite covers:

- Core text processing and BM25 ranking
- Planner intents and subquery generation
- Ranker, Writer, and Critic integration
- Provider parsing and fallback logic
- API health, JSON search, SSE streaming, history, and validation

Network calls are mocked for deterministic tests.

## 8. Results

Example live behavior in free mode:

- Query: `What is quantum computing?`
- Result: cited extractive answer with multiple sources.
- Typical latency: a few seconds depending on provider response time.
- Fallback behavior: when DuckDuckGo is rate-limited, Wikipedia or Bing RSS can take over.

## 9. Limitations

- Extractive answers are less fluent than LLM-generated answers.
- Public search endpoints may rate-limit requests.
- Lexical BM25 ranking has limited semantic understanding.
- News freshness filtering is basic.
- Free mode is intended for demos, learning, and lightweight use.

## 10. Future Scope

- Optional LLM integration for abstractive answers.
- Embedding-based semantic re-ranking.
- Redis cache and distributed workers.
- PDF/URL upload and local RAG.
- User accounts and saved collections.
- Browser extension.
- Cloud deployment templates.

## 11. Conclusion

AgentSearch demonstrates that multi-agent orchestration, classic information retrieval, and transparent streaming can produce a useful, free, cited search engine. Its modular design makes future LLM and semantic upgrades straightforward.
