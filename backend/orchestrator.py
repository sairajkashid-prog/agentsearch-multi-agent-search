"""Orchestrator: runs the 6-agent pipeline and the Critic feedback retry loop.

Flow:
  Planner → Search → Reader → Ranker → Synthesizer → Critic
                                              ↑___________|  (if confidence is low)
"""
from __future__ import annotations

import time
import uuid

from .agents import (CriticAgent, PlannerAgent, RankerAgent, ReaderAgent,
                     SearchAgent, SynthesizerAgent)
from .config import settings
from .core.events import EventBus
from .models import Answer, Critique, PipelineResult
from .storage import init_db, save_run


async def run_pipeline(query: str, depth: str = "standard",
                       bus: EventBus | None = None) -> PipelineResult:
    bus = bus or EventBus()
    await init_db()
    run_id = uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    await bus.emit("pipeline_start", "orchestrator",
                   f"Run {run_id} started: “{query}” (depth={depth})",
                   {"run_id": run_id, "query": query, "depth": depth})

    emit = bus.emit
    planner = PlannerAgent(emit)
    searcher = SearchAgent(emit)
    reader = ReaderAgent(emit)
    ranker = RankerAgent(emit)
    synth = SynthesizerAgent(emit)
    critic = CriticAgent(emit)

    retries = 0
    exclude: set[str] = set()
    plan = await planner.run(query, depth)
    max_rounds = 1 + (settings.max_retry if settings.enable_critic_retry and depth != "quick" else 0)

    result: PipelineResult | None = None
    try:
        for round_no in range(1, max_rounds + 1):
            if round_no > 1:
                await emit("retry", "orchestrator",
                           f"Running round {round_no} based on Critic feedback…",
                           {"round": round_no})
            results = await searcher.run(plan, depth, exclude_urls=exclude)
            if not results:
                answer = Answer(
                    markdown="No search results were found. This may be a network/provider issue. Please try again shortly or rephrase the query.",
                    cited_source_ids=[], confidence=0.05,
                    follow_ups=[], warnings=["All search providers returned no results."])
                critique = Critique(0, 0, 0.05, answer.warnings, False, None)
                result = PipelineResult(query, plan, [], answer, critique, {})
                break

            docs = await reader.run(results, depth)
            passages, sources = await ranker.run(plan, docs, results)
            answer = await synth.run(plan, passages, sources)
            allow_retry = round_no < max_rounds
            critique = await critic.run(plan, answer, sources, passages, allow_retry=allow_retry)
            answer.confidence = critique.confidence
            answer.warnings = critique.warnings

            result = PipelineResult(query, plan, sources, answer, critique, {})
            if critique.needs_retry and allow_retry and critique.retry_query:
                retries += 1
                exclude.update(r.url for r in results)
                plan = planner.refine(plan, critique.retry_query)
                await emit("plan_refined", "planner", f"Refined query: {critique.retry_query}",
                           {"plan": plan.to_dict()})
                continue
            break

        assert result is not None
        elapsed = round(time.perf_counter() - t0, 2)
        providers = sorted({s.provider for s in result.sources if s.provider})
        result.stats = {
            "run_id": run_id,
            "elapsed_seconds": elapsed,
            "depth": depth,
            "rounds": retries + 1,
            "retries": retries,
            "sources": len(result.sources),
            "cited_sources": len(result.answer.cited_source_ids),
            "providers": providers,
            "tavily_enabled": settings.tavily_enabled,
            "mode": "tavily+free-fallback" if settings.tavily_enabled else "free-no-key",
        }
        await save_run(run_id, query, depth, result.to_dict(), bus.history)
        await bus.emit("result", "orchestrator", "Final answer ready", result.to_dict())
        await bus.emit("done", "orchestrator", f"Completed in {elapsed}s", {"run_id": run_id})
        return result
    except Exception as exc:  # noqa: BLE001
        await bus.emit("error", "orchestrator", f"Pipeline failed: {exc}", {"error": str(exc)})
        await bus.emit("done", "orchestrator", "Finished with error", {"run_id": run_id})
        raise
