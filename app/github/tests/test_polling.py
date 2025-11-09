"""Tests for GitHub polling service."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.core.state import StateManager
from app.github.client import GitHubClient
from app.github.polling import GitHubPollingService
from app.shared.exceptions import GitHubPollingError


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.poll_interval_minutes = 5
    settings.state_file_path = "test_state.json"
    return settings


@pytest.fixture
def mock_client() -> GitHubClient:
    """Create mock GitHub client."""
    client = MagicMock(spec=GitHubClient)
    client.fetch_user_events = AsyncMock()
    return client


@pytest.fixture
def mock_state() -> StateManager:
    """Create mock state manager."""
    state = MagicMock(spec=StateManager)
    state.get_last_event_id = MagicMock()
    state.set_last_event_id = MagicMock()
    return state


@pytest.mark.asyncio
async def test_poll_once_first_run(
    mock_client: GitHubClient, mock_state: StateManager, mock_settings: Settings
) -> None:
    """Test first run stores event ID without processing."""
    mock_state.get_last_event_id.return_value = None
    mock_client.fetch_user_events.return_value = [{"id": "123", "type": "PushEvent"}]

    service = GitHubPollingService(mock_client, mock_state, mock_settings, "testuser")
    count = await service.poll_once()

    assert count == 0
    mock_state.set_last_event_id.assert_called_once_with("123")


@pytest.mark.asyncio
async def test_poll_once_subsequent_run(
    mock_client: GitHubClient, mock_state: StateManager, mock_settings: Settings
) -> None:
    """Test subsequent run processes new events."""
    mock_state.get_last_event_id.return_value = "100"

    # Mock new events with IDs greater than 100
    new_events: list[dict[str, Any]] = [
        {
            "id": "105",
            "type": "PushEvent",
            "repo": {"name": "owner/repo"},
            "payload": {
                "ref": "refs/heads/main",
                "commits": [
                    {
                        "sha": "abc123",
                        "message": "Test commit",
                        "author": {
                            "name": "User",
                            "email": "user@example.com",
                            "date": "2025-01-09T12:00:00Z",
                        },
                    }
                ],
            },
        }
    ]

    # Mock _fetch_events_until_last_id to return new events
    service = GitHubPollingService(mock_client, mock_state, mock_settings, "testuser")
    service._fetch_events_until_last_id = AsyncMock(return_value=new_events)

    count = await service.poll_once()

    assert count == 1
    mock_state.set_last_event_id.assert_called_once_with("105")


@pytest.mark.asyncio
async def test_poll_once_pagination(
    mock_client: GitHubClient, mock_state: StateManager, mock_settings: Settings
) -> None:
    """Test multi-page fetch until last_event_id found."""
    mock_state.get_last_event_id.return_value = "95"

    # Page 1: Events 100-99
    page1_events = [{"id": "100", "type": "PushEvent"}, {"id": "99", "type": "PushEvent"}]
    # Page 2: Events 98-96
    page2_events = [
        {"id": "98", "type": "PushEvent"},
        {"id": "97", "type": "PushEvent"},
        {"id": "96", "type": "PushEvent"},
    ]

    # Mock fetch to return pages sequentially, then empty lists for subsequent calls
    mock_client.fetch_user_events.side_effect = [page1_events, page2_events, [], [], [], [], [], [], [], []]

    service = GitHubPollingService(mock_client, mock_state, mock_settings, "testuser")
    collected = await service._fetch_events_until_last_id("95")

    # Should have collected events until it found 95 (which isn't in our pages)
    assert len(collected) == 5  # All events from both pages
    assert mock_client.fetch_user_events.call_count >= 2


@pytest.mark.asyncio
async def test_poll_once_consecutive_failures(
    mock_client: GitHubClient, mock_state: StateManager, mock_settings: Settings
) -> None:
    """Test failure counter increments and raises after 2."""
    mock_state.get_last_event_id.return_value = None
    mock_client.fetch_user_events.side_effect = Exception("API error")

    service = GitHubPollingService(mock_client, mock_state, mock_settings, "testuser")

    # First failure - should not raise
    count1 = await service.poll_once()
    assert count1 == 0
    assert service.consecutive_failures == 1

    # Second failure - should raise
    with pytest.raises(GitHubPollingError):
        await service.poll_once()


@pytest.mark.asyncio
async def test_poll_once_success_resets_failures(
    mock_client: GitHubClient, mock_state: StateManager, mock_settings: Settings
) -> None:
    """Test success resets consecutive_failures to 0."""
    mock_state.get_last_event_id.return_value = None
    mock_client.fetch_user_events.return_value = [{"id": "123"}]

    service = GitHubPollingService(mock_client, mock_state, mock_settings, "testuser")
    service.consecutive_failures = 1

    await service.poll_once()

    assert service.consecutive_failures == 0


@pytest.mark.asyncio
async def test_fetch_events_until_last_id_pagination(
    mock_client: GitHubClient, mock_state: StateManager, mock_settings: Settings
) -> None:
    """Test pagination stops at last event with correct integer comparison."""
    # Event IDs as strings (as they come from GitHub API)
    page1 = [{"id": "12345678905"}, {"id": "12345678904"}]
    page2 = [{"id": "12345678903"}, {"id": "12345678900"}]  # Contains our last_event_id

    mock_client.fetch_user_events.side_effect = [page1, page2]

    service = GitHubPollingService(mock_client, mock_state, mock_settings, "testuser")
    collected = await service._fetch_events_until_last_id("12345678900")

    # Should collect events until it finds 12345678900
    assert len(collected) == 3  # All from page1 + first from page2
    assert all(int(e["id"]) > 12345678900 for e in collected)


@pytest.mark.asyncio
async def test_start_stop_lifecycle(
    mock_client: GitHubClient, mock_state: StateManager, mock_settings: Settings
) -> None:
    """Test task creation and cancellation."""
    service = GitHubPollingService(mock_client, mock_state, mock_settings, "testuser")

    # Start service
    await service.start()
    assert service.running is True
    assert service.task is not None

    # Stop service
    await service.stop()
    assert service.running is False
