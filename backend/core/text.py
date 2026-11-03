"""Lightweight English text processing: tokenization, stopwords, sentences.

No ML models are required. This keeps the project free, fast, and easy to run.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

EN_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "while",
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does", "did",
    "have", "has", "had", "having", "will", "would", "shall", "should", "can",
    "could", "may", "might", "must", "of", "in", "on", "at", "by", "for", "with",
    "about", "against", "between", "into", "through", "during", "before", "after",
    "above", "below", "to", "from", "up", "down", "out", "off", "over", "under",
    "again", "further", "once", "here", "there", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only",
    "own", "same", "so", "than", "too", "very", "just", "also", "as", "it", "its",
    "itself", "this", "that", "these", "those", "i", "me", "my", "we", "our",
    "you", "your", "he", "him", "his", "she", "her", "they", "them", "their",
    "what", "which", "who", "whom", "whose", "how", "why", "where", "please",
    "tell", "give", "explain", "define", "meaning", "vs", "versus",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-']*|\d+(?:\.\d+)?")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def normalize(text: str) -> str:
    """Unicode-normalize text and collapse whitespace."""
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    text = normalize(text).lower()
    return _WORD_RE.findall(text)


def content_tokens(text: str) -> list[str]:
    return [t for t in tokenize(text) if t not in EN_STOPWORDS and len(t) > 1]


def keywords(text: str, limit: int = 12) -> list[str]:
    counts = Counter(content_tokens(text))
    return [w for w, _ in counts.most_common(limit)]


def sentences(text: str) -> list[str]:
    text = normalize(text)
    if not text:
        return []
    parts = _SENT_SPLIT_RE.split(text)
    out: list[str] = []
    for p in parts:
        p = p.strip(" \t-•·")
        if len(p) < 15:
            continue
        if len(p) > 420:
            chunks = re.split(r"(?<=[,;])\s+", p)
            buf = ""
            for c in chunks:
                if len(buf) + len(c) < 300:
                    buf = (buf + " " + c).strip()
                else:
                    if len(buf) >= 25:
                        out.append(buf)
                    buf = c
            if len(buf) >= 25:
                out.append(buf)
        else:
            out.append(p)
    return out


def detect_language(text: str) -> str:
    """English-first project. Non-Latin scripts are reported as 'other'."""
    if not text:
        return "en"
    latin = len(re.findall(r"[A-Za-z]", text))
    letters = len(re.findall(r"\w", text, flags=re.UNICODE))
    if letters and latin / max(1, letters) < 0.5:
        return "other"
    return "en"


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def ngrams(tokens: list[str], n: int = 2) -> list[tuple[str, ...]]:
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def domain_of(url: str) -> str:
    from urllib.parse import urlparse
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""
