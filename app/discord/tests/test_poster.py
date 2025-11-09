"""Tests for Discord poster with retry logic."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from app.discord.bot import DiscordBot
from app.discord.poster import DiscordPoster
from app.shared.exceptions import DiscordAPIError
from app.shared.models import CommitEvent


@pytest.fixture
def mock_bot() -> MagicMock:
    """Create a mock Discord bot.

    Returns:
        Mock DiscordBot with get_channel method
    """
    bot = MagicMock(spec=DiscordBot)
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    bot.get_channel.return_value = channel
    return bot


@pytest.fixture
def sample_commit() -> CommitEvent:
    """Create a sample commit event for testing.

    Returns:
        CommitEvent instance
    """
    return CommitEvent(
        sha="a" * 40,
        short_sha="a" * 7,
        author="TestAuthor",
        author_email="test@example.com",
        message="Test commit message",
        message_body="Test commit message",
        repo_owner="owner",
        repo_name="repo",
        timestamp=datetime.now(timezone.utc),
        url="https://github.com/owner/repo/commit/aaaaaaa",
        branch="main",
    )


@pytest.mark.asyncio
async def test_post_commits_empty_list(mock_bot: MagicMock) -> None:
    """Test posting empty commit list is a no-op."""
    poster = DiscordPoster(mock_bot)

    await poster.post_commits([])

    # Should not call get_channel or send
    mock_bot.get_channel.assert_not_called()


@pytest.mark.asyncio
async def test_post_commits_single_commit(mock_bot: MagicMock, sample_commit: CommitEvent) -> None:
    """Test posting a single commit."""
    poster = DiscordPoster(mock_bot)

    await poster.post_commits([sample_commit])

    # Should call get_channel and send once
    mock_bot.get_channel.assert_called()
    channel = mock_bot.get_channel.return_value
    assert channel.send.call_count == 1


@pytest.mark.asyncio
async def test_post_commits_success_clears_queue(
    mock_bot: MagicMock, sample_commit: CommitEvent
) -> None:
    """Test successful posting clears the queue."""
    poster = DiscordPoster(mock_bot)

    # Add to queue
    poster.queue = [sample_commit]

    # Post new commits (should merge with queue)
    await poster.post_commits([sample_commit])

    # Queue should be empty after success
    assert len(poster.queue) == 0


@pytest.mark.asyncio
async def test_post_commits_failure_adds_to_queue(
    mock_bot: MagicMock, sample_commit: CommitEvent
) -> None:
    """Test failed commits are added to queue."""
    poster = DiscordPoster(mock_bot)

    # Make send fail
    channel = mock_bot.get_channel.return_value
    channel.send.side_effect = discord.HTTPException(MagicMock(), "Test error")

    await poster.post_commits([sample_commit])

    # Failed commit should be queued
    assert len(poster.queue) == 1
    assert poster.queue[0] == sample_commit


@pytest.mark.asyncio
async def test_post_commits_merges_existing_queue(
    mock_bot: MagicMock, sample_commit: CommitEvent
) -> None:
    """Test new commits are merged with existing queue."""
    poster = DiscordPoster(mock_bot)

    # Add to queue
    poster.queue = [sample_commit]

    # Create a different commit
    new_commit = CommitEvent(
        sha="b" * 40,
        short_sha="b" * 7,
        author="OtherAuthor",
        author_email="other@example.com",
        message="Another commit",
        message_body="Another commit",
        repo_owner="owner",
        repo_name="repo",
        timestamp=datetime.now(timezone.utc),
        url="https://github.com/owner/repo/commit/bbbbbbb",
        branch="main",
    )

    await poster.post_commits([new_commit])

    # Should have called send twice (two authors)
    channel = mock_bot.get_channel.return_value
    assert channel.send.call_count == 2


@pytest.mark.asyncio
async def test_post_commits_groups_by_author(mock_bot: MagicMock) -> None:
    """Test commits are grouped by author before posting."""
    poster = DiscordPoster(mock_bot)

    commits = [
        CommitEvent(
            sha="a" * 40,
            short_sha="a" * 7,
            author="Alice",
            author_email="alice@example.com",
            message="Alice commit 1",
            message_body="Alice commit 1",
            repo_owner="owner",
            repo_name="repo",
            timestamp=datetime.now(timezone.utc),
            url="https://github.com/owner/repo/commit/aaaaaaa",
            branch="main",
        ),
        CommitEvent(
            sha="b" * 40,
            short_sha="b" * 7,
            author="Bob",
            author_email="bob@example.com",
            message="Bob commit 1",
            message_body="Bob commit 1",
            repo_owner="owner",
            repo_name="repo",
            timestamp=datetime.now(timezone.utc),
            url="https://github.com/owner/repo/commit/bbbbbbb",
            branch="main",
        ),
    ]

    await poster.post_commits(commits)

    # Should send one embed per author (2 total)
    channel = mock_bot.get_channel.return_value
    assert channel.send.call_count == 2


@pytest.mark.asyncio
async def test_retry_on_http_exception(mock_bot: MagicMock, sample_commit: CommitEvent) -> None:
    """Test retry logic on HTTP exception."""
    poster = DiscordPoster(mock_bot)
    channel = mock_bot.get_channel.return_value

    # Fail once, then succeed
    channel.send.side_effect = [
        discord.HTTPException(MagicMock(), "Temporary error"),
        None,
    ]

    await poster.post_commits([sample_commit])

    # Should have retried and succeeded
    assert channel.send.call_count == 2
    assert len(poster.queue) == 0  # Success, so queue is empty


@pytest.mark.asyncio
async def test_retry_on_rate_limit_429(mock_bot: MagicMock, sample_commit: CommitEvent) -> None:
    """Test rate limit handling (429 status)."""
    poster = DiscordPoster(mock_bot)
    channel = mock_bot.get_channel.return_value

    # Create HTTPException with 429 status
    response = MagicMock()
    http_error = discord.HTTPException(response, "Rate limited")
    http_error.status = 429
    http_error.retry_after = 0.01  # Very short for testing

    # Fail with 429, then succeed
    channel.send.side_effect = [http_error, None]

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await poster.post_commits([sample_commit])

    # Should have slept for retry_after duration
    mock_sleep.assert_called()
    assert channel.send.call_count == 2


@pytest.mark.asyncio
async def test_retry_exhausted_raises_error(
    mock_bot: MagicMock, sample_commit: CommitEvent
) -> None:
    """Test error raised after max retries exhausted."""
    poster = DiscordPoster(mock_bot)
    channel = mock_bot.get_channel.return_value

    # Always fail
    channel.send.side_effect = discord.HTTPException(MagicMock(), "Persistent error")

    await poster.post_commits([sample_commit])

    # Should have retried MAX_RETRIES times and queued the commit
    assert channel.send.call_count == poster.MAX_RETRIES
    assert len(poster.queue) == 1  # Failed commit queued


@pytest.mark.asyncio
async def test_retry_exponential_backoff(mock_bot: MagicMock, sample_commit: CommitEvent) -> None:
    """Test exponential backoff delays."""
    poster = DiscordPoster(mock_bot)
    channel = mock_bot.get_channel.return_value

    # Fail all retries
    channel.send.side_effect = discord.HTTPException(MagicMock(), "Error")

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await poster.post_commits([sample_commit])

    # MAX_RETRIES=2 means: attempt 0 (initial), then retry (attempt 1 with sleep)
    # So only 1 sleep call with first delay
    assert mock_sleep.call_count == 1
    # Verify delay matches first RETRY_DELAY
    assert mock_sleep.call_args[0][0] == 2


@pytest.mark.asyncio
async def test_partial_failure_partial_queue(mock_bot: MagicMock) -> None:
    """Test partial failure: one author succeeds, another fails."""
    poster = DiscordPoster(mock_bot)

    alice_commit = CommitEvent(
        sha="a" * 40,
        short_sha="a" * 7,
        author="Alice",
        author_email="alice@example.com",
        message="Alice commit",
        message_body="Alice commit",
        repo_owner="owner",
        repo_name="repo",
        timestamp=datetime.now(timezone.utc),
        url="https://github.com/owner/repo/commit/aaaaaaa",
        branch="main",
    )

    bob_commit = CommitEvent(
        sha="b" * 40,
        short_sha="b" * 7,
        author="Bob",
        author_email="bob@example.com",
        message="Bob commit",
        message_body="Bob commit",
        repo_owner="owner",
        repo_name="repo",
        timestamp=datetime.now(timezone.utc),
        url="https://github.com/owner/repo/commit/bbbbbbb",
        branch="main",
    )

    channel = mock_bot.get_channel.return_value

    # First send (Alice) succeeds, second (Bob) fails
    channel.send.side_effect = [
        None,  # Alice success
        discord.HTTPException(MagicMock(), "Bob fails"),  # Bob fail
        discord.HTTPException(MagicMock(), "Bob fails"),  # Bob retry 1
    ]

    await poster.post_commits([alice_commit, bob_commit])

    # Queue should only contain Bob's commit
    assert len(poster.queue) == 1
    assert poster.queue[0].author == "Bob"
