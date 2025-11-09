"""Quote service with database-backed cache and automatic refresh."""

import asyncio
import random
from datetime import datetime
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.shared.exceptions import DatabaseError

if TYPE_CHECKING:
    from app.core.database import DatabaseClient

logger = get_logger(__name__)


class QuoteService:
    """Quote service with automatic cache refresh."""

    def __init__(self, db_client: "DatabaseClient", refresh_interval_minutes: int = 60):
        """Initialize quote service.

        Args:
            db_client: Database client for fetching quotes
            refresh_interval_minutes: How often to refresh cache (minutes)
        """
        self.db_client = db_client
        self.refresh_interval_minutes = refresh_interval_minutes
        self._cache: list[str] = []
        self._last_refresh: datetime | None = None
        self._refresh_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Initialize cache and start refresh loop."""
        await self._refresh_cache()
        if not self._cache:
            logger.error("quotes.cache.empty")
            raise DatabaseError("Quote table is empty - run migration")

        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info("quotes.service.started", quotes_count=len(self._cache))

    async def stop(self) -> None:
        """Stop refresh loop."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        logger.info("quotes.service.stopped")

    async def _refresh_cache(self) -> None:
        """Refresh cache from database."""
        try:
            rows = await self.db_client.fetch_all_quotes()
            formatted = []
            for text, author in rows:
                if author:
                    formatted.append(f"{text} — {author}")
                else:
                    formatted.append(text)
            self._cache = formatted
            self._last_refresh = datetime.now()
            logger.info("quotes.cache.refreshed", count=len(self._cache))
        except Exception as e:
            logger.error("quotes.cache.refresh_failed", error=str(e), exc_info=True)
            # Keep serving stale cache

    async def _refresh_loop(self) -> None:
        """Background refresh task."""
        while True:
            await asyncio.sleep(self.refresh_interval_minutes * 60)
            await self._refresh_cache()

    def get_random_quote(self) -> str:
        """Get random quote from cache.

        Returns:
            A randomly selected quote from the cache.

        Raises:
            DatabaseError: If cache is empty.
        """
        if not self._cache:
            raise DatabaseError("Quote cache is empty")
        return random.choice(self._cache)


# Module-level singleton
_quote_service: QuoteService | None = None


def get_quote_service() -> QuoteService:
    """Get the global quote service instance.

    Returns:
        The initialized QuoteService instance.

    Raises:
        RuntimeError: If quote service has not been initialized.
    """
    if _quote_service is None:
        raise RuntimeError("QuoteService not initialized")
    return _quote_service


def set_quote_service(service: QuoteService) -> None:
    """Set the global quote service instance.

    Args:
        service: The QuoteService instance to set as global.
    """
    global _quote_service
    _quote_service = service


def get_random_quote() -> str:
    """Backward-compatible sync function for getting a random quote.

    Returns:
        A randomly selected quote from the service cache.

    Raises:
        RuntimeError: If quote service has not been initialized.
        DatabaseError: If quote cache is empty.
    """
    return get_quote_service().get_random_quote()
