"""Test script to preview all stats embeds in a Discord test channel.

This script creates fake data and posts all embed types to a test channel
so you can verify the visual appearance without needing real database data.

Usage:
    uv run python test_stats_embeds.py

Requirements:
    - Set TEST_DISCORD_CHANNEL_ID in .env (different from main channel)
    - Bot must have access to the test channel
"""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import discord
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

from app.core.config import get_settings
from app.discord.bot import DiscordBot
from app.discord.stats_embeds import (
    create_achievement_announcement_embed,
    create_badges_embed,
    create_insights_embed,
    create_repos_embed,
    create_stats_embed,
    create_streak_embed,
)
from app.discord.summaries import (
    generate_daily_summary,
    generate_monthly_summary,
    generate_weekly_summary,
)
from app.stats.achievements import get_achievements
from app.stats.models import RepoStats, StreakInfo, TimePatternStats, UserStats


def create_fake_user_stats() -> UserStats:
    """Create fake user statistics for testing."""
    return UserStats(
        username="testuser",
        total_commits=342,
        total_prs=45,
        total_issues=12,
        total_reviews=23,
        total_releases=5,
        total_creations=8,
        total_deletions=3,
        total_forks=2,
        commits_today=8,
        commits_this_week=42,
        commits_this_month=125,
        prs_today=2,
        prs_this_week=7,
        prs_this_month=18,
        most_active_repo="testuser/activity-bot",
        most_active_repo_count=89,
        last_activity=datetime.now(UTC),
    )


def create_fake_streaks() -> dict[str, StreakInfo]:
    """Create fake streak data for testing."""
    return {
        "daily": StreakInfo(
            streak_type="daily",
            current_streak=15,
            longest_streak=42,
            last_activity_date=datetime.now(UTC).date(),
        ),
        "weekly": StreakInfo(
            streak_type="weekly",
            current_streak=3,
            longest_streak=8,
            last_activity_date=datetime.now(UTC).date(),
        ),
        "monthly": StreakInfo(
            streak_type="monthly",
            current_streak=2,
            longest_streak=6,
            last_activity_date=datetime.now(UTC).date(),
        ),
        "yearly": StreakInfo(
            streak_type="yearly",
            current_streak=1,
            longest_streak=1,
            last_activity_date=datetime.now(UTC).date(),
        ),
    }


def create_fake_repos() -> list[RepoStats]:
    """Create fake repository statistics for testing."""
    return [
        RepoStats(
            repo_full_name="testuser/activity-bot",
            commits=89,
            prs=15,
            issues=5,
            reviews=12,
            total_events=121,
        ),
        RepoStats(
            repo_full_name="testuser/web-app",
            commits=56,
            prs=8,
            issues=3,
            reviews=6,
            total_events=73,
        ),
        RepoStats(
            repo_full_name="testuser/api-service",
            commits=34,
            prs=5,
            issues=2,
            reviews=3,
            total_events=44,
        ),
        RepoStats(
            repo_full_name="testuser/mobile-app",
            commits=28,
            prs=4,
            issues=1,
            reviews=2,
            total_events=35,
        ),
        RepoStats(
            repo_full_name="testuser/data-pipeline",
            commits=15,
            prs=2,
            issues=1,
            reviews=0,
            total_events=18,
        ),
    ]


