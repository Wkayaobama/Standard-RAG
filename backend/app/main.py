from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import connect
from app.routes import chat as chat_router
from app.routes import corpus as corpus_router
from app.routes import pdfs as pdfs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.pdf_dir.mkdir(parents=True, exist_ok=True)
    settings.markdown_dir.mkdir(parents=True, exist_ok=True)

    db = await connect(str(settings.db_path))
    app.state.db = db
    app.state.db_lock = asyncio.Lock()
    try:
        yield
    finally:
        await db.close()


app = FastAPI(
    title=settings.project_name,
    lifespan=lifespan,
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pdfs_router.router)
app.include_router(corpus_router.router)
app.include_router(chat_router.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "project": settings.project_name}
