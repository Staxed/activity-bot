"""Summary generation for daily/weekly/monthly stats reports."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord

from app.core.logging import get_logger
from app.discord.event_colors import SUMMARY_COLOR
from app.stats.calculator import calculate_repo_stats
from app.stats.streak_calculator import calculate_all_streaks

if TYPE_CHECKING:
    from app.core.database import DatabaseClient

logger = get_logger(__name__)


async def generate_daily_summary(
    db: "DatabaseClient", username: str, target_date: datetime | None = None
) -> discord.Embed:
    """Generate daily activity summary for a user.

    Args:
        db: Database client
        username: GitHub username
        target_date: Optional date to generate summary for (defaults to yesterday)

    Returns:
        Discord embed with daily summary
    """
    if target_date is None:
        target_date = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        target_date -= timedelta(days=1)  # Yesterday

    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    # Get commits for the day
    commits_query = """
        SELECT COUNT(*) as count
        FROM commits
        WHERE author_username = $1
          AND commit_timestamp >= $2
          AND commit_timestamp < $3
    """

    prs_query = """
        SELECT COUNT(*) as count
        FROM pull_requests
        WHERE author_username = $1
          AND event_timestamp >= $2
          AND event_timestamp < $3
    """

    issues_query = """
        SELECT COUNT(*) as count
        FROM issues
        WHERE author_username = $1
          AND event_timestamp >= $2
          AND event_timestamp < $3
    """

    if not db.pool:
        raise RuntimeError("Database pool not initialized")

    async with db.pool.acquire() as conn:
        commits_count = await conn.fetchval(commits_query, username, day_start, day_end) or 0
        prs_count = await conn.fetchval(prs_query, username, day_start, day_end) or 0
        issues_count = await conn.fetchval(issues_query, username, day_start, day_end) or 0

    # Get streaks
    streaks = await calculate_all_streaks(db, username)
    daily_streak = streaks.get("daily")

    # Get repos for the period
    repos = await calculate_repo_stats(db, username, since=day_start)

    # Create embed
    embed = discord.Embed(
        title=f"📊 Daily Summary for {username}",
        description=f"Activity for {target_date.strftime('%B %d, %Y')}",
        color=SUMMARY_COLOR,
    )

    # Activity field
    embed.add_field(
        name="Activity",
        value=(
            f"💻 {commits_count} commits\n"
            f"🔀 {prs_count} pull requests\n"
            f"🐛 {issues_count} issues"
        ),
        inline=True,
    )

    # Streak field
    streak_text = f"🔥 {daily_streak.current_streak} days" if daily_streak else "No streak"
    if daily_streak and daily_streak.current_streak == daily_streak.longest_streak and daily_streak.current_streak > 0:
        streak_text += "\n⭐ Personal best!"
    embed.add_field(name="Streak", value=streak_text, inline=True)

    # Repositories field with truncation
    if repos:
        sorted_repos = sorted(repos, key=lambda r: r.total_events, reverse=True)
        repos_lines = []
        char_count = 0
        max_chars = 1024  # Discord field value limit

        for repo in sorted_repos:
            line = f"• {repo.repo_full_name} ({repo.commits}c/{repo.prs}p/{repo.issues}i)\n"
            if char_count + len(line) + 30 > max_chars:  # Leave room for "... and X more"
                remaining = len(sorted_repos) - len(repos_lines)
                repos_lines.append(f"... and {remaining} more")
                break
            repos_lines.append(line.rstrip())
            char_count += len(line)

        embed.add_field(name="Repositories", value="\n".join(repos_lines), inline=False)

    # Check if it was a productive day
    if commits_count >= 10:
        embed.set_footer(text="🔥 Productive day!")
    elif commits_count == 0 and prs_count == 0:
        embed.set_footer(text="💤 Rest day")
    else:
        embed.set_footer(text="✨ Keep coding!")

    return embed


async def generate_weekly_summary(
    db: "DatabaseClient", username: str, week_start: datetime | None = None
) -> discord.Embed:
    """Generate weekly activity summary for a user.

    Args:
        db: Database client
        username: GitHub username
        week_start: Optional Monday date to start week (defaults to last Monday)

    Returns:
        Discord embed with weekly summary
    """
    if week_start is None:
        now = datetime.now(UTC)
        days_since_monday = now.weekday()
        week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=days_since_monday + 7
        )

    week_end = week_start + timedelta(days=7)

    # Get week-specific counts
    if not db.pool:
        raise RuntimeError("Database pool not initialized")

    async with db.pool.acquire() as conn:
        commits_count = (
            await conn.fetchval(
                """
            SELECT COUNT(*) FROM commits
            WHERE author_username = $1
              AND commit_timestamp >= $2
              AND commit_timestamp < $3
        """,
                username,
                week_start,
                week_end,
            )
            or 0
        )

        prs_count = (
            await conn.fetchval(
                """
            SELECT COUNT(*) FROM pull_requests
            WHERE author_username = $1
              AND event_timestamp >= $2
              AND event_timestamp < $3
        """,
                username,
                week_start,
                week_end,
            )
            or 0
        )

        issues_count = (
            await conn.fetchval(
                """
            SELECT COUNT(*) FROM issues
            WHERE author_username = $1
              AND event_timestamp >= $2
              AND event_timestamp < $3
        """,
                username,
                week_start,
                week_end,
            )
            or 0
        )

        # Get active days
        active_days = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT DATE(commit_timestamp)) FROM commits
            WHERE author_username = $1
              AND commit_timestamp >= $2
              AND commit_timestamp < $3
        """,
            username,
            week_start,
            week_end,
        )

    # Get streaks
    streaks = await calculate_all_streaks(db, username)
    weekly_streak = streaks.get("weekly")

    # Get repos for the period
    repos = await calculate_repo_stats(db, username, since=week_start)

    # Create embed
    # week_end is exclusive boundary, so display the last day of the week (week_end - 1)
    week_last_day = week_end - timedelta(days=1)
    week_label = f"{week_start.strftime('%b %d')} - {week_last_day.strftime('%b %d, %Y')}"
    embed = discord.Embed(
        title=f"📅 Weekly Summary for {username}",
        description=f"Week of {week_label}",
        color=SUMMARY_COLOR,
    )

    # Activity stats
    embed.add_field(
        name="Activity",
        value=(
            f"💻 {commits_count} commits\n"
            f"🔀 {prs_count} pull requests\n"
            f"🐛 {issues_count} issues\n"
            f"📆 {active_days or 0} active days"
        ),
        inline=True,
    )

    # Streak info
    streak_text = f"🔥 {weekly_streak.current_streak} weeks" if weekly_streak else "No streak"
    if weekly_streak and weekly_streak.current_streak == weekly_streak.longest_streak and weekly_streak.current_streak > 0:
        streak_text += "\n⭐ Personal best!"
    embed.add_field(name="Streak", value=streak_text, inline=True)

    # Repositories field with truncation
    if repos:
        sorted_repos = sorted(repos, key=lambda r: r.total_events, reverse=True)
        repos_lines = []
        char_count = 0
        max_chars = 1024  # Discord field value limit

        for repo in sorted_repos:
            line = f"• {repo.repo_full_name} ({repo.commits}c/{repo.prs}p/{repo.issues}i)\n"
            if char_count + len(line) + 30 > max_chars:  # Leave room for "... and X more"
                remaining = len(sorted_repos) - len(repos_lines)
                repos_lines.append(f"... and {remaining} more")
                break
            repos_lines.append(line.rstrip())
            char_count += len(line)

        embed.add_field(name="Repositories", value="\n".join(repos_lines), inline=False)

    # Footer based on activity
    if commits_count >= 25:
        embed.set_footer(text="🚀 Amazing week!")
    elif commits_count >= 10:
        embed.set_footer(text="✨ Great week!")
    elif commits_count > 0:
        embed.set_footer(text="👍 Solid week!")
    else:
        embed.set_footer(text="💤 Quiet week")

    return embed


