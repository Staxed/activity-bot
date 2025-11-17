"""Streak calculation functions for daily/weekly/monthly/yearly streaks.

All streaks are based on consecutive daily commits:
- Daily: Count of consecutive days with commits
- Weekly: Count of complete 7-day periods in consecutive daily streak
- Monthly: Count of complete calendar months with commits every day
- Yearly: Count of complete 365-day periods in consecutive daily streak
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import asyncpg

from app.core.logging import get_logger
from app.shared.exceptions import DatabaseError
from app.stats.models import StreakInfo
from app.stats.queries import GET_ACTIVITY_DATES

if TYPE_CHECKING:
    from app.core.database import DatabaseClient

logger = get_logger(__name__)


def _get_consecutive_daily_streaks(activity_dates: list[date], today: date) -> tuple[int, int]:
    """Calculate current and longest consecutive daily streaks.

    Args:
        activity_dates: List of activity dates in descending order
        today: Current date

    Returns:
        Tuple of (current_streak_days, longest_streak_days)
    """
    if not activity_dates:
        return 0, 0

    last_date = activity_dates[0]

    # Check if streak is still active (last commit today or yesterday - grace period)
    if last_date < today - timedelta(days=1):
        current_streak = 0
    else:
        # Count consecutive days from most recent
        current_streak = 1
        expected_date = last_date - timedelta(days=1)

        for activity_date in activity_dates[1:]:
            if activity_date == expected_date:
                current_streak += 1
                expected_date -= timedelta(days=1)
            elif activity_date < expected_date:
                break

    # Calculate longest streak ever
    longest_streak = 0
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

    return current_streak, longest_streak


async def calculate_daily_streak(db: "DatabaseClient", username: str) -> StreakInfo:
    """Calculate daily commit streak.

    Args:
        db: Database client
        username: GitHub username

    Returns:
        StreakInfo with daily streak data (consecutive days)

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(GET_ACTIVITY_DATES, username)
            if not rows:
                return StreakInfo(
                    streak_type="daily", current_streak=0, longest_streak=0, last_activity_date=None
                )

            activity_dates = [row["activity_date"] for row in rows]
            today = datetime.now(UTC).date()

            current_streak, longest_streak = _get_consecutive_daily_streaks(activity_dates, today)

            return StreakInfo(
                streak_type="daily",
                current_streak=current_streak,
                longest_streak=longest_streak,
                last_activity_date=activity_dates[0],
            )

    except asyncpg.PostgresError as e:
        logger.error("streak.daily.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to calculate daily streak: {e}") from e


