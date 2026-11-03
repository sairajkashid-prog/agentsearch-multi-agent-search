"""Vercel serverless entrypoint for the AgentSearch FastAPI backend.

Vercel's Python runtime looks for an ASGI callable named ``app`` in this file.
The real application lives in ``backend.main``; this module only adds the
project root to ``sys.path`` and normalises the request path, because Vercel
rewrites every ``/api/*`` request onto this single function.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Serverless filesystems are read-only except /tmp.
os.environ.setdefault("AGENTSEARCH_DB_PATH", "/tmp/agentsearch.db")

from backend.main import app as _app  # noqa: E402


class _OriginalPathMiddleware:
    """Restore the original /api/... path if the platform rewrote it.

    Different Vercel routing configurations expose the pre-rewrite path in
    different headers. If none is present we keep the path untouched, which is
    the correct behaviour when the original path is already preserved.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path", "")
            if path.rstrip("/") in ("/api/index", "/api"):
                headers = dict(scope.get("headers") or [])
                for key in (b"x-forwarded-uri", b"x-original-uri", b"x-vercel-original-path", b"x-invoke-path"):
                    raw = headers.get(key)
                    if not raw:
                        continue
                    candidate = raw.decode("latin-1").split("?")[0]
                    if candidate.startswith("/api"):
                        scope = dict(scope)
                        scope["path"] = candidate
                        scope["raw_path"] = candidate.encode("latin-1")
                        break
        await self.app(scope, receive, send)


app = _OriginalPathMiddleware(_app)
