"""Base agent: gives every agent a name, role, and event-emitting helpers."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

Emit = Callable[..., Awaitable[None]]


async def noop_emit(*args: Any, **kwargs: Any) -> None:
    return None


class BaseAgent:
    name: str = "agent"
    role: str = ""
    emoji: str = "🤖"

    def __init__(self, emit: Emit | None = None):
        self.emit = emit or noop_emit

    async def start(self, message: str = "") -> None:
        await self.emit("agent_start", self.name, message or f"{self.role} started…",
                        {"role": self.role, "emoji": self.emoji})

    async def done(self, message: str = "", data: dict[str, Any] | None = None) -> None:
        await self.emit("agent_done", self.name, message, data or {})

    async def log(self, message: str, data: dict[str, Any] | None = None) -> None:
        await self.emit("agent_log", self.name, message, data or {})

    async def fail(self, message: str) -> None:
        await self.emit("agent_error", self.name, message)
