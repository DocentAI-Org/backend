from functools import lru_cache
from typing import Literal, NamedTuple

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["ollama", "openai", "anthropic"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]
# What the model is asked to do (specs/014); each can have its own provider and model.
Task = Literal["tutor", "feedback", "review", "questions"]


class Route(NamedTuple):
    provider: Provider
    model: str
    effort: Effort | None
    # A course's own (specs/019); None keeps the call's temperature and the server's
    # max tokens.
    temperature: float | None = None
    max_tokens: int | None = None


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

    # LLM layer (research R1-R3, R12; providers per task, specs/014). A task's own
    # provider, model and effort override the defaults.
    llm_provider: Provider = "ollama"
    llm_chat_model: str = Field(
        "qwen2.5:7b", validation_alias=AliasChoices("LLM_MODEL", "LLM_CHAT_MODEL")
    )
    llm_effort: Effort | None = None
    llm_tutor_provider: Provider | None = None
    llm_tutor_model: str | None = None
    llm_tutor_effort: Effort | None = None
    llm_feedback_provider: Provider | None = None
    llm_feedback_model: str | None = None
    llm_feedback_effort: Effort | None = None
    llm_review_provider: Provider | None = None
    llm_review_model: str | None = None
    llm_review_effort: Effort | None = None
    llm_questions_provider: Provider | None = None
    llm_questions_model: str | None = None
    llm_questions_effort: Effort | None = None
    ollama_base_url: str = Field(
        "http://localhost:11434/v1",
        validation_alias=AliasChoices("OLLAMA_BASE_URL", "LLM_BASE_URL"),
    )
    ollama_api_key: str = Field(
        "ollama", validation_alias=AliasChoices("OLLAMA_API_KEY", "LLM_API_KEY")
    )
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    # Server-side fallback when a Claude model declines; "" turns it off.
    llm_anthropic_fallbacks: str = "default"
    llm_max_tokens: int = 16000
    # Anthropic has no embeddings API (specs/014).
    llm_embedding_provider: Literal["ollama", "openai"] = "ollama"
    llm_embedding_model: str = "bge-m3"
    embedding_dimensions: int = 1024
    llm_timeout_seconds: float = 60.0
    # USD per million tokens, input and output, by model; others use the fallback.
    llm_prices: dict[str, tuple[float, float]] = {}
    llm_price_input_per_mtok: float = 0.0
    llm_price_output_per_mtok: float = 0.0
    # Exercise feedback must classify the same mistake the same way (spec 009).
    llm_feedback_temperature: float = 0.0

    # Retrieval and context (research R5)
    retrieval_top_k: int = 4
    retrieval_min_similarity: float = 0.55
    # Exercise statements are short and symbolic: lower similarity (spec 009 US3).
    retrieval_min_similarity_exercises: float = 0.40
    history_max_messages: int = 6

    # Limits (research R10, R11)
    daily_message_limit: int = 30
    daily_reset_timezone: str = "Europe/Madrid"
    max_upload_mb: int = 20
    tutor_language: str = "es"
    # Adaptive quizzes (specs/006, provisional): questions per quiz, starting
    # level (1-3) and the right or wrong answers in a row that move the level.
    quiz_length: int = 5
    quiz_start_level: int = 2
    quiz_streak: int = 2
    # Repeated mistakes, adaptation and mastery are pedagogical criteria in the
    # database since specs/015, set by the admin and per course by the teacher.
    recover_interrupted_on_startup: bool = True

    # Study consent (specs/002): bump when the approved consent text changes.
    consent_version: str = "2026-10"

    # Privacy (research R12)
    log_pseudonym_secret: str = "change-me"
    # Study export ids (specs/011): a different key, so the export cannot be joined
    # with the interaction logs without it.
    study_export_secret: str = "change-me-too"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    def route(self, task: Task) -> Route:
        """The provider, model and effort for a task: its own, or the defaults."""
        return Route(
            getattr(self, f"llm_{task}_provider") or self.llm_provider,
            getattr(self, f"llm_{task}_model") or self.llm_chat_model,
            getattr(self, f"llm_{task}_effort") or self.llm_effort,
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
