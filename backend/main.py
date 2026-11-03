"""FastAPI app: REST + SSE streaming + static frontend."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import ROOT_DIR, settings
from .core.events import EventBus
from .orchestrator import run_pipeline
from .storage import clear_runs, get_run, init_db, list_runs

FRONTEND_DIR = ROOT_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="AgentSearch - Multi-Agent Search Engine",
    description="Six agents, free no-key mode, live SSE activity, cited answers.",
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=300)
    depth: str = Field("standard", pattern="^(quick|standard|deep)$")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": __version__,
        "mode": "tavily+free-fallback" if settings.tavily_enabled else "free-no-key",
        "tavily_enabled": settings.tavily_enabled,
        "providers": (["tavily"] if settings.tavily_enabled else []) + ["duckduckgo", "wikipedia", "bing-rss"],
    }


@app.get("/api/search")
async def search_sse(request: Request, q: str = Query(..., min_length=2, max_length=300),
                     depth: str = Query("standard", pattern="^(quick|standard|deep)$")) -> StreamingResponse:
    """Server-Sent Events stream of live agent activity + final result."""
    bus = EventBus()

    async def event_gen() -> AsyncIterator[str]:
        task = asyncio.create_task(run_pipeline(q.strip(), depth, bus))
        try:
            async for event in bus.stream():
                if await request.is_disconnected():
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


@app.post("/api/search")
async def search_json(body: SearchRequest) -> JSONResponse:
    """Non-streaming endpoint: returns the full result as JSON (for tests/API clients)."""
    result = await run_pipeline(body.query.strip(), body.depth)
    return JSONResponse(result.to_dict())


@app.get("/api/history")
async def history(limit: int = Query(30, ge=1, le=100)) -> dict[str, Any]:
    return {"runs": await list_runs(limit)}


@app.get("/api/history/{run_id}")
async def history_item(run_id: str) -> dict[str, Any]:
    run = await get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@app.delete("/api/history")
async def history_clear() -> dict[str, str]:
    await clear_runs()
    return {"status": "cleared"}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


# Static assets (CSS/JS). Mounted last so /api/* routes match first.
# On serverless hosts the frontend is served by the CDN instead, so the
# directory may not be bundled with the function — only mount when present.
if FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
