"""Event bus: agents emit events, and the SSE endpoint streams them to the browser.

Each agent emits events when it starts, logs progress, and finishes. This powers
the live agent activity feed in the UI.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class EventBus:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    history: list[dict[str, Any]] = field(default_factory=list)

    async def emit(self, type_: str, agent: str = "system", message: str = "",
                   data: dict[str, Any] | None = None) -> None:
        event = {
            "type": type_,
            "agent": agent,
            "message": message,
            "data": data or {},
            "ts": round(time.time(), 3),
        }
        self.history.append(event)
        await self.queue.put(event)

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            event = await self.queue.get()
            yield event
            if event["type"] == "done":
                break
