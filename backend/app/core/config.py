"""Central configuration. Every setting has a dev-safe default so the
platform boots with zero external services (SQLite + in-memory vectors + mock LLM)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "EAIOS — Enterprise AI Operating System"
    VERSION: str = "0.1.0"
    SECRET_KEY: str = "dev-secret-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    DATABASE_URL: str = "sqlite:///./eaios.db"
    QDRANT_URL: str = ""            # empty → in-memory vector store
    REDIS_URL: str = ""

    LLM_PROVIDER: str = "auto"      # auto | mock | ollama | openai | anthropic
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"  # any OpenAI-compatible endpoint (Groq, vLLM…)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5"

    EMBEDDING_PROVIDER: str = "auto"  # auto | hash | ollama | sentence-transformers
    EMBEDDING_DIM: int = 384

    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    UPLOAD_DIR: str = "./uploads"

    RATE_LIMIT_ENABLED: bool = True  # token buckets on auth/chat/upload (see core/ratelimit.py)

    # Agent routing: auto = LLM semantic router when a real model is available,
    # regex otherwise · llm = always try the LLM router · regex = never use it
    ROUTER_MODE: str = "auto"

    TEMPERATURE: float = 0.3  # generation temperature for all providers (0.0–1.0)

    # LangGraph-style checkpointer: persist orchestrator graph state to the DB
    # after every super-step (keyed by conversation) so interrupted runs resume
    GRAPH_CHECKPOINTS: bool = True

    # Scheduled workflows: background loop firing trigger=schedule automations
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_INTERVAL: int = 60  # seconds between due-checks

    # Compliance: auto-purge conversations older than N days (0 = keep forever)
    RETENTION_DAYS: int = 0

    # Blob storage: local disk by default. Set SUPABASE_URL + SUPABASE_SERVICE_KEY
    # to ALSO mirror uploaded files to a Supabase Storage bucket so they survive
    # container redeploys (the DB already persists via DATABASE_URL).
    SUPABASE_URL: str = ""            # e.g. https://<ref>.supabase.co
    SUPABASE_SERVICE_KEY: str = ""    # service_role key (secret) — server-side only
    STORAGE_BUCKET: str = "documents"

    # One-click "Connect with Google" for the Connectors app (Drive/Gmail).
    # Create an OAuth *Web application* client ID in Google Cloud Console,
    # add your site to Authorized JavaScript origins, and set it here.
    # Empty → the Connectors UI falls back to paste-an-access-token.
    GOOGLE_CLIENT_ID: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
