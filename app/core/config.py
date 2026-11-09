from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_path: str = "./survey_assistant.sqlite3"
    session_storage_path: str = "./browser-state"
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_provider: str = "disabled"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    llm_timeout_seconds: float = 30
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
