"""PostgreSQL database client with connection pooling."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any, ClassVar

import asyncpg

from app.core.config import get_settings
from app.core.logging import get_logger
from app.shared.exceptions import DatabaseError

# TYPE_CHECKING import to avoid circular imports
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.nft.models import (
        NFTBurnEvent,
        NFTDelistingEvent,
        NFTListingEvent,
        NFTMintEvent,
        NFTSaleEvent,
        NFTTransferEvent,
    )

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
        exc_tb: TracebackType | None,
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
            Number of rows attempted to insert (actual inserts may be less due to
            ON CONFLICT DO NOTHING deduplication)

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
                # Note: ON CONFLICT DO NOTHING may skip some rows, actual inserts may be less
                logger.info("database.insert_commits.success", total=len(commits))
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
                        _to_naive_utc(pr.event_timestamp),
                    )
                    for pr in prs
                ]
                await conn.executemany(query, data)
                # Note: ON CONFLICT DO NOTHING may skip some rows, actual inserts may be less
                logger.info("database.insert_pull_requests.success", total=len(prs))
                return len(prs)
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
                        _to_naive_utc(r.event_timestamp),
                    )
                    for r in reviews
                ]
                await conn.executemany(query, data)
                # Note: ON CONFLICT DO NOTHING may skip some rows, actual inserts may be less
                logger.info("database.insert_pr_reviews.success", total=len(reviews))
                return len(reviews)
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
                        _to_naive_utc(i.event_timestamp),
                    )
                    for i in issues
                ]
                await conn.executemany(query, data)
                # Note: ON CONFLICT DO NOTHING may skip some rows, actual inserts may be less
                logger.info("database.insert_issues.success", total=len(issues))
                return len(issues)
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
                        _to_naive_utc(r.event_timestamp),
                    )
                    for r in releases
                ]
                await conn.executemany(query, data)
                # Note: ON CONFLICT DO NOTHING may skip some rows, actual inserts may be less
                logger.info("database.insert_releases.success", total=len(releases))
                return len(releases)
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
                        _to_naive_utc(c.event_timestamp),
                    )
                    for c in creations
                ]
                await conn.executemany(query, data)
                # Note: ON CONFLICT DO NOTHING may skip some rows, actual inserts may be less
                logger.info("database.insert_creations.success", total=len(creations))
                return len(creations)
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
                        _to_naive_utc(d.event_timestamp),
                    )
                    for d in deletions
                ]
                await conn.executemany(query, data)
                # Note: ON CONFLICT DO NOTHING may skip some rows, actual inserts may be less
                logger.info("database.insert_deletions.success", total=len(deletions))
                return len(deletions)
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
                        _to_naive_utc(f.event_timestamp),
                    )
                    for f in forks
                ]
                await conn.executemany(query, data)
                # Note: ON CONFLICT DO NOTHING may skip some rows, actual inserts may be less
                logger.info("database.insert_forks.success", total=len(forks))
                return len(forks)
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

    async def get_unposted_prs(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted pull requests within time window for recovery.

        Args:
            max_age_hours: Maximum age of PRs to retrieve (default 12 hours)

        Returns:
            List of PullRequestEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import PullRequestEvent

        query = """
            SELECT * FROM pull_requests
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                prs = [
                    PullRequestEvent(
                        event_id=row["event_id"],
                        pr_number=row["pr_number"],
                        action=row["action"],
                        title=row["title"],
                        state=row["state"],
                        merged=row["merged"],
                        author_username=row["author_username"],
                        author_avatar_url=row["author_avatar_url"] or "",
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        is_public=row["is_public"],
                        url=row["url"] or "",
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_prs.success", count=len(prs))
                return prs
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_prs.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted PRs: {e}") from e

    async def mark_prs_posted(self, event_ids: list[str]) -> None:
        """Mark pull requests as posted to Discord.

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
            UPDATE pull_requests
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_prs_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_prs_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark PRs as posted: {e}") from e

    async def get_unposted_issues(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted issues within time window for recovery.

        Args:
            max_age_hours: Maximum age of issues to retrieve (default 12 hours)

        Returns:
            List of IssuesEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import IssuesEvent

        query = """
            SELECT * FROM issues
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                issues = [
                    IssuesEvent(
                        event_id=row["event_id"],
                        issue_number=row["issue_number"],
                        action=row["action"],
                        title=row["title"],
                        state=row["state"],
                        author_username=row["author_username"],
                        author_avatar_url=row["author_avatar_url"] or "",
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        is_public=row["is_public"],
                        url=row["url"] or "",
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_issues.success", count=len(issues))
                return issues
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_issues.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted issues: {e}") from e

    async def mark_issues_posted(self, event_ids: list[str]) -> None:
        """Mark issues as posted to Discord.

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
            UPDATE issues
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_issues_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_issues_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark issues as posted: {e}") from e

    async def get_unposted_releases(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted releases within time window for recovery.

        Args:
            max_age_hours: Maximum age of releases to retrieve (default 12 hours)

        Returns:
            List of ReleaseEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import ReleaseEvent

        query = """
            SELECT * FROM releases
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                releases = [
                    ReleaseEvent(
                        event_id=row["event_id"],
                        tag_name=row["tag_name"],
                        release_name=row["release_name"],
                        is_prerelease=row["is_prerelease"],
                        is_draft=row["is_draft"],
                        author_username=row["author_username"],
                        author_avatar_url=row["author_avatar_url"] or "",
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        is_public=row["is_public"],
                        url=row["url"],
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_releases.success", count=len(releases))
                return releases
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_releases.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted releases: {e}") from e

    async def mark_releases_posted(self, event_ids: list[str]) -> None:
        """Mark releases as posted to Discord.

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
            UPDATE releases
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_releases_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_releases_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark releases as posted: {e}") from e

    async def get_unposted_reviews(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted PR reviews within time window for recovery.

        Args:
            max_age_hours: Maximum age of reviews to retrieve (default 12 hours)

        Returns:
            List of PullRequestReviewEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import PullRequestReviewEvent

        query = """
            SELECT * FROM pr_reviews
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                reviews = [
                    PullRequestReviewEvent(
                        event_id=row["event_id"],
                        pr_number=row["pr_number"],
                        action=row["action"],
                        review_state=row["review_state"],
                        reviewer_username=row["reviewer_username"],
                        reviewer_avatar_url=row["reviewer_avatar_url"] or "",
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        is_public=row["is_public"],
                        url=row["url"] or "",
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_reviews.success", count=len(reviews))
                return reviews
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_reviews.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted reviews: {e}") from e

    async def mark_reviews_posted(self, event_ids: list[str]) -> None:
        """Mark PR reviews as posted to Discord.

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
            UPDATE pr_reviews
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_reviews_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_reviews_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark reviews as posted: {e}") from e

    async def get_unposted_creations(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted creation events within time window for recovery.

        Args:
            max_age_hours: Maximum age of creations to retrieve (default 12 hours)

        Returns:
            List of CreateEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import CreateEvent

        query = """
            SELECT * FROM creations
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                creations = [
                    CreateEvent(
                        event_id=row["event_id"],
                        ref_type=row["ref_type"],
                        ref_name=row["ref_name"],
                        author_username=row["author_username"],
                        author_avatar_url=row["author_avatar_url"] or "",
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        is_public=row["is_public"],
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_creations.success", count=len(creations))
                return creations
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_creations.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted creations: {e}") from e

    async def mark_creations_posted(self, event_ids: list[str]) -> None:
        """Mark creation events as posted to Discord.

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
            UPDATE creations
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_creations_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_creations_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark creations as posted: {e}") from e

    async def get_unposted_deletions(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted deletion events within time window for recovery.

        Args:
            max_age_hours: Maximum age of deletions to retrieve (default 12 hours)

        Returns:
            List of DeleteEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import DeleteEvent

        query = """
            SELECT * FROM deletions
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                deletions = [
                    DeleteEvent(
                        event_id=row["event_id"],
                        ref_type=row["ref_type"],
                        ref_name=row["ref_name"],
                        author_username=row["author_username"],
                        author_avatar_url=row["author_avatar_url"] or "",
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        is_public=row["is_public"],
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_deletions.success", count=len(deletions))
                return deletions
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_deletions.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted deletions: {e}") from e

    async def mark_deletions_posted(self, event_ids: list[str]) -> None:
        """Mark deletion events as posted to Discord.

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
            UPDATE deletions
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_deletions_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_deletions_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark deletions as posted: {e}") from e

    async def get_unposted_forks(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted fork events within time window for recovery.

        Args:
            max_age_hours: Maximum age of forks to retrieve (default 12 hours)

        Returns:
            List of ForkEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import ForkEvent

        query = """
            SELECT * FROM forks
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                forks = [
                    ForkEvent(
                        event_id=row["event_id"],
                        forker_username=row["forker_username"],
                        forker_avatar_url=row["forker_avatar_url"] or "",
                        source_repo_owner=row["source_repo_owner"],
                        source_repo_name=row["source_repo_name"],
                        fork_repo_owner=row["fork_repo_owner"],
                        fork_repo_name=row["fork_repo_name"],
                        is_public=row["is_public"],
                        fork_url=row["fork_url"],
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_forks.success", count=len(forks))
                return forks
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_forks.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted forks: {e}") from e

    async def mark_forks_posted(self, event_ids: list[str]) -> None:
        """Mark fork events as posted to Discord.

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
            UPDATE forks
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_forks_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_forks_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark forks as posted: {e}") from e

    async def get_unposted_commit_shas(self, shas: list[str]) -> set[str]:
        """Get list of commit SHAs that haven't been posted to Discord yet.

        Args:
            shas: List of full commit SHAs to check

        Returns:
            Set of SHAs that have posted_to_discord = FALSE

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not shas:
            return set()

        query = """
            SELECT sha
            FROM commits
            WHERE sha = ANY($1::text[])
              AND posted_to_discord = FALSE
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, shas)
                unposted_shas = {row["sha"] for row in rows}
                logger.info(
                    "database.get_unposted_shas.success",
                    total=len(shas),
                    unposted=len(unposted_shas),
                )
                return unposted_shas
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_shas.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted commit SHAs: {e}") from e

    async def insert_stars(self, stars: list[Any]) -> int:
        """Bulk insert stars with deduplication.

        Args:
            stars: List of WatchEvent objects

        Returns:
            Number of rows attempted to insert (actual inserts may be less due to
            ON CONFLICT DO NOTHING deduplication)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not stars:
            return 0

        query = """
            INSERT INTO stars (
                event_id, stargazer_username, stargazer_avatar_url, repo_owner, repo_name,
                is_public, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        s.event_id,
                        s.stargazer_username,
                        s.stargazer_avatar_url,
                        s.repo_owner,
                        s.repo_name,
                        s.is_public,
                        _to_naive_utc(s.event_timestamp),
                    )
                    for s in stars
                ]
                await conn.executemany(query, data)
                logger.info("database.insert_stars.success", total=len(stars))
                return len(stars)
        except asyncpg.PostgresError as e:
            logger.error("database.insert_stars.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert stars: {e}") from e

    async def insert_issue_comments(self, comments: list[Any]) -> int:
        """Bulk insert issue comments with deduplication.

        Args:
            comments: List of IssueCommentEvent objects

        Returns:
            Number of rows attempted to insert (actual inserts may be less due to
            ON CONFLICT DO NOTHING deduplication)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not comments:
            return 0

        query = """
            INSERT INTO issue_comments (
                event_id, action, issue_number, issue_title, commenter_username,
                commenter_avatar_url, comment_body, repo_owner, repo_name, is_public,
                url, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        c.event_id,
                        c.action,
                        c.issue_number,
                        c.issue_title,
                        c.commenter_username,
                        c.commenter_avatar_url,
                        c.comment_body,
                        c.repo_owner,
                        c.repo_name,
                        c.is_public,
                        c.url,
                        _to_naive_utc(c.event_timestamp),
                    )
                    for c in comments
                ]
                await conn.executemany(query, data)
                logger.info("database.insert_issue_comments.success", total=len(comments))
                return len(comments)
        except asyncpg.PostgresError as e:
            logger.error("database.insert_issue_comments.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert issue comments: {e}") from e

    async def insert_pr_review_comments(self, comments: list[Any]) -> int:
        """Bulk insert PR review comments with deduplication.

        Args:
            comments: List of PullRequestReviewCommentEvent objects

        Returns:
            Number of rows attempted to insert (actual inserts may be less due to
            ON CONFLICT DO NOTHING deduplication)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not comments:
            return 0

        query = """
            INSERT INTO pr_review_comments (
                event_id, action, pr_number, pr_title, commenter_username,
                commenter_avatar_url, comment_body, file_path, repo_owner, repo_name,
                is_public, url, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        c.event_id,
                        c.action,
                        c.pr_number,
                        c.pr_title,
                        c.commenter_username,
                        c.commenter_avatar_url,
                        c.comment_body,
                        c.file_path,
                        c.repo_owner,
                        c.repo_name,
                        c.is_public,
                        c.url,
                        _to_naive_utc(c.event_timestamp),
                    )
                    for c in comments
                ]
                await conn.executemany(query, data)
                logger.info("database.insert_pr_review_comments.success", total=len(comments))
                return len(comments)
        except asyncpg.PostgresError as e:
            logger.error("database.insert_pr_review_comments.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert PR review comments: {e}") from e

    async def insert_commit_comments(self, comments: list[Any]) -> int:
        """Bulk insert commit comments with deduplication.

        Args:
            comments: List of CommitCommentEvent objects

        Returns:
            Number of rows attempted to insert (actual inserts may be less due to
            ON CONFLICT DO NOTHING deduplication)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not comments:
            return 0

        query = """
            INSERT INTO commit_comments (
                event_id, action, commit_sha, short_sha, commenter_username,
                commenter_avatar_url, comment_body, file_path, repo_owner, repo_name,
                is_public, url, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        c.event_id,
                        c.action,
                        c.commit_sha,
                        c.short_sha,
                        c.commenter_username,
                        c.commenter_avatar_url,
                        c.comment_body,
                        c.file_path,
                        c.repo_owner,
                        c.repo_name,
                        c.is_public,
                        c.url,
                        _to_naive_utc(c.event_timestamp),
                    )
                    for c in comments
                ]
                await conn.executemany(query, data)
                logger.info("database.insert_commit_comments.success", total=len(comments))
                return len(comments)
        except asyncpg.PostgresError as e:
            logger.error("database.insert_commit_comments.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert commit comments: {e}") from e

    async def insert_members(self, members: list[Any]) -> int:
        """Bulk insert members with deduplication.

        Args:
            members: List of MemberEvent objects

        Returns:
            Number of rows attempted to insert (actual inserts may be less due to
            ON CONFLICT DO NOTHING deduplication)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not members:
            return 0

        query = """
            INSERT INTO members (
                event_id, action, member_username, member_avatar_url, actor_username,
                repo_owner, repo_name, is_public, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        m.event_id,
                        m.action,
                        m.member_username,
                        m.member_avatar_url,
                        m.actor_username,
                        m.repo_owner,
                        m.repo_name,
                        m.is_public,
                        _to_naive_utc(m.event_timestamp),
                    )
                    for m in members
                ]
                await conn.executemany(query, data)
                logger.info("database.insert_members.success", total=len(members))
                return len(members)
        except asyncpg.PostgresError as e:
            logger.error("database.insert_members.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert members: {e}") from e

    async def insert_wiki_pages(self, pages: list[Any]) -> int:
        """Bulk insert wiki pages with deduplication.

        Args:
            pages: List of GollumEvent objects

        Returns:
            Number of rows attempted to insert (actual inserts may be less due to
            ON CONFLICT DO NOTHING deduplication)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not pages:
            return 0

        query = """
            INSERT INTO wiki_pages (
                event_id, action, page_name, page_title, editor_username,
                editor_avatar_url, repo_owner, repo_name, is_public, url, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        p.event_id,
                        p.action,
                        p.page_name,
                        p.page_title,
                        p.editor_username,
                        p.editor_avatar_url,
                        p.repo_owner,
                        p.repo_name,
                        p.is_public,
                        p.url,
                        _to_naive_utc(p.event_timestamp),
                    )
                    for p in pages
                ]
                await conn.executemany(query, data)
                logger.info("database.insert_wiki_pages.success", total=len(pages))
                return len(pages)
        except asyncpg.PostgresError as e:
            logger.error("database.insert_wiki_pages.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert wiki pages: {e}") from e

    async def insert_public_events(self, events: list[Any]) -> int:
        """Bulk insert public events with deduplication.

        Args:
            events: List of PublicEvent objects

        Returns:
            Number of rows attempted to insert (actual inserts may be less due to
            ON CONFLICT DO NOTHING deduplication)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not events:
            return 0

        query = """
            INSERT INTO public_events (
                event_id, actor_username, actor_avatar_url, repo_owner, repo_name,
                event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        e.event_id,
                        e.actor_username,
                        e.actor_avatar_url,
                        e.repo_owner,
                        e.repo_name,
                        _to_naive_utc(e.event_timestamp),
                    )
                    for e in events
                ]
                await conn.executemany(query, data)
                logger.info("database.insert_public_events.success", total=len(events))
                return len(events)
        except asyncpg.PostgresError as e:
            logger.error("database.insert_public_events.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert public events: {e}") from e

    async def insert_discussions(self, discussions: list[Any]) -> int:
        """Bulk insert discussions with deduplication.

        Args:
            discussions: List of DiscussionEvent objects

        Returns:
            Number of rows attempted to insert (actual inserts may be less due to
            ON CONFLICT DO NOTHING deduplication)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        if not discussions:
            return 0

        query = """
            INSERT INTO discussions (
                event_id, action, discussion_number, discussion_title, category,
                author_username, author_avatar_url, repo_owner, repo_name, is_public,
                url, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (event_id) DO NOTHING
        """

        try:
            async with self.pool.acquire() as conn:
                data = [
                    (
                        d.event_id,
                        d.action,
                        d.discussion_number,
                        d.discussion_title,
                        d.category,
                        d.author_username,
                        d.author_avatar_url,
                        d.repo_owner,
                        d.repo_name,
                        d.is_public,
                        d.url,
                        _to_naive_utc(d.event_timestamp),
                    )
                    for d in discussions
                ]
                await conn.executemany(query, data)
                logger.info("database.insert_discussions.success", total=len(discussions))
                return len(discussions)
        except asyncpg.PostgresError as e:
            logger.error("database.insert_discussions.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert discussions: {e}") from e

    async def get_unposted_stars(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted stars within time window for recovery.

        Args:
            max_age_hours: Maximum age of stars to retrieve (default 12 hours)

        Returns:
            List of WatchEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import WatchEvent

        query = """
            SELECT * FROM stars
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                stars = [
                    WatchEvent(
                        event_id=row["event_id"],
                        stargazer_username=row["stargazer_username"],
                        stargazer_avatar_url=row["stargazer_avatar_url"] or "",
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        is_public=row["is_public"],
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_stars.success", count=len(stars))
                return stars
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_stars.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted stars: {e}") from e

    async def get_unposted_issue_comments(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted issue comments within time window for recovery.

        Args:
            max_age_hours: Maximum age of comments to retrieve (default 12 hours)

        Returns:
            List of IssueCommentEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import IssueCommentEvent

        query = """
            SELECT * FROM issue_comments
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                comments = [
                    IssueCommentEvent(
                        event_id=row["event_id"],
                        action=row["action"],
                        issue_number=row["issue_number"],
                        issue_title=row["issue_title"],
                        commenter_username=row["commenter_username"],
                        commenter_avatar_url=row["commenter_avatar_url"] or "",
                        comment_body=row["comment_body"],
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        is_public=row["is_public"],
                        url=row["url"] or "",
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_issue_comments.success", count=len(comments))
                return comments
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_issue_comments.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted issue comments: {e}") from e

    async def get_unposted_pr_review_comments(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted PR review comments within time window for recovery.

        Args:
            max_age_hours: Maximum age of comments to retrieve (default 12 hours)

        Returns:
            List of PullRequestReviewCommentEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import PullRequestReviewCommentEvent

        query = """
            SELECT * FROM pr_review_comments
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                comments = [
                    PullRequestReviewCommentEvent(
                        event_id=row["event_id"],
                        action=row["action"],
                        pr_number=row["pr_number"],
                        pr_title=row["pr_title"],
                        commenter_username=row["commenter_username"],
                        commenter_avatar_url=row["commenter_avatar_url"] or "",
                        comment_body=row["comment_body"],
                        file_path=row["file_path"],
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        is_public=row["is_public"],
                        url=row["url"] or "",
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_pr_review_comments.success", count=len(comments))
                return comments
        except asyncpg.PostgresError as e:
            logger.error(
                "database.get_unposted_pr_review_comments.failed", error=str(e), exc_info=True
            )
            raise DatabaseError(f"Failed to get unposted PR review comments: {e}") from e

    async def get_unposted_commit_comments(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted commit comments within time window for recovery.

        Args:
            max_age_hours: Maximum age of comments to retrieve (default 12 hours)

        Returns:
            List of CommitCommentEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import CommitCommentEvent

        query = """
            SELECT * FROM commit_comments
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                comments = [
                    CommitCommentEvent(
                        event_id=row["event_id"],
                        action=row["action"],
                        commit_sha=row["commit_sha"],
                        short_sha=row["short_sha"],
                        commenter_username=row["commenter_username"],
                        commenter_avatar_url=row["commenter_avatar_url"] or "",
                        comment_body=row["comment_body"],
                        file_path=row["file_path"],
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        is_public=row["is_public"],
                        url=row["url"] or "",
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_commit_comments.success", count=len(comments))
                return comments
        except asyncpg.PostgresError as e:
            logger.error(
                "database.get_unposted_commit_comments.failed", error=str(e), exc_info=True
            )
            raise DatabaseError(f"Failed to get unposted commit comments: {e}") from e

    async def get_unposted_members(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted member events within time window for recovery.

        Args:
            max_age_hours: Maximum age of members to retrieve (default 12 hours)

        Returns:
            List of MemberEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import MemberEvent

        query = """
            SELECT * FROM members
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                members = [
                    MemberEvent(
                        event_id=row["event_id"],
                        action=row["action"],
                        member_username=row["member_username"],
                        member_avatar_url=row["member_avatar_url"] or "",
                        actor_username=row["actor_username"],
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        is_public=row["is_public"],
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_members.success", count=len(members))
                return members
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_members.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted members: {e}") from e

    async def get_unposted_wiki_pages(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted wiki pages within time window for recovery.

        Args:
            max_age_hours: Maximum age of pages to retrieve (default 12 hours)

        Returns:
            List of GollumEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import GollumEvent

        query = """
            SELECT * FROM wiki_pages
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                pages = [
                    GollumEvent(
                        event_id=row["event_id"],
                        action=row["action"],
                        page_name=row["page_name"],
                        page_title=row["page_title"],
                        editor_username=row["editor_username"],
                        editor_avatar_url=row["editor_avatar_url"] or "",
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        is_public=row["is_public"],
                        url=row["url"] or "",
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_wiki_pages.success", count=len(pages))
                return pages
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_wiki_pages.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted wiki pages: {e}") from e

    async def get_unposted_public_events(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted public events within time window for recovery.

        Args:
            max_age_hours: Maximum age of events to retrieve (default 12 hours)

        Returns:
            List of PublicEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import PublicEvent

        query = """
            SELECT * FROM public_events
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                events = [
                    PublicEvent(
                        event_id=row["event_id"],
                        actor_username=row["actor_username"],
                        actor_avatar_url=row["actor_avatar_url"] or "",
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_public_events.success", count=len(events))
                return events
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_public_events.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted public events: {e}") from e

    async def get_unposted_discussions(self, max_age_hours: int = 12) -> list[Any]:
        """Get unposted discussions within time window for recovery.

        Args:
            max_age_hours: Maximum age of discussions to retrieve (default 12 hours)

        Returns:
            List of DiscussionEvent objects reconstructed from database rows

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.shared.models import DiscussionEvent

        query = """
            SELECT * FROM discussions
            WHERE posted_to_discord = FALSE
              AND created_at > NOW() - $1::interval
            ORDER BY event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                discussions = [
                    DiscussionEvent(
                        event_id=row["event_id"],
                        action=row["action"],
                        discussion_number=row["discussion_number"],
                        discussion_title=row["discussion_title"],
                        category=row["category"],
                        author_username=row["author_username"],
                        author_avatar_url=row["author_avatar_url"] or "",
                        repo_owner=row["repo_owner"],
                        repo_name=row["repo_name"],
                        is_public=row["is_public"],
                        url=row["url"] or "",
                        event_timestamp=row["event_timestamp"],
                    )
                    for row in rows
                ]
                logger.info("database.get_unposted_discussions.success", count=len(discussions))
                return discussions
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_discussions.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted discussions: {e}") from e

    async def mark_stars_posted(self, event_ids: list[str]) -> None:
        """Mark stars as posted to Discord.

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
            UPDATE stars
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_stars_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_stars_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark stars as posted: {e}") from e

    async def mark_issue_comments_posted(self, event_ids: list[str]) -> None:
        """Mark issue comments as posted to Discord.

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
            UPDATE issue_comments
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_issue_comments_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_issue_comments_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark issue comments as posted: {e}") from e

    async def mark_pr_review_comments_posted(self, event_ids: list[str]) -> None:
        """Mark PR review comments as posted to Discord.

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
            UPDATE pr_review_comments
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_pr_review_comments_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error(
                "database.mark_pr_review_comments_posted.failed", error=str(e), exc_info=True
            )
            raise DatabaseError(f"Failed to mark PR review comments as posted: {e}") from e

    async def mark_commit_comments_posted(self, event_ids: list[str]) -> None:
        """Mark commit comments as posted to Discord.

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
            UPDATE commit_comments
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_commit_comments_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_commit_comments_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark commit comments as posted: {e}") from e

    async def mark_members_posted(self, event_ids: list[str]) -> None:
        """Mark member events as posted to Discord.

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
            UPDATE members
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_members_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_members_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark members as posted: {e}") from e

    async def mark_wiki_pages_posted(self, event_ids: list[str]) -> None:
        """Mark wiki pages as posted to Discord.

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
            UPDATE wiki_pages
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_wiki_pages_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_wiki_pages_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark wiki pages as posted: {e}") from e

    async def mark_public_events_posted(self, event_ids: list[str]) -> None:
        """Mark public events as posted to Discord.

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
            UPDATE public_events
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_public_events_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_public_events_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark public events as posted: {e}") from e

    async def mark_discussions_posted(self, event_ids: list[str]) -> None:
        """Mark discussions as posted to Discord.

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
            UPDATE discussions
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE event_id = ANY($1::text[])
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, event_ids)
                logger.info("database.mark_discussions_posted.success", count=len(event_ids))
        except asyncpg.PostgresError as e:
            logger.error("database.mark_discussions_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark discussions as posted: {e}") from e

    # ==================== NFT Operations ====================

    async def get_nft_collection_db_id(self, collection_id: str) -> int | None:
        """Get database ID for an NFT collection by its string identifier.

        Args:
            collection_id: Collection string identifier (e.g., "aeon-forge-genesis")

        Returns:
            Database ID or None if not found

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = "SELECT id FROM nft_collections WHERE collection_id = $1"

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, collection_id)
                return row["id"] if row else None
        except asyncpg.PostgresError as e:
            logger.error("database.get_nft_collection_id.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get NFT collection ID: {e}") from e

    async def sync_nft_collection(
        self,
        collection_id: str,
        name: str,
        chain: str,
        contract_address: str,
        discord_channel_id: int,
        is_active: bool = True,
    ) -> int:
        """Sync NFT collection config to database.

        Inserts or updates the collection record.

        Args:
            collection_id: Unique collection identifier
            name: Collection name
            chain: Blockchain network
            contract_address: NFT contract address
            discord_channel_id: Discord channel for notifications
            is_active: Whether collection is active

        Returns:
            Database ID of the collection

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            INSERT INTO nft_collections (
                collection_id, name, chain, contract_address, discord_channel_id, is_active
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (chain, contract_address)
            DO UPDATE SET
                collection_id = $1,
                name = $2,
                discord_channel_id = $5,
                is_active = $6
            RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    collection_id,
                    name,
                    chain,
                    contract_address.lower(),
                    discord_channel_id,
                    is_active,
                )
                db_id: int = row["id"]
                logger.info("database.sync_nft_collection.success", collection_id=collection_id)
                return db_id
        except asyncpg.PostgresError as e:
            logger.error("database.sync_nft_collection.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to sync NFT collection: {e}") from e

    async def insert_nft_mint(self, event: "NFTMintEvent") -> bool:
        """Insert NFT mint event.

        Args:
            event: NFTMintEvent object

        Returns:
            True if inserted, False if duplicate

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            INSERT INTO nft_mints (
                collection_id, token_id, to_address, price_native, price_usd,
                transaction_hash, block_number, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (collection_id, token_id, transaction_hash) DO NOTHING
            RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    event.collection_id,
                    event.token_id,
                    event.to_address,
                    event.price_native,
                    event.price_usd,
                    event.transaction_hash,
                    event.block_number,
                    _to_naive_utc(event.event_timestamp),
                )
                return row is not None
        except asyncpg.PostgresError as e:
            logger.error("database.insert_nft_mint.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert NFT mint: {e}") from e

    async def insert_nft_transfer(self, event: "NFTTransferEvent") -> bool:
        """Insert NFT transfer event.

        Args:
            event: NFTTransferEvent object

        Returns:
            True if inserted, False if duplicate

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            INSERT INTO nft_transfers (
                collection_id, token_id, from_address, to_address,
                transaction_hash, block_number, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (collection_id, token_id, transaction_hash) DO NOTHING
            RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    event.collection_id,
                    event.token_id,
                    event.from_address,
                    event.to_address,
                    event.transaction_hash,
                    event.block_number,
                    _to_naive_utc(event.event_timestamp),
                )
                return row is not None
        except asyncpg.PostgresError as e:
            logger.error("database.insert_nft_transfer.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert NFT transfer: {e}") from e

    async def insert_nft_burn(self, event: "NFTBurnEvent") -> bool:
        """Insert NFT burn event.

        Args:
            event: NFTBurnEvent object

        Returns:
            True if inserted, False if duplicate

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            INSERT INTO nft_burns (
                collection_id, token_id, from_address,
                transaction_hash, block_number, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (collection_id, token_id, transaction_hash) DO NOTHING
            RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    event.collection_id,
                    event.token_id,
                    event.from_address,
                    event.transaction_hash,
                    event.block_number,
                    _to_naive_utc(event.event_timestamp),
                )
                return row is not None
        except asyncpg.PostgresError as e:
            logger.error("database.insert_nft_burn.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert NFT burn: {e}") from e

    async def insert_nft_listing(self, event: "NFTListingEvent") -> bool:
        """Insert NFT listing event.

        Args:
            event: NFTListingEvent object

        Returns:
            True if inserted, False if duplicate

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            INSERT INTO nft_listings (
                collection_id, token_id, token_name, token_image_url, seller_address,
                marketplace, price_native, price_usd, floor_price_native, rarity_rank,
                listing_id, event_timestamp, is_active
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (collection_id, marketplace, listing_id) DO NOTHING
            RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    event.collection_id,
                    event.token_id,
                    event.token_name,
                    event.token_image_url,
                    event.seller_address,
                    event.marketplace,
                    event.price_native,
                    event.price_usd,
                    event.floor_price_native,
                    event.rarity_rank,
                    event.listing_id,
                    _to_naive_utc(event.event_timestamp),
                    event.is_active,
                )
                return row is not None
        except asyncpg.PostgresError as e:
            logger.error("database.insert_nft_listing.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert NFT listing: {e}") from e

    async def insert_nft_sale(self, event: "NFTSaleEvent") -> bool:
        """Insert NFT sale event.

        Args:
            event: NFTSaleEvent object

        Returns:
            True if inserted, False if duplicate

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            INSERT INTO nft_sales (
                collection_id, token_id, token_name, token_image_url, seller_address,
                buyer_address, marketplace, price_native, price_usd, floor_price_native,
                rarity_rank, sale_id, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (collection_id, marketplace, sale_id) DO NOTHING
            RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    event.collection_id,
                    event.token_id,
                    event.token_name,
                    event.token_image_url,
                    event.seller_address,
                    event.buyer_address,
                    event.marketplace,
                    event.price_native,
                    event.price_usd,
                    event.floor_price_native,
                    event.rarity_rank,
                    event.sale_id,
                    _to_naive_utc(event.event_timestamp),
                )
                return row is not None
        except asyncpg.PostgresError as e:
            logger.error("database.insert_nft_sale.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert NFT sale: {e}") from e

    async def insert_nft_delisting(self, event: "NFTDelistingEvent") -> bool:
        """Insert NFT delisting event.

        Args:
            event: NFTDelistingEvent object

        Returns:
            True if inserted, False if duplicate

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            INSERT INTO nft_delistings (
                collection_id, token_id, token_name, seller_address, marketplace,
                original_price_native, delisting_id, event_timestamp
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (collection_id, marketplace, delisting_id) DO NOTHING
            RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    event.collection_id,
                    event.token_id,
                    event.token_name,
                    event.seller_address,
                    event.marketplace,
                    event.original_price_native,
                    event.delisting_id,
                    _to_naive_utc(event.event_timestamp),
                )
                return row is not None
        except asyncpg.PostgresError as e:
            logger.error("database.insert_nft_delisting.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to insert NFT delisting: {e}") from e

    async def mark_nft_mint_posted(
        self, collection_id: int, token_id: str, transaction_hash: str | None
    ) -> None:
        """Mark NFT mint as posted to Discord.

        Args:
            collection_id: Database collection ID
            token_id: NFT token ID
            transaction_hash: Transaction hash

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            UPDATE nft_mints
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE collection_id = $1 AND token_id = $2 AND transaction_hash = $3
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, collection_id, token_id, transaction_hash)
        except asyncpg.PostgresError as e:
            logger.error("database.mark_nft_mint_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark NFT mint posted: {e}") from e

    async def mark_nft_transfer_posted(
        self, collection_id: int, token_id: str, transaction_hash: str | None
    ) -> None:
        """Mark NFT transfer as posted to Discord.

        Args:
            collection_id: Database collection ID
            token_id: NFT token ID
            transaction_hash: Transaction hash

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            UPDATE nft_transfers
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE collection_id = $1 AND token_id = $2 AND transaction_hash = $3
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, collection_id, token_id, transaction_hash)
        except asyncpg.PostgresError as e:
            logger.error("database.mark_nft_transfer_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark NFT transfer posted: {e}") from e

    async def mark_nft_burn_posted(
        self, collection_id: int, token_id: str, transaction_hash: str | None
    ) -> None:
        """Mark NFT burn as posted to Discord.

        Args:
            collection_id: Database collection ID
            token_id: NFT token ID
            transaction_hash: Transaction hash

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            UPDATE nft_burns
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE collection_id = $1 AND token_id = $2 AND transaction_hash = $3
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, collection_id, token_id, transaction_hash)
        except asyncpg.PostgresError as e:
            logger.error("database.mark_nft_burn_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark NFT burn posted: {e}") from e

    async def mark_nft_listing_posted(
        self, collection_id: int, marketplace: str, listing_id: str
    ) -> None:
        """Mark NFT listing as posted to Discord.

        Args:
            collection_id: Database collection ID
            marketplace: Marketplace name
            listing_id: Listing ID

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            UPDATE nft_listings
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE collection_id = $1 AND marketplace = $2 AND listing_id = $3
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, collection_id, marketplace, listing_id)
        except asyncpg.PostgresError as e:
            logger.error("database.mark_nft_listing_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark NFT listing posted: {e}") from e

    async def mark_nft_sale_posted(
        self, collection_id: int, marketplace: str, sale_id: str
    ) -> None:
        """Mark NFT sale as posted to Discord.

        Args:
            collection_id: Database collection ID
            marketplace: Marketplace name
            sale_id: Sale ID

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            UPDATE nft_sales
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE collection_id = $1 AND marketplace = $2 AND sale_id = $3
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, collection_id, marketplace, sale_id)
        except asyncpg.PostgresError as e:
            logger.error("database.mark_nft_sale_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark NFT sale posted: {e}") from e

    async def mark_nft_delisting_posted(
        self, collection_id: int, marketplace: str, delisting_id: str
    ) -> None:
        """Mark NFT delisting as posted to Discord.

        Args:
            collection_id: Database collection ID
            marketplace: Marketplace name
            delisting_id: Delisting ID

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            UPDATE nft_delistings
            SET posted_to_discord = TRUE, posted_at = NOW()
            WHERE collection_id = $1 AND marketplace = $2 AND delisting_id = $3
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, collection_id, marketplace, delisting_id)
        except asyncpg.PostgresError as e:
            logger.error("database.mark_nft_delisting_posted.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to mark NFT delisting posted: {e}") from e

    async def get_nft_marketplace_state(
        self, collection_id: int, marketplace: str
    ) -> datetime | None:
        """Get last poll timestamp for a collection/marketplace pair.

        Args:
            collection_id: Database collection ID
            marketplace: Marketplace name

        Returns:
            Last poll timestamp or None if never polled

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            SELECT last_poll_timestamp FROM nft_marketplace_state
            WHERE collection_id = $1 AND marketplace = $2
        """

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, collection_id, marketplace)
                if row and row["last_poll_timestamp"]:
                    # Add UTC timezone to naive datetime
                    return row["last_poll_timestamp"].replace(tzinfo=UTC)
                return None
        except asyncpg.PostgresError as e:
            logger.error("database.get_nft_marketplace_state.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get marketplace state: {e}") from e

    async def set_nft_marketplace_state(
        self, collection_id: int, marketplace: str, event_id: str | None = None
    ) -> None:
        """Update marketplace polling state.

        Args:
            collection_id: Database collection ID
            marketplace: Marketplace name
            event_id: Optional last event ID for cursor pagination

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        query = """
            INSERT INTO nft_marketplace_state (collection_id, marketplace, last_poll_timestamp, last_event_id)
            VALUES ($1, $2, NOW(), $3)
            ON CONFLICT (collection_id, marketplace)
            DO UPDATE SET last_poll_timestamp = NOW(), last_event_id = $3, updated_at = NOW()
        """

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(query, collection_id, marketplace, event_id)
        except asyncpg.PostgresError as e:
            logger.error("database.set_nft_marketplace_state.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to set marketplace state: {e}") from e

    async def get_unposted_nft_mints(
        self, max_age_hours: int = 12
    ) -> list[tuple[int, "NFTMintEvent", str, int]]:
        """Get unposted NFT mint events for recovery.

        Args:
            max_age_hours: Maximum age of events to retrieve

        Returns:
            List of tuples: (db_id, NFTMintEvent, collection_name, discord_channel_id)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.nft.models import NFTMintEvent

        query = """
            SELECT m.*, c.name as collection_name, c.discord_channel_id
            FROM nft_mints m
            JOIN nft_collections c ON m.collection_id = c.id
            WHERE m.posted_to_discord = FALSE
              AND m.created_at > NOW() - $1::interval
              AND c.is_active = TRUE
            ORDER BY m.event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                results = []
                for row in rows:
                    event = NFTMintEvent(
                        collection_id=row["collection_id"],
                        token_id=row["token_id"],
                        to_address=row["to_address"],
                        price_native=row["price_native"],
                        price_usd=row["price_usd"],
                        transaction_hash=row["transaction_hash"],
                        block_number=row["block_number"],
                        event_timestamp=row["event_timestamp"].replace(tzinfo=UTC),
                    )
                    results.append(
                        (
                            row["id"],
                            event,
                            row["collection_name"],
                            row["discord_channel_id"],
                        )
                    )
                return results
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_nft_mints.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted NFT mints: {e}") from e

    async def get_unposted_nft_transfers(
        self, max_age_hours: int = 12
    ) -> list[tuple[int, "NFTTransferEvent", str, int]]:
        """Get unposted NFT transfer events for recovery.

        Args:
            max_age_hours: Maximum age of events to retrieve

        Returns:
            List of tuples: (db_id, NFTTransferEvent, collection_name, discord_channel_id)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.nft.models import NFTTransferEvent

        query = """
            SELECT t.*, c.name as collection_name, c.discord_channel_id
            FROM nft_transfers t
            JOIN nft_collections c ON t.collection_id = c.id
            WHERE t.posted_to_discord = FALSE
              AND t.created_at > NOW() - $1::interval
              AND c.is_active = TRUE
            ORDER BY t.event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                results = []
                for row in rows:
                    event = NFTTransferEvent(
                        collection_id=row["collection_id"],
                        token_id=row["token_id"],
                        from_address=row["from_address"],
                        to_address=row["to_address"],
                        transaction_hash=row["transaction_hash"],
                        block_number=row["block_number"],
                        event_timestamp=row["event_timestamp"].replace(tzinfo=UTC),
                    )
                    results.append(
                        (
                            row["id"],
                            event,
                            row["collection_name"],
                            row["discord_channel_id"],
                        )
                    )
                return results
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_nft_transfers.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted NFT transfers: {e}") from e

    async def get_unposted_nft_burns(
        self, max_age_hours: int = 12
    ) -> list[tuple[int, "NFTBurnEvent", str, int]]:
        """Get unposted NFT burn events for recovery.

        Args:
            max_age_hours: Maximum age of events to retrieve

        Returns:
            List of tuples: (db_id, NFTBurnEvent, collection_name, discord_channel_id)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.nft.models import NFTBurnEvent

        query = """
            SELECT b.*, c.name as collection_name, c.discord_channel_id
            FROM nft_burns b
            JOIN nft_collections c ON b.collection_id = c.id
            WHERE b.posted_to_discord = FALSE
              AND b.created_at > NOW() - $1::interval
              AND c.is_active = TRUE
            ORDER BY b.event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                results = []
                for row in rows:
                    event = NFTBurnEvent(
                        collection_id=row["collection_id"],
                        token_id=row["token_id"],
                        from_address=row["from_address"],
                        transaction_hash=row["transaction_hash"],
                        block_number=row["block_number"],
                        event_timestamp=row["event_timestamp"].replace(tzinfo=UTC),
                    )
                    results.append(
                        (
                            row["id"],
                            event,
                            row["collection_name"],
                            row["discord_channel_id"],
                        )
                    )
                return results
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_nft_burns.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted NFT burns: {e}") from e

    async def get_unposted_nft_listings(
        self, max_age_hours: int = 12
    ) -> list[tuple[int, "NFTListingEvent", str, int]]:
        """Get unposted NFT listing events for recovery.

        Args:
            max_age_hours: Maximum age of events to retrieve

        Returns:
            List of tuples: (db_id, NFTListingEvent, collection_name, discord_channel_id)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.nft.models import NFTListingEvent

        query = """
            SELECT l.*, c.name as collection_name, c.discord_channel_id
            FROM nft_listings l
            JOIN nft_collections c ON l.collection_id = c.id
            WHERE l.posted_to_discord = FALSE
              AND l.created_at > NOW() - $1::interval
              AND c.is_active = TRUE
            ORDER BY l.event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                results = []
                for row in rows:
                    event = NFTListingEvent(
                        collection_id=row["collection_id"],
                        token_id=row["token_id"],
                        token_name=row["token_name"],
                        token_image_url=row["token_image_url"],
                        seller_address=row["seller_address"],
                        marketplace=row["marketplace"],
                        price_native=row["price_native"],
                        price_usd=row["price_usd"],
                        floor_price_native=row["floor_price_native"],
                        rarity_rank=row["rarity_rank"],
                        listing_id=row["listing_id"],
                        event_timestamp=row["event_timestamp"].replace(tzinfo=UTC),
                        is_active=row["is_active"],
                    )
                    results.append(
                        (
                            row["id"],
                            event,
                            row["collection_name"],
                            row["discord_channel_id"],
                        )
                    )
                return results
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_nft_listings.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted NFT listings: {e}") from e

    async def get_unposted_nft_sales(
        self, max_age_hours: int = 12
    ) -> list[tuple[int, "NFTSaleEvent", str, int]]:
        """Get unposted NFT sale events for recovery.

        Args:
            max_age_hours: Maximum age of events to retrieve

        Returns:
            List of tuples: (db_id, NFTSaleEvent, collection_name, discord_channel_id)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.nft.models import NFTSaleEvent

        query = """
            SELECT s.*, c.name as collection_name, c.discord_channel_id
            FROM nft_sales s
            JOIN nft_collections c ON s.collection_id = c.id
            WHERE s.posted_to_discord = FALSE
              AND s.created_at > NOW() - $1::interval
              AND c.is_active = TRUE
            ORDER BY s.event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                results = []
                for row in rows:
                    event = NFTSaleEvent(
                        collection_id=row["collection_id"],
                        token_id=row["token_id"],
                        token_name=row["token_name"],
                        token_image_url=row["token_image_url"],
                        seller_address=row["seller_address"],
                        buyer_address=row["buyer_address"],
                        marketplace=row["marketplace"],
                        price_native=row["price_native"],
                        price_usd=row["price_usd"],
                        floor_price_native=row["floor_price_native"],
                        rarity_rank=row["rarity_rank"],
                        sale_id=row["sale_id"],
                        event_timestamp=row["event_timestamp"].replace(tzinfo=UTC),
                    )
                    results.append(
                        (
                            row["id"],
                            event,
                            row["collection_name"],
                            row["discord_channel_id"],
                        )
                    )
                return results
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_nft_sales.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted NFT sales: {e}") from e

    async def get_unposted_nft_delistings(
        self, max_age_hours: int = 12
    ) -> list[tuple[int, "NFTDelistingEvent", str, int]]:
        """Get unposted NFT delisting events for recovery.

        Args:
            max_age_hours: Maximum age of events to retrieve

        Returns:
            List of tuples: (db_id, NFTDelistingEvent, collection_name, discord_channel_id)

        Raises:
            DatabaseError: If connection pool is not initialized or query fails
        """
        if not self.pool:
            raise DatabaseError("Connection pool not initialized")

        from app.nft.models import NFTDelistingEvent

        query = """
            SELECT d.*, c.name as collection_name, c.discord_channel_id
            FROM nft_delistings d
            JOIN nft_collections c ON d.collection_id = c.id
            WHERE d.posted_to_discord = FALSE
              AND d.created_at > NOW() - $1::interval
              AND c.is_active = TRUE
            ORDER BY d.event_timestamp ASC
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, timedelta(hours=max_age_hours))
                results = []
                for row in rows:
                    event = NFTDelistingEvent(
                        collection_id=row["collection_id"],
                        token_id=row["token_id"],
                        token_name=row["token_name"],
                        seller_address=row["seller_address"],
                        marketplace=row["marketplace"],
                        original_price_native=row["original_price_native"],
                        delisting_id=row["delisting_id"],
                        event_timestamp=row["event_timestamp"].replace(tzinfo=UTC),
                    )
                    results.append(
                        (
                            row["id"],
                            event,
                            row["collection_name"],
                            row["discord_channel_id"],
                        )
                    )
                return results
        except asyncpg.PostgresError as e:
            logger.error("database.get_unposted_nft_delistings.failed", error=str(e), exc_info=True)
            raise DatabaseError(f"Failed to get unposted NFT delistings: {e}") from e
