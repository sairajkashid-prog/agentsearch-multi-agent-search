"""CLI demo: run the pipeline without a browser.

Usage:
    python scripts/demo_cli.py "What is quantum computing?"
    python scripts/demo_cli.py "Python vs JavaScript" --depth quick
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.core.events import EventBus
from backend.orchestrator import run_pipeline

COLORS = {"planner": "\033[94m", "search": "\033[96m", "reader": "\033[93m",
          "ranker": "\033[95m", "synthesizer": "\033[92m", "critic": "\033[91m",
          "orchestrator": "\033[97m"}
RESET = "\033[0m"


async def main(query: str, depth: str) -> None:
    bus = EventBus()
    task = asyncio.create_task(run_pipeline(query, depth, bus))
    result = None
    async for e in bus.stream():
        color = COLORS.get(e["agent"], "")
        if e["type"] in {"agent_start", "agent_done", "agent_log", "retry", "error"}:
            print(f"{color}[{e['agent']:12}]{RESET} {e['message']}")
        if e["type"] == "result":
            result = e["data"]
    await task
    if result:
        print("\n" + "=" * 70)
        print("ANSWER:\n")
        print(result["answer"]["markdown"])
        print(f"\nConfidence: {result['answer']['confidence']:.0%} | "
              f"Sources: {len(result['sources'])} | Time: {result['stats']['elapsed_seconds']}s")
        print("\nSOURCES:")
        for s in result["sources"][:8]:
            print(f"  [{s['id']}] {s['title']} — {s['url']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="AgentSearch CLI demo")
    ap.add_argument("query", help="Search query")
    ap.add_argument("--depth", choices=["quick", "standard", "deep"], default="standard")
    args = ap.parse_args()
    asyncio.run(main(args.query, args.depth))
