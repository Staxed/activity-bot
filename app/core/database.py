"""PostgreSQL database client with connection pooling."""

import asyncio
from typing import Any

import asyncpg

from app.core.config import get_settings
from app.core.logging import get_logger
from app.shared.exceptions import DatabaseError

logger = get_logger(__name__)


class DatabaseClient:
    """Async PostgreSQL client with connection pooling."""

    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 4, 8]

    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None

    async def __aenter__(self) -> "DatabaseClient":
        """Create connection pool with retry logic."""
        settings = get_settings()

        for attempt in range(self.MAX_RETRIES):
            try:
                self.pool = await asyncpg.create_pool(
                    host=settings.db_host,
                    port=settings.db_port,
                    database=settings.db_name,
                    user=settings.db_user,
                    password=settings.db_password,
                    min_size=2,
                    max_size=5,
                    timeout=60.0,
                )
                logger.info("database.pool.created", min_size=2, max_size=5)
                return self
            except (asyncpg.PostgresError, OSError) as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning("database.pool.retry", attempt=attempt + 1, error=str(e))
                    await asyncio.sleep(self.RETRY_DELAYS[attempt])
                else:
                    logger.error("database.pool.failed", error=str(e), exc_info=True)
                    raise DatabaseError(f"Failed to create pool: {e}") from e
        raise DatabaseError("Unreachable")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("database.pool.closed")

    async def fetch_all_quotes(self) -> list[tuple[str, str]]:
        """Fetch all active quotes.

        Returns:
            List of (text, author) tuples for all active quotes.

        Raises:
            DatabaseError: If connection pool is not initialized or query fails.
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            SELECT text, COALESCE(author, '') as author
            FROM quotes
            WHERE is_active = TRUE
            ORDER BY id
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query)
                return [(row["text"], row["author"]) for row in rows]
        except asyncpg.PostgresError as e:
            logger.error("database.fetch_quotes.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to fetch quotes: {e}") from e
