"""Discord embed creation for stats and achievements."""

import discord

from app.discord.event_colors import (
    ACHIEVEMENT_COLOR,
    REPO_STATS_COLOR,
    STATS_COLOR,
    STREAK_COLOR,
    TIME_PATTERN_COLOR,
)
from app.stats.models import RepoStats, StreakInfo, TimePatternStats, UserStats

# Discord embed limits
MAX_ITEMS = 10
MAX_DESCRIPTION_LENGTH = 4096


def create_stats_embed(stats: UserStats, timeframe: str = "week") -> discord.Embed:
    """Create Discord embed for user statistics.

    Args:
        stats: UserStats object
        timeframe: Time window to highlight (today, week, month, all)

    Returns:
        Discord embed with stats
    """
    embed = discord.Embed(
        title=f"📊 Stats for {stats.username}",
        color=STATS_COLOR,
    )

    # Select stats based on timeframe
    if timeframe == "today":
        current_commits = stats.commits_today
        current_prs = stats.prs_today
        period_label = "Today"
    elif timeframe == "month":
        current_commits = stats.commits_this_month
        current_prs = stats.prs_this_month
        period_label = "This Month"
    elif timeframe == "all":
        current_commits = stats.total_commits
        current_prs = stats.total_prs
        period_label = "All Time"
    else:  # week (default)
        current_commits = stats.commits_this_week
        current_prs = stats.prs_this_week
        period_label = "This Week"

    # Build description
    lines = [
        f"**{period_label}**: {current_commits} commits, {current_prs} PRs",
        f"**Total Activity**: {stats.total_commits + stats.total_prs + stats.total_issues} events",
    ]

    if stats.most_active_repo:
        lines.append(
            f"**Most Active Repo**: {stats.most_active_repo} ({stats.most_active_repo_count} events)"
        )

    if stats.last_activity:
        unix_ts = int(stats.last_activity.timestamp())
        lines.append(f"**Last Activity**: <t:{unix_ts}:R>")

    embed.description = "\n".join(lines)

    # Add detailed breakdown as fields
    embed.add_field(
        name="All-Time Totals",
        value=(
            f"💻 {stats.total_commits} commits\n"
            f"🔀 {stats.total_prs} PRs\n"
            f"🐛 {stats.total_issues} issues\n"
            f"✅ {stats.total_reviews} reviews"
        ),
        inline=True,
    )

    embed.add_field(
        name="\u200b",  # Zero-width space for no title
        value=(
            f"🚀 {stats.total_releases} releases\n"
            f"➕ {stats.total_creations} creations\n"
            f"➖ {stats.total_deletions} deletions\n"
            f"🍴 {stats.total_forks} forks"
        ),
        inline=True,
    )

    return embed


def create_streak_embed(streaks: dict[str, StreakInfo]) -> discord.Embed:
    """Create Discord embed for streak information.

    Args:
        streaks: Dictionary mapping streak type to StreakInfo

    Returns:
        Discord embed with all streaks
    """
    embed = discord.Embed(
        title="🔥 Streaks",
        color=STREAK_COLOR,
    )

    # Emoji mapping for streak types
    streak_emojis = {
        "daily": "🔥",
        "weekly": "📅",
        "monthly": "📆",
        "yearly": "🏆",
    }

    lines = []
    for streak_type in ["daily", "weekly", "monthly", "yearly"]:
        streak = streaks.get(streak_type)
        if not streak:
            continue

        emoji = streak_emojis.get(streak_type, "📊")
        type_label = streak_type.capitalize()

        line = (
            f"{emoji} **{type_label}**: "
            f"{streak.current_streak} current / {streak.longest_streak} longest"
        )
        lines.append(line)

    embed.description = "\n".join(lines) if lines else "No streaks yet!"

    return embed


def create_badges_embed(
    milestone_achievements: list[tuple[str, str, str]],
    repeatable_counts: list[tuple[str, str, int]],
) -> discord.Embed:
    """Create Discord embed for achievements and badges.

    Args:
        milestone_achievements: List of (emoji, name, description) tuples for milestones
        repeatable_counts: List of (emoji, name, count) tuples for repeatable achievements

    Returns:
        Discord embed with badges
    """
    embed = discord.Embed(
        title="🏅 Achievements",
        color=ACHIEVEMENT_COLOR,
    )

    # Milestone section
    if milestone_achievements:
        milestone_lines = [
            f"{emoji} **{name}** - {desc}"
            for emoji, name, desc in milestone_achievements[:MAX_ITEMS]
        ]
        embed.add_field(
            name="Milestones Unlocked",
            value="\n".join(milestone_lines),
            inline=False,
        )

    # Repeatable section (top achievements by count)
    if repeatable_counts:
        repeatable_lines = [
            f"{emoji} **{name}** x{count}" for emoji, name, count in repeatable_counts[:5]
        ]
        embed.add_field(
            name="Top Repeatable Achievements",
            value="\n".join(repeatable_lines),
            inline=False,
        )

    if not milestone_achievements and not repeatable_counts:
        embed.description = "No achievements earned yet. Keep coding!"

    return embed


