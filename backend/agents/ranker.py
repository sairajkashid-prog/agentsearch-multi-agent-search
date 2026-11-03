"""RankerAgent: splits documents into passages and ranks them using BM25,
credibility, and diversity. The ranked passages become evidence for synthesis.
"""
from __future__ import annotations

from ..core.ranking import bm25_scores, credibility
from ..core.text import content_tokens, domain_of, jaccard, sentences
from ..models import Document, Passage, Plan, Source
from .base import BaseAgent

PASSAGE_MIN = 180
PASSAGE_MAX = 900
TOP_PASSAGES = 14
MAX_PER_DOMAIN = 4


def chunk_document(text: str) -> list[str]:
    """Paragraph-aware chunking: merge small paragraphs, split large ones."""
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    if not paras:
        paras = sentences(text)
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(p) > PASSAGE_MAX:
            if buf:
                chunks.append(buf)
                buf = ""
            sents = sentences(p)
            cur = ""
            for s in sents:
                if len(cur) + len(s) + 1 <= PASSAGE_MAX:
                    cur = (cur + " " + s).strip()
                else:
                    if cur:
                        chunks.append(cur)
                    cur = s
            if cur:
                chunks.append(cur)
        elif len(buf) + len(p) + 1 <= PASSAGE_MAX:
            buf = (buf + "\n" + p).strip()
            if len(buf) >= PASSAGE_MIN:
                chunks.append(buf)
                buf = ""
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf and len(buf) >= 60:
        chunks.append(buf)
    return chunks


class RankerAgent(BaseAgent):
    name = "ranker"
    role = "Evidence Ranker"
    emoji = "⚖️"

    async def run(self, plan: Plan, docs: list[Document],
                  results: list) -> tuple[list[Passage], list[Source]]:
        await self.start("Ranking evidence passages (BM25 + trust)…")
        query_text = plan.query + " " + " ".join(plan.keywords) + " " + " ".join(plan.subqueries)
        q_tokens = content_tokens(query_text)

        passages: list[Passage] = []
        for d in docs:
            if not d.text.strip():
                continue
            for chunk in chunk_document(d.text):
                passages.append(Passage(doc_url=d.url, doc_title=d.title, text=chunk, provider=d.provider))

        if not passages:
            await self.done("No passages found", {"passages": 0})
            return [], []

        tokens = [content_tokens(p.text) for p in passages]
        scores = bm25_scores(q_tokens, tokens)
        q_set = set(q_tokens)
        title_tokens = {p.doc_url: set(content_tokens(p.doc_title)) for p in passages}
        for p, s, toks in zip(passages, scores, tokens):
            overlap = len(q_set & set(toks)) / max(1, len(q_set))
            trust = credibility(p.doc_url)
            length_bonus = min(1.0, len(p.text) / 400) * 0.3
            title_boost = len(q_set & title_tokens.get(p.doc_url, set())) / max(1, len(q_set)) * 2.2
            tl = p.doc_title.lower()
            list_penalty = 1.4 if (plan.intent in {"definition", "fact", "general"} and
                                   tl.startswith(("list of", "timeline of", "glossary", "index of", "outline of"))) else 0.0
            p.score = round(s * (0.7 + 0.6 * trust) + overlap * 2.0 + length_bonus +
                            title_boost - list_penalty, 4)

        passages.sort(key=lambda p: p.score, reverse=True)

        # Diversity: avoid too many passages from one domain and remove near-duplicates.
        selected: list[Passage] = []
        domain_count: dict[str, int] = {}
        seen_tokens: list[set[str]] = []
        for p in passages:
            dom = domain_of(p.doc_url)
            if domain_count.get(dom, 0) >= MAX_PER_DOMAIN:
                continue
            toks = set(content_tokens(p.text))
            if any(jaccard(toks, prev) > 0.82 for prev in seen_tokens):
                continue
            selected.append(p)
            seen_tokens.append(toks)
            domain_count[dom] = domain_count.get(dom, 0) + 1
            if len(selected) >= TOP_PASSAGES:
                break

        used_urls = list(dict.fromkeys(p.doc_url for p in selected))
        by_url = {r.url: r for r in results}
        sources: list[Source] = []
        for i, url in enumerate(used_urls, 1):
            r = by_url.get(url)
            title = next((p.doc_title for p in selected if p.doc_url == url), url)
            sources.append(Source(
                id=i, title=(r.title if r else title) or title, url=url,
                domain=domain_of(url), provider=(r.provider if r else ""),
                snippet=(r.snippet if r else "")[:300], credibility=round(credibility(url), 2),
            ))
        for r in results:
            if len(sources) >= 10:
                break
            if r.url not in used_urls:
                sources.append(Source(id=len(sources) + 1, title=r.title, url=r.url,
                                      domain=domain_of(r.url), provider=r.provider,
                                      snippet=r.snippet[:300], credibility=round(credibility(r.url), 2)))
                used_urls.append(r.url)

        await self.done(f"{len(selected)} best passages selected, {len(sources)} sources",
                        {"passages": len(selected), "sources": len(sources),
                         "top": [{"title": p.doc_title, "score": p.score, "url": p.doc_url} for p in selected[:5]]})
        return selected, sources
