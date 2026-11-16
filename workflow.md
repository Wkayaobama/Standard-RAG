# Workflow — launching Standard-RAG

Sequential steps from a fresh clone to a working chat session. Assumes Docker Desktop is installed and running.

Expected total time on first run: ~3 minutes (mostly the backend image build downloading wheels). Subsequent runs reuse the cached image and start in ~10 seconds.

---

## Step 0 — Prerequisites

- **Docker Desktop** running (`docker --version` and `docker compose version` must both print, no error).
- **An Anthropic API key**. Get one at https://console.anthropic.com/settings/keys — look for a value starting with `sk-ant-`.
- **The repo cloned locally**. If you haven't yet:
  ```bash
  git clone https://github.com/Wkayaobama/Standard-RAG.git
  cd Standard-RAG
  ```

### Windows (PowerShell)

```powershell
docker --version
docker compose version

# If `docker info` fails, Docker Desktop isn't running. Start it and wait for the daemon:
if (-not (docker info --format '{{.ServerVersion}}' 2>$null)) {
    Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    Write-Host "Waiting for Docker daemon..."
    while (-not (docker info --format '{{.ServerVersion}}' 2>$null)) { Start-Sleep -Seconds 2 }
}

git clone https://github.com/Wkayaobama/Standard-RAG.git
Set-Location Standard-RAG
```

No Python, Node, or any SDK installed on the host — everything runs inside the two Docker containers.

---

## Step 1 — Configure `.env`

The repo ships with `.env.example`. Copy it to `.env` (which is gitignored, so your key never reaches GitHub) and fill in the key.

**macOS / Linux:**
```bash
cp .env.example .env
```

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
notepad .env   # paste your real ANTHROPIC_API_KEY, save, close
```

Open `.env` in any editor and set:

```
ANTHROPIC_API_KEY=sk-ant-...        # paste your real key
AI_MODEL=claude-sonnet-4-6          # keep default, or switch to claude-opus-4-7 / claude-haiku-4-5
FRONTEND_PORT=5173                  # change if 5173 is taken on your host
BACKEND_PORT=8000                   # change if 8000 is taken on your host
```

`ANTHROPIC_API_KEY` is the only required value. The other three have working defaults.

---

## Step 2 — Start the stack

From the repo root:

```bash
docker compose up --build
```

First run: Docker builds two images (backend ~250 MB, frontend ~400 MB), then starts both services. You'll see interleaved logs from `backend` and `frontend`. Watch for:

- `backend | INFO:     Uvicorn running on http://0.0.0.0:8000`
- `frontend | VITE v5.x.x  ready in ... ms`
- `frontend | Local:   http://localhost:5173/`

Leave the terminal open — Ctrl+C stops the app.

To start it in the background instead:
```bash
docker compose up --build -d
```
and view logs later with `docker compose logs -f`.

### Windows (PowerShell)

```powershell
# Foreground (Ctrl+C to stop):
docker compose up --build

# Or background + follow logs in the same shell:
docker compose up --build -d
docker compose logs -f
```

---

## Step 3 — Verify the backend is live

In a second terminal:

```bash
curl http://localhost:8000/api/health
```

Expected response:
```json
{"status":"ok","project":"standard-rag"}
```

If this fails, see **Troubleshooting** below before proceeding.

### Windows (PowerShell)

```powershell
Invoke-RestMethod http://localhost:8000/api/health
# Expected: @{ status = 'ok'; project = 'standard-rag' }

# Open the OpenAPI docs in the default browser:
Start-Process http://localhost:8000/api/docs
```

The OpenAPI docs are at http://localhost:8000/api/docs — useful for driving the backend without the UI.

---

## Step 4 — Open the frontend and upload PDFs

Open http://localhost:5173 in your browser. You'll see three sections appear progressively as data moves through the pipeline:

1. **Upload PDFs** — drag one or more `.pdf` files onto the drop zone, or click to browse.
2. After upload, a **PDFs** card lists each file with a live status badge: `pending` → `running` → `done` (or `error`). The list polls `GET /api/pdfs` every 1.5 s, so you'll see the states change without refresh.
3. Each PDF converts in parallel on the backend via `asyncio.gather` over per-file coroutines; a 30-page PDF typically completes in 2–5 seconds.
4. When a file reaches `done`, a `.md` download button appears next to it — click to see the individual converted markdown.

### Windows (PowerShell)

```powershell
# Open the UI:
Start-Process http://localhost:5173

# Or upload entirely from the shell (one or many PDFs, comma-separated):
$form = @{ files = Get-Item C:\path\to\deck1.pdf, C:\path\to\deck2.pdf }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/pdfs -Form $form
# -> @{ job_id = '...'; pdf_ids = @('...','...') }

# Poll one job:
Invoke-RestMethod http://localhost:8000/api/jobs/<job_id_from_above>

# Or list every PDF the backend knows about:
Invoke-RestMethod http://localhost:8000/api/pdfs
```

---

## Step 5 — Build the consolidated corpus

Once at least one PDF is `done`, a **Consolidated corpus** card appears. Click **Build corpus**.

This calls `POST /api/corpus/build`, which concatenates every converted PDF into `/app/data/corpus.md` inside the backend container:

