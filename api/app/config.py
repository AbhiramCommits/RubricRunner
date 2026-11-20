from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from the environment (and .env)."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://rubric:rubric@localhost:5434/rubricrunner"
    llm_provider: str = "mock"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    openai_model: str = "gpt-4o"
    api_base_url: str = "http://localhost:8000"

    # Batch grading worker pool size.
    grading_concurrency: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()
