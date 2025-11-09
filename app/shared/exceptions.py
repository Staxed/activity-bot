"""Custom exception hierarchy for Activity Bot."""


class ActivityBotError(Exception):
    """Base exception for all bot errors."""

    pass


class ConfigError(ActivityBotError):
    """Raised when configuration validation fails."""

    pass


class GitHubAPIError(ActivityBotError):
    """Raised when GitHub API requests fail."""

    pass


class DiscordAPIError(ActivityBotError):
    """Raised when Discord API requests fail."""

    pass


class StateError(ActivityBotError):
    """Raised when state persistence operations fail."""

    pass
