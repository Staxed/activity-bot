"""Tests for Discord embed helper functions."""

from datetime import UTC, datetime

from app.discord.embeds import format_commit_time, truncate_message


def test_truncate_message_under_limit() -> None:
    """Test message unchanged if under limit."""
    message = "Short message"
    result = truncate_message(message, max_length=200)
    assert result == message


def test_truncate_message_exactly_at_limit() -> None:
    """Test no truncation at exact limit."""
    message = "x" * 200
    result = truncate_message(message, max_length=200)
    assert result == message


def test_truncate_message_over_limit() -> None:
    """Test truncation adds ellipsis and respects length."""
    message = "x" * 250
    result = truncate_message(message, max_length=200)
    assert result.endswith("...")
    assert len(result) == 200


def test_format_commit_time_today() -> None:
    """Test formatting for commits made today."""
    now = datetime.now(UTC)
    result = format_commit_time(now)

    # Should return Discord timestamp format
    assert result.startswith("<t:")
    assert result.endswith(":t>")
    # Should contain unix timestamp
    assert str(int(now.timestamp())) in result


def test_format_commit_time_this_year() -> None:
    """Test formatting for commits this year but not today."""
    # Create a timestamp from 30 days ago
    now = datetime.now(UTC)
    timestamp = now.replace(month=max(1, now.month - 1))

    result = format_commit_time(timestamp)

    # Should return Discord timestamp format
    assert result.startswith("<t:")
    assert result.endswith(":t>")


def test_format_commit_time_past_year() -> None:
    """Test formatting for commits from past years."""
    timestamp = datetime(2023, 6, 15, 14, 30, tzinfo=UTC)
    result = format_commit_time(timestamp)

    # Should return Discord timestamp format
    assert result.startswith("<t:")
    assert result.endswith(":t>")
    assert str(int(timestamp.timestamp())) in result
