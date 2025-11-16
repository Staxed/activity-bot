"""Scheduler for automatic daily/weekly/monthly summary posts."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.logging import get_logger
from app.discord.summaries import (
    generate_daily_summary,
    generate_monthly_summary,
    generate_weekly_summary,
)

if TYPE_CHECKING:
    from app.core.database import DatabaseClient
    from app.discord.poster import DiscordPoster

logger = get_logger(__name__)


class SummaryScheduler:
    """Scheduler for posting daily/weekly/monthly summaries at configured times."""

    def __init__(self, db: "DatabaseClient", discord_poster: "DiscordPoster") -> None:
        """Initialize summary scheduler.

        Args:
            db: Database client
            discord_poster: Discord poster for sending summaries
        """
        self.db = db
        self.discord_poster = discord_poster
        self.settings = get_settings()
        self.running = False
        self.task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the summary scheduler.

        Creates and starts the background scheduling task.
        """
        if self.running:
            logger.warning("summary.scheduler.already_running")
            return

        self.running = True
        self.task = asyncio.create_task(self._schedule_loop())
        logger.info(
            "summary.scheduler.started",
            daily_time=self.settings.daily_summary_time,
            weekly_time=self.settings.weekly_summary_time,
            monthly_time=self.settings.monthly_summary_time,
        )

    async def stop(self) -> None:
        """Stop the summary scheduler.

        Cancels the background scheduling task.
        """
        if not self.running:
            logger.warning("summary.scheduler.not_running")
            return

        self.running = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        logger.info("summary.scheduler.stopped")

    async def _schedule_loop(self) -> None:
        """Background loop that checks if it's time to post summaries."""
        while self.running:
            try:
                await self._check_and_post_summaries()
            except Exception as e:
                logger.error("summary.scheduler.error", error=str(e), exc_info=True)

            # Sleep for 1 minute before next check
            await asyncio.sleep(60)

    async def _check_and_post_summaries(self) -> None:
        """Check current time and post summaries if scheduled time has arrived."""
        import pytz

        # Get current time in configured timezone
        try:
            tz = pytz.timezone(self.settings.stats_timezone)
        except Exception as e:
            logger.error("summary.timezone.invalid", timezone=self.settings.stats_timezone, error=str(e))
            tz = pytz.UTC

        now = datetime.now(tz)
        current_time = now.strftime("%H:%M")

        # Check daily summary
        if current_time == self.settings.daily_summary_time:
            await self._post_daily_summaries()

        # Check weekly summary (only on Mondays)
        if now.weekday() == 0 and current_time == self.settings.weekly_summary_time:
            await self._post_weekly_summaries()

        # Check monthly summary (only on 1st of month)
        if now.day == 1 and current_time == self.settings.monthly_summary_time:
            await self._post_monthly_summaries()

    async def _post_daily_summaries(self) -> None:
        """Post daily summaries for all tracked users."""
        logger.info("summary.daily.posting")

        for username in self.settings.tracked_users_list:
            try:
                embed = await generate_daily_summary(self.db, username)
                await self.discord_poster.post_custom_embed(embed)
                logger.info("summary.daily.posted", username=username)
            except Exception as e:
                logger.error(
                    "summary.daily.failed",
                    username=username,
                    error=str(e),
                    exc_info=True,
                )

    async def _post_weekly_summaries(self) -> None:
        """Post weekly summaries for all tracked users."""
        logger.info("summary.weekly.posting")

        for username in self.settings.tracked_users_list:
            try:
                embed = await generate_weekly_summary(self.db, username)
                await self.discord_poster.post_custom_embed(embed)
                logger.info("summary.weekly.posted", username=username)
            except Exception as e:
                logger.error(
                    "summary.weekly.failed",
                    username=username,
                    error=str(e),
                    exc_info=True,
                )

    async def _post_monthly_summaries(self) -> None:
        """Post monthly summaries for all tracked users."""
        logger.info("summary.monthly.posting")

        for username in self.settings.tracked_users_list:
            try:
                embed = await generate_monthly_summary(self.db, username)
                await self.discord_poster.post_custom_embed(embed)
                logger.info("summary.monthly.posted", username=username)
            except Exception as e:
                logger.error(
                    "summary.monthly.failed",
                    username=username,
                    error=str(e),
                    exc_info=True,
                )


# Module-level singleton
_summary_scheduler: SummaryScheduler | None = None


def get_summary_scheduler() -> SummaryScheduler:
    """Get the global summary scheduler instance.

    Returns:
        The initialized SummaryScheduler instance.

    Raises:
        RuntimeError: If summary scheduler has not been initialized.
    """
    if _summary_scheduler is None:
        raise RuntimeError("SummaryScheduler not initialized")
    return _summary_scheduler


def set_summary_scheduler(scheduler: SummaryScheduler) -> None:
    """Set the global summary scheduler instance.

    Args:
        scheduler: The SummaryScheduler instance to set as global.
    """
    global _summary_scheduler
    _summary_scheduler = scheduler
