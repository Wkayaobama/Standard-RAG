"""PDF upload + per-file status endpoints."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.jobs import create_job, create_pdf, ingest_pdfs

router = APIRouter(prefix="/api", tags=["pdfs"])


@router.post("/pdfs")
async def upload_pdfs(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile],
):
    if not files:
        raise HTTPException(status_code=400, detail="At least one PDF is required.")

    db = request.app.state.db
    lock = request.app.state.db_lock

    jobs: list[tuple[str, Path]] = []
    pdf_ids: list[str] = []

    for f in files:
        if not (f.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Not a PDF: {f.filename}")
        pdf_id = uuid.uuid4().hex
        dest = settings.pdf_dir / f"{pdf_id}.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = await f.read()
        dest.write_bytes(content)
        await create_pdf(db, lock, pdf_id, f.filename or f"{pdf_id}.pdf")
        jobs.append((pdf_id, dest))
        pdf_ids.append(pdf_id)

    job_id = uuid.uuid4().hex
    await create_job(db, lock, job_id, pdf_ids)
    background_tasks.add_task(
        ingest_pdfs, db, lock, job_id, jobs, settings.markdown_dir
    )
    return {"job_id": job_id, "pdf_ids": pdf_ids}


@router.get("/pdfs")
async def list_pdfs(request: Request):
    db = request.app.state.db
    async with db.execute(
        "SELECT id, filename, status, error, created_at FROM pdfs ORDER BY created_at"
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/pdfs/{pdf_id}/markdown")
async def get_markdown(pdf_id: str, request: Request):
    db = request.app.state.db
    async with db.execute(
        "SELECT markdown_path, status FROM pdfs WHERE id = ?", (pdf_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Unknown pdf_id.")
    if row["status"] != "done" or not row["markdown_path"]:
        raise HTTPException(status_code=409, detail=f"PDF status is {row['status']}.")
    return FileResponse(row["markdown_path"], media_type="text/markdown")


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    db = request.app.state.db
    async with db.execute(
        "SELECT id, pdf_ids, state, created_at FROM jobs WHERE id = ?", (job_id,)
    ) as cur:
        job = await cur.fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Unknown job_id.")

    pdf_ids: list[str] = json.loads(job["pdf_ids"])
    placeholders = ",".join("?" * len(pdf_ids))
    async with db.execute(
        f"SELECT id, filename, status, error FROM pdfs WHERE id IN ({placeholders})",
        pdf_ids,
    ) as cur:
        pdfs = [dict(r) for r in await cur.fetchall()]

    overall = (
        "error"
        if any(p["status"] == "error" for p in pdfs)
        else "done"
        if all(p["status"] == "done" for p in pdfs)
        else "running"
    )
    return {"job_id": job["id"], "state": overall, "pdfs": pdfs}
