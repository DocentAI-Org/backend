from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DocentAI API"
    app_version: str = "0.1.0"
    allowed_origins: str = "http://localhost:3000"

    # Database and Supabase (research R7, R8, R9)
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres"
    )
    supabase_url: str = "http://127.0.0.1:54321"
    supabase_service_role_key: str | None = None
    supabase_jwt_secret: str | None = None
    jwt_audience: str = "authenticated"
    storage_bucket: str = "course-material"
    signed_url_ttl_seconds: int = 300
    pseudonym_email_domain: str = "students.docentai.invalid"

    # LLM layer (research R1-R3, R12)
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_chat_model: str = "qwen2.5:7b"
    llm_embedding_model: str = "bge-m3"
    embedding_dimensions: int = 1024
    llm_timeout_seconds: float = 60.0
    llm_price_input_per_mtok: float = 0.0
    llm_price_output_per_mtok: float = 0.0

    # Retrieval and context (research R5)
    retrieval_top_k: int = 4
    retrieval_min_similarity: float = 0.55
    history_max_messages: int = 6

    # Limits (research R10, R11)
    daily_message_limit: int = 30
    daily_reset_timezone: str = "Europe/Madrid"
    max_upload_mb: int = 20
    tutor_language: str = "es"
    # A repeated mistake (specs/005, provisional): the same error type and topic this
    # many times within this many days, counting the current one.
    repeated_mistake_count: int = 3
    repeated_mistake_days: int = 30
    recover_interrupted_on_startup: bool = True

    # Study consent (specs/002): bump when the approved consent text changes.
    consent_version: str = "2026-10"

    # Privacy (research R12)
    log_pseudonym_secret: str = "change-me"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def allowed_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