- Top-level TOC referencing each source document by filename.
- Per-PDF H1 banner sections, in upload order.

When build completes, a **Download** button appears. The file is served at `GET /api/corpus` as `text/markdown`.

Building is idempotent — click again later after adding more PDFs; it overwrites with the current set.

### Windows (PowerShell)

```powershell
# Build corpus.md server-side:
Invoke-RestMethod -Method Post http://localhost:8000/api/corpus/build
# -> @{ path = '/app/data/corpus.md'; bytes = ...; pdfs = ... }

# Download it to the current directory:
Invoke-WebRequest http://localhost:8000/api/corpus -OutFile .\corpus.md
```

---

## Step 6 — Chat with the corpus

The **Assistant** card is available as soon as there's at least one `done` PDF. Type a question, hit Enter or click **Send**.

Behind the scenes, `POST /api/chat` runs this pipeline per request:

1. BM25 over every markdown chunk in SQLite (`chunks` table), top 6 matches.
2. Assembles a system prompt that pins Claude to the retrieved excerpts and tells it to cite by section path.
3. Calls `AsyncAnthropic(api_key=...).messages.create(...)` directly — no proxy, no middleware.
4. Returns `{answer, citations: [{pdf_id, section_path}]}`.

The UI shows citations as small badges under each assistant message so you can see which parts of which PDF grounded the answer.

Conversation history lives in the browser and is sent back with each turn — the backend is stateless per request.

### Windows (PowerShell)

```powershell
$body = @{
    question = 'What are the three main sections in the first PDF?'
    history  = @()
    top_k    = 6
} | ConvertTo-Json

$resp = Invoke-RestMethod -Method Post `
    -Uri http://localhost:8000/api/chat `
    -ContentType 'application/json' `
    -Body $body

$resp.answer
$resp.citations | Format-Table pdf_id, section_path
```

---

## Step 7 — Stopping the app

```bash
docker compose down
```

This stops and removes the containers but **keeps your data**: PDFs, converted markdown, consolidated corpus, and the SQLite database all persist in the `rag-data` named volume. Next `docker compose up` picks up where you left off.

To wipe everything (for a clean restart):

```bash
docker compose down -v
```

The `-v` flag drops the `rag-data` and `frontend-node-modules` volumes. All uploaded PDFs and chat context are gone.

### Windows (PowerShell)

```powershell
# Stop containers, keep volumes:
docker compose down

# Stop + wipe all persisted PDFs/markdown/SQLite (rag-data and frontend-node-modules):
docker compose down -v
```

---

## Troubleshooting

### "No AI credentials configured" when sending a chat

The backend reads `ANTHROPIC_API_KEY` from `.env` at startup. If it's missing or still has the placeholder value `sk-ant-...`, the first `/api/chat` request fails.

Fix: edit `.env`, put a real key in, restart the backend:
```bash
docker compose restart backend
```

### "AuthenticationError (401)" in the backend logs

The key is syntactically valid but rejected by Anthropic. Check for whitespace, truncated paste, or an expired/revoked key. Regenerate at https://console.anthropic.com/settings/keys.

### Port 5173 or 8000 already in use

Something else on your host is binding the port. Either:
- stop the other process, or
- set `FRONTEND_PORT=5174` / `BACKEND_PORT=8001` in `.env` and `docker compose up` again.

Note that the backend container always listens on 8000 **inside** the Docker network — only the host-side mapping changes.

### Frontend can't reach the backend ("Failed to fetch")

The Vite dev server proxies `/api/*` to `http://backend:8000` over the compose network. If you see fetch errors in the browser console:

1. Confirm the backend container is actually up: `docker compose ps` shows `backend` as `Up`.
2. Confirm `curl http://localhost:8000/api/health` works from the host.
3. If both pass but the browser fails, hard-refresh (Shift+Reload) — the Vite HMR state can get stale after a backend restart.

### PDF stuck in `running` forever

`pymupdf4llm` is CPU-bound and runs in a background thread. A very large PDF (500+ pages) or one with heavily embedded images can take 30+ seconds. Watch `docker compose logs backend` — if there's no traceback and no status change after 2 minutes, the file is likely malformed. The backend marks it `error` with the exception message once the thread raises.

### "Build corpus" returns 409

No PDFs have reached `done` yet. Wait for at least one to finish converting, then retry.

### Backend container restarts in a loop

Check `docker compose logs backend`. The most common cause is an import error after an edit to `backend/app/*.py` — the volume mount is live, so a bad save shows up immediately. Uvicorn's `--reload` tries to recover; if it can't, fix the file and the container settles on the next save.

---

## What's next

- **Change retrieval depth** — pass `top_k` in the chat request body (default `6`). Lower = faster, less context; higher = richer, more tokens.
- **Switch models** — set `AI_MODEL=claude-opus-4-7` in `.env` for harder reasoning, or `claude-haiku-4-5` for cheap high-volume runs.
- **Add streaming** — `backend/app/claude_examples.py` already exposes `stream_chat`; wire it into a new SSE endpoint if you want token-by-token UI.
- **Inspect the SQLite DB directly** — `docker compose exec backend sqlite3 /app/data/rag.db ".tables"`.
