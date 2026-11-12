"""Heading-aware markdown chunker.

Splits markdown on `#..######` headings, carries a breadcrumb path so each
chunk knows where it sits in the document ("Intro > Context > Why this
exists"). Oversized sections are further split at ~1500 chars.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
MAX_CHUNK_CHARS = 1500


@dataclass
class Chunk:
    section_path: str
    content: str


def _split_oversized(body: str) -> list[str]:
    if len(body) <= MAX_CHUNK_CHARS:
        return [body]
    pieces: list[str] = []
    paragraphs = body.split("\n\n")
    buf: list[str] = []
    size = 0
    for p in paragraphs:
        if size + len(p) > MAX_CHUNK_CHARS and buf:
            pieces.append("\n\n".join(buf))
            buf = [p]
            size = len(p)
        else:
            buf.append(p)
            size += len(p) + 2
    if buf:
        pieces.append("\n\n".join(buf))
    return pieces


def chunk_markdown(md: str) -> list[Chunk]:
    matches = list(HEADING_RE.finditer(md))
    chunks: list[Chunk] = []
    breadcrumb: list[str] = []

    if not matches:
        for piece in _split_oversized(md.strip()):
            if piece:
                chunks.append(Chunk(section_path="(root)", content=piece))
        return chunks

    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        body = md[body_start:body_end].strip()

        breadcrumb = breadcrumb[: level - 1]
        while len(breadcrumb) < level - 1:
            breadcrumb.append("")
        breadcrumb.append(title)
        section_path = " > ".join(b for b in breadcrumb if b)

        if not body:
            continue
        for piece in _split_oversized(body):
            chunks.append(Chunk(section_path=section_path, content=piece))

    return chunks


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())
