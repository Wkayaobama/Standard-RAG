# Standard-RAG

A clean, provider-agnostic, Docker-based RAG app: upload PDFs, get a consolidated Markdown artifact, ask questions through a Claude-powered assistant that retrieves from your corpus.

- **Backend:** FastAPI + SQLite + Anthropic SDK + `pymupdf4llm` + `rank-bm25`
- **Frontend:** React 18 + Vite + Tailwind + shadcn-style primitives
- **Runtime:** Docker Compose, two services, localhost

No external vector database. No LangChain. No middleware between your app and the Anthropic API.

---

## Quick start

```bash
cp .env.example .env            # put your ANTHROPIC_API_KEY in it
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend:  http://localhost:8000
- API docs: http://localhost:8000/api/docs

Stop with `docker compose down`. Persisted PDFs, markdown, and the SQLite index live in the `rag-data` named volume — survives restarts. Drop that volume with `docker compose down -v`.

---

## What it does

1. **Ingest** — `POST /api/pdfs` accepts N PDFs. Each is converted to Markdown by `pymupdf4llm` in a background task (`asyncio.gather` over per-file coroutines). Status per file is tracked in SQLite; poll with `GET /api/jobs/{job_id}`.
2. **Consolidate** — `POST /api/corpus/build` writes `corpus.md` with a top-level TOC and every converted PDF as an H1-banner section. `GET /api/corpus` downloads it.
3. **Chat** — `POST /api/chat` runs BM25 over heading-aware markdown chunks, sends the top-6 excerpts plus your question to Claude via the Anthropic SDK, returns answer + citations (`pdf_id`, `section_path`).

Conversation state lives in the client — the backend is stateless per request.

---

## Project structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI entrypoint (lifespan, CORS, routers)
│   │   ├── config.py             # pydantic-settings — standalone-only
│   │   ├── claude_examples.py    # Anthropic SDK cookbook (chat, stream, vision, tools, JSON)
│   │   ├── db.py                 # aiosqlite connect + schema
│   │   ├── pdf.py                # pymupdf4llm wrapper
│   │   ├── chunker.py            # heading-aware markdown splitter + tokenizer
│   │   ├── retrieval.py          # rank-bm25 over SQLite chunks
│   │   ├── jobs.py               # async ingest orchestration
│   │   └── routes/
│   │       ├── pdfs.py           # upload, list, markdown, job polling
│   │       ├── corpus.py         # build + download consolidated .md
│   │       └── chat.py           # RAG query endpoint
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx               # single-page: upload / status / corpus / chat
│   │   ├── index.css             # Tailwind + HSL design tokens
│   │   └── components/ui/        # Button, Card, Input, Label, Badge
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/pdfs` | Upload one or more PDFs; kicks off async conversion. Returns `{job_id, pdf_ids}`. |
| GET  | `/api/pdfs` | List all PDFs with per-file status. |
| GET  | `/api/pdfs/{pdf_id}/markdown` | Serve the converted `.md` for one PDF. |
| GET  | `/api/jobs/{job_id}` | Poll ingest job state + per-PDF statuses. |
| POST | `/api/corpus/build` | Concatenate all converted PDFs into `corpus.md`. Idempotent. |
| GET  | `/api/corpus` | Download the consolidated `corpus.md`. |
| POST | `/api/chat` | RAG query: `{question, history?}` → `{answer, citations}`. |
| GET  | `/api/health` | Liveness + project name. |

---

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Standalone Anthropic SDK auth — direct to `api.anthropic.com`. |
| `AI_MODEL` | `claude-sonnet-4-6` | Default model for chat. Override to Opus/Haiku per need. |
| `FRONTEND_PORT` | `5173` | Host port the Vite dev server publishes on. |
| `BACKEND_PORT` | `8000` | Host port the FastAPI backend publishes on. |

---

## Customising

- **Switch model per call** — pass `model=` to `claude_examples.chat_once` / `stream_chat`.
- **Change retrieval top-k** — request body `top_k` field on `/api/chat` (default 6).
- **Add new chat features** — see `backend/app/claude_examples.py`: streaming, vision, tool use, and structured JSON extraction are all covered.
- **Rebuild backend after dep changes** — `docker compose up --build backend`.
- **Rebuild frontend after dep changes** — `docker compose up --build frontend`.

---

## Notes

PDF→Markdown is provided by `pymupdf4llm`, which depends on PyMuPDF (AGPL-3.0). That's fine for this scaffold's intended use (localhost tool, private deployments). If you plan to ship this as a hosted product that isn't itself open-sourced under a compatible licence, swap the engine — `pypdf` (text-only, MIT) is a drop-in for `app/pdf.py`.
