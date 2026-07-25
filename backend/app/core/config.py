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

    # Deployment environment. Set ENVIRONMENT=production to enable fail-closed
    # checks (a weak SECRET_KEY refuses to boot, API docs are hidden).
    ENVIRONMENT: str = "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in ("production", "prod")

    RATE_LIMIT_ENABLED: bool = True  # token buckets on auth/chat/upload (see core/ratelimit.py)

    # ── Rate-limit thresholds ────────────────────────────────────────────
    # Every limit is tunable per deployment: 0 keeps the built-in default.
    # Names map to rules in core/ratelimit.py as RL_<NAME>_CAPACITY/_WINDOW.
    RL_LOGIN_CAPACITY: int = 0
    RL_LOGIN_WINDOW: int = 0
    RL_SIGNUP_CAPACITY: int = 0
    RL_SIGNUP_WINDOW: int = 0
    RL_REGISTER_CAPACITY: int = 0
    RL_REGISTER_WINDOW: int = 0
    RL_UPLOAD_CAPACITY: int = 0
    RL_UPLOAD_WINDOW: int = 0
    RL_CONNECTOR_CAPACITY: int = 0
    RL_CONNECTOR_WINDOW: int = 0
    RL_CHAT_CAPACITY: int = 0
    RL_CHAT_WINDOW: int = 0
    RL_SQL_CAPACITY: int = 0
    RL_SQL_WINDOW: int = 0
    RL_SEARCH_CAPACITY: int = 0
    RL_SEARCH_WINDOW: int = 0
    RL_WF_RUN_CAPACITY: int = 0
    RL_WF_RUN_WINDOW: int = 0
    RL_REPORT_CAPACITY: int = 0
    RL_REPORT_WINDOW: int = 0
    RL_ORG_DEL_CAPACITY: int = 0
    RL_ORG_DEL_WINDOW: int = 0

    # ── Upload limits ────────────────────────────────────────────────────
    # Without a cap, one request can fill the disk. Enforced while streaming,
    # so an oversized body is refused before it is written.
    # SQL Studio is a developer-facing tool, so a deployment may choose to
    # show database errors there. Off by default: they describe the schema.
    SQL_SHOW_DB_ERRORS: bool = False

    MAX_UPLOAD_MB: int = 25
    MAX_UPLOAD_FILENAME: int = 255

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

    # Platform owner(s) — the vendor running this multi-tenant deployment.
    # Comma-separated emails. These accounts get the Workspaces console: list,
    # suspend and delete ANY company workspace. Empty (the default) disables
    # the console entirely, so a stolen demo login can never reach it.
    PLATFORM_OWNER_EMAILS: str = ""

    @property
    def platform_owners(self) -> set[str]:
        return {e.strip().lower() for e in self.PLATFORM_OWNER_EMAILS.split(",") if e.strip()}

    def is_platform_owner(self, email: str | None) -> bool:
        owners = self.platform_owners
        return bool(owners and (email or "").lower() in owners)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


DEV_SECRET = "dev-secret-change-in-production"


def verify_production_secrets(s: "Settings") -> list[str]:
    """Return blocking misconfigurations for a production deployment.

    Signing tokens with a public default means anyone who has read this
    repository can mint an admin session, so production refuses to start
    rather than running in a state that only *looks* secure."""
    problems: list[str] = []
    if not s.is_production:
        return problems
    if s.SECRET_KEY == DEV_SECRET or len(s.SECRET_KEY) < 32:
        problems.append(
            "SECRET_KEY is the shipped default or too short — set a random value "
            "of at least 32 characters (e.g. `python -c \"import secrets;print(secrets.token_urlsafe(48))\"`)."
        )
    if s.CORS_ORIGINS.strip() == "*":
        problems.append("CORS_ORIGINS must not be '*' in production.")
    return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
