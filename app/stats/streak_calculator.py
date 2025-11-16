"""Streak calculation functions for daily/weekly/monthly/yearly streaks."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import asyncpg

from app.core.logging import get_logger
from app.shared.exceptions import DatabaseError
from app.stats.models import StreakInfo
from app.stats.queries import (
    GET_ACTIVITY_DATES,
    GET_MONTHLY_ACTIVITY,
    GET_WEEKLY_ACTIVITY,
    GET_YEARLY_ACTIVITY,
)

if TYPE_CHECKING:
    from app.core.database import DatabaseClient

logger = get_logger(__name__)


async def calculate_daily_streak(db: "DatabaseClient", username: str) -> StreakInfo:
    """Calculate daily commit streak.

    Args:
        db: Database client
        username: GitHub username

    Returns:
        StreakInfo with daily streak data

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    try:
        async with db.pool.acquire() as conn:
            # Get all unique activity dates in descending order
            rows = await conn.fetch(GET_ACTIVITY_DATES, username)
            if not rows:
                return StreakInfo(
                    streak_type="daily", current_streak=0, longest_streak=0, last_activity_date=None
                )

            activity_dates = [row["activity_date"] for row in rows]
            last_date = activity_dates[0]
            today = datetime.now(UTC).date()

            # Check if streak is still active (last commit today or yesterday - grace period)
            if last_date < today - timedelta(days=1):
                # Streak broken (no activity today or yesterday)
                current_streak = 0
            else:
                # Count consecutive days
                current_streak = 1
                expected_date = last_date - timedelta(days=1)

                for activity_date in activity_dates[1:]:
                    if activity_date == expected_date:
                        current_streak += 1
                        expected_date -= timedelta(days=1)
                    elif activity_date < expected_date:
                        # Gap found, stop counting
                        break

            # Calculate longest streak
            longest_streak = 0
            if len(activity_dates) > 0:
                temp_streak = 1
                expected_date = activity_dates[0] - timedelta(days=1)

                for activity_date in activity_dates[1:]:
                    if activity_date == expected_date:
                        temp_streak += 1
                        expected_date -= timedelta(days=1)
                    else:
                        longest_streak = max(longest_streak, temp_streak)
                        temp_streak = 1
                        expected_date = activity_date - timedelta(days=1)

                longest_streak = max(longest_streak, temp_streak)

            return StreakInfo(
                streak_type="daily",
                current_streak=current_streak,
                longest_streak=max(longest_streak, current_streak),
                last_activity_date=last_date,
            )

    except asyncpg.PostgresError as e:
        logger.error("streak.daily.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to calculate daily streak: {e}") from e


