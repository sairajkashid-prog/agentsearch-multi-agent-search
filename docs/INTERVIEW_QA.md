# Interview / Viva Questions and Answers

**Q1. What is a multi-agent system?**
A multi-agent system divides a problem across multiple specialized agents that coordinate to complete a task. Here, Planner, Search, Reader, Ranker, Writer, and Critic each handle a distinct responsibility.

**Q2. Why use multiple agents instead of one LLM call?**
Benefits include transparency, modularity, cost control, reliability through fallback/retry, and grounded citations. Each step can be inspected, replaced, or upgraded independently.

**Q3. What is BM25?**
BM25 is a ranking function based on term frequency, inverse document frequency, and document length normalization. A common formula is:

```text
idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
```

**Q4. Why use MMR?**
Maximal Marginal Relevance balances relevance and diversity. It reduces repetitive sentences in the final answer.

**Q5. What is the difference between extractive and abstractive summarization?**
Extractive summarization selects sentences from sources. Abstractive summarization generates new wording, usually with an LLM. Free mode uses extractive summarization to reduce hallucination.

**Q6. Why SSE instead of WebSocket?**
SSE is simple one-way server-to-client streaming over HTTP. It is sufficient for live agent events and has built-in browser support through `EventSource`.

**Q7. How does provider fallback work?**
If the primary provider fails or returns no results, the SearchAgent tries Wikipedia and then Bing RSS. Rate-limit responses trigger exponential backoff and respect `Retry-After` when available.

**Q8. How is Critic confidence calculated?**
It is a weighted sum of coverage, source diversity, average credibility, evidence strength, and citation integrity.

**Q9. How do you reduce hallucination?**
The free-mode answer is built from source sentences, every selected sentence is cited, and the Critic checks citation integrity. No generative LLM is used in free mode.

**Q10. Why is the project English-first?**
The interface, documentation, default search behavior, and NLP utilities are designed for English. This keeps the UX and ranking logic consistent.

**Q11. Why use a cache?**
A TTL cache reduces repeated network calls, improves latency, and helps avoid rate limits.

**Q12. Why SQLite instead of PostgreSQL?**
SQLite is lightweight and zero-config for a single-node demo/history store. A production system could migrate to PostgreSQL and Redis.

**Q13. What security measures are included?**
Input validation, http/https-only URLs, tracking-parameter stripping, HTML escaping in the frontend, and controlled provider retry behavior.

**Q14. How would you add a new provider?**
Subclass `SearchProvider`, implement `async search(query, limit)`, and register it in the SearchAgent fallback chain.

**Q15. How would you add an LLM?**
Replace or augment `SynthesizerAgent` with an LLM call. Provide ranked passages and source IDs in the prompt, and preserve citations in the output.

**Q16. Why mock network calls in tests?**
Mocking makes tests deterministic, fast, and suitable for offline CI.

**Q17. How do you deploy with Docker?**
Run:

```bash
docker compose up --build
```

The app is exposed on port 8000, and SQLite data is persisted in a Docker volume.

**Q18. What are the rate-limit ethics?**
Use public endpoints responsibly, apply backoff, cache results, limit fetched pages, and use a descriptive User-Agent for Wikipedia. For heavy production use, prefer an official search API.
