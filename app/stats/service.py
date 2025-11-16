"""Stats service with database-backed cache and automatic refresh."""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.shared.exceptions import DatabaseError
from app.stats.calculator import calculate_user_stats
from app.stats.models import UserStats

if TYPE_CHECKING:
    from app.core.database import DatabaseClient

logger = get_logger(__name__)


class StatsService:
    """Stats service with automatic cache refresh."""

    def __init__(self, db_client: "DatabaseClient", refresh_interval_minutes: int = 60):
        """Initialize stats service.

        Args:
            db_client: Database client for fetching stats
            refresh_interval_minutes: How often to refresh cache (minutes)
        """
        self.db_client = db_client
        self.refresh_interval_minutes = refresh_interval_minutes
        self._stats_cache: dict[str, UserStats] = {}
        self._last_refresh: datetime | None = None
        self._refresh_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Initialize cache and start refresh loop."""
        await self._refresh_cache()
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info(
            "stats.service.started",
            users_cached=len(self._stats_cache),
            refresh_interval=self.refresh_interval_minutes,
        )

    async def stop(self) -> None:
        """Stop refresh loop."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        logger.info("stats.service.stopped")

    async def _refresh_cache(self) -> None:
        """Refresh cache from database for all tracked users."""
        try:
            from app.core.config import get_settings

            settings = get_settings()
            tracked_users = settings.tracked_users_list

            # Calculate stats for all tracked users
            new_cache = {}
            for username in tracked_users:
                try:
                    stats = await calculate_user_stats(self.db_client, username)
                    new_cache[username] = stats
                except Exception as e:
                    logger.error(
                        "stats.cache.user_failed", username=username, error=str(e), exc_info=True
                    )
                    # Keep serving stale cache for this user if available
                    if username in self._stats_cache:
                        new_cache[username] = self._stats_cache[username]

            self._stats_cache = new_cache
            self._last_refresh = datetime.now()
            logger.info("stats.cache.refreshed", users_count=len(self._stats_cache))

        except Exception as e:
            logger.error("stats.cache.refresh_failed", error=str(e), exc_info=True)
            # Keep serving stale cache

    async def _refresh_loop(self) -> None:
        """Background refresh task."""
        while True:
            await asyncio.sleep(self.refresh_interval_minutes * 60)
            await self._refresh_cache()

    async def get_user_stats(self, username: str) -> UserStats:
        """Get user stats from cache.

        Args:
            username: GitHub username

        Returns:
            UserStats from cache

        Raises:
            DatabaseError: If user not in cache (not tracked)
        """
        if username not in self._stats_cache:
            # Try to calculate on-demand for non-tracked users
            logger.info("stats.cache.miss", username=username)
            return await calculate_user_stats(self.db_client, username)

        return self._stats_cache[username]

    async def get_user_stats_fresh(self, username: str) -> UserStats:
        """Get fresh user stats bypassing cache.

        Args:
            username: GitHub username

        Returns:
            Freshly calculated UserStats

        Raises:
            DatabaseError: If calculation fails
        """
        return await calculate_user_stats(self.db_client, username)


# Module-level singleton
_stats_service: StatsService | None = None


def get_stats_service() -> StatsService:
    """Get the global stats service instance.

    Returns:
        The initialized StatsService instance.

    Raises:
        RuntimeError: If stats service has not been initialized.
    """
    if _stats_service is None:
        raise RuntimeError("StatsService not initialized")
    return _stats_service


def set_stats_service(service: StatsService) -> None:
    """Set the global stats service instance.

    Args:
        service: The StatsService instance to set as global.
    """
    global _stats_service
    _stats_service = service
