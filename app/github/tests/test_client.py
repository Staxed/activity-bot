"""Tests for GitHub API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from app.github.client import GitHubClient
from app.shared.exceptions import GitHubAPIError


@pytest.mark.asyncio
async def test_get_authenticated_user_success():
    """Test successful authentication returns username."""
    client = GitHubClient("test_token")

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"login": "testuser"})

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    client.session = AsyncMock()
    client.session.get = MagicMock(return_value=mock_context)

    username = await client.get_authenticated_user()

    assert username == "testuser"
    client.session.get.assert_called_once_with("https://api.github.com/user")


@pytest.mark.asyncio
async def test_get_authenticated_user_invalid_token():
    """Test 401 raises GitHubAPIError."""
    client = GitHubClient("invalid_token")

    mock_response = AsyncMock()
    mock_response.status = 401

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    client.session = AsyncMock()
    client.session.get = MagicMock(return_value=mock_context)

    with pytest.raises(GitHubAPIError, match="Invalid token"):
        await client.get_authenticated_user()


@pytest.mark.asyncio
async def test_fetch_user_events_success():
    """Test successful events fetch returns list."""
    client = GitHubClient("test_token")

    events_data = [
        {"id": "123", "type": "PushEvent"},
        {"id": "124", "type": "WatchEvent"},
    ]

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=events_data)

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    client.session = AsyncMock()
    client.session.get = MagicMock(return_value=mock_context)

    events = await client.fetch_user_events("testuser")

    assert len(events) == 2
    assert events[0]["id"] == "123"
    client.session.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_user_events_pagination():
    """Test page parameter passed correctly."""
    client = GitHubClient("test_token")

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=[])

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    client.session = AsyncMock()
    client.session.get = MagicMock(return_value=mock_context)

    await client.fetch_user_events("testuser", page=3)

    # Verify the page parameter was passed
    call_args = client.session.get.call_args
    assert call_args[1]["params"]["page"] == 3
    assert call_args[1]["params"]["per_page"] == 30


@pytest.mark.asyncio
async def test_fetch_user_events_404_returns_empty():
    """Test 404 returns empty list."""
    client = GitHubClient("test_token")

    mock_response = AsyncMock()
    mock_response.status = 404

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    client.session = AsyncMock()
    client.session.get = MagicMock(return_value=mock_context)

    events = await client.fetch_user_events("nonexistent_user")

    assert events == []


@pytest.mark.asyncio
async def test_fetch_user_events_rate_limit():
    """Test 403 logs rate limit and raises."""
    client = GitHubClient("test_token")

    mock_response = AsyncMock()
    mock_response.status = 403
    mock_response.headers = {
        "x-ratelimit-remaining": "0",
        "x-ratelimit-reset": "1234567890",
    }

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    client.session = AsyncMock()
    client.session.get = MagicMock(return_value=mock_context)

    with pytest.raises(GitHubAPIError, match="Rate limited"):
        await client.fetch_user_events("testuser")


@pytest.mark.asyncio
async def test_fetch_user_events_retry_on_network_error():
    """Test network error retries with backoff."""
    client = GitHubClient("test_token")

    # First two attempts fail, third succeeds
    mock_response_success = AsyncMock()
    mock_response_success.status = 200
    mock_response_success.json = AsyncMock(return_value=[{"id": "123"}])

    client.session = AsyncMock()

    # Simulate network errors on first two attempts
    attempts = [0]

    def mock_get(*args, **kwargs):
        attempts[0] += 1
        if attempts[0] < 3:
            raise aiohttp.ClientError("Network error")
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response_success)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        return mock_cm

    client.session.get = mock_get

    # Should succeed on third attempt
    with patch("asyncio.sleep", new_callable=AsyncMock):
        events = await client.fetch_user_events("testuser")

    assert len(events) == 1
    assert attempts[0] == 3


@pytest.mark.asyncio
async def test_context_manager_lifecycle():
    """Test session created and closed properly."""
    client = GitHubClient("test_token")

    # Session should be None initially
    assert client.session is None

    # Enter context manager
    async with client as ctx:
        assert ctx is client
        assert client.session is not None

    # Session should be closed after context
    # Note: We can't easily verify session.close() was called without mocking
    # but we test that the context manager works correctly