async def generate_monthly_summary(
    db: "DatabaseClient", username: str, month_start: datetime | None = None
) -> discord.Embed:
    """Generate monthly activity summary for a user.

    Args:
        db: Database client
        username: GitHub username
        month_start: Optional first day of month (defaults to last month)

    Returns:
        Discord embed with monthly summary
    """
    if month_start is None:
        now = datetime.now(UTC)
        if now.month == 1:
            month_start = now.replace(
                year=now.year - 1, month=12, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        else:
            month_start = now.replace(
                month=now.month - 1, day=1, hour=0, minute=0, second=0, microsecond=0
            )

    # Calculate next month start
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1, day=1)

    # Get month stats
    if not db.pool:
        raise RuntimeError("Database pool not initialized")

    async with db.pool.acquire() as conn:
        commits_count = (
            await conn.fetchval(
                """
            SELECT COUNT(*) FROM commits
            WHERE author_username = $1
              AND commit_timestamp >= $2
              AND commit_timestamp < $3
        """,
                username,
                month_start,
                month_end,
            )
            or 0
        )

        prs_count = (
            await conn.fetchval(
                """
            SELECT COUNT(*) FROM pull_requests
            WHERE author_username = $1
              AND event_timestamp >= $2
              AND event_timestamp < $3
        """,
                username,
                month_start,
                month_end,
            )
            or 0
        )

        issues_count = (
            await conn.fetchval(
                """
            SELECT COUNT(*) FROM issues
            WHERE author_username = $1
              AND event_timestamp >= $2
              AND event_timestamp < $3
        """,
                username,
                month_start,
                month_end,
            )
            or 0
        )

        # Get active days
        active_days = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT DATE(commit_timestamp)) FROM commits
            WHERE author_username = $1
              AND commit_timestamp >= $2
              AND commit_timestamp < $3
        """,
            username,
            month_start,
            month_end,
        )

    # Get streaks
    streaks = await calculate_all_streaks(db, username)
    monthly_streak = streaks.get("monthly")

    # Get repos for the period
    repos = await calculate_repo_stats(db, username, since=month_start)

    # Create embed
    month_label = month_start.strftime("%B %Y")
    embed = discord.Embed(
        title=f"📊 Monthly Summary for {username}",
        description=f"Activity for {month_label}",
        color=SUMMARY_COLOR,
    )

    # Main stats
    embed.add_field(
        name="Activity",
        value=(
            f"💻 {commits_count} commits\n"
            f"🔀 {prs_count} pull requests\n"
            f"🐛 {issues_count} issues\n"
            f"📆 {active_days or 0} active days"
        ),
        inline=True,
    )

    # Streak info
    streak_text = f"🔥 {monthly_streak.current_streak} months" if monthly_streak else "No streak"
    if monthly_streak and monthly_streak.current_streak == monthly_streak.longest_streak and monthly_streak.current_streak > 0:
        streak_text += "\n⭐ Personal best!"
    embed.add_field(name="Streak", value=streak_text, inline=True)

    # Repositories field with truncation
    if repos:
        sorted_repos = sorted(repos, key=lambda r: r.total_events, reverse=True)
        repos_lines = []
        char_count = 0
        max_chars = 1024  # Discord field value limit

        for repo in sorted_repos:
            line = f"• {repo.repo_full_name} ({repo.commits}c/{repo.prs}p/{repo.issues}i)\n"
            if char_count + len(line) + 30 > max_chars:  # Leave room for "... and X more"
                remaining = len(sorted_repos) - len(repos_lines)
                repos_lines.append(f"... and {remaining} more")
                break
            repos_lines.append(line.rstrip())
            char_count += len(line)

        embed.add_field(name="Repositories", value="\n".join(repos_lines), inline=False)

    # Footer based on achievements
    if commits_count >= 100:
        embed.set_footer(text="💯 Century month achieved!")
    elif commits_count >= 50:
        embed.set_footer(text="🚀 Incredible month!")
    elif commits_count >= 25:
        embed.set_footer(text="✨ Great month!")
    elif commits_count > 0:
        embed.set_footer(text="👍 Productive month!")
    else:
        embed.set_footer(text="💤 Quiet month")

    return embed
