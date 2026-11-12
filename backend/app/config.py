from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "standard-rag"

    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"

    data_dir: Path = Path("/app/data")
    db_path: Path = Path("/app/data/rag.db")
    pdf_dir: Path = Path("/app/data/pdfs")
    markdown_dir: Path = Path("/app/data/markdown")
    corpus_path: Path = Path("/app/data/corpus.md")

    allowed_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
