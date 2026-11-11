from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_DASHBOARD_TOKEN_LENGTH = 32


class ConfigurationError(RuntimeError):
    """Raised when required runtime security configuration is invalid."""


def validate_auth_settings(settings: "Settings") -> None:
    if not settings.dashboard_auth_required:
        return
    token = settings.dashboard_auth_token
    if not token:
        raise ConfigurationError("DASHBOARD_AUTH_TOKEN is required when dashboard authentication is enabled.")
    if len(token) < MIN_DASHBOARD_TOKEN_LENGTH:
        raise ConfigurationError(
            f"DASHBOARD_AUTH_TOKEN must be at least {MIN_DASHBOARD_TOKEN_LENGTH} characters."
        )


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
    approved_survey_domains: tuple[str, ...] = ()
    dashboard_auth_token: str | None = None
    dashboard_auth_required: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
