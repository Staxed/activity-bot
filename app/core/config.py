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
    tracked_branches: str = "main"
    ignore_branch_patterns: str = ""
    tracked_github_users: str = "staxed"  # Comma-separated list

    # Event type toggles
    post_commits: bool = True
    post_pull_requests: bool = True
    post_issues: bool = True
    post_releases: bool = True
    post_reviews: bool = True
    post_creations: bool = True
    post_deletions: bool = True
    post_forks: bool = True

    # Action filters (comma-separated)
    post_pr_actions: str = "opened,closed,merged"
    post_issue_actions: str = "opened,closed,reopened"
    post_review_states: str = "approved,changes_requested"

    # Discord configuration
    discord_token: str
    discord_channel_id: int

    # Database configuration
    db_host: str = "postgres"
    db_port: int = 5432
    db_name: str = "activity_bot"
    db_user: str = "activity_bot"
    db_password: str  # Required, no default

    # Quote cache settings
    quote_cache_refresh_minutes: int = 60

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

    @field_validator("quote_cache_refresh_minutes")
    @classmethod
    def validate_quote_refresh_interval(cls, v: int) -> int:
        """Validate quote cache refresh interval (1-1440 minutes / 24 hours)."""
        if not 1 <= v <= 1440:
            raise ConfigError(f"Quote refresh interval must be 1-1440 minutes, got {v}")
        return v

    @property
    def tracked_branches_list(self) -> list[str]:
        """Parse comma-separated tracked branches into a list.

        Returns:
            List of branch names to track (e.g., ['main', 'develop'])
        """
        if not self.tracked_branches:
            return []
        return [branch.strip() for branch in self.tracked_branches.split(",") if branch.strip()]

    @property
    def ignore_branch_patterns_list(self) -> list[str]:
        """Parse comma-separated ignore patterns into a list.

        Returns:
            List of branch patterns to ignore (e.g., ['feature/*', 'hotfix/*'])
        """
        if not self.ignore_branch_patterns:
            return []
        return [
            pattern.strip() for pattern in self.ignore_branch_patterns.split(",") if pattern.strip()
        ]


def get_settings() -> Settings:
    """Get or create the global Settings instance (cached singleton)."""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
