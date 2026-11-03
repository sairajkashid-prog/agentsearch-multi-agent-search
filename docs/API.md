# API Reference

Base URL: `http://localhost:8000`

## GET /api/health

Returns server status and active providers.

Example response:

```json
{
  "status": "ok",
  "version": "1.1.0",
  "mode": "free-no-key",
  "tavily_enabled": false,
  "providers": ["duckduckgo", "wikipedia", "bing-rss"]
}
```

## GET /api/search (SSE)

Streams live agent activity and the final result.

Query parameters:

- `q`: required, 2–300 characters
- `depth`: `quick`, `standard`, or `deep`; default is `standard`

Example:

```bash
curl -N "http://localhost:8000/api/search?q=What%20is%20quantum%20computing%3F&depth=quick"
```

Each SSE message is formatted as:

```text
data: {JSON event}

```

Event envelope:

```json
{
  "type": "agent_done",
  "agent": "ranker",
  "message": "14 best passages selected, 7 sources",
  "data": {},
  "ts": 1730000000.0
}
```

The final `result` event contains the full pipeline result:

```json
{
  "query": "What is quantum computing?",
  "plan": {
    "intent": "definition",
    "language": "en",
    "keywords": ["quantum", "computing"],
    "subqueries": ["What is quantum computing?"],
    "entities": ["quantum computing"]
  },
  "sources": [
    {
      "id": 1,
      "title": "Quantum computing",
      "url": "https://en.wikipedia.org/wiki/Quantum_computing",
      "domain": "en.wikipedia.org",
      "provider": "wikipedia",
      "snippet": "...",
      "credibility": 0.92
    }
  ],
  "answer": {
    "markdown": "Quantum computing is ... [1]",
    "cited_source_ids": [1, 2],
    "confidence": 0.86,
    "follow_ups": ["quantum computing real-world examples"],
    "warnings": ["Free mode: the answer is extractive (source sentences), not LLM-generated."]
  },
  "critique": {
    "coverage": 0.8,
    "source_diversity": 0.67,
    "confidence": 0.86,
    "warnings": [],
    "needs_retry": false,
    "retry_query": null
  },
  "stats": {
    "run_id": "abc123",
    "elapsed_seconds": 2.1,
    "depth": "quick",
    "rounds": 1,
    "sources": 7,
    "providers": ["wikipedia", "duckduckgo"],
    "mode": "free-no-key"
  }
}
```

## POST /api/search

Non-streaming JSON endpoint.

Request:

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"Python vs JavaScript","depth":"standard"}'
```

Response: the same pipeline result JSON shown above.

## GET /api/history?limit=30

Returns recent searches.

```json
{
  "runs": [
    {
      "id": "abc123",
      "query": "What is quantum computing?",
      "depth": "standard",
      "created_at": 1730000000.0,
      "confidence": 0.86
    }
  ]
}
```

## GET /api/history/{run_id}

Returns a full run snapshot:

```json
{
  "id": "abc123",
  "query": "What is quantum computing?",
  "depth": "standard",
  "created_at": 1730000000.0,
  "confidence": 0.86,
  "result": {},
  "events": []
}
```

## DELETE /api/history

Clears search history.

```json
{
  "status": "cleared"
}
```

## Error Format

FastAPI validation errors use the standard format:

```json
{
  "detail": [
    {
      "type": "string_pattern_mismatch",
      "loc": ["query", "depth"],
      "msg": "String should match pattern '^(quick|standard|deep)$'"
    }
  ]
}
```