def create_fake_time_patterns() -> TimePatternStats:
    """Create fake time pattern statistics for testing."""
    commits_by_hour = {
        0: 2,
        1: 1,
        2: 0,
        3: 0,
        4: 1,
        5: 3,
        6: 8,
        7: 12,
        8: 15,
        9: 18,
        10: 22,
        11: 19,
        12: 16,
        13: 20,
        14: 25,  # Peak hour
        15: 23,
        16: 21,
        17: 18,
        18: 14,
        19: 10,
        20: 8,
        21: 6,
        22: 5,
        23: 3,
    }

    commits_by_day = {
        0: 45,  # Monday
        1: 52,  # Tuesday
        2: 48,  # Wednesday
        3: 55,  # Thursday (peak day)
        4: 42,  # Friday
        5: 12,  # Saturday
        6: 8,  # Sunday
    }

    night_commits = commits_by_hour[22] + commits_by_hour[23] + sum(
        commits_by_hour.get(h, 0) for h in range(0, 6)
    )
    early_commits = sum(commits_by_hour.get(h, 0) for h in range(5, 9))

    return TimePatternStats(
        peak_hour=14,
        peak_day=3,
        night_commits=night_commits,
        early_commits=early_commits,
        commits_by_hour=commits_by_hour,
        commits_by_day=commits_by_day,
    )


def create_fake_milestone_achievements() -> list[tuple[str, str, str]]:
    """Create fake milestone achievements (emoji, name, description)."""
    return [
        ("🔥", "Fire Starter", "Reached a 7-day commit streak"),
        ("⚡", "Lightning Bolt", "Reached a 30-day commit streak"),
        ("💯", "Century Club", "Reached 100 total commits"),
        ("🎯", "Sharpshooter", "Reached 500 total commits"),
    ]


def create_fake_repeatable_achievements() -> list[tuple[str, str, int]]:
    """Create fake repeatable achievements (emoji, name, count)."""
    return [
        ("🔥", "Daily Dozen", 23),
        ("🦉", "Night Owl", 15),
        ("📈", "Productive Week", 8),
        ("💼", "Weekday Grind", 12),
        ("🐦", "Early Bird", 7),
    ]


class FakeDatabaseClient:
    """Fake database client for summary generation."""

    def __init__(self):
        """Initialize fake db client."""
        self.pool = self  # Fake pool

    def acquire(self):
        """Fake acquire context manager."""
        return self

    async def __aenter__(self):
        """Fake context manager entry."""
        return FakeConnection()

    async def __aexit__(self, *args):
        """Fake context manager exit."""
        pass


class FakeConnection:
    """Fake database connection."""

    async def fetchval(self, query: str, *args):
        """Return fake values based on query."""
        if "COUNT(*)" in query and "commits" in query:
            if "commit_timestamp >=" in query and "commit_timestamp <" in query:
                # Time-bounded count
                return 15
            return 342
        elif "COUNT(*)" in query and "pull_requests" in query:
            return 3
        elif "COUNT(*)" in query and "issues" in query:
            return 1
        elif "COUNT(DISTINCT DATE" in query:
            return 5  # Active days
        elif "MAX(latest)" in query:
            return None
        return 0

    async def fetchrow(self, query: str, *args):
        """Return fake row based on query."""
        if "COALESCE(c.commit_count" in query:
            # GET_USER_TOTALS query
            return {
                "total_commits": 342,
                "total_prs": 45,
                "total_issues": 12,
                "total_reviews": 23,
                "total_releases": 5,
                "total_creations": 8,
                "total_deletions": 3,
                "total_forks": 2,
            }
        elif "repo_full_name" in query and "event_count" in query:
            # GET_MOST_ACTIVE_REPO query
            return {"repo_full_name": "testuser/activity-bot", "event_count": 89}
        return None

    async def fetch(self, query: str, *args):
        """Return fake rows based on query."""
        if "DISTINCT repo_owner" in query:
            # Repos query
            return [
                {"repo": "testuser/activity-bot"},
                {"repo": "testuser/web-app"},
                {"repo": "testuser/api-service"},
            ]
        elif "EXTRACT(HOUR FROM commit_timestamp)" in query:
            # Commits by hour
            return []
        elif "EXTRACT(DOW FROM commit_timestamp)" in query:
            # Commits by day
            return []
        elif "repo_full_name" in query and "commits" in query and "prs" in query:
            # Repo stats query
            return [
                {
                    "repo_full_name": "testuser/activity-bot",
                    "commits": 89,
                    "prs": 15,
                    "issues": 5,
                    "reviews": 12,
                    "total_events": 121,
                },
                {
                    "repo_full_name": "testuser/web-app",
                    "commits": 56,
                    "prs": 8,
                    "issues": 3,
                    "reviews": 6,
                    "total_events": 73,
                },
            ]
        return []


