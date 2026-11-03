"""SynthesizerAgent: builds a cited, extractive answer from ranked evidence.

In free mode there is no LLM. The answer is extractive: the best source
sentences are selected and structured with citations. This keeps hallucination
near zero because every line comes from a source.
"""
from __future__ import annotations

import re

from ..core.ranking import bm25_scores, credibility
from ..core.text import content_tokens, jaccard, normalize, sentences
from ..models import Answer, Passage, Plan, Source
from .base import BaseAgent

BOILERPLATE_RE = re.compile(
    r"(cookie|subscribe|newsletter|sign up|log in|advertisement|all rights reserved|"
    r"privacy policy|terms of|skip to|share this|follow us|click here|read more|"
    r"image caption|getty images|reuters\)|^photo|^video|whether you|our team|contact us|we offer|industry-changing|in-depth discussions|click below|sign up today)", re.I)
DEF_RE = re.compile(r"\b(is a|is an|are a|refers to|is the|was a|means|defined as)\b", re.I)
STEP_RE = re.compile(r"^\s*(step\s*\d|\d+[.)]|first|second|third|next|then|finally)", re.I)


class SynthesizerAgent(BaseAgent):
    name = "synthesizer"
    role = "Answer Writer"
    emoji = "✍️"

    async def run(self, plan: Plan, passages: list[Passage], sources: list[Source]) -> Answer:
        await self.start("Writing a cited answer from evidence…")
        url_to_source = {s.url: s.id for s in sources}
        candidates = self._candidates(passages, url_to_source)

        if not candidates:
            await self.fail("Not enough evidence to answer")
            return Answer(
                markdown="I could not find enough reliable evidence for this query. Please try rephrasing it.",
                cited_source_ids=[], confidence=0.1,
                follow_ups=self._follow_ups(plan),
                warnings=["No usable evidence found."],
            )

        scored = self._score(plan, candidates)
        chosen = self._mmr_select(scored, plan, max_sentences=8)
        chosen = self._order(plan, chosen)

        markdown, cited = self._render(plan, chosen)
        warnings: list[str] = []
        if len(cited) < 2:
            warnings.append("The answer is based on a single source; cross-checking is recommended.")
        warnings.append("Free mode: the answer is extractive (source sentences), not LLM-generated.")

        await self.done(f"Answer built from {len(chosen)} evidence sentences ({len(cited)} sources cited)",
                        {"sentences": len(chosen), "cited": cited})
        return Answer(markdown=markdown, cited_source_ids=cited, confidence=0.0,
                      follow_ups=self._follow_ups(plan), warnings=warnings)

    def _candidates(self, passages: list[Passage], url_to_source: dict[str, int]) -> list[dict]:
        out = []
        for rank, p in enumerate(passages):
            sid = url_to_source.get(p.doc_url)
            if sid is None:
                continue
            for s in sentences(p.text):
                s = normalize(s)
                if len(s) < 40 or len(s) > 380:
                    continue
                if BOILERPLATE_RE.search(s):
                    continue
                if s.count("?") > 1:
                    continue
                if s.startswith("=") or "==" in s:
                    continue
                out.append({"text": s, "source_id": sid, "passage_rank": rank,
                            "tokens": set(content_tokens(s)),
                            "cred": credibility(p.doc_url),
                            "provider": p.provider, "url": p.doc_url})
        seen, uniq = set(), []
        for c in out:
            key = c["text"].lower()
            if key not in seen:
                seen.add(key)
                uniq.append(c)
        return uniq

    def _score(self, plan: Plan, candidates: list[dict]) -> list[dict]:
        q_tokens = content_tokens(plan.query + " " + " ".join(plan.keywords))
        texts = [c["text"] for c in candidates]
        bm = bm25_scores(q_tokens, [content_tokens(t) for t in texts])
        q_set = set(q_tokens)
        for c, b in zip(candidates, bm):
            overlap = len(q_set & c["tokens"]) / max(1, len(q_set))
            pos_bonus = max(0.0, 1.0 - c["passage_rank"] * 0.08)
            def_bonus = 0.0
            if plan.intent in {"definition", "general", "fact"} and DEF_RE.search(c["text"]):
                def_bonus = 1.2
            step_bonus = 0.8 if plan.intent == "howto" and STEP_RE.search(c["text"]) else 0.0
            num_bonus = 0.4 if plan.intent in {"fact", "news"} and re.search(r"\d", c["text"]) else 0.0
            len_penalty = 0.3 if len(c["text"]) < 60 else 0.0
            promo_penalty = 1.5 if re.search(r"(whether you|our |we offer|contact us|newsletter|in-depth discussions|industry-changing)", c["text"], re.I) else 0.0
            hist_penalty = 0.8 if plan.intent in {"definition", "fact", "general"} and re.search(r"(during|formerly|until|19\d\d)", c["text"], re.I) else 0.0
            c["score"] = round(b + overlap * 2.5 + pos_bonus + def_bonus +
                               step_bonus + num_bonus + c["cred"] * 0.8 - len_penalty - promo_penalty - hist_penalty, 4)
        return sorted(candidates, key=lambda c: c["score"], reverse=True)

    def _mmr_select(self, scored: list[dict], plan: Plan, max_sentences: int = 8) -> list[dict]:
        """Maximal Marginal Relevance: balance relevance and diversity."""
        selected: list[dict] = []
        pool = scored[:40]
        if plan.intent in {"definition", "general", "fact"}:
            ent_tokens = set(content_tokens(" ".join(plan.entities) + " " + plan.query))
            def lead_rank(c: dict) -> float:
                text = c["text"].lower()
                wiki = 1.5 if ("wikipedia.org" in c.get("url", "") or "britannica.com" in c.get("url", "")) else 0.0
                overlap = len(ent_tokens & c["tokens"]) / max(1, len(ent_tokens))
                density = len(ent_tokens & c["tokens"]) / max(1, len(c["tokens"]))
                starts = 0.8 if any(text.startswith(e.lower()) for e in plan.entities if e) else 0.0
                list_pen = 1.0 if text.startswith(("list of", "glossary", "timeline")) else 0.0
                return c["score"] + wiki + overlap * 2.0 + density * 3.0 + starts - list_pen
            leads = [c for c in pool if DEF_RE.search(c["text"])]
            if leads:
                lead = max(leads, key=lead_rank)
                selected.append(lead)
                pool.remove(lead)
        lam = 0.72
        while pool and len(selected) < max_sentences:
            best, best_val = None, -1e9
            for c in pool:
                sim = max((jaccard(c["tokens"], s["tokens"]) for s in selected), default=0.0)
                val = lam * c["score"] - (1 - lam) * sim * 6.0
                if val > best_val:
                    best_val, best = val, c
            if best is None:
                break
            selected.append(best)
            pool.remove(best)
        return selected

    def _order(self, plan: Plan, chosen: list[dict]) -> list[dict]:
        if plan.intent == "howto":
            steps = [c for c in chosen if STEP_RE.search(c["text"])]
            rest = [c for c in chosen if c not in steps]
            return steps + rest
        if plan.intent in {"definition", "general", "fact"}:
            defs = [c for c in chosen if DEF_RE.search(c["text"])]
            rest = [c for c in chosen if c not in defs]
            return defs[:1] + rest
        return chosen

    def _render(self, plan: Plan, chosen: list[dict]) -> tuple[str, list[int]]:
        cited: list[int] = []

        def cite(c: dict) -> str:
            sid = c["source_id"]
            if sid not in cited:
                cited.append(sid)
            return f"{c['text']} [{sid}]"

        lead = chosen[0]
        body = chosen[1:]
        lines = [cite(lead), ""]

        if plan.intent == "howto" and any(STEP_RE.search(c["text"]) for c in body):
            lines.append("**Steps:**")
            for i, c in enumerate(body, 1):
                txt = re.sub(r"^\s*(step\s*\d+[.:)]?|\d+[.)])\s*", "", c["text"], flags=re.I)
                lines.append(f"{i}. {cite({**c, 'text': txt})}")
        else:
            if body:
                lines.append("**Key points:**")
                for c in body[:6]:
                    lines.append(f"- {cite(c)}")
        markdown = "\n".join(lines).strip()
        return markdown, cited

    def _follow_ups(self, plan: Plan) -> list[str]:
        topic = " ".join(plan.entities[:2]) or " ".join(plan.keywords[:2]) or plan.query
        topic = topic.strip()
        base = {
            "definition": [f"{topic} real-world examples", f"{topic} vs alternatives", f"future of {topic}"],
            "howto": [f"{topic} common mistakes", f"{topic} best tools", f"{topic} advanced tips"],
            "comparison": [f"{topic} which is better for beginners", f"{topic} performance benchmark", f"{topic} cost comparison"],
            "news": [f"{topic} latest updates", f"{topic} expert analysis", f"{topic} impact"],
            "list": [f"{topic} detailed comparison", f"{topic} how to choose", f"{topic} pros and cons"],
            "fact": [f"{topic} related facts", f"{topic} history", f"{topic} detailed explanation"],
            "general": [f"{topic} explained simply", f"{topic} latest developments", f"{topic} pros and cons"],
        }
        return base.get(plan.intent, base["general"])[:3]
