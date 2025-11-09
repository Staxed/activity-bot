"""Pytest fixtures for Discord tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock

import discord


@pytest.fixture
def mock_discord_channel() -> MagicMock:
    """Create a mock Discord text channel.

    Returns:
        Mock text channel with async send method
    """
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    channel.id = 123456789
    return channel


@pytest.fixture
def mock_discord_client() -> MagicMock:
    """Create a mock Discord client.

    Returns:
        Mock Discord client with user attribute
    """
    client = MagicMock(spec=discord.Client)
    client.user = MagicMock()
    client.user.name = "TestBot"
    return client
