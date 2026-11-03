"""BM25 ranking and source credibility scoring (classic IR, no ML)."""
from __future__ import annotations

import math
from collections import Counter
from urllib.parse import urlparse

from .text import content_tokens, domain_of

K1 = 1.5
B = 0.75

# Heuristic domain trust. This is not a truth guarantee; it is only a ranking signal.
HIGH_TRUST = {
    "wikipedia.org": 0.92, "britannica.com": 0.92, "nature.com": 0.93,
    "science.org": 0.93, "nih.gov": 0.94, "nasa.gov": 0.95, "who.int": 0.93,
    "worldbank.org": 0.9, "imf.org": 0.9, "un.org": 0.9, "gov.in": 0.93,
    "nic.in": 0.9, "rbi.org.in": 0.94, "isro.gov.in": 0.95, "pib.gov.in": 0.9,
    "python.org": 0.93, "developer.mozilla.org": 0.93, "docs.python.org": 0.94,
    "stackoverflow.com": 0.82, "github.com": 0.8, "arxiv.org": 0.88,
    "ieee.org": 0.9, "acm.org": 0.9, "reuters.com": 0.88, "apnews.com": 0.88,
    "bbc.com": 0.87, "bbc.co.uk": 0.87, "thehindu.com": 0.84,
    "indianexpress.com": 0.82, "ndtv.com": 0.8, "economist.com": 0.86,
    "mit.edu": 0.93, "stanford.edu": 0.93, "harvard.edu": 0.93,
    "iitb.ac.in": 0.9, "iitd.ac.in": 0.9, "edu": 0.88, "gov": 0.9,
}
LOW_TRUST_HINTS = ("pinterest.", "quora.com", "reddit.com", "answers.",
                   "blogspot.", "wordpress.com", "medium.com", "facebook.com",
                   "instagram.com", "tiktok.com", "youtube.com")


def bm25_scores(query_tokens: list[str], docs_tokens: list[list[str]]) -> list[float]:
    """Return a BM25 score for each document against the query."""
    n = len(docs_tokens)
    if n == 0:
        return []
    counts = [Counter(d) for d in docs_tokens]
    lengths = [len(d) for d in docs_tokens]
    avgdl = sum(lengths) / n if n else 0.0
    df: Counter = Counter()
    for c in counts:
        for t in set(c):
            df[t] += 1
    scores = []
    for i, c in enumerate(counts):
        s = 0.0
        dl = lengths[i] or 1
        for t in set(query_tokens):
            if t not in c:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            tf = c[t]
            s += idf * (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * dl / (avgdl or 1)))
        scores.append(s)
    return scores


def credibility(url: str) -> float:
    host = domain_of(url)
    if not host:
        return 0.4
    for dom, score in HIGH_TRUST.items():
        if host == dom or host.endswith("." + dom) or host.endswith(dom):
            return score
    if any(h in host for h in LOW_TRUST_HINTS):
        return 0.5
    try:
        tld = host.rsplit(".", 1)[-1]
        if tld in {"gov", "edu", "int"}:
            return 0.88
        if tld in {"ac", "in"} and host.endswith((".ac.in", ".gov.in", ".nic.in")):
            return 0.88
    except Exception:
        pass
    return 0.68


def is_probably_article(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in {"http", "https"}:
        return False
    bad = (".pdf", ".zip", ".jpg", ".png", ".gif", ".mp4", ".mp3", ".exe", ".dmg")
    return not p.path.lower().endswith(bad)
