from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        extra="ignore",
    )

    # LLM
    llm_base_url: str = "http://localhost:1234/v1"
    llm_model: str = "qwen2.5-14b-instruct"
    llm_api_key: str = "lm-studio"
    llm_temperature: float = 0.2
    llm_timeout_s: float = 300

    # Embeddings / RAG
    embedding_provider: Literal["fastembed", "openai"] = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    sparse_model: str = "Qdrant/bm25"
    reranker_model: str | None = "Xenova/ms-marco-MiniLM-L-6-v2"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "documents"
    chunk_size: int = 1000
    chunk_overlap: int = 150
    retrieval_candidates: int = 24
    retrieval_top_k: int = 6

    # Databases
    database_url: str = "postgresql+asyncpg://connecter:connecter@localhost:5433/connecter"
    checkpointer: Literal["postgres", "memory"] = "postgres"

    # MCP servers
    file_workspace: Path = Path.home() / "AI-Agent-Workspace"
    email_address: str = ""
    email_password: str = ""
    email_imap_host: str = "imap.gmail.com"
    email_imap_port: int = 993
    email_smtp_host: str = "smtp.gmail.com"
    email_smtp_port: int = 465
    email_drafts_folder: str = "[Gmail]/Drafts"
    browser_headless: bool = False

    # Agent
    agent_max_steps: int = 15
    agent_history_messages: int = 10
    tool_result_max_chars: int = 6000

    # App
    data_dir: Path = BACKEND_DIR / ".data"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("reranker_model", mode="before")
    @classmethod
    def _empty_is_none(cls, v):
        return v or None

    @property
    def checkpointer_dsn(self) -> str:
        # psycopg (used by the LangGraph checkpointer) wants a plain postgres URL.
        return self.database_url.replace("+asyncpg", "")

    @property
    def documents_dir(self) -> Path:
        return self.file_workspace / "documents"

    @property
    def screenshots_dir(self) -> Path:
        return self.data_dir / "screenshots"


@lru_cache
def get_settings() -> Settings:
    return Settings()
