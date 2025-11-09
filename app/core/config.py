"""Configuration management using Pydantic Settings."""

from typing import ClassVar

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.shared.exceptions import ConfigError

# Singleton instance
_settings: "Settings | None" = None


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # GitHub configuration
    github_token: str
    github_repos: str
    private_repos: str = ""

    # Discord configuration
    discord_token: str
    discord_channel_id: int

    # Application settings
    log_level: str = "INFO"
    state_file_path: str = "data/state.json"
    poll_interval_minutes: int = 5
    app_version: str = "0.1.0"
    environment: str = "development"

    # Valid log levels
    VALID_LOG_LEVELS: ClassVar[set[str]] = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the allowed values."""
        v_upper = v.upper()
        if v_upper not in cls.VALID_LOG_LEVELS:
            raise ConfigError(
                f"Invalid log level: {v}. Must be one of {', '.join(cls.VALID_LOG_LEVELS)}"
            )
        return v_upper

    @field_validator("poll_interval_minutes")
    @classmethod
    def validate_poll_interval(cls, v: int) -> int:
        """Validate poll interval is within acceptable range (1-60 minutes)."""
        if not 1 <= v <= 60:
            raise ConfigError(f"Poll interval must be between 1 and 60 minutes, got {v}")
        return v

    @property
    def github_repo_list(self) -> list[str]:
        """Parse comma-separated github_repos into a list."""
        return [repo.strip() for repo in self.github_repos.split(",") if repo.strip()]

    @property
    def private_repo_list(self) -> list[str]:
        """Parse comma-separated private_repos into a list."""
        if not self.private_repos:
            return []
        return [repo.strip() for repo in self.private_repos.split(",") if repo.strip()]


def get_settings() -> Settings:
    """Get or create the global Settings instance (cached singleton)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
