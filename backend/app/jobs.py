"""Async ingest orchestration.

`ingest_pdfs` fans out per-file converters via `asyncio.gather`. Each worker
runs: PDF→Markdown → chunk → persist chunks → mark pdf status. SQLite writes
are serialised through `app.state.db_lock` because SQLite is single-writer.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from app.chunker import chunk_markdown, tokenize
from app.pdf import pdf_to_markdown


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _ingest_one(
    db: aiosqlite.Connection,
    lock: asyncio.Lock,
    pdf_id: str,
    pdf_path: Path,
    markdown_dir: Path,
) -> None:
    async with lock:
        await db.execute(
            "UPDATE pdfs SET status = ? WHERE id = ?", ("running", pdf_id)
        )
        await db.commit()

    try:
        md = await pdf_to_markdown(pdf_path)

        markdown_path = markdown_dir / f"{pdf_id}.md"
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(md, encoding="utf-8")

        chunks = chunk_markdown(md)

        async with lock:
            for c in chunks:
                await db.execute(
                    "INSERT INTO chunks (pdf_id, section_path, content, tokens) "
                    "VALUES (?, ?, ?, ?)",
                    (pdf_id, c.section_path, c.content, json.dumps(tokenize(c.content))),
                )
            await db.execute(
                "UPDATE pdfs SET status = ?, markdown_path = ? WHERE id = ?",
                ("done", str(markdown_path), pdf_id),
            )
            await db.commit()

    except Exception as e:
        async with lock:
            await db.execute(
                "UPDATE pdfs SET status = ?, error = ? WHERE id = ?",
                ("error", str(e), pdf_id),
            )
            await db.commit()


async def ingest_pdfs(
    db: aiosqlite.Connection,
    lock: asyncio.Lock,
    job_id: str,
    jobs: list[tuple[str, Path]],
    markdown_dir: Path,
) -> None:
    await asyncio.gather(
        *(_ingest_one(db, lock, pid, p, markdown_dir) for pid, p in jobs)
    )
    async with lock:
        await db.execute(
            "UPDATE jobs SET state = ? WHERE id = ?", ("done", job_id)
        )
        await db.commit()


async def create_job(
    db: aiosqlite.Connection, lock: asyncio.Lock, job_id: str, pdf_ids: list[str]
) -> None:
    async with lock:
        await db.execute(
            "INSERT INTO jobs (id, pdf_ids, state, created_at) VALUES (?, ?, ?, ?)",
            (job_id, json.dumps(pdf_ids), "running", _utcnow()),
        )
        await db.commit()


async def create_pdf(
    db: aiosqlite.Connection,
    lock: asyncio.Lock,
    pdf_id: str,
    filename: str,
) -> None:
    async with lock:
        await db.execute(
            "INSERT INTO pdfs (id, filename, status, created_at) VALUES (?, ?, ?, ?)",
            (pdf_id, filename, "pending", _utcnow()),
        )
        await db.commit()
