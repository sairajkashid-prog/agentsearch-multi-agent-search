"""SQLite persistence: search history and full run snapshots (including events).

The database location is configurable through ``AGENTSEARCH_DB_PATH``. On
serverless platforms (Vercel) the project directory is read-only, so the
entrypoint points this at ``/tmp``. If no writable location exists at all,
history degrades gracefully instead of breaking search.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent


def _resolve_db_path() -> Path:
    """Pick a writable database path, preferring the configured location."""
    configured = os.getenv("AGENTSEARCH_DB_PATH", "").strip()
    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.append(_ROOT / "data" / "agentsearch.db")
    candidates.append(Path(tempfile.gettempdir()) / "agentsearch.db")

    for candidate in candidates:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            probe = candidate.parent / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except OSError:
            continue
    # Nothing writable: fall back to an in-memory-style temp name; callers
    # handle sqlite3 errors so search still works without history.
    return Path(tempfile.gettempdir()) / "agentsearch.db"


DB_PATH = _resolve_db_path()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_sync() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                depth TEXT NOT NULL,
                created_at REAL NOT NULL,
                confidence REAL,
                result_json TEXT NOT NULL,
                events_json TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC)")


async def init_db() -> None:
    try:
        await asyncio.to_thread(_init_sync)
    except sqlite3.Error:
        pass


def _save_sync(run_id: str, query: str, depth: str, result: dict, events: list) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs (id, query, depth, created_at, confidence, result_json, events_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, query, depth, time.time(), result.get("answer", {}).get("confidence"),
             json.dumps(result, ensure_ascii=False), json.dumps(events, ensure_ascii=False)),
        )


async def save_run(run_id: str, query: str, depth: str, result: dict[str, Any], events: list[dict]) -> None:
    """Persist a run. Failures are non-fatal: search results still reach the user."""
    try:
        await asyncio.to_thread(_save_sync, run_id, query, depth, result, events)
    except sqlite3.Error:
        pass


def _list_sync(limit: int = 30) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, query, depth, created_at, confidence FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


async def list_runs(limit: int = 30) -> list[dict[str, Any]]:
    try:
        return await asyncio.to_thread(_list_sync, limit)
    except sqlite3.Error:
        return []


def _get_sync(run_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["result"] = json.loads(d.pop("result_json"))
    d["events"] = json.loads(d.pop("events_json"))
    return d


async def get_run(run_id: str) -> dict[str, Any] | None:
    try:
        return await asyncio.to_thread(_get_sync, run_id)
    except sqlite3.Error:
        return None


def _clear_sync() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM runs")


async def clear_runs() -> None:
    try:
        await asyncio.to_thread(_clear_sync)
    except sqlite3.Error:
        pass