async def calculate_weekly_streak(db: "DatabaseClient", username: str) -> StreakInfo:
    """Calculate weekly commit streak (7+ consecutive days = 1 week).

    Weekly streak counts complete 7-day periods within consecutive daily commits.
    Example: 15 consecutive days = 2 week streak (2 complete 7-day periods)

    Args:
        db: Database client
        username: GitHub username

    Returns:
        StreakInfo with weekly streak data (count of 7-day periods)

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(GET_ACTIVITY_DATES, username)
            if not rows:
                return StreakInfo(
                    streak_type="weekly", current_streak=0, longest_streak=0, last_activity_date=None
                )

            activity_dates = [row["activity_date"] for row in rows]
            today = datetime.now(UTC).date()

            current_days, longest_days = _get_consecutive_daily_streaks(activity_dates, today)

            # Convert days to weeks (integer division by 7)
            current_weeks = current_days // 7
            longest_weeks = longest_days // 7

            return StreakInfo(
                streak_type="weekly",
                current_streak=current_weeks,
                longest_streak=longest_weeks,
                last_activity_date=activity_dates[0],
            )

    except asyncpg.PostgresError as e:
        logger.error("streak.weekly.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to calculate weekly streak: {e}") from e


async def calculate_monthly_streak(db: "DatabaseClient", username: str) -> StreakInfo:
    """Calculate monthly commit streak (every day for full calendar months).

    Monthly streak counts complete calendar months where every day had commits.
    Must code every single day in the month (28-31 days depending on month).

    Args:
        db: Database client
        username: GitHub username

    Returns:
        StreakInfo with monthly streak data (count of complete months)

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(GET_ACTIVITY_DATES, username)
            if not rows:
                return StreakInfo(
                    streak_type="monthly",
                    current_streak=0,
                    longest_streak=0,
                    last_activity_date=None,
                )

            activity_dates = [row["activity_date"] for row in rows]
            today = datetime.now(UTC).date()

            # Convert to set for O(1) lookup
            activity_set = set(activity_dates)

            # Calculate current monthly streak
            current_months = 0
            check_date = today

            # Start from current or previous month depending on today's date
            # If we haven't coded today, start checking from previous month
            if today not in activity_set:
                # Go to first day of current month, then back one day to previous month
                check_date = today.replace(day=1) - timedelta(days=1)

            # Check consecutive months backward
            while True:
                # Get first and last day of this month
                first_day = check_date.replace(day=1)
                if check_date.month == 12:
                    last_day = check_date.replace(day=31)
                else:
                    last_day = (check_date.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(
                        days=1
                    )

                # Check if every day in this month has activity
                month_complete = True
                current_day = first_day
                while current_day <= last_day:
                    if current_day not in activity_set:
                        month_complete = False
                        break
                    current_day += timedelta(days=1)

                if not month_complete:
                    break

                current_months += 1
                # Move to previous month
                check_date = first_day - timedelta(days=1)

            # Calculate longest monthly streak (check all history)
            longest_months = 0
            if activity_dates:
                # Start from earliest date and work forward
                earliest = activity_dates[-1]
                check_date = earliest

                temp_months = 0
                while check_date <= today:
                    first_day = check_date.replace(day=1)
                    if check_date.month == 12:
                        last_day = check_date.replace(day=31)
                    else:
                        last_day = (check_date.replace(day=1) + timedelta(days=32)).replace(
                            day=1
                        ) - timedelta(days=1)

                    # Check if every day in this month has activity
                    month_complete = True
                    current_day = first_day
                    while current_day <= last_day:
                        if current_day not in activity_set:
                            month_complete = False
                            break
                        current_day += timedelta(days=1)

                    if month_complete:
                        temp_months += 1
                    else:
                        longest_months = max(longest_months, temp_months)
                        temp_months = 0

                    # Move to next month
                    if check_date.month == 12:
                        check_date = check_date.replace(year=check_date.year + 1, month=1, day=1)
                    else:
                        check_date = check_date.replace(month=check_date.month + 1, day=1)

                longest_months = max(longest_months, temp_months)

            return StreakInfo(
                streak_type="monthly",
                current_streak=current_months,
                longest_streak=max(longest_months, current_months),
                last_activity_date=activity_dates[0],
            )

    except asyncpg.PostgresError as e:
        logger.error("streak.monthly.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to calculate monthly streak: {e}") from e


async def calculate_yearly_streak(db: "DatabaseClient", username: str) -> StreakInfo:
    """Calculate yearly commit streak (365+ consecutive days = 1 year).

    Yearly streak counts complete 365-day periods within consecutive daily commits.
    Example: 400 consecutive days = 1 year streak (1 complete 365-day period)

    Args:
        db: Database client
        username: GitHub username

    Returns:
        StreakInfo with yearly streak data (count of 365-day periods)

    Raises:
        DatabaseError: If database query fails
    """
    if not db.pool:
        raise DatabaseError("Connection pool not initialized")

    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(GET_ACTIVITY_DATES, username)
            if not rows:
                return StreakInfo(
                    streak_type="yearly", current_streak=0, longest_streak=0, last_activity_date=None
                )

            activity_dates = [row["activity_date"] for row in rows]
            today = datetime.now(UTC).date()

            current_days, longest_days = _get_consecutive_daily_streaks(activity_dates, today)

            # Convert days to years (integer division by 365)
            current_years = current_days // 365
            longest_years = longest_days // 365

            return StreakInfo(
                streak_type="yearly",
                current_streak=current_years,
                longest_streak=longest_years,
                last_activity_date=activity_dates[0],
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
