"""Statistics calculator functions."""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import asyncpg

from app.core.logging import get_logger
from app.shared.exceptions import DatabaseError
from app.stats.models import RepoStats, TimePatternStats, UserStats
from app.stats.queries import (
    GET_COMMITS_BY_DAY,
    GET_COMMITS_BY_HOUR,
    GET_MOST_ACTIVE_REPO,
    GET_REPO_STATS,
    GET_USER_TIME_WINDOW_STATS,
    GET_USER_TOTALS,
)

if TYPE_CHECKING:
    from app.core.database import DatabaseClient

logger = get_logger(__name__)


async def calculate_user_stats(db: "DatabaseClient", username: str) -> UserStats:
    """Calculate comprehensive user statistics.

    Args:
        db: Database client
        username: GitHub username

    Returns:
        UserStats object with all calculated statistics

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    try:
        async with db.pool.acquire() as conn:
            # Get all-time totals
            totals_row = await conn.fetchrow(GET_USER_TOTALS, username)
            if not totals_row:
                # User has no activity
                return UserStats(username=username)

            # Get time window stats (today, this week, this month)
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=today_start.weekday())
            month_start = today_start.replace(day=1)

            # For commits and PRs in different time windows
            commits_today = await conn.fetchval(
                """
                SELECT COUNT(*) FROM commits
                WHERE author_username = $1 AND commit_timestamp >= $2
                """,
                username,
                today_start,
            )

            commits_week = await conn.fetchval(
                """
                SELECT COUNT(*) FROM commits
                WHERE author_username = $1 AND commit_timestamp >= $2
                """,
                username,
                week_start,
            )

            commits_month = await conn.fetchval(
                """
                SELECT COUNT(*) FROM commits
                WHERE author_username = $1 AND commit_timestamp >= $2
                """,
                username,
                month_start,
            )

            prs_today = await conn.fetchval(
                """
                SELECT COUNT(*) FROM pull_requests
                WHERE author_username = $1 AND event_timestamp >= $2
                """,
                username,
                today_start,
            )

            prs_week = await conn.fetchval(
                """
                SELECT COUNT(*) FROM pull_requests
                WHERE author_username = $1 AND event_timestamp >= $2
                """,
                username,
                week_start,
            )

            prs_month = await conn.fetchval(
                """
                SELECT COUNT(*) FROM pull_requests
                WHERE author_username = $1 AND event_timestamp >= $2
                """,
                username,
                month_start,
            )

            # Get most active repo
            repo_row = await conn.fetchrow(GET_MOST_ACTIVE_REPO, username)
            most_active_repo = repo_row["repo_full_name"] if repo_row else None
            most_active_count = repo_row["event_count"] if repo_row else 0

            # Get last activity
            last_activity = await conn.fetchval(
                """
                SELECT MAX(latest) FROM (
                    SELECT MAX(commit_timestamp) as latest FROM commits WHERE author_username = $1
                    UNION ALL
                    SELECT MAX(event_timestamp) FROM pull_requests WHERE author_username = $1
                    UNION ALL
                    SELECT MAX(event_timestamp) FROM issues WHERE author_username = $1
                ) all_times
                """,
                username,
            )

            return UserStats(
                username=username,
                total_commits=totals_row["total_commits"],
                total_prs=totals_row["total_prs"],
                total_issues=totals_row["total_issues"],
                total_reviews=totals_row["total_reviews"],
                total_releases=totals_row["total_releases"],
                total_creations=totals_row["total_creations"],
                total_deletions=totals_row["total_deletions"],
                total_forks=totals_row["total_forks"],
                commits_today=commits_today or 0,
                commits_this_week=commits_week or 0,
                commits_this_month=commits_month or 0,
                prs_today=prs_today or 0,
                prs_this_week=prs_week or 0,
                prs_this_month=prs_month or 0,
                most_active_repo=most_active_repo,
                most_active_repo_count=most_active_count,
                last_activity=last_activity,
            )

    except asyncpg.PostgresError as e:
        logger.error("stats.calculate.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to calculate user stats: {e}") from e


async def calculate_time_patterns(db: "DatabaseClient", username: str) -> TimePatternStats:
    """Calculate time-based activity patterns.

    Args:
        db: Database client
        username: GitHub username

    Returns:
        TimePatternStats with hour/day patterns

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    try:
        async with db.pool.acquire() as conn:
            # Get commits by hour
            hour_rows = await conn.fetch(GET_COMMITS_BY_HOUR, username)
            commits_by_hour = {int(row["hour"]): row["count"] for row in hour_rows}

            # Get commits by day (convert DOW: 0=Sun to 0=Mon)
            day_rows = await conn.fetch(GET_COMMITS_BY_DAY, username)
            commits_by_day = {}
            for row in day_rows:
                dow_sunday = int(row["dow"])  # 0=Sunday
                dow_monday = (dow_sunday + 6) % 7  # Convert to 0=Monday
                commits_by_day[dow_monday] = row["count"]

            # Find peak hour and day
            peak_hour = max(commits_by_hour, key=commits_by_hour.get) if commits_by_hour else None
            peak_day = max(commits_by_day, key=commits_by_day.get) if commits_by_day else None

            # Count night commits (10pm-6am) and early commits (5am-9am)
            night_commits = sum(
                commits_by_hour.get(h, 0) for h in list(range(22, 24)) + list(range(0, 6))
            )
            early_commits = sum(commits_by_hour.get(h, 0) for h in range(5, 9))

            return TimePatternStats(
                peak_hour=peak_hour,
                peak_day=peak_day,
                night_commits=night_commits,
                early_commits=early_commits,
                commits_by_hour=commits_by_hour,
                commits_by_day=commits_by_day,
            )

    except asyncpg.PostgresError as e:
        logger.error("stats.time_patterns.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to calculate time patterns: {e}") from e


async def calculate_repo_stats(
    db: "DatabaseClient", username: str, since: datetime | None = None
) -> list[RepoStats]:
    """Calculate per-repository statistics.

    Args:
        db: Database client
        username: GitHub username
        since: Optional start time to filter events

    Returns:
        List of RepoStats sorted by total_events descending

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(GET_REPO_STATS, username, since)
            return [
                RepoStats(
                    repo_full_name=row["repo_full_name"],
                    commits=row["commits"] or 0,
                    prs=row["prs"] or 0,
                    issues=row["issues"] or 0,
                    reviews=row["reviews"] or 0,
                    total_events=row["total_events"] or 0,
                )
                for row in rows
            ]

    except asyncpg.PostgresError as e:
        logger.error("stats.repo_stats.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to calculate repo stats: {e}") from e
