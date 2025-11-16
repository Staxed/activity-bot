"""Achievement checking and recording functions."""

import json
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import asyncpg

from app.core.database import _to_naive_utc
from app.core.logging import get_logger
from app.shared.exceptions import DatabaseError
from app.stats.achievements import get_achievements
from app.stats.models import EarnedAchievement
from app.stats.queries import (
    CHECK_ACHIEVEMENT_EARNED,
    GET_ACHIEVEMENT_COUNT,
    GET_DAILY_COMMIT_COUNT,
    GET_EARLY_BIRD_COUNT,
    GET_LONGEST_COMMIT_MESSAGE,
    GET_NIGHT_OWL_COUNT,
    INSERT_ACHIEVEMENT,
)

if TYPE_CHECKING:
    from app.core.database import DatabaseClient

logger = get_logger(__name__)


async def _already_earned(
    conn: asyncpg.Connection,
    username: str,
    achievement_id: str,
    period_type: str,
    period_date: date,
) -> bool:
    """Check if achievement already earned for this period.

    Args:
        conn: Database connection
        username: GitHub username
        achievement_id: Achievement identifier
        period_type: Period type (daily, weekly, monthly, milestone)
        period_date: Date of the period

    Returns:
        True if already earned, False otherwise
    """
    result = await conn.fetchval(
        CHECK_ACHIEVEMENT_EARNED, username, achievement_id, period_type, period_date
    )
    return result is not None


async def _count_night_commits(conn: asyncpg.Connection, username: str, check_date: date) -> int:
    """Count commits between 10pm-6am on a specific date.

    Args:
        conn: Database connection
        username: GitHub username
        check_date: Date to check

    Returns:
        Count of night commits
    """
    count = await conn.fetchval(GET_NIGHT_OWL_COUNT, username, check_date)
    return count or 0


async def _count_early_commits(conn: asyncpg.Connection, username: str, check_date: date) -> int:
    """Count commits between 5am-9am on a specific date.

    Args:
        conn: Database connection
        username: GitHub username
        check_date: Date to check

    Returns:
        Count of early commits
    """
    count = await conn.fetchval(GET_EARLY_BIRD_COUNT, username, check_date)
    return count or 0


async def _count_daily_commits(conn: asyncpg.Connection, username: str, check_date: date) -> int:
    """Count total commits on a specific date.

    Args:
        conn: Database connection
        username: GitHub username
        check_date: Date to check

    Returns:
        Count of commits
    """
    count = await conn.fetchval(GET_DAILY_COMMIT_COUNT, username, check_date)
    return count or 0


async def _check_commit_poet(conn: asyncpg.Connection, username: str, check_date: date) -> bool:
    """Check if user made a commit with message > 100 chars.

    Args:
        conn: Database connection
        username: GitHub username
        check_date: Date to check

    Returns:
        True if condition met
    """
    max_length = await conn.fetchval(GET_LONGEST_COMMIT_MESSAGE, username, check_date)
    return (max_length or 0) > 100


async def check_daily_achievements(
    db: "DatabaseClient", username: str, check_date: date
) -> list[EarnedAchievement]:
    """Check and return newly earned daily achievements.

    Args:
        db: Database client
        username: GitHub username
        check_date: Date to check achievements for

    Returns:
        List of newly earned achievements

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    achievements = get_achievements()
    earned = []

    try:
        async with db.pool.acquire() as conn:
            # Check each daily achievement
            for ach_id, ach in achievements.items():
                if ach.frequency != "daily":
                    continue

                # Check if already earned
                if await _already_earned(conn, username, ach_id, "daily", check_date):
                    continue

                # Check specific achievement conditions
                earned_now = False
                metadata = {}

                if ach_id == "night_owl":
                    count = await _count_night_commits(conn, username, check_date)
                    if count >= ach.threshold:
                        earned_now = True
                        metadata = {"count": count, "threshold": ach.threshold}

                elif ach_id == "early_bird":
                    count = await _count_early_commits(conn, username, check_date)
                    if count >= ach.threshold:
                        earned_now = True
                        metadata = {"count": count, "threshold": ach.threshold}

                elif ach_id == "daily_dozen":
                    count = await _count_daily_commits(conn, username, check_date)
                    if count >= ach.threshold:
                        earned_now = True
                        metadata = {"count": count, "threshold": ach.threshold}

                elif ach_id == "streak_keeper":
                    # Checked elsewhere (in streak calculator), just verify commit exists
                    count = await _count_daily_commits(conn, username, check_date)
                    if count > 0:
                        earned_now = True
                        metadata = {"count": count}

                elif ach_id == "commit_poet":
                    if await _check_commit_poet(conn, username, check_date):
                        earned_now = True
                        metadata = {"threshold": 100}

                if earned_now:
                    earned_achievement = EarnedAchievement(
                        achievement_id=ach_id,
                        period_type="daily",
                        period_date=check_date,
                        earned_at=datetime.now(UTC),
                        metadata=metadata,
                    )
                    earned.append(earned_achievement)

            logger.info(
                "achievements.daily.checked",
                username=username,
                date=check_date,
                earned_count=len(earned),
            )

            return earned

    except asyncpg.PostgresError as e:
        logger.error("achievements.daily.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to check daily achievements: {e}") from e


async def record_achievement(
    db: "DatabaseClient", username: str, achievement: EarnedAchievement
) -> None:
    """Record an earned achievement to the database.

    Args:
        db: Database client
        username: GitHub username
        achievement: EarnedAchievement object to record

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    try:
        async with db.pool.acquire() as conn:
            await conn.execute(
                INSERT_ACHIEVEMENT,
                username,
                achievement.achievement_id,
                achievement.period_type,
                achievement.period_date,
                _to_naive_utc(achievement.earned_at),
                json.dumps(achievement.metadata),
            )
            logger.info(
                "achievement.recorded",
                username=username,
                achievement_id=achievement.achievement_id,
                period_date=achievement.period_date,
            )

    except asyncpg.PostgresError as e:
        logger.error("achievement.record.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to record achievement: {e}") from e


async def get_achievement_count(db: "DatabaseClient", username: str, achievement_id: str) -> int:
    """Get total count of times an achievement was earned.

    Args:
        db: Database client
        username: GitHub username
        achievement_id: Achievement identifier

    Returns:
        Total earn count

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    try:
        async with db.pool.acquire() as conn:
            count = await conn.fetchval(GET_ACHIEVEMENT_COUNT, username, achievement_id)
            return count or 0

    except asyncpg.PostgresError as e:
        logger.error("achievement.count.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to get achievement count: {e}") from e
