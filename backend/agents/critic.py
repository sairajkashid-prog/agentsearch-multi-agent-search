"""CriticAgent: audits answer quality and triggers a retry when needed.

This is the self-reflection loop. It computes coverage, source diversity,
citation integrity, and confidence. If confidence is low, it sends a refined
query back to the Planner for another search round.
"""
from __future__ import annotations

import re

from ..core.text import content_tokens, domain_of
from ..models import Answer, Critique, Passage, Plan, Source
from .base import BaseAgent


class CriticAgent(BaseAgent):
    name = "critic"
    role = "Quality Critic"
    emoji = "🧪"

    async def run(self, plan: Plan, answer: Answer, sources: list[Source],
                  passages: list[Passage], allow_retry: bool = True) -> Critique:
        await self.start("Auditing answer quality…")
        q_tokens = set(content_tokens(plan.query + " " + " ".join(plan.keywords)))
        a_tokens = set(content_tokens(answer.markdown))
        coverage = len(q_tokens & a_tokens) / max(1, len(q_tokens))

        cited = [s for s in sources if s.id in answer.cited_source_ids]
        domains = {domain_of(s.url) for s in cited}
        diversity = min(1.0, len(domains) / 3.0)

        valid_ids = {s.id for s in sources}
        citation_ok = all(i in valid_ids for i in answer.cited_source_ids)
        avg_cred = sum(s.credibility for s in cited) / len(cited) if cited else 0.0
        evidence_strength = min(1.0, len(passages) / 8.0)

        confidence = (0.34 * coverage + 0.20 * diversity + 0.22 * avg_cred +
                      0.14 * evidence_strength + 0.10 * (1.0 if citation_ok else 0.0))
        confidence = round(min(0.97, max(0.05, confidence)), 2)

        warnings = list(answer.warnings)
        if coverage < 0.45:
            warnings.append(f"Query coverage is low ({coverage:.0%}); some query keywords are missing from the answer.")
        if not citation_ok:
            warnings.append("Some citations are invalid.")
        if len(cited) == 0:
            warnings.append("No sources were cited.")
        if plan.intent == "news":
            warnings.append("For news/current-events queries, verify freshness; date filtering is limited in free mode.")

        needs_retry = allow_retry and (confidence < 0.5 or coverage < 0.4) and len(passages) < 10
        retry_query = None
        if needs_retry:
            missing = [t for t in content_tokens(plan.query) if t not in a_tokens][:4]
            topic = " ".join(plan.entities[:2]) or plan.query
            retry_query = f"{topic} {' '.join(missing)} overview facts".strip()
            retry_query = re.sub(r"\s+", " ", retry_query)

        await self.done(
            f"Confidence {confidence:.0%} | coverage {coverage:.0%} | {len(domains)} domains"
            + (" → retry recommended" if needs_retry else ""),
            {"confidence": confidence, "coverage": round(coverage, 2),
             "diversity": round(diversity, 2), "needs_retry": needs_retry},
        )
        return Critique(coverage=round(coverage, 2), source_diversity=round(diversity, 2),
                        confidence=confidence, warnings=warnings,
                        needs_retry=needs_retry, retry_query=retry_query)
