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
        extra="allow",
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
    post_stars: bool = True
    post_issue_comments: bool = True
    post_pr_review_comments: bool = True
    post_commit_comments: bool = True
    post_members: bool = True
    post_wiki_pages: bool = True
    post_public_events: bool = True
    post_discussions: bool = True

    # Action filters (comma-separated)
    post_pr_actions: str = "opened,closed,merged"
    post_issue_actions: str = "opened,closed,reopened"
    post_review_states: str = "approved,changes_requested"
    issue_comment_actions: str = ""
    pr_review_comment_actions: str = ""
    commit_comment_actions: str = ""
    member_actions: str = ""
    wiki_actions: str = ""
    discussion_actions: str = ""

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

    # Stats and achievements settings
    enable_stats: bool = True
    stats_refresh_interval_minutes: int = 60
    stats_timezone: str = "America/New_York"

    # Achievement thresholds
    achievement_night_owl_threshold: int = 5
    achievement_early_bird_threshold: int = 5
    achievement_daily_dozen_threshold: int = 12
    achievement_weekend_warrior_threshold: int = 10
    achievement_century_month_threshold: int = 100

    # Summary times (HH:MM format)
    daily_summary_time: str = "09:00"
    weekly_summary_time: str = "09:00"
    monthly_summary_time: str = "09:00"

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

    @field_validator("stats_refresh_interval_minutes")
    @classmethod
    def validate_stats_refresh_interval(cls, v: int) -> int:
        """Validate stats cache refresh interval (1-1440 minutes / 24 hours)."""
        if not 1 <= v <= 1440:
            raise ConfigError(f"Stats refresh interval must be 1-1440 minutes, got {v}")
        return v

    @field_validator(
        "achievement_night_owl_threshold",
        "achievement_early_bird_threshold",
        "achievement_daily_dozen_threshold",
        "achievement_weekend_warrior_threshold",
        "achievement_century_month_threshold",
    )
    @classmethod
    def validate_achievement_thresholds(cls, v: int) -> int:
        """Validate achievement thresholds (1-1000)."""
        if not 1 <= v <= 1000:
            raise ConfigError(f"Achievement threshold must be between 1 and 1000, got {v}")
        return v

    def model_post_init(self, __context: object) -> None:
        """Load dynamic fields from environment variables.

        Scans environment for keys ending in _IGNORED_REPOS and stores them
        as lowercase attributes for per-user repository blacklists.
        """
        import os

        for key, value in os.environ.items():
            if key.endswith("_IGNORED_REPOS"):
                # Store as lowercase attribute (e.g., USER1_IGNORED_REPOS → user1_ignored_repos)
                setattr(self, key.lower(), value)

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

    @property
    def tracked_users_list(self) -> list[str]:
        """Parse comma-separated tracked users into a list.

        Returns:
            List of GitHub usernames to track (e.g., ['user1', 'user2'])
        """
        if not self.tracked_github_users:
            return []
        return [user.strip() for user in self.tracked_github_users.split(",") if user.strip()]

    @property
    def pr_actions_list(self) -> list[str]:
        """Parse comma-separated PR actions into a list.

        Returns:
            List of PR actions to post (e.g., ['opened', 'closed', 'merged'])
        """
        if not self.post_pr_actions:
            return []
        return [action.strip() for action in self.post_pr_actions.split(",") if action.strip()]

    @property
    def issue_actions_list(self) -> list[str]:
        """Parse comma-separated issue actions into a list.

        Returns:
            List of issue actions to post (e.g., ['opened', 'closed', 'reopened'])
        """
        if not self.post_issue_actions:
            return []
        return [action.strip() for action in self.post_issue_actions.split(",") if action.strip()]

    @property
    def review_states_list(self) -> list[str]:
        """Parse comma-separated review states into a list.

        Returns:
            List of review states to post (e.g., ['approved', 'changes_requested'])
        """
        if not self.post_review_states:
            return []
        return [state.strip() for state in self.post_review_states.split(",") if state.strip()]

    @property
    def allowed_issue_comment_actions_list(self) -> list[str]:
        """Parse issue comment actions from comma-separated string.

        Returns:
            List of allowed actions for issue comments (e.g., ['created', 'edited'])
        """
        if not self.issue_comment_actions:
            return []
        return [
            action.strip() for action in self.issue_comment_actions.split(",") if action.strip()
        ]

    @property
    def allowed_pr_review_comment_actions_list(self) -> list[str]:
        """Parse PR review comment actions from comma-separated string.

        Returns:
            List of allowed actions for PR review comments (e.g., ['created', 'edited'])
        """
        if not self.pr_review_comment_actions:
            return []
        return [
            action.strip() for action in self.pr_review_comment_actions.split(",") if action.strip()
        ]

    @property
    def allowed_commit_comment_actions_list(self) -> list[str]:
        """Parse commit comment actions from comma-separated string.

        Returns:
            List of allowed actions for commit comments (e.g., ['created', 'edited'])
        """
        if not self.commit_comment_actions:
            return []
        return [
            action.strip() for action in self.commit_comment_actions.split(",") if action.strip()
        ]

    @property
    def allowed_member_actions_list(self) -> list[str]:
        """Parse member actions from comma-separated string.

        Returns:
            List of allowed actions for members (e.g., ['added', 'removed'])
        """
        if not self.member_actions:
            return []
        return [action.strip() for action in self.member_actions.split(",") if action.strip()]

    @property
    def allowed_wiki_actions_list(self) -> list[str]:
        """Parse wiki actions from comma-separated string.

        Returns:
            List of allowed actions for wiki pages (e.g., ['created', 'edited'])
        """
        if not self.wiki_actions:
            return []
        return [action.strip() for action in self.wiki_actions.split(",") if action.strip()]

    @property
    def allowed_discussion_actions_list(self) -> list[str]:
        """Parse discussion actions from comma-separated string.

        Returns:
            List of allowed actions for discussions (e.g., ['created', 'answered'])
        """
        if not self.discussion_actions:
            return []
        return [action.strip() for action in self.discussion_actions.split(",") if action.strip()]

    def get_user_ignored_repos(self, username: str) -> list[str]:
        """Get list of ignored repositories for a specific user.

        Reads {USERNAME_UPPER}_IGNORED_REPOS environment variable and parses
        comma-separated repository patterns.

        Args:
            username: GitHub username (will be uppercased for env var lookup)

        Returns:
            List of repository patterns to ignore (e.g., ['org/repo1', 'user/*'])
        """
        import os

        env_var_name = f"{username.upper()}_IGNORED_REPOS"
        ignored_repos = os.environ.get(env_var_name, "")
        if not ignored_repos:
            return []
        return [repo.strip() for repo in ignored_repos.split(",") if repo.strip()]


def get_settings() -> Settings:
    """Get or create the global Settings instance (cached singleton)."""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings
