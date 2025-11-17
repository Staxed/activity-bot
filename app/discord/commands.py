"""Discord slash commands for stats and achievements."""

from typing import TYPE_CHECKING, Literal

import discord
from discord import app_commands

from app.core.config import get_settings
from app.core.logging import get_logger
from app.discord.stats_embeds import (
    create_badges_embed,
    create_insights_embed,
    create_repos_embed,
    create_stats_embed,
    create_streak_embed,
)
from app.stats.achievements import get_achievements
from app.stats.calculator import calculate_repo_stats, calculate_time_patterns
from app.stats.queries import GET_ACHIEVEMENT_COUNT, GET_MILESTONE_ACHIEVEMENTS
from app.stats.service import get_stats_service
from app.stats.streak_calculator import calculate_all_streaks

if TYPE_CHECKING:
    from app.core.database import DatabaseClient

logger = get_logger(__name__)


class StatsCommands(app_commands.Group, name="activity"):
    """Activity and stats slash commands."""

    def __init__(self, db_client: "DatabaseClient") -> None:
        """Initialize stats commands group.

        Args:
            db_client: Database client for stats queries
        """
        super().__init__()
        self.db_client = db_client

    @app_commands.command(name="stats", description="View your development statistics")
    @app_commands.describe(
        timeframe="Time window to display (default: week)",
        username="GitHub username (defaults to you)",
    )
    async def stats(
        self,
        interaction: discord.Interaction,
        timeframe: Literal["today", "week", "month", "all"] = "week",
        username: str | None = None,
    ) -> None:
        """Display user statistics.

        Args:
            interaction: Discord interaction
            timeframe: Time window for stats
            username: Optional GitHub username
        """
        await interaction.response.defer()

        try:
            # Get Discord username and map to GitHub username
            discord_username = username or interaction.user.name
            target_username = get_settings().get_github_username(discord_username)

            # Calculate since date based on timeframe
            from datetime import datetime, timedelta
            import pytz

            settings = get_settings()
            tz = pytz.timezone(settings.stats_timezone)
            now_local = datetime.now(tz)
            today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

            if timeframe == "today":
                since = today_start.astimezone(pytz.UTC).replace(tzinfo=None)
            elif timeframe == "week":
                week_start = today_start - timedelta(days=today_start.weekday())
                since = week_start.astimezone(pytz.UTC).replace(tzinfo=None)
            elif timeframe == "month":
                month_start = today_start.replace(day=1)
                since = month_start.astimezone(pytz.UTC).replace(tzinfo=None)
            else:  # all
                since = None

            # Get stats from service and top repos from database
            stats_service = get_stats_service()
            user_stats = await stats_service.get_user_stats_fresh(target_username)
            top_repos = await calculate_repo_stats(self.db_client, target_username, since=since)

            # Create embed with top 3 repos
            embed = create_stats_embed(user_stats, timeframe, top_repos=top_repos[:3])

            await interaction.followup.send(embed=embed)
            logger.info(
                "discord.command.stats",
                user=interaction.user.name,
                target=target_username,
                timeframe=timeframe,
            )

        except Exception as e:
            logger.error("discord.command.stats.failed", error=str(e), exc_info=True)
            await interaction.followup.send(f"❌ Failed to fetch stats: {e!s}", ephemeral=True)

    @app_commands.command(name="streak", description="View your commit streaks")
    @app_commands.describe(username="GitHub username (defaults to you)")
    async def streak(self, interaction: discord.Interaction, username: str | None = None) -> None:
        """Display commit streaks.

        Args:
            interaction: Discord interaction
            username: Optional GitHub username
        """
        await interaction.response.defer()

        try:
            # Get Discord username and map to GitHub username
            discord_username = username or interaction.user.name
            target_username = get_settings().get_github_username(discord_username)

            # Calculate streaks using bot's database client
            streaks = await calculate_all_streaks(self.db_client, target_username)

            # Create embed
            embed = create_streak_embed(streaks)

            await interaction.followup.send(embed=embed)
            logger.info(
                "discord.command.streak",
                user=interaction.user.name,
                target=target_username,
            )

        except Exception as e:
            logger.error("discord.command.streak.failed", error=str(e), exc_info=True)
            await interaction.followup.send(f"❌ Failed to fetch streaks: {e!s}", ephemeral=True)

    @app_commands.command(name="repos", description="View repository activity")
    @app_commands.describe(
        sort_by="Sort repositories by metric (default: total)",
        username="GitHub username (defaults to you)",
    )
    async def repos(
        self,
        interaction: discord.Interaction,
        sort_by: Literal["total", "commits", "prs", "issues"] = "total",
        username: str | None = None,
    ) -> None:
        """Display repository statistics.

        Args:
            interaction: Discord interaction
            sort_by: Sort criteria
            username: Optional GitHub username
        """
        await interaction.response.defer()

        try:
            # Get Discord username and map to GitHub username
            discord_username = username or interaction.user.name
            target_username = get_settings().get_github_username(discord_username)

            # Calculate repo stats using bot's database client
            repos = await calculate_repo_stats(self.db_client, target_username, since=None)

            # Create embed
            embed = create_repos_embed(repos, sort_by)

            await interaction.followup.send(embed=embed)
            logger.info(
                "discord.command.repos",
                user=interaction.user.name,
                target=target_username,
                sort_by=sort_by,
            )

        except Exception as e:
            logger.error("discord.command.repos.failed", error=str(e), exc_info=True)
            await interaction.followup.send(f"❌ Failed to fetch repos: {e!s}", ephemeral=True)

    @app_commands.command(name="insights", description="View coding time patterns")
    @app_commands.describe(username="GitHub username (defaults to you)")
    async def insights(self, interaction: discord.Interaction, username: str | None = None) -> None:
        """Display time pattern insights.

        Args:
            interaction: Discord interaction
            username: Optional GitHub username
        """
        await interaction.response.defer()

        try:
            # Get Discord username and map to GitHub username
            discord_username = username or interaction.user.name
            target_username = get_settings().get_github_username(discord_username)

            # Calculate time patterns using bot's database client
            patterns = await calculate_time_patterns(self.db_client, target_username)

            # Create embed
            embed = create_insights_embed(patterns)

            await interaction.followup.send(embed=embed)
            logger.info(
                "discord.command.insights",
                user=interaction.user.name,
                target=target_username,
            )

        except Exception as e:
            logger.error("discord.command.insights.failed", error=str(e), exc_info=True)
            await interaction.followup.send(f"❌ Failed to fetch insights: {e!s}", ephemeral=True)

    @app_commands.command(name="badges", description="View your earned achievements and badges")
    @app_commands.describe(username="GitHub username (defaults to you)")
    async def badges(self, interaction: discord.Interaction, username: str | None = None) -> None:
        """Display earned achievements and badges.

        Args:
            interaction: Discord interaction
            username: Optional GitHub username
        """
        await interaction.response.defer()

        try:
            # Get Discord username and map to GitHub username
            discord_username = username or interaction.user.name
            target_username = get_settings().get_github_username(discord_username)

            # Get all achievement definitions
            all_achievements = get_achievements()

            async with self.db_client.pool.acquire() as conn:
                # Get milestone achievements
                milestone_rows = await conn.fetch(GET_MILESTONE_ACHIEVEMENTS, target_username)

                milestone_achievements = []
                for row in milestone_rows:
                    ach_id = row["achievement_id"]
                    if ach_id in all_achievements:
                        ach = all_achievements[ach_id]
                        milestone_achievements.append((ach.emoji, ach.name, ach.description))

                # Get repeatable achievement counts
                repeatable_achievements = []
                for ach_id, ach in all_achievements.items():
                    if ach.achievement_type == "repeatable":
                        count_row = await conn.fetchval(GET_ACHIEVEMENT_COUNT, target_username, ach_id)
                        if count_row and count_row > 0:
                            repeatable_achievements.append((ach.emoji, ach.name, count_row))

                # Sort repeatable by count (highest first)
                repeatable_achievements.sort(key=lambda x: x[2], reverse=True)

            # Create embed
            embed = create_badges_embed(milestone_achievements, repeatable_achievements)

            await interaction.followup.send(embed=embed)
            logger.info(
                "discord.command.badges",
                user=interaction.user.name,
                target=target_username,
                milestones=len(milestone_achievements),
                repeatables=len(repeatable_achievements),
            )

        except Exception as e:
            logger.error("discord.command.badges.failed", error=str(e), exc_info=True)
            await interaction.followup.send(f"❌ Failed to fetch badges: {e!s}", ephemeral=True)


def setup_commands(tree: app_commands.CommandTree, db_client: "DatabaseClient") -> None:
    """Setup stats commands on the command tree.

    Args:
        tree: Discord command tree to add commands to
        db_client: Database client for stats queries
    """
    stats_commands = StatsCommands(db_client)
    tree.add_command(stats_commands)
    logger.info(
        "discord.commands.setup",
        commands=[
            "activity stats",
            "activity streak",
            "activity repos",
            "activity insights",
            "activity badges",
        ],
    )
