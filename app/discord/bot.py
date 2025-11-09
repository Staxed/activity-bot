"""Discord bot lifecycle management."""

from typing import Any

import discord

from app.core.logging import get_logger
from app.shared.exceptions import DiscordAPIError

logger = get_logger(__name__)


class DiscordBot:
    """Discord bot manager with async context manager lifecycle.

    Provides connection management and channel access for posting embeds.
    Follows the async context manager pattern from github/client.py.
    """

    def __init__(self, token: str, channel_id: int) -> None:
        """Initialize Discord bot with token and target channel.

        Args:
            token: Discord bot token
            channel_id: Discord channel ID to post to
        """
        self.token = token
        self.channel_id = channel_id
        self.client: discord.Client | None = None

    async def __aenter__(self) -> "DiscordBot":
        """Context manager entry: create client and login.

        Returns:
            Self for use in async with statement

        Raises:
            DiscordAPIError: If login fails or channel is inaccessible
        """
        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)

        # Set up ready event handler
        @self.client.event
        async def on_ready() -> None:
            """Log when bot is ready."""
            if self.client and self.client.user:
                logger.info("discord.bot.ready", username=self.client.user.name)

        try:
            # Login without running the event loop (we manage it in main.py)
            await self.client.login(self.token)
            logger.info("discord.bot.login.success")

            # Start the client (this will trigger on_ready)
            # We need to start the websocket connection but not block
            import asyncio

            asyncio.create_task(self.client.connect(reconnect=True))

            # Wait for the client to be ready
            await self.client.wait_until_ready()

            # Validate channel access
            channel = self.client.get_channel(self.channel_id)
            if channel is None:
                raise DiscordAPIError(f"Cannot access channel {self.channel_id}")

            if not isinstance(channel, discord.TextChannel):
                raise DiscordAPIError(f"Channel {self.channel_id} is not a text channel")

            logger.info("discord.bot.channel.validated", channel_id=self.channel_id)

        except discord.HTTPException as e:
            logger.error("discord.bot.login.failed", error=str(e), exc_info=True)
            raise DiscordAPIError(f"Failed to login: {e}") from e

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit: close Discord client.

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised
        """
        if self.client:
            await self.client.close()
            logger.info("discord.bot.closed")

    def get_channel(self) -> discord.TextChannel:
        """Get the configured Discord text channel.

        Returns:
            Discord text channel for posting

        Raises:
            DiscordAPIError: If client not initialized or channel inaccessible
        """
        if not self.client:
            raise DiscordAPIError("Discord client not initialized")

        channel = self.client.get_channel(self.channel_id)

        if channel is None:
            raise DiscordAPIError(f"Cannot access channel {self.channel_id}")

        if not isinstance(channel, discord.TextChannel):
            raise DiscordAPIError(f"Channel {self.channel_id} is not a text channel")

        return channel
