"""Tests for app.core.config module."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.shared.exceptions import ConfigError


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that settings load correctly from environment variables."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.github_token == "test_token"
    assert settings.discord_token == "discord_token"
    assert settings.discord_channel_id == 123456789


def test_settings_default_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that default values are applied correctly."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.log_level == "INFO"
    assert settings.state_file_path == "data/state.json"
    assert settings.poll_interval_minutes == 5
    assert settings.app_version == "0.1.0"
    assert settings.environment == "development"


def test_settings_log_level_validation_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that valid log levels are accepted."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")

    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    for level in valid_levels:
        monkeypatch.setenv("LOG_LEVEL", level)
        settings = Settings()  # type: ignore[call-arg]
        assert settings.log_level == level


def test_settings_log_level_validation_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that invalid log level raises ConfigError."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("LOG_LEVEL", "INVALID")

    with pytest.raises(ConfigError, match="Invalid log level"):
        Settings()  # type: ignore[call-arg]


def test_settings_poll_interval_validation_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that poll intervals 1-60 are accepted."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")

    for interval in [1, 30, 60]:
        monkeypatch.setenv("POLL_INTERVAL_MINUTES", str(interval))
        settings = Settings()  # type: ignore[call-arg]
        assert settings.poll_interval_minutes == interval


def test_settings_poll_interval_validation_too_low(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that poll interval < 1 raises ConfigError."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("POLL_INTERVAL_MINUTES", "0")

    with pytest.raises(ConfigError, match="Poll interval must be between 1 and 60"):
        Settings()  # type: ignore[call-arg]


def test_settings_poll_interval_validation_too_high(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that poll interval > 60 raises ConfigError."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("POLL_INTERVAL_MINUTES", "61")

    with pytest.raises(ConfigError, match="Poll interval must be between 1 and 60"):
        Settings()  # type: ignore[call-arg]


def test_settings_missing_required_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing required field raises ValidationError."""
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    # Missing GITHUB_TOKEN

    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_get_settings_caching(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that get_settings() returns cached instance."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")

    settings1 = get_settings()
    settings2 = get_settings()

    assert settings1 is settings2
