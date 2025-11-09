"""Discord posting service with retry logic and queue management."""

import asyncio

import discord

from app.core.logging import get_logger
from app.discord.bot import DiscordBot
from app.discord.embeds import create_commit_embeds, group_commits_by_author
from app.shared.exceptions import DiscordAPIError
from app.shared.models import CommitEvent

logger = get_logger(__name__)


class DiscordPoster:
    """Discord posting service with retry logic and failure queue.

    Handles posting commit embeds to Discord with automatic retry on failure.
    Failed posts are queued and merged by author on next attempt.
    """

    MAX_RETRIES = 2
    RETRY_DELAYS = [2, 4]  # Exponential backoff: 2s, 4s

    def __init__(self, bot: DiscordBot) -> None:
        """Initialize Discord poster with bot instance.

        Args:
            bot: Initialized DiscordBot instance
        """
        self.bot = bot
        self.queue: list[CommitEvent] = []

    async def post_commits(self, commits: list[CommitEvent]) -> None:
        """Post commits to Discord, merging with queued failures.

        Groups commits by author, creates embeds, and posts with retry logic.
        Failed posts are added back to the queue for next attempt.

        Args:
            commits: List of commit events to post
        """
        # Merge queue with new commits
        all_commits = self.queue + commits
        self.queue = []

        if not all_commits:
            logger.info("discord.post.skip", reason="no_commits")
            return

        logger.info("discord.post.started", total_commits=len(all_commits))

        # Group commits by author
        grouped = group_commits_by_author(all_commits)

        # Track failures for requeueing
        failed_commits: list[CommitEvent] = []

        # Post each author's commits
        for author, repos in grouped.items():
            try:
                embeds = create_commit_embeds(author, repos)
                logger.info(
                    "discord.post.author.started",
                    author=author,
                    repos=len(repos),
                    embeds=len(embeds),
                )

                # Post each embed with retry
                for embed_idx, embed in enumerate(embeds):
                    await self._post_embed_with_retry(embed)
                    logger.info(
                        "discord.post.embed.success",
                        author=author,
                        embed=f"{embed_idx + 1}/{len(embeds)}",
                    )

                logger.info("discord.post.author.success", author=author)

            except Exception as e:
                logger.error(
                    "discord.post.author.failed",
                    author=author,
                    error=str(e),
                    exc_info=True,
                )

                # Add this author's commits back to failed list
                for repo_commits in repos.values():
                    failed_commits.extend(repo_commits)

        # Update queue with failed commits
        self.queue = failed_commits

        if failed_commits:
            logger.warning(
                "discord.post.complete.partial",
                posted=len(all_commits) - len(failed_commits),
                queued=len(failed_commits),
            )
        else:
            logger.info("discord.post.complete.success", posted=len(all_commits))

    async def _post_embed_with_retry(self, embed: discord.Embed) -> None:
        """Post a single embed with retry logic.

        Args:
            embed: Discord embed to post

        Raises:
            DiscordAPIError: If posting fails after all retries
        """
        channel = self.bot.get_channel()

        for attempt in range(self.MAX_RETRIES):
            try:
                await channel.send(embed=embed)
                return

            except discord.HTTPException as e:
                # Handle rate limiting (429)
                if e.status == 429:
                    retry_after = getattr(e, "retry_after", self.RETRY_DELAYS[min(attempt, 1)])
                    logger.warning(
                        "discord.ratelimit.hit",
                        retry_after=retry_after,
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(retry_after)

                elif attempt < self.MAX_RETRIES - 1:
                    # Generic HTTP error with retry
                    delay = self.RETRY_DELAYS[attempt]
                    logger.warning(
                        "discord.post.retry",
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

                else:
                    # Max retries exhausted
                    logger.error(
                        "discord.post.failed",
                        attempts=self.MAX_RETRIES,
                        error=str(e),
                        exc_info=True,
                    )
                    raise DiscordAPIError(
                        f"Failed to post embed after {self.MAX_RETRIES} retries"
                    ) from e

            except Exception as e:
                # Non-HTTP exception
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    logger.warning(
                        "discord.post.retry",
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "discord.post.failed",
                        attempts=self.MAX_RETRIES,
                        error=str(e),
                        exc_info=True,
                    )
                    raise DiscordAPIError(
                        f"Failed to post embed after {self.MAX_RETRIES} retries"
                    ) from e
