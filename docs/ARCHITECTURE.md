# Architecture Deep Dive

## 1. Design Goals

1. **Zero-cost default**: no mandatory API key.
2. **Transparency**: every agent emits live events through SSE.
3. **Grounded answers**: answer sentences are cited and extractive.
4. **Modularity**: providers and agents can be added or replaced easily.
5. **Reliability**: provider failures trigger fallback and retry behavior.
6. **English-first UX**: interface, docs, and default search behavior are English.

## 2. Pipeline Flow

```text
User query
   |
   v
PlannerAgent ---- intent, language, keywords, entities, subqueries
   |
   v
SearchAgent ----- parallel provider calls: Tavily* -> DDG -> Wikipedia -> Bing RSS
   |              canonical URL dedup, TTL cache, credibility pre-score
   v
ReaderAgent ----- top-N page fetch, boilerplate removal, Wikipedia extracts
   |              snippet fallback when fetching fails
   v
RankerAgent ----- paragraph chunking -> BM25 -> credibility boost -> diversity filter
   |              output: ranked passages + numbered sources
   v
SynthesizerAgent - sentence scoring -> MMR selection -> definition lead -> markdown + citations
   |
   v
CriticAgent ----- coverage, source diversity, citation integrity, confidence
   |
   +-- confidence OK -> finalize
   +-- confidence low -> Planner.refine() -> SearchAgent round 2
```

## 3. Key Algorithms

### BM25

The Ranker uses Okapi BM25 with `k1=1.5` and `b=0.75`.

Query tokens are built from the original query, extracted keywords, and subqueries.

Passage score:

```text
BM25 * (0.7 + 0.6 * credibility)
+ overlap * 2
+ title_boost
+ length_bonus
- list_penalty
```

### MMR

The Writer uses Maximal Marginal Relevance to balance relevance and diversity:

```text
score = lambda * relevance - (1 - lambda) * max_similarity_to_selected
```

`lambda = 0.72`.

This reduces repetitive sentences in the final answer.

### Extractive Synthesis

Free mode does not call an LLM. Instead, it:

1. Extracts candidate sentences from ranked passages.
2. Scores them using BM25, query overlap, position, definition/step bonuses, and penalties.
3. Selects a diverse set using MMR.
4. Chooses a strong lead sentence for definition/fact queries.
5. Renders markdown with `[source_id]` citations.

### Critic Confidence

```text
confidence = 0.34 * coverage
           + 0.20 * diversity
           + 0.22 * average_credibility
           + 0.14 * evidence_strength
           + 0.10 * citation_integrity
```

If confidence is below `0.5`, the Critic can recommend a retry. Quick mode disables retry.

## 4. Provider Strategy

| Provider | Key required? | Role | Notes |
|---|---|---|---|
| Tavily | Optional | Primary if key is configured | Clean search results, free tier available |
| DuckDuckGo | No | Primary free provider | Lite and HTML endpoints parsed with BeautifulSoup |
| Wikipedia | No | Fallback and supplement | MediaWiki API, English Wikipedia by default |
| Bing RSS | No | Last-resort fallback | Public RSS XML endpoint |

Retry/backoff handles `429`, `202`, and `503` responses and respects `Retry-After` when present.

Cache: in-memory TTL cache, default 15 minutes, for search results and fetched pages.

## 5. Event Bus and SSE

Each agent calls `EventBus.emit()`. FastAPI streams these events as `text/event-stream`.

The frontend uses `EventSource` and updates the active assistant message:

- Agent step status: pending, running, done, error.
- Live log lines.
- Final answer, sources, confidence, and follow-up chips.

Event types:

```text
pipeline_start, agent_start, agent_log, agent_done, agent_error,
retry, plan_refined, result, done, error
```

## 6. Storage

SQLite database: `data/agentsearch.db`.

Each run stores:

- Query
- Depth
- Timestamp
- Confidence
- Full result JSON
- Full event history JSON

The sidebar can reload a previous run and replay its result.

Async access uses `asyncio.to_thread`.

## 7. Frontend Design

The frontend is a ChatGPT-style single-page app:

- Sidebar: new chat, history, theme toggle, API docs, clear history.
- Top bar: product name and depth selector.
- Chat area: welcome screen, user bubbles, assistant answers.
- Assistant answer: collapsible agent activity panel, markdown answer, sources, notes, follow-ups.
- Composer: auto-growing textarea, send button, stop button.
- Theme: dark/light, persisted in localStorage.

No frontend build step is required.

## 8. Security and Ethics

- Only `http` and `https` URLs are accepted.
- Tracking parameters are stripped and URLs are canonicalized.
- Query length and depth values are validated.
- Frontend escapes HTML before rendering markdown.
- Public endpoints are used with retry/backoff and a descriptive Wikipedia User-Agent.
- History is stored locally in SQLite.
- Citations are mandatory in free mode.

## 9. Extension Points

- **New provider**: subclass `SearchProvider`, implement `async search()`, and add it to the SearchAgent fallback chain.
- **New agent**: subclass `BaseAgent`, add a pipeline step in the orchestrator, and emit events.
- **LLM upgrade**: replace or augment `SynthesizerAgent` with an LLM call while preserving source IDs and citations.
- **Semantic ranking**: add embedding cosine similarity alongside or instead of BM25.
- **Production cache**: replace the in-memory TTL cache with Redis.
