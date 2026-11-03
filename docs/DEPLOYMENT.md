# Deployment Guide

This project runs in two modes:

| Mode | Where | Streaming | History |
|---|---|---|---|
| **Local / Docker** | Your machine, any VPS | ✅ Live SSE agent activity | ✅ Persistent SQLite |
| **Vercel (serverless)** | https://agentsearch-red.vercel.app | ✅ SSE verified working (JSON fallback if a host buffers it) | ⚠️ Ephemeral (`/tmp`) |

---

## 1. Local (recommended for the full experience)

Double-click `START_HERE.bat` (Windows), `START_HERE.command` (macOS), or run
`./start.sh` (Linux). See `START_HERE.txt`.

Or manually:

```bash
pip install -r requirements.txt
python run.py
```

Open http://localhost:8000.

## 2. Docker

```bash
docker compose up --build
```

Open http://localhost:8000. History persists in the `agentsearch-data` volume.

---

## 3. Vercel (serverless)

### Files that make it work

| File | Purpose |
|---|---|
| `api/index.py` | Serverless ASGI entrypoint. Exposes `app`, adds the project root to `sys.path`, and restores the original `/api/...` path after Vercel's rewrite. |
| `api/requirements.txt` | Slim runtime deps — no `uvicorn`/`uvloop` (Vercel supplies the server) and no test tooling. |
| `vercel.json` | Build command, output directory, 60 s function timeout, and the `/api/*` rewrite. |
| `scripts/vercel_build.sh` | Copies `frontend/` into `public/` so the chat UI is served from Vercel's CDN. |

### How routing works

```
Browser ──► /                      → public/index.html   (CDN, static)
        ──► /static/styles.css     → public/static/...   (CDN, static)
        ──► /api/search            → api/index.py        (Python function)
        ──► /api/health            → api/index.py
        ──► /api/history           → api/index.py
```

### Verified deployment

The live deployment was tested end-to-end after release:

| Check | Result |
|---|---|
| `GET /` | 200 — chat UI served from CDN |
| `GET /static/styles.css`, `/static/app.js` | 200 |
| `GET /api/health` | 200 — `free-no-key`, 3 providers |
| `GET /api/search` (SSE) | 200 — all 6 agents streamed, result in ~1.9 s |
| `POST /api/search` (JSON) | 200 — confidence 0.92, 6 sources, ~1.4 s |
| `GET /api/history` | 200 — runs persisted within the warm instance |

> **Note on URLs:** Vercel's team-scoped alias
> (`agentsearch-sairaj-kashid.vercel.app`) is behind Vercel Authentication by
> default. The public production URL is **https://agentsearch-red.vercel.app** —
> use that one when sharing.

### Deploy from the dashboard

1. Push this repo to GitHub.
2. Vercel → **Add New → Project** → import the repo.
3. Framework preset: **Other**. Build command and output directory are already
   defined in `vercel.json` — leave them as detected.
4. (Optional) Add environment variable `TAVILY_API_KEY` for better search results.
5. **Deploy**.

### Deploy from the CLI

```bash
npm i -g vercel
vercel login
vercel --prod
```

### Serverless behaviour and limits

- **Database**: the project directory is read-only on Vercel, so
  `api/index.py` sets `AGENTSEARCH_DB_PATH=/tmp/agentsearch.db`. `/tmp` is
  per-instance and cleared on cold starts, so **history is not durable**.
  `backend/storage.py` probes for a writable location and every history call
  degrades gracefully — search never fails because history is unavailable.
- **Streaming**: `frontend/app.js` opens an `EventSource` first. If the host
  buffers or blocks SSE and no event arrives, it automatically retries the same
  query via `POST /api/search` and renders the finished answer. The UI therefore
  works either way; you may just lose the live per-agent animation.
- **Timeout**: `maxDuration` is 60 s. Use **Quick** or **Standard** depth on
  Vercel; **Deep** reads more pages and can approach the limit.
- **Cold starts**: the first request after idle is slower.
- **Outbound requests**: search providers may rate-limit datacenter IPs more
  aggressively than residential ones. The provider chain
  (Tavily → DuckDuckGo → Wikipedia → Bing RSS) plus retries handles this, but a
  free `TAVILY_API_KEY` makes cloud results noticeably more reliable.

### For durable history in the cloud

SQLite on `/tmp` is intentionally simple. To persist history properly, swap
`backend/storage.py` for a hosted database — Vercel Postgres, Supabase, or
Turso (SQLite-compatible, smallest change). The storage module exposes only
`init_db`, `save_run`, `list_runs`, `get_run`, and `clear_runs`, so replacing it
does not touch the agents or the API layer.

### Environment variables

| Variable | Default | Notes |
|---|---|---|
| `TAVILY_API_KEY` | empty | Optional. Enables Tavily as the primary provider. |
| `AGENTSEARCH_DB_PATH` | auto-detected | Set to `/tmp/...` automatically on Vercel. |
| `MAX_SEARCH_RESULTS` | `10` | Results per subquery. |
| `MAX_PAGES_TO_READ` | `6` | Pages the Reader fetches. |
| `REQUEST_TIMEOUT` | `10` | Per-request timeout (seconds). |
| `CACHE_TTL_SECONDS` | `900` | In-memory provider cache TTL. |
| `ENABLE_CRITIC_RETRY` | `true` | Allow the Critic to trigger a refined retry. |
| `MAX_RETRY` | `1` | Maximum refinement rounds. |

Never commit a real `.env`. Use the platform's environment-variable settings.
