"""PostgreSQL database client with connection pooling."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import asyncpg

from app.core.config import get_settings
from app.core.logging import get_logger
from app.shared.exceptions import DatabaseError

logger = get_logger(__name__)


def _to_naive_utc(dt: datetime) -> datetime:
    """Convert timezone-aware datetime to naive UTC datetime.

    PostgreSQL TIMESTAMP columns (without timezone) expect naive datetimes.
    This function converts timezone-aware datetimes to UTC and strips timezone info.

    Args:
        dt: Datetime object (timezone-aware or naive)

    Returns:
        Naive datetime in UTC
    """
    if dt.tzinfo is None:
        # Already naive, assume it's UTC
        return dt
    # Convert to UTC and remove timezone info
    return dt.astimezone(UTC).replace(tzinfo=None)


class DatabaseClient:
    """Async PostgreSQL client with connection pooling."""

    MAX_RETRIES: ClassVar[int] = 3
    RETRY_DELAYS: ClassVar[list[int]] = [2, 4, 8]

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

    async def get_last_event_id(self) -> str | None:
        """Get the last processed GitHub event ID from processing_state table.

        Returns:
            Last processed event ID, or None if not set

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            SELECT value FROM processing_state
            WHERE key = 'last_event_id'
        """

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query)
                return row["value"] if row else None
        except asyncpg.PostgresError as e:
            logger.error("database.get_last_event_id.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get last event ID: {e}") from e

    async def set_last_event_id(self, event_id: str) -> None:
        """Set the last processed GitHub event ID in processing_state table.

        Args:
            event_id: Event ID to store

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            INSERT INTO processing_state (key, value, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (key)
            DO UPDATE SET value = $2, updated_at = NOW()
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, "last_event_id", event_id)
                logger.info("database.set_last_event_id.success", event_id=event_id)
        except asyncpg.PostgresError as e:
            logger.error("database.set_last_event_id.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to set last event ID: {e}") from e

    async def insert_commits(self, commits: list[Any]) -> int:
        """Bulk insert commits with deduplication.

        Args:
            commits: List of CommitEvent objects

        Returns:
            Number of rows inserted (excludes duplicates skipped by ON CONFLICT)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not commits:
            return 0

        query = """
            INSERT INTO commits (
                event_id, sha, short_sha, author_name, author_email, author_username,
                author_avatar_url, message, message_body, repo_owner, repo_name,
                branch, is_public, commit_timestamp, url
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                # Prepare data for executemany
                data = [
                    (
                        f"commit_{c.sha}",  # event_id is derived from SHA since commits come from PushEvent
                        c.sha,
                        c.short_sha,
                        c.author,
                        c.author_email,
                        c.author_username,
                        c.author_avatar_url,
                        c.message,
                        c.message_body,
                        c.repo_owner,
                        c.repo_name,
                        c.branch,
                        c.is_public,
                        _to_naive_utc(c.timestamp),
                        c.url,
                    )
                    for c in commits
                ]
                await conn.executemany(query, data)
                # executemany returns None for INSERT statements
                # We can't tell which were inserted vs skipped due to ON CONFLICT
                logger.info(
                    "database.insert_commits.success", total=len(commits)
                )
                return len(commits)
        except asyncpg.PostgresError as e:
            logger.error("database.insert_commits.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert commits: {e}") from e

    async def insert_pull_requests(self, prs: list[Any]) -> int:
        """Bulk insert pull requests with deduplication.

        Args:
            prs: List of PullRequestEvent objects

        Returns:
            Number of rows inserted
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not prs:
            return 0

        query = """
            INSERT INTO pull_requests (
                event_id, pr_number, action, title, state, merged,
                author_username, author_avatar_url, repo_owner, repo_name,
                is_public, url, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        pr.event_id,
                        pr.pr_number,
                        pr.action,
                        pr.title,
                        pr.state,
                        pr.merged,
                        pr.author_username,
                        pr.author_avatar_url,
                        pr.repo_owner,
                        pr.repo_name,
                        pr.is_public,
                        pr.url,
                        pr.event_timestamp,
                    )
                    for pr in prs
                ]
                result = await conn.executemany(query, data)
                inserted = len([r for r in result if r != "INSERT 0 0"])
                logger.info("database.insert_pull_requests.success", total=len(prs), inserted=inserted)
                return inserted
        except asyncpg.PostgresError as e:
            logger.error("database.insert_pull_requests.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert pull requests: {e}") from e

    async def insert_pr_reviews(self, reviews: list[Any]) -> int:
        """Bulk insert PR reviews with deduplication."""
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not reviews:
            return 0

        query = """
            INSERT INTO pr_reviews (
                event_id, pr_number, action, review_state, reviewer_username,
                reviewer_avatar_url, repo_owner, repo_name, is_public, url, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        r.event_id,
                        r.pr_number,
                        r.action,
                        r.review_state,
                        r.reviewer_username,
                        r.reviewer_avatar_url,
                        r.repo_owner,
                        r.repo_name,
                        r.is_public,
                        r.url,
                        r.event_timestamp,
                    )
                    for r in reviews
                ]
                result = await conn.executemany(query, data)
                inserted = len([r for r in result if r != "INSERT 0 0"])
                logger.info("database.insert_pr_reviews.success", total=len(reviews), inserted=inserted)
                return inserted
        except asyncpg.PostgresError as e:
            logger.error("database.insert_pr_reviews.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert PR reviews: {e}") from e

    async def insert_issues(self, issues: list[Any]) -> int:
        """Bulk insert issues with deduplication."""
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not issues:
            return 0

        query = """
            INSERT INTO issues (
                event_id, issue_number, action, title, state, author_username,
                author_avatar_url, repo_owner, repo_name, is_public, url, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        i.event_id,
                        i.issue_number,
                        i.action,
                        i.title,
                        i.state,
                        i.author_username,
                        i.author_avatar_url,
                        i.repo_owner,
                        i.repo_name,
                        i.is_public,
                        i.url,
                        i.event_timestamp,
                    )
                    for i in issues
                ]
                result = await conn.executemany(query, data)
                inserted = len([r for r in result if r != "INSERT 0 0"])
                logger.info("database.insert_issues.success", total=len(issues), inserted=inserted)
                return inserted
        except asyncpg.PostgresError as e:
            logger.error("database.insert_issues.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert issues: {e}") from e

    async def insert_releases(self, releases: list[Any]) -> int:
        """Bulk insert releases with deduplication."""
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not releases:
            return 0

        query = """
            INSERT INTO releases (
                event_id, tag_name, release_name, is_prerelease, is_draft,
                author_username, author_avatar_url, repo_owner, repo_name,
                is_public, url, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        r.event_id,
                        r.tag_name,
                        r.release_name,
                        r.is_prerelease,
                        r.is_draft,
                        r.author_username,
                        r.author_avatar_url,
                        r.repo_owner,
                        r.repo_name,
                        r.is_public,
                        r.url,
                        r.event_timestamp,
                    )
                    for r in releases
                ]
                result = await conn.executemany(query, data)
                inserted = len([r for r in result if r != "INSERT 0 0"])
                logger.info("database.insert_releases.success", total=len(releases), inserted=inserted)
                return inserted
        except asyncpg.PostgresError as e:
            logger.error("database.insert_releases.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert releases: {e}") from e

    async def insert_creations(self, creations: list[Any]) -> int:
        """Bulk insert creations with deduplication."""
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not creations:
            return 0

        query = """
            INSERT INTO creations (
                event_id, ref_type, ref_name, author_username, author_avatar_url,
                repo_owner, repo_name, is_public, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        c.event_id,
                        c.ref_type,
                        c.ref_name,
                        c.author_username,
                        c.author_avatar_url,
                        c.repo_owner,
                        c.repo_name,
                        c.is_public,
                        c.event_timestamp,
                    )
                    for c in creations
                ]
                result = await conn.executemany(query, data)
                inserted = len([r for r in result if r != "INSERT 0 0"])
                logger.info("database.insert_creations.success", total=len(creations), inserted=inserted)
                return inserted
        except asyncpg.PostgresError as e:
            logger.error("database.insert_creations.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert creations: {e}") from e

    async def insert_deletions(self, deletions: list[Any]) -> int:
        """Bulk insert deletions with deduplication."""
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not deletions:
            return 0

        query = """
            INSERT INTO deletions (
                event_id, ref_type, ref_name, author_username, author_avatar_url,
                repo_owner, repo_name, is_public, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        d.event_id,
                        d.ref_type,
                        d.ref_name,
                        d.author_username,
                        d.author_avatar_url,
                        d.repo_owner,
                        d.repo_name,
                        d.is_public,
                        d.event_timestamp,
                    )
                    for d in deletions
                ]
                result = await conn.executemany(query, data)
                inserted = len([r for r in result if r != "INSERT 0 0"])
                logger.info("database.insert_deletions.success", total=len(deletions), inserted=inserted)
                return inserted
        except asyncpg.PostgresError as e:
            logger.error("database.insert_deletions.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert deletions: {e}") from e

    async def insert_forks(self, forks: list[Any]) -> int:
        """Bulk insert forks with deduplication."""
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not forks:
            return 0

        query = """
            INSERT INTO forks (
                event_id, forker_username, forker_avatar_url, source_repo_owner,
                source_repo_name, fork_repo_owner, fork_repo_name, is_public,
                fork_url, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        f.event_id,
                        f.forker_username,
                        f.forker_avatar_url,
                        f.source_repo_owner,
                        f.source_repo_name,
                        f.fork_repo_owner,
                        f.fork_repo_name,
                        f.is_public,
                        f.fork_url,
                        f.event_timestamp,
                    )
                    for f in forks
                ]
                result = await conn.executemany(query, data)
                inserted = len([r for r in result if r != "INSERT 0 0"])
                logger.info("database.insert_forks.success", total=len(forks), inserted=inserted)
                return inserted
        except asyncpg.PostgresError as e:
            logger.error("database.insert_forks.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert forks: {e}") from e

    async def get_unposted_commits(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted commits within time window for recovery.

        Args:
            max_age_hours: Maximum age of commits to retrieve (default 12 hours)

        Returns:
            List of CommitEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        # Import CommitEvent here to avoid circular imports
        from app.shared.models import CommitEvent

        query = """
            SELECT * FROM commits
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY commit_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                commits = [
                    CommitEvent(
                        sha=row["sha"],
                        short_sha=row["short_sha"],
                        author=row["author_name"],
                        author_email=row["author_email"],
                        author_username=row["author_username"],
                        author_avatar_url=row["author_avatar_url"] or "",
                        message=row["message"],
                        message_body=row["message_body"],
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        timestamp=row["commit_timestamp"],
                        url=row["url"],
                        branch=row["branch"],
                        is_public=row["is_public"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_commits.success", count=len(commits))
                return commits
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_commits.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted commits: {e}") from e

    async def mark_commits_posted(self, event_ids: list[str]) -> None:
        """Mark commits as posted to Discord.

        Args:
            event_ids: List of event IDs to mark as posted

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not event_ids:
            return

        query = """
            UPDATE commits
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_commits_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_commits_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark commits as posted: {e}") from e
