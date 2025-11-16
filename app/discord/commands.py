"""Discord slash commands for stats and achievements."""

from typing import Literal

import discord
from discord import app_commands

from app.core.logging import get_logger
from app.discord.stats_embeds import (
    create_insights_embed,
    create_repos_embed,
    create_stats_embed,
    create_streak_embed,
)
from app.stats.calculator import calculate_repo_stats, calculate_time_patterns
from app.stats.service import get_stats_service
from app.stats.streak_calculator import calculate_all_streaks

logger = get_logger(__name__)


class StatsCommands(app_commands.Group, name="activity"):
    """Activity and stats slash commands."""

    def __init__(self) -> None:
        """Initialize stats commands group."""
        super().__init__()

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
            # Get username from interaction or parameter
            target_username = username or interaction.user.name

            # Get stats from service
            stats_service = get_stats_service()
            user_stats = await stats_service.get_user_stats_fresh(target_username)

            # Create embed
            embed = create_stats_embed(user_stats, timeframe)

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
            from app.core.database import DatabaseClient

            # Get username
            target_username = username or interaction.user.name

            # Calculate streaks (requires fresh calculation)
            # TODO: Get db_client from bot instance
            db_client = DatabaseClient()  # This needs to come from bot
            async with db_client:
                streaks = await calculate_all_streaks(db_client, target_username)

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
            from app.core.database import DatabaseClient

            target_username = username or interaction.user.name

            # Calculate repo stats
            db_client = DatabaseClient()
            async with db_client:
                repos = await calculate_repo_stats(db_client, target_username, since=None)

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
            from app.core.database import DatabaseClient

            target_username = username or interaction.user.name

            # Calculate time patterns
            db_client = DatabaseClient()
            async with db_client:
                patterns = await calculate_time_patterns(db_client, target_username)

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
            await interaction.followup.send(
                f"❌ Failed to fetch insights: {e!s}", ephemeral=True
            )


def setup_commands(tree: app_commands.CommandTree) -> None:
    """Setup stats commands on the command tree.

    Args:
        tree: Discord command tree to add commands to
    """
    stats_commands = StatsCommands()
    tree.add_command(stats_commands)
    logger.info(
        "discord.commands.setup",
        commands=["activity stats", "activity streak", "activity repos", "activity insights"],
    )
