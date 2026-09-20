from functools import lru_cache

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )

    app_name: str = "OpsPilot"
    app_version: str = "0.1.0"
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("environment", "APP_ENV", "ENVIRONMENT"),
    )
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+asyncpg://opspilot@localhost:5432/opspilot"
    )
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    cors_origins: str = "http://localhost:5173"

    jwt_secret: str = "dev-placeholder"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=15, ge=1)
    refresh_token_expire_days: int = Field(default=7, ge=1)
    incident_correlation_window_minutes: int = Field(default=5, ge=1, le=1440)
    simulator_enabled: bool = False
    simulator_tick_interval_seconds: float = Field(default=1.0, gt=0, le=3600)
    simulator_random_seed: int = 20260908
    celery_result_backend: str | None = None
    celery_worker_concurrency: int = Field(default=1, ge=1, le=64)
    celery_worker_prefetch_multiplier: int = Field(default=1, ge=1, le=32)
    celery_task_max_retries: int = Field(default=3, ge=0, le=10)
    celery_task_soft_time_limit: int = Field(default=60, ge=1, le=3600)
    celery_task_time_limit: int = Field(default=120, ge=1, le=7200)
    ai_provider: str = "mock"
    ai_model: str = "mock-v1"
    ai_api_key: str | None = None
    ai_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    ai_max_output_tokens: int = Field(default=2000, ge=128, le=16000)
    ai_max_tool_calls: int = Field(default=5, ge=1, le=50)
    ai_max_investigation_seconds: int = Field(default=30, ge=1, le=300)
    ai_max_retries: int = Field(default=2, ge=0, le=5)
    ai_max_alerts: int = Field(default=20, ge=1, le=100)
    ai_max_events: int = Field(default=50, ge=1, le=200)
    ai_max_logs: int = Field(default=50, ge=1, le=200)
    ai_max_metric_points: int = Field(default=100, ge=1, le=500)
    ai_max_deployments: int = Field(default=20, ge=1, le=100)
    ai_max_context_chars: int = Field(default=50000, ge=1000, le=200000)
    ai_prompt_version: str = "v1"
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "opspilot_knowledge"
    embedding_provider: str = "mock"
    embedding_model: str = "mock-embedding-v1"
    embedding_dimension: int = Field(default=64, ge=8, le=4096)
    embedding_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    rag_chunk_size: int = Field(default=1200, ge=200, le=10000)
    rag_chunk_overlap: int = Field(default=150, ge=0, le=2000)
    rag_top_k: int = Field(default=5, ge=1, le=20)
    rag_max_results: int = Field(default=10, ge=1, le=50)
    rag_max_context_chars: int = Field(default=12000, ge=1000, le=100000)
    max_simulated_replicas: int = Field(default=20, ge=1, le=1000)
    max_simulated_workers: int = Field(default=50, ge=1, le=1000)
    tool_execution_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    tool_max_retries: int = Field(default=2, ge=0, le=5)
    approval_expiration_minutes: int = Field(default=60, ge=1, le=10080)
    verification_max_attempts: int = Field(default=3, ge=1, le=10)
    verification_interval_seconds: float = Field(default=1.0, gt=0, le=300)
    verification_consecutive_successes: int = Field(default=1, ge=1, le=10)

    @property
    def effective_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    dev_admin_email: str = "admin@opspilot.local"
    dev_admin_password: str = ""
    dev_engineer_email: str = "engineer@opspilot.local"
    dev_engineer_password: str = ""
    dev_viewer_email: str = "viewer@opspilot.local"
    dev_viewer_password: str = ""

    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
        if self.environment.lower() == "production" and (
            self.jwt_secret == "dev-placeholder"
            or self.jwt_secret.startswith("replace-with-")
            or len(self.jwt_secret) < 32
        ):
            raise ValueError("JWT_SECRET must be a strong production secret")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
