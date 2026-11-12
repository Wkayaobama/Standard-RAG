"""BM25 retrieval over markdown chunks stored in SQLite.

Index is rebuilt from scratch on each query — the SELECT is cheap for the
localhost corpus sizes this app targets. No background index maintenance.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import aiosqlite
from rank_bm25 import BM25Okapi

from app.chunker import tokenize


@dataclass
class RetrievedChunk:
    pdf_id: str
    section_path: str
    content: str
    score: float


async def top_k(db: aiosqlite.Connection, question: str, k: int = 6) -> list[RetrievedChunk]:
    async with db.execute(
        "SELECT pdf_id, section_path, content, tokens FROM chunks"
    ) as cur:
        rows = await cur.fetchall()

    if not rows:
        return []

    corpus_tokens = [json.loads(r["tokens"]) for r in rows]
    bm25 = BM25Okapi(corpus_tokens)
    query_tokens = tokenize(question)
    if not query_tokens:
        return []

    scores = bm25.get_scores(query_tokens)
    ranked = sorted(
        zip(rows, scores), key=lambda t: t[1], reverse=True
    )[:k]

    return [
        RetrievedChunk(
            pdf_id=r["pdf_id"],
            section_path=r["section_path"],
            content=r["content"],
            score=float(s),
        )
        for r, s in ranked
        if s > 0
    ]
