"""PDF → Markdown via pymupdf4llm.

PyMuPDF is sync CPU-bound; wrap it in `asyncio.to_thread` so the event loop
stays live while the conversion runs.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pymupdf4llm


async def pdf_to_markdown(path: Path) -> str:
    return await asyncio.to_thread(pymupdf4llm.to_markdown, str(path))