def create_repos_embed(repos: list[RepoStats], sort_by: str = "total") -> discord.Embed:
    """Create Discord embed for repository statistics.

    Args:
        repos: List of RepoStats
        sort_by: Sort criteria (total, commits, prs, issues)

    Returns:
        Discord embed with repo stats
    """
    embed = discord.Embed(
        title="📦 Repository Activity",
        color=REPO_STATS_COLOR,
    )

    # Sort repos
    if sort_by == "commits":
        sorted_repos = sorted(repos, key=lambda r: r.commits, reverse=True)
    elif sort_by == "prs":
        sorted_repos = sorted(repos, key=lambda r: r.prs, reverse=True)
    elif sort_by == "issues":
        sorted_repos = sorted(repos, key=lambda r: r.issues, reverse=True)
    else:  # total
        sorted_repos = sorted(repos, key=lambda r: r.total_events, reverse=True)

    # Build description with top repos
    lines = []
    for i, repo in enumerate(sorted_repos[:MAX_ITEMS], 1):
        line = (
            f"{i}. **{repo.repo_full_name}** - "
            f"{repo.total_events} events "
            f"({repo.commits}c, {repo.prs}p, {repo.issues}i)"
        )
        lines.append(line)

    embed.description = "\n".join(lines) if lines else "No repository activity yet!"

    # Add overflow footer
    overflow_count = len(sorted_repos) - MAX_ITEMS
    if overflow_count > 0:
        embed.set_footer(text=f"... and {overflow_count} more repositories")

    return embed


def create_insights_embed(patterns: TimePatternStats) -> discord.Embed:
    """Create Discord embed for time pattern insights.

    Args:
        patterns: TimePatternStats object

    Returns:
        Discord embed with insights
    """
    embed = discord.Embed(
        title="🔍 Coding Insights",
        color=TIME_PATTERN_COLOR,
    )

    lines = []

    # Peak times
    if patterns.peak_hour is not None:
        # Convert 24h to 12h format
        hour_12 = patterns.peak_hour % 12 or 12
        am_pm = "AM" if patterns.peak_hour < 12 else "PM"
        lines.append(f"⏰ **Peak Hour**: {hour_12} {am_pm}")

    if patterns.peak_day is not None:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_name = days[patterns.peak_day] if 0 <= patterns.peak_day < 7 else "Unknown"
        lines.append(f"📅 **Peak Day**: {day_name}")

    # Night owl / early bird detection
    total_commits = sum(patterns.commits_by_hour.values())
    if total_commits > 0:
        night_percent = (patterns.night_commits / total_commits) * 100
        early_percent = (patterns.early_commits / total_commits) * 100

        if night_percent > 20:
            lines.append(
                f"🦉 **Night Owl**: {patterns.night_commits} commits after 10pm ({night_percent:.0f}%)"
            )
        if early_percent > 15:
            lines.append(
                f"🐦 **Early Bird**: {patterns.early_commits} commits before 9am ({early_percent:.0f}%)"
            )

    embed.description = "\n".join(lines) if lines else "Not enough data yet!"

    return embed


def create_achievement_announcement_embed(
    achievement_emoji: str,
    achievement_name: str,
    achievement_desc: str,
    total_count: int,
) -> discord.Embed:
    """Create Discord embed for achievement unlock announcement.

    Args:
        achievement_emoji: Achievement emoji
        achievement_name: Achievement name
        achievement_desc: Achievement description
        total_count: Total times this achievement was earned

    Returns:
        Discord embed for announcement
    """
    embed = discord.Embed(
        title="🎉 Achievement Unlocked!",
        color=ACHIEVEMENT_COLOR,
    )

    embed.description = f"{achievement_emoji} **{achievement_name}**\n{achievement_desc}"

    embed.set_footer(text=f"Earned {total_count} time(s)")

    return embed
