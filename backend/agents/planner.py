"""PlannerAgent: understands the query and creates a search plan (rule-based NLU)."""
from __future__ import annotations

import re

from ..core.text import content_tokens, detect_language, keywords
from ..models import Plan
from .base import BaseAgent

INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("comparison", re.compile(r"\b(vs\.?|versus|difference between|compare|comparison|better than)\b", re.I)),
    ("howto", re.compile(r"\b(how to|how do|steps|tutorial|guide|way to)\b", re.I)),
    ("news", re.compile(r"\b(latest|news|today|current|recent|update|202\d)\b", re.I)),
    ("list", re.compile(r"\b(top|best|list of|examples|types|benefits|advantages|disadvantages)\b", re.I)),
    ("definition", re.compile(r"\b(what is|what are|define|definition|meaning of|who is|explain)\b", re.I)),
    ("fact", re.compile(r"\b(when|where|which|who|why|population|capital|height|age)\b", re.I)),
]

ENTITY_STOP = {"what", "is", "are", "the", "a", "an", "how", "to", "of", "in",
               "on", "for", "and", "vs", "latest", "news", "best", "top"}


class PlannerAgent(BaseAgent):
    name = "planner"
    role = "Query Planner"
    emoji = "🧭"

    async def run(self, query: str, depth: str = "standard") -> Plan:
        await self.start("Analyzing the query…")
        query = query.strip()
        intent = self._intent(query)
        lang = detect_language(query)
        kws = keywords(query, 10)
        entities = self._entities(query, kws)
        subqueries = self._subqueries(query, intent, entities, kws, depth)
        plan = Plan(query=query, intent=intent, language=lang, keywords=kws,
                    subqueries=subqueries, entities=entities)
        await self.done(
            f"Intent: {intent} | Language: {lang} | {len(subqueries)} sub-queries",
            {"plan": plan.to_dict()},
        )
        return plan

    def _intent(self, query: str) -> str:
        for intent, pat in INTENT_PATTERNS:
            if pat.search(query):
                return intent
        return "general"

    def _entities(self, query: str, kws: list[str]) -> list[str]:
        caps = re.findall(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+){0,2})\b", query)
        ents = [c.strip() for c in caps if c.lower() not in ENTITY_STOP]
        if not ents:
            ents = [k for k in kws if k not in ENTITY_STOP][:3]
        seen, out = set(), []
        for e in ents:
            if e.lower() not in seen:
                seen.add(e.lower())
                out.append(e)
        return out[:4]

    def _subqueries(self, query: str, intent: str, entities: list[str],
                    kws: list[str], depth: str) -> list[str]:
        topic = " ".join(entities[:2]) if entities else " ".join(kws[:3]) or query
        topic = topic.strip() or query
        n = {"quick": 1, "standard": 2, "deep": 3}.get(depth, 2)
        subs = [query]
        if intent == "comparison":
            parts = re.split(r"\bvs\.?\b|\bversus\b|\bdifference between\b", query, flags=re.I)
            parts = [re.sub(r"^(what is the|what is|compare|between)\s+", "", p.strip(), flags=re.I) for p in parts if p.strip()]
            if len(parts) >= 2:
                subs += [f"{parts[0]} features overview", f"{parts[1]} features overview"]
            else:
                subs += [f"{topic} comparison pros cons"]
        elif intent == "howto":
            subs += [f"{topic} step by step guide", f"{topic} tutorial beginners"]
        elif intent == "news":
            subs += [f"{topic} latest news", f"{topic} recent updates"]
        elif intent == "definition":
            subs += [f"{topic} overview", f"{topic} explained simply"]
        elif intent == "list":
            subs += [f"{topic} list examples", f"{topic} key benefits"]
        elif intent == "fact":
            subs += [f"{topic} facts details", f"{topic} information"]
        else:
            subs += [f"{topic} overview", f"{topic} key facts"]
        seen, out = set(), []
        for s in subs:
            s = s.strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s)
        return out[: max(1, n)]

    def refine(self, plan: Plan, retry_query: str) -> Plan:
        """Refine the plan using Critic feedback (retry loop)."""
        new_kws = keywords(retry_query, 10)
        merged = list(dict.fromkeys(plan.keywords + new_kws))[:12]
        subs = list(dict.fromkeys([retry_query] + plan.subqueries))[:4]
        return Plan(query=plan.query, intent=plan.intent, language=plan.language,
                    keywords=merged, subqueries=subs, entities=plan.entities)