async def post_all_embeds():
    """Post all embed types to the test channel."""
    settings = get_settings()

    # Get test channel ID from environment or use a default
    import os

    test_channel_id = int(os.getenv("TEST_DISCORD_CHANNEL_ID", settings.discord_channel_id))

    print(f"🤖 Connecting to Discord...")
    print(f"📍 Will post to channel ID: {test_channel_id}")
    print()

    # Initialize Discord bot (no database client needed for test)
    discord_bot = DiscordBot(
        settings.discord_token,
        test_channel_id,
        enable_commands=False,  # Don't sync commands for testing
    )

    async with discord_bot:
        channel = discord_bot.get_channel()
        print(f"✅ Connected! Channel: #{channel.name if hasattr(channel, 'name') else 'unknown'}")
        print()
        print("=" * 80)
        print("POSTING TEST EMBEDS")
        print("=" * 80)
        print()

        # 1. Stats embed - different timeframes
        print("1️⃣  Posting stats embeds (4 timeframes)...")
        fake_stats = create_fake_user_stats()
        fake_repos = create_fake_repos()

        for timeframe in ["today", "week", "month", "all"]:
            # Post comment describing this embed
            await channel.send(f"**TEST EMBED:** Stats for `{timeframe}` timeframe (`/activity stats {timeframe}`)")
            embed = create_stats_embed(fake_stats, timeframe, top_repos=fake_repos)
            await channel.send(embed=embed)
            await asyncio.sleep(0.5)
        print("   ✓ Posted stats embeds\n")

        # 2. Streak embed
        print("2️⃣  Posting streak embed...")
        fake_streaks = create_fake_streaks()
        await channel.send("**TEST EMBED:** Streak information (`/activity streak`)")
        embed = create_streak_embed(fake_streaks)
        await channel.send(embed=embed)
        await asyncio.sleep(0.5)
        print("   ✓ Posted streak embed\n")

        # 3. Badges/Achievements embed
        print("3️⃣  Posting achievements/badges embed...")
        milestone_achievements = create_fake_milestone_achievements()
        repeatable_achievements = create_fake_repeatable_achievements()
        await channel.send("**TEST EMBED:** Achievements and badges (milestone + repeatable)")
        embed = create_badges_embed(milestone_achievements, repeatable_achievements)
        await channel.send(embed=embed)
        await asyncio.sleep(0.5)
        print("   ✓ Posted badges embed\n")

        # 4. Repository stats - different sort orders
        print("4️⃣  Posting repository stats embeds (4 sort orders)...")
        fake_repos = create_fake_repos()

        for sort_by in ["total", "commits", "prs", "issues"]:
            await channel.send(f"**TEST EMBED:** Repository stats sorted by `{sort_by}` (`/activity repos {sort_by}`)")
            embed = create_repos_embed(fake_repos, sort_by)
            await channel.send(embed=embed)
            await asyncio.sleep(0.5)
        print("   ✓ Posted repo stats embeds\n")

        # 5. Time insights embed
        print("5️⃣  Posting time insights embed...")
        fake_patterns = create_fake_time_patterns()
        await channel.send("**TEST EMBED:** Coding time patterns and insights (`/activity insights`)")
        embed = create_insights_embed(fake_patterns)
        await channel.send(embed=embed)
        await asyncio.sleep(0.5)
        print("   ✓ Posted insights embed\n")

        # 6. Achievement announcement embeds (sample achievements)
        print("6️⃣  Posting achievement announcement embeds (5 examples)...")
        achievements = get_achievements()

        # Post a few different achievement announcements
        sample_achievement_ids = [
            "night_owl",
            "daily_dozen",
            "daily_fire_starter",
            "century_club",
            "productive_week",
        ]

        for ach_id in sample_achievement_ids:
            ach = achievements[ach_id]
            await channel.send(f"**TEST EMBED:** Achievement unlock announcement - `{ach.name}` (posted automatically when earned)")
            embed = create_achievement_announcement_embed(
                ach.emoji, ach.name, ach.description, total_count=5
            )
            await channel.send(embed=embed)
            await asyncio.sleep(0.5)
        print("   ✓ Posted achievement announcements\n")

        # 7. Daily summary
        print("7️⃣  Posting daily summary...")
        fake_db = FakeDatabaseClient()
        await channel.send("**TEST EMBED:** Daily summary (posted automatically at 9:00 AM with yesterday's stats)")
        daily_embed = await generate_daily_summary(fake_db, "testuser")
        await channel.send(embed=daily_embed)
        await asyncio.sleep(0.5)
        print("   ✓ Posted daily summary\n")

        # 8. Weekly summary
        print("8️⃣  Posting weekly summary...")
        await channel.send("**TEST EMBED:** Weekly summary (posted automatically on Mondays at 9:00 AM)")
        weekly_embed = await generate_weekly_summary(fake_db, "testuser")
        await channel.send(embed=weekly_embed)
        await asyncio.sleep(0.5)
        print("   ✓ Posted weekly summary\n")

        # 9. Monthly summary
        print("9️⃣  Posting monthly summary...")
        await channel.send("**TEST EMBED:** Monthly summary (posted automatically on 1st of month at 9:00 AM)")
        monthly_embed = await generate_monthly_summary(fake_db, "testuser")
        await channel.send(embed=monthly_embed)
        await asyncio.sleep(0.5)
        print("   ✓ Posted monthly summary\n")

        print("=" * 80)
        print("✅ ALL EMBEDS POSTED SUCCESSFULLY!")
        print("=" * 80)
        print()
        print("📊 Total embeds posted:")
        print("   - 4 stats embeds (today/week/month/all)")
        print("   - 1 streak embed")
        print("   - 1 badges/achievements embed")
        print("   - 4 repository stats embeds (different sorts)")
        print("   - 1 time insights embed")
        print("   - 5 achievement announcement embeds")
        print("   - 1 daily summary")
        print("   - 1 weekly summary")
        print("   - 1 monthly summary")
        print()
        print("   Total: 19 embeds")
        print()
        print(f"🔍 Check your test channel (ID: {test_channel_id}) to see all the embeds!")
        print()
        print("💡 TIP: To adjust colors/formatting, edit files in app/discord/:")
        print("   - stats_embeds.py (for slash command embeds)")
        print("   - summaries.py (for daily/weekly/monthly summaries)")
        print("   - event_colors.py (for embed colors)")


async def main():
    """Main entry point."""
    print()
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║           STATS & ACHIEVEMENTS EMBED PREVIEW SCRIPT                          ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print()
    print("This script will post all stats/achievement embeds to your test channel")
    print("using fake data so you can preview how everything looks.")
    print()
    print("⚙️  Configuration:")
    print("   - Set TEST_DISCORD_CHANNEL_ID in .env (optional)")
    print("   - Uses your normal DISCORD_TOKEN from .env")
    print("   - Falls back to DISCORD_CHANNEL_ID if TEST_DISCORD_CHANNEL_ID not set")
    print()

    try:
        await post_all_embeds()
        print("✨ Done! You can now adjust colors and formatting as needed.")
        print()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        print()
        print("💡 Common issues:")
        print("   - Make sure .env has DISCORD_TOKEN set")
        print("   - Make sure bot has access to the test channel")
        print("   - Check that the channel ID is correct")


if __name__ == "__main__":
    asyncio.run(main())
