"""Corpus consolidation endpoints.

`POST /api/corpus/build` writes `corpus.md` with a top-level TOC followed by
every converted PDF's markdown, each prefixed with an H1 banner derived from
the uploaded filename. `GET /api/corpus` streams the file back.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.config import settings

router = APIRouter(prefix="/api", tags=["corpus"])


@router.post("/corpus/build")
async def build_corpus(request: Request):
    db = request.app.state.db
    async with db.execute(
        "SELECT id, filename, markdown_path FROM pdfs "
        "WHERE status = 'done' AND markdown_path IS NOT NULL "
        "ORDER BY created_at"
    ) as cur:
        rows = await cur.fetchall()

    if not rows:
        raise HTTPException(
            status_code=409, detail="No successfully converted PDFs yet."
        )

    toc_lines = ["# Consolidated corpus", "", "## Table of contents", ""]
    body_parts: list[str] = []
    for r in rows:
        title = Path(r["filename"]).stem
        anchor = title.lower().replace(" ", "-")
        toc_lines.append(f"- [{title}](#{anchor})")
        md = Path(r["markdown_path"]).read_text(encoding="utf-8")
        body_parts.append(f"\n\n---\n\n# {title}\n\n{md.strip()}\n")

    corpus = "\n".join(toc_lines) + "\n" + "".join(body_parts)
    settings.corpus_path.parent.mkdir(parents=True, exist_ok=True)
    settings.corpus_path.write_text(corpus, encoding="utf-8")

    return {"path": str(settings.corpus_path), "bytes": len(corpus), "pdfs": len(rows)}


@router.get("/corpus")
async def download_corpus():
    if not settings.corpus_path.exists():
        raise HTTPException(
            status_code=404, detail="Corpus not built yet. POST /api/corpus/build first."
        )
    return FileResponse(
        settings.corpus_path,
        media_type="text/markdown",
        filename="corpus.md",
    )
