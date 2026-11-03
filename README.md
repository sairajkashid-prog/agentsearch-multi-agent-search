# AgentSearch — Multi-Agent Search Engine

[![CI](https://github.com/sairajkashid-prog/agentsearch-multi-agent-search/actions/workflows/ci.yml/badge.svg)](https://github.com/sairajkashid-prog/agentsearch-multi-agent-search/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![No API key](https://img.shields.io/badge/API%20key-not%20required-brightgreen)

**Live demo:** https://agentsearch-sairaj-kashid.vercel.app
**Deployment guide:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

A free, English-language, multi-agent search engine with a ChatGPT-style chat interface.

Ask a question and six agents collaborate to produce a cited answer:

**Plan → Search → Read → Rank → Write → Audit**

The project runs in 100% free mode by default. No API key is required. If you add a Tavily API key, Tavily becomes the primary search provider.

---

## Features

- **ChatGPT-style interface**: sidebar, chat thread, composer, suggestion cards, dark/light theme.
- **6 specialized agents**: Planner, Search, Reader, Ranker, Writer, Critic.
- **Live agent activity**: collapsible per-answer agent panel with step status and logs.
- **Free search providers**: DuckDuckGo, Wikipedia, and Bing RSS fallback.
- **Optional Tavily support**: set `TAVILY_API_KEY` for cleaner search results.
- **Cited answers**: answer sentences include source citations such as `[1]`.
- **Self-reflection loop**: the Critic can trigger a refined retry round.
- **Classic IR ranking**: BM25, credibility heuristics, and MMR diversity selection.
- **Search history**: SQLite-backed history with full run/event replay.
- **Docker ready**: run with one command.
- **Automated tests**: pytest unit and API tests.

---

## Quick Start (one click — recommended)

Just double-click the launcher for your operating system. It creates the virtual
environment, installs all dependencies, starts the server, and opens your browser
automatically.

| OS | Double-click this file |
|---|---|
| **Windows** | `START_HERE.bat` |
| **macOS** | `START_HERE.command` |
| **Linux** | run `./start.sh` in a terminal |

Then open **http://localhost:8000** (it opens by itself).

- Keep the launcher window open while using the app; press `Ctrl+C` there to stop it.
- Only requirement: **Python 3.10+** installed. On Windows, tick **"Add Python to PATH"** during installation.
- macOS blocked the file? Right-click → **Open**, or run `chmod +x START_HERE.command start.sh`.
- Full troubleshooting guide: **`START_HERE.txt`**.

## Manual Setup (alternative)

```bash
cd multi-agent-search

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Optional: configure Tavily
cp .env.example .env             # then edit TAVILY_API_KEY if desired

# Start the server
python run.py
```

Open:

- App: **http://localhost:8000**
- Swagger API docs: **http://localhost:8000/docs**

### Run with Docker

```bash
docker compose up --build
```

Then open **http://localhost:8000**.

### CLI demo

```bash
python scripts/demo_cli.py "What is quantum computing?"
python scripts/demo_cli.py "Python vs JavaScript" --depth quick
```

---

## Interface

The frontend is designed to feel like a modern chat assistant:

- Left sidebar with **New chat**, recent searches, theme toggle, API docs, and clear history.
- Centered chat thread with user messages and assistant answers.
- Welcome screen with example prompts.
- Bottom composer with Enter-to-send and Shift+Enter for a new line.
- Each assistant answer includes:
  - A collapsible **Agent activity** panel.
  - The cited answer.
  - Confidence and timing metadata.
  - Expandable sources.
  - Follow-up suggestion chips.

---

## Architecture

```text
User query
   |
   v
PlannerAgent ---- intent, keywords, entities, sub-queries
   |
   v
SearchAgent ----- Tavily* -> DuckDuckGo -> Wikipedia -> Bing RSS
   |              parallel search, cache, retry/backoff, deduplication
   v
ReaderAgent ----- fetch top pages, extract clean text, snippet fallback
   |
   v
RankerAgent ----- BM25 + credibility + title boost + diversity filtering
   |
   v
WriterAgent ----- extractive cited answer using MMR sentence selection
   |
   v
CriticAgent ----- coverage, diversity, citation integrity, confidence
   |
   +-- confidence OK -> finalize
   +-- confidence low -> refined retry round
```

### Agents

| Agent | Responsibility | Technique |
|---|---|---|
| Planner | Understand the query and create a search plan | Regex intent detection, keyword extraction |
| Search | Find web sources with fallback | asyncio, TTL cache, retry/backoff |
| Reader | Fetch and clean page content | httpx, BeautifulSoup, Wikipedia API |
| Ranker | Rank evidence passages | BM25, credibility, diversity |
| Writer | Build a cited answer | Extractive summarization, MMR |
| Critic | Audit quality and trigger retry | Heuristic confidence scoring |

---

## Project Structure

```text
multi-agent-search/
├── START_HERE.bat       # Windows one-click launcher
├── START_HERE.command   # macOS one-click launcher
├── start.sh             # macOS / Linux launcher
├── START_HERE.txt       # simple instructions + troubleshooting
├── backend/
│   ├── agents/          # Six agents + base class
│   ├── providers/       # DuckDuckGo, Wikipedia, Bing RSS, Tavily
│   ├── core/            # Text processing, BM25, cache, event bus
│   ├── main.py          # FastAPI app: REST + SSE + static frontend
│   ├── orchestrator.py  # Pipeline + retry loop
│   ├── models.py        # Shared dataclasses
│   ├── storage.py       # SQLite history
│   └── config.py        # Environment settings
├── frontend/            # ChatGPT-style HTML/CSS/JS interface
├── tests/               # pytest unit and API tests
├── scripts/             # CLI demo
├── docs/                # Architecture, API, report, interview Q&A
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── run.py
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Server status and active providers |
| GET | `/api/search?q=...&depth=quick\|standard\|deep` | SSE stream of live agent events and final result |
| POST | `/api/search` | JSON body `{query, depth}` returning the full result |
| GET | `/api/history?limit=30` | Recent searches |
| GET | `/api/history/{run_id}` | Full run snapshot and event history |
| DELETE | `/api/history` | Clear history |
| GET | `/docs` | Swagger UI |

### SSE event types

`pipeline_start`, `agent_start`, `agent_log`, `agent_done`, `agent_error`, `retry`, `plan_refined`, `result`, `done`, `error`

---

## Configuration

Copy `.env.example` to `.env` if you want to override defaults.

| Variable | Default | Description |
|---|---|---|
| `TAVILY_API_KEY` | empty | Optional premium search provider |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8000` | Server port |
| `MAX_SEARCH_RESULTS` | `10` | Maximum sources per search |
| `MAX_PAGES_TO_READ` | `6` | Pages fetched by the Reader agent |
| `REQUEST_TIMEOUT` | `10` | HTTP timeout in seconds |
| `CACHE_TTL_SECONDS` | `900` | Search/page cache TTL |
| `ENABLE_CRITIC_RETRY` | `true` | Enable Critic feedback retry |
| `MAX_RETRY` | `1` | Maximum extra retry rounds |

---

## Tests

```bash
pytest tests/ -v
```

The test suite covers:

- Text processing and BM25 ranking
- Planner, Ranker, Writer, and Critic behavior
- Provider parsing and fallback logic
- REST API, SSE streaming, history, and validation

Network calls are mocked in unit/API tests so they are fast and deterministic.

---

## Free Mode Limitations

- The answer is **extractive**, not LLM-generated. It selects and structures source sentences, which reduces hallucination but may sound less fluent than a large language model.
- Public search endpoints can rate-limit requests. The app retries and falls back to Wikipedia/Bing RSS when possible.
- Semantic understanding is limited because ranking is lexical BM25 rather than embedding-based.
- News freshness filtering is basic.
- For production use, an official search API such as Tavily is recommended.

---

## Future Improvements

- Optional LLM integration for abstractive answers.
- Embedding-based semantic re-ranking.
- Redis cache and distributed workers.
- User accounts and saved collections.
- PDF/URL upload and local RAG.
- Browser extension.
- Deployment templates for Render, Railway, Fly.io, or Vercel.

---

## License

MIT. See `LICENSE`.
