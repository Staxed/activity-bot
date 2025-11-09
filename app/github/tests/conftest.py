"""Shared test fixtures for GitHub integration tests."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.github.client import GitHubClient


@pytest.fixture
def mock_aiohttp_session() -> AsyncMock:
    """Create a mock aiohttp ClientSession.

    Returns:
        AsyncMock configured as aiohttp session
    """
    session = AsyncMock()
    session.get = AsyncMock()
    return session


@pytest.fixture
def sample_push_event() -> dict[str, Any]:
    """Sample GitHub PushEvent for testing.

    Returns:
        Dictionary representing a GitHub PushEvent
    """
    return {
        "id": "12345678900",
        "type": "PushEvent",
        "repo": {"name": "testuser/testrepo"},
        "payload": {
            "ref": "refs/heads/main",
            "commits": [
                {
                    "sha": "abc123def456",
                    "message": "Fix bug in parser\n\nAdded validation logic",
                    "author": {
                        "name": "Test User",
                        "email": "test@example.com",
                        "date": "2025-01-09T12:00:00Z",
                    },
                }
            ],
        },
    }


@pytest.fixture
def github_client() -> GitHubClient:
    """Create a GitHub client instance for testing.

    Returns:
        GitHubClient instance with test token
    """
    return GitHubClient("test_token_12345")
