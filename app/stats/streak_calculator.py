"""Streak calculation functions for daily/weekly/monthly/yearly streaks.

Streak definitions:
- Daily: Consecutive days with commits (strict - must commit every day)
- Weekly: Consecutive weeks with at least 1 commit (breaks after 7 days without activity)
- Monthly: Consecutive months with at least 1 commit (breaks after missing a full month)
- Yearly: Consecutive years with at least 1 commit (breaks after missing a full year)
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
    """Calculate weekly commit streak (consecutive weeks with at least 1 commit).

    Streak breaks after 7+ consecutive days without a commit.
    Each week that has at least one commit counts toward the streak.

    Args:
        db: Database client
        username: GitHub username

    Returns:
        StreakInfo with weekly streak data (count of consecutive weeks)

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

            if not activity_dates:
                return StreakInfo(
                    streak_type="weekly", current_streak=0, longest_streak=0, last_activity_date=None
                )

            last_date = activity_dates[0]

            # Check if streak is still active (last commit within 7 days)
            if last_date < today - timedelta(days=6):
                current_streak = 0
            else:
                # Count consecutive weeks with activity
                current_streak = 0
                current_week_start = last_date - timedelta(days=last_date.weekday())  # Monday of last commit

                for activity_date in activity_dates:
                    week_start = activity_date - timedelta(days=activity_date.weekday())

                    # If we hit a new week, increment streak
                    if week_start < current_week_start:
                        # Check if gap is more than 7 days (missed a week)
                        if current_week_start - week_start > timedelta(days=7):
                            break
                        current_week_start = week_start
                        current_streak += 1
                    elif week_start == current_week_start:
                        # First week counts
                        if current_streak == 0:
                            current_streak = 1

            # Calculate longest streak
            longest_streak = 0
            if activity_dates:
                temp_streak = 1
                current_week_start = activity_dates[0] - timedelta(days=activity_dates[0].weekday())

                for activity_date in activity_dates[1:]:
                    week_start = activity_date - timedelta(days=activity_date.weekday())

                    if week_start < current_week_start:
                        # Check gap
                        if current_week_start - week_start > timedelta(days=7):
                            longest_streak = max(longest_streak, temp_streak)
                            temp_streak = 1
                        else:
                            temp_streak += 1
                        current_week_start = week_start

                longest_streak = max(longest_streak, temp_streak)

            return StreakInfo(
                streak_type="weekly",
                current_streak=current_streak,
                longest_streak=longest_streak,
                last_activity_date=activity_dates[0],
            )

    except asyncpg.PostgresError as e:
        logger.error("streak.weekly.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to calculate weekly streak: {e}") from e


async def calculate_monthly_streak(db: "DatabaseClient", username: str) -> StreakInfo:
    """Calculate monthly commit streak (consecutive months with at least 1 commit).

    Streak breaks after going a full calendar month without a commit.
    Each month that has at least one commit counts toward the streak.

    Args:
        db: Database client
        username: GitHub username

    Returns:
        StreakInfo with monthly streak data (count of consecutive months)

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

            if not activity_dates:
                return StreakInfo(
                    streak_type="monthly",
                    current_streak=0,
                    longest_streak=0,
                    last_activity_date=None,
                )

            # Group activity dates by month
            months_with_activity = set()
            for activity_date in activity_dates:
                month_key = (activity_date.year, activity_date.month)
                months_with_activity.add(month_key)

            last_date = activity_dates[0]
            current_month = (today.year, today.month)
            last_activity_month = (last_date.year, last_date.month)

            # Check if streak is still active (activity in current or previous month)
            if last_activity_month < current_month:
                # Check if we skipped a month
                prev_year = current_month[0] if current_month[1] > 1 else current_month[0] - 1
                prev_month = current_month[1] - 1 if current_month[1] > 1 else 12
                if last_activity_month < (prev_year, prev_month):
                    current_streak = 0
                else:
                    # Start from last activity month
                    current_streak = 1
                    check_year, check_month = last_activity_month

                    while True:
                        # Move to previous month
                        if check_month == 1:
                            check_year -= 1
                            check_month = 12
                        else:
                            check_month -= 1

                        month_key = (check_year, check_month)
                        if month_key in months_with_activity:
                            current_streak += 1
                        else:
                            break
            else:
                # Activity in current month, count backwards
                current_streak = 1
                check_year, check_month = current_month

                while True:
                    # Move to previous month
                    if check_month == 1:
                        check_year -= 1
                        check_month = 12
                    else:
                        check_month -= 1

                    month_key = (check_year, check_month)
                    if month_key in months_with_activity:
                        current_streak += 1
                    else:
                        break

            # Calculate longest streak
            longest_streak = 0
            if months_with_activity:
                sorted_months = sorted(months_with_activity)
                temp_streak = 1

                for i in range(1, len(sorted_months)):
                    prev_year, prev_month = sorted_months[i - 1]
                    curr_year, curr_month = sorted_months[i]

                    # Check if consecutive months
                    expected_year = prev_year if prev_month < 12 else prev_year + 1
                    expected_month = prev_month + 1 if prev_month < 12 else 1

                    if (curr_year, curr_month) == (expected_year, expected_month):
                        temp_streak += 1
                    else:
                        longest_streak = max(longest_streak, temp_streak)
                        temp_streak = 1

                longest_streak = max(longest_streak, temp_streak)

            return StreakInfo(
                streak_type="monthly",
                current_streak=current_streak,
                longest_streak=longest_streak,
                last_activity_date=activity_dates[0],
            )

    except asyncpg.PostgresError as e:
        logger.error("streak.monthly.failed", username=username, error=str(e), exc_info=True)
        raise DatabaseError(f"Failed to calculate monthly streak: {e}") from e


async def calculate_yearly_streak(db: "DatabaseClient", username: str) -> StreakInfo:
    """Calculate yearly commit streak (consecutive years with at least 1 commit).

    Streak breaks after going a full calendar year without a commit.
    Each year that has at least one commit counts toward the streak.

    Args:
        db: Database client
        username: GitHub username

    Returns:
        StreakInfo with yearly streak data (count of consecutive years)

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

            if not activity_dates:
                return StreakInfo(
                    streak_type="yearly", current_streak=0, longest_streak=0, last_activity_date=None
                )

            # Group activity dates by year
            years_with_activity = set()
            for activity_date in activity_dates:
                years_with_activity.add(activity_date.year)

            last_date = activity_dates[0]
            current_year = today.year
            last_activity_year = last_date.year

            # Check if streak is still active (activity in current or previous year)
            if last_activity_year < current_year:
                # Check if we skipped a year
                if last_activity_year < current_year - 1:
                    current_streak = 0
                else:
                    # Start from last activity year
                    current_streak = 1
                    check_year = last_activity_year - 1

                    while check_year in years_with_activity:
                        current_streak += 1
                        check_year -= 1
            else:
                # Activity in current year, count backwards
                current_streak = 1
                check_year = current_year - 1

                while check_year in years_with_activity:
                    current_streak += 1
                    check_year -= 1

            # Calculate longest streak
            longest_streak = 0
            if years_with_activity:
                sorted_years = sorted(years_with_activity)
                temp_streak = 1

                for i in range(1, len(sorted_years)):
                    if sorted_years[i] == sorted_years[i - 1] + 1:
                        temp_streak += 1
                    else:
                        longest_streak = max(longest_streak, temp_streak)
                        temp_streak = 1

                longest_streak = max(longest_streak, temp_streak)

            return StreakInfo(
                streak_type="yearly",
                current_streak=current_streak,
                longest_streak=longest_streak,
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
