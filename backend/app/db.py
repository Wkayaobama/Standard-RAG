"""SQLite persistence layer.

One file at `settings.db_path`. One shared `aiosqlite.Connection` opened in
the FastAPI lifespan and stored on `app.state.db`. Writes are serialised
through `app.state.db_lock` because SQLite allows only one writer at a time.
"""
from __future__ import annotations

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS pdfs (
  id TEXT PRIMARY KEY,
  filename TEXT NOT NULL,
  status TEXT NOT NULL,
  error TEXT,
  markdown_path TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pdf_id TEXT NOT NULL REFERENCES pdfs(id) ON DELETE CASCADE,
  section_path TEXT NOT NULL,
  content TEXT NOT NULL,
  tokens TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_pdf ON chunks(pdf_id);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  pdf_ids TEXT NOT NULL,
  state TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


async def connect(db_path: str) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    await conn.commit()
    return conn