async def calculate_weekly_streak(db: "DatabaseClient", username: str) -> StreakInfo:
    """Calculate weekly commit streak (any activity in Mon-Sun week counts).

    Args:
        db: Database client
        username: GitHub username

    Returns:
        StreakInfo with weekly streak data

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(GET_WEEKLY_ACTIVITY, username)
            if not rows:
                return StreakInfo(
                    streak_type="weekly",
                    current_streak=0,
                    longest_streak=0,
                    last_activity_date=None,
                )

            week_starts = [row["week_start"] for row in rows]
            last_week = week_starts[0]
            today = datetime.now(UTC).date()
            current_week_start = today - timedelta(days=today.weekday())

            # Check if streak is active (activity in current or previous week)
            if last_week < current_week_start - timedelta(weeks=1):
                current_streak = 0
            else:
                current_streak = 1
                expected_week = last_week - timedelta(weeks=1)

                for week_start in week_starts[1:]:
                    if week_start == expected_week:
                        current_streak += 1
                        expected_week -= timedelta(weeks=1)
                    elif week_start < expected_week:
                        break

            # Calculate longest streak
            longest_streak = 0
            if len(week_starts) > 0:
                temp_streak = 1
                expected_week = week_starts[0] - timedelta(weeks=1)

                for week_start in week_starts[1:]:
                    if week_start == expected_week:
                        temp_streak += 1
                        expected_week -= timedelta(weeks=1)
                    else:
                        longest_streak = max(longest_streak, temp_streak)
                        temp_streak = 1
                        expected_week = week_start - timedelta(weeks=1)

                longest_streak = max(longest_streak, temp_streak)

            return StreakInfo(
                streak_type="weekly",
                current_streak=current_streak,
                longest_streak=max(longest_streak, current_streak),
                last_activity_date=last_week,
            )

    except asyncpg.PostgresError as e:
        logger.error("streak.weekly.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to calculate weekly streak: {e}") from e


async def calculate_monthly_streak(db: "DatabaseClient", username: str) -> StreakInfo:
    """Calculate monthly commit streak.

    Args:
        db: Database client
        username: GitHub username

    Returns:
        StreakInfo with monthly streak data

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(GET_MONTHLY_ACTIVITY, username)
            if not rows:
                return StreakInfo(
                    streak_type="monthly",
                    current_streak=0,
                    longest_streak=0,
                    last_activity_date=None,
                )

            month_starts = [row["month_start"] for row in rows]
            last_month = month_starts[0]
            today = datetime.now(UTC).date()
            current_month_start = today.replace(day=1)

            # Previous month
            if current_month_start.month == 1:
                prev_month = current_month_start.replace(
                    year=current_month_start.year - 1, month=12
                )
            else:
                prev_month = current_month_start.replace(month=current_month_start.month - 1)

            # Check if streak is active
            if last_month < prev_month:
                current_streak = 0
            else:
                current_streak = 1

                for i in range(1, len(month_starts)):
                    prev_start = month_starts[i - 1]
                    curr_start = month_starts[i]

                    # Check if consecutive months
                    if prev_start.month == 1:
                        expected = prev_start.replace(year=prev_start.year - 1, month=12)
                    else:
                        expected = prev_start.replace(month=prev_start.month - 1)

                    if curr_start == expected:
                        current_streak += 1
                    else:
                        break

            # Calculate longest streak
            longest_streak = 1
            temp_streak = 1

            for i in range(1, len(month_starts)):
                prev_start = month_starts[i - 1]
                curr_start = month_starts[i]

                if prev_start.month == 1:
                    expected = prev_start.replace(year=prev_start.year - 1, month=12)
                else:
                    expected = prev_start.replace(month=prev_start.month - 1)

                if curr_start == expected:
                    temp_streak += 1
                else:
                    longest_streak = max(longest_streak, temp_streak)
                    temp_streak = 1

            longest_streak = max(longest_streak, temp_streak)

            return StreakInfo(
                streak_type="monthly",
                current_streak=current_streak,
                longest_streak=max(longest_streak, current_streak),
                last_activity_date=last_month,
            )

    except asyncpg.PostgresError as e:
        logger.error("streak.monthly.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to calculate monthly streak: {e}") from e


async def calculate_yearly_streak(db: "DatabaseClient", username: str) -> StreakInfo:
    """Calculate yearly commit streak.

    Args:
        db: Database client
        username: GitHub username

    Returns:
        StreakInfo with yearly streak data

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(GET_YEARLY_ACTIVITY, username)
            if not rows:
                return StreakInfo(
                    streak_type="yearly",
                    current_streak=0,
                    longest_streak=0,
                    last_activity_date=None,
                )

            years = [row["year"] for row in rows]
            last_year = years[0]
            current_year = datetime.now(UTC).date().year

            # Check if streak is active
            if last_year < current_year - 1:
                current_streak = 0
            else:
                current_streak = 1

                for i in range(1, len(years)):
                    if years[i] == years[i - 1] - 1:
                        current_streak += 1
                    else:
                        break

            # Calculate longest streak
            longest_streak = 1
            temp_streak = 1

            for i in range(1, len(years)):
                if years[i] == years[i - 1] - 1:
                    temp_streak += 1
                else:
                    longest_streak = max(longest_streak, temp_streak)
                    temp_streak = 1

            longest_streak = max(longest_streak, temp_streak)

            return StreakInfo(
                streak_type="yearly",
                current_streak=current_streak,
                longest_streak=max(longest_streak, current_streak),
                last_activity_date=date(last_year, 12, 31),
            )

    except asyncpg.PostgresError as e:
        logger.error("streak.yearly.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to calculate yearly streak: {e}") from e


async def calculate_all_streaks(db: "DatabaseClient", username: str) -> dict[str, StreakInfo]:
    """Calculate all streak types concurrently.

    Args:
        db: Database client
        username: GitHub username

    Returns:
        Dictionary mapping streak type to StreakInfo

    Raises:
        DatabaseError: If any streak calculation fails
    """
    daily, weekly, monthly, yearly = await asyncio.gather(
        calculate_daily_streak(db, username),
        calculate_weekly_streak(db, username),
        calculate_monthly_streak(db, username),
        calculate_yearly_streak(db, username),
    )

    return {"daily": daily, "weekly": weekly, "monthly": monthly, "yearly": yearly}
