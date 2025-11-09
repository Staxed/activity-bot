"""Shared pytest fixtures for Activity Bot tests."""

from pathlib import Path

import pytest

from app.core.config import Settings


@pytest.fixture
def temp_state_file(tmp_path: Path) -> Path:
    """Create a temporary state file path for testing.

    Args:
        tmp_path: pytest's temporary directory fixture

    Returns:
        Path to temporary state.json file
    """
    return tmp_path / "state.json"


@pytest.fixture
def mock_settings(temp_state_file: Path) -> Settings:
    """Create Settings instance with test values.

    Args:
        temp_state_file: Temporary state file path

    Returns:
        Settings instance configured for testing
    """
    return Settings(
        github_token="test_github_token",
        github_repos="owner/repo1,owner/repo2",
        private_repos="owner/private-repo",
        discord_token="test_discord_token",
        discord_channel_id=123456789012345678,
        log_level="INFO",
        state_file_path=str(temp_state_file),
        poll_interval_minutes=5,
        app_version="0.1.0",
        environment="test",
    )


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    """Reset the global settings cache before and after each test.

    This ensures tests don't interfere with each other via cached settings.
    """
    # Import here to avoid circular dependencies
    import app.core.config

    # Clear cache before test
    app.core.config._settings = None

    yield

    # Clear cache after test
    app.core.config._settings = None
