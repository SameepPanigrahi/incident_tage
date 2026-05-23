from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── LLM ──
    OPENAI_API_KEY: str = "sk-placeholder"
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ── Vector Store ──
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    COLLECTION_NAME: str = "incident_knowledge"
    TOP_K: int = 5

    # ── Chunking ──
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 50

    # ── App ──
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # ── Mock Data ──
    MOCK_DATA_DIR: str = "./mock_data"


@lru_cache()
def get_settings() -> Settings:
    """Return a cached Settings instance (reads .env once)."""
    return Settings()