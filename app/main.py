"""Activity Bot main entry point."""

import asyncio
import signal
import sys
from typing import Any

from app.core.config import Settings, get_settings
from app.core.database import DatabaseClient
from app.core.logging import get_logger, setup_logging
from app.core.state import StateManager
from app.discord.bot import DiscordBot
from app.discord.poster import DiscordPoster
from app.discord.quotes import QuoteService, set_quote_service
from app.github.action_filter import (
    filter_issue_actions,
    filter_pr_actions,
    filter_review_states,
)
from app.github.branch_filter import should_track_branch
from app.github.client import GitHubClient
from app.github.polling import GitHubPollingService
from app.shared.exceptions import ConfigError, GitHubAPIError

logger = get_logger(__name__)

# Module-level variables for lifecycle management
database_client: DatabaseClient | None = None
quote_service: QuoteService | None = None
stats_service: Any | None = None  # Avoid circular import, type is StatsService
github_client: GitHubClient | None = None
discord_bot: DiscordBot | None = None
discord_poster: DiscordPoster | None = None
polling_service: GitHubPollingService | None = None


async def recover_unposted_events(
    db: DatabaseClient,
    discord_poster: DiscordPoster,
    settings: Settings,
) -> None:
    """Recover and post unposted events from database on startup.

    Args:
        db: Database client
        discord_poster: Discord poster for event notifications
        settings: Application settings

    Note:
        Recovers all 8 event types within 12-hour window with filtering applied.
        Errors are logged but don't fail startup.
    """
    try:
        logger.info("recovery.started", max_age_hours=12)

        # Fetch all unposted events from database in parallel
        (
            commits,
            prs,
            issues,
            releases,
            reviews,
            creations,
            deletions,
            forks,
        ) = await asyncio.gather(
            db.get_unposted_commits(max_age_hours=12),
            db.get_unposted_prs(max_age_hours=12),
            db.get_unposted_issues(max_age_hours=12),
            db.get_unposted_releases(max_age_hours=12),
            db.get_unposted_reviews(max_age_hours=12),
            db.get_unposted_creations(max_age_hours=12),
            db.get_unposted_deletions(max_age_hours=12),
            db.get_unposted_forks(max_age_hours=12),
        )

        # Apply branch filtering to commits
        commits = [
            c
            for c in commits
            if should_track_branch(
                c.branch,
                settings.tracked_branches_list,
                settings.ignore_branch_patterns_list,
            )
        ]

        # Apply action filtering
        prs = filter_pr_actions(prs, settings.pr_actions_list)
        issues = filter_issue_actions(issues, settings.issue_actions_list)
        reviews = filter_review_states(reviews, settings.review_states_list)

        total_events = (
            len(commits)
            + len(prs)
            + len(issues)
            + len(releases)
            + len(reviews)
            + len(creations)
            + len(deletions)
            + len(forks)
        )

        if total_events == 0:
            logger.info("recovery.no_events")
            return

        logger.info(
            "recovery.posting_events",
            total=total_events,
            commits=len(commits),
            prs=len(prs),
            issues=len(issues),
            releases=len(releases),
            reviews=len(reviews),
            creations=len(creations),
            deletions=len(deletions),
            forks=len(forks),
        )

        # Post all events to Discord
        await discord_poster.post_all_events(
            commits=commits,
            prs=prs,
            issues=issues,
            releases=releases,
            reviews=reviews,
            creations=creations,
            deletions=deletions,
            forks=forks,
            settings=settings,
        )

        # Mark all events as posted
        await asyncio.gather(
            db.mark_commits_posted([f"commit_{c.sha}" for c in commits])
            if commits
            else asyncio.sleep(0),
            db.mark_prs_posted([pr.event_id for pr in prs]) if prs else asyncio.sleep(0),
            db.mark_issues_posted([i.event_id for i in issues]) if issues else asyncio.sleep(0),
            db.mark_releases_posted([r.event_id for r in releases])
            if releases
            else asyncio.sleep(0),
            db.mark_reviews_posted([r.event_id for r in reviews]) if reviews else asyncio.sleep(0),
            db.mark_creations_posted([c.event_id for c in creations])
            if creations
            else asyncio.sleep(0),
            db.mark_deletions_posted([d.event_id for d in deletions])
            if deletions
            else asyncio.sleep(0),
            db.mark_forks_posted([f.event_id for f in forks]) if forks else asyncio.sleep(0),
        )

        logger.info("recovery.completed", posted=total_events)

    except Exception as e:
        # Log error but don't fail startup
        logger.error("recovery.failed", error=str(e), exc_info=True)


async def startup() -> None:
    """Initialize application on startup."""
    global \
        database_client, \
        quote_service, \
        github_client, \
        discord_bot, \
        discord_poster, \
        polling_service

    settings = get_settings()

    logger.info(
        "application.lifecycle.started",
        version=settings.app_version,
        environment=settings.environment,
    )

    logger.info(
        "application.config.loaded",
        log_level=settings.log_level,
        poll_interval=settings.poll_interval_minutes,
        state_file=settings.state_file_path,
    )

    # Initialize database client
    database_client = DatabaseClient()
    await database_client.__aenter__()
    logger.info("database.client.initialized")

    # Initialize quote service
    quote_service = QuoteService(
        db_client=database_client,
        refresh_interval_minutes=settings.quote_cache_refresh_minutes,
    )
    await quote_service.start()
    set_quote_service(quote_service)

    # Initialize stats service if enabled
    stats_service = None
    if settings.enable_stats:
        from app.stats.service import StatsService, set_stats_service

        stats_service = StatsService(
            db_client=database_client,
            refresh_interval_minutes=settings.stats_refresh_interval_minutes,
        )
        await stats_service.start()
        set_stats_service(stats_service)
        logger.info("stats.service.initialized")

    # Initialize GitHub client
    github_client = GitHubClient(settings.github_token)
    await github_client.__aenter__()

    # Validate GitHub token
    try:
        authenticated_user = await github_client.get_authenticated_user()
        logger.info("github.auth.validated", username=authenticated_user)
    except GitHubAPIError as e:
        logger.error("github.auth.failed", error=str(e))
        await github_client.__aexit__(None, None, None)
        raise ConfigError(f"Invalid GitHub token: {e}") from e

    # Initialize state manager
    state = StateManager(settings.state_file_path)

    # Initialize Discord bot
    discord_bot = DiscordBot(settings.discord_token, settings.discord_channel_id)
    await discord_bot.__aenter__()
    logger.info("discord.bot.initialized")

    # Create Discord poster
    discord_poster = DiscordPoster(discord_bot)

    # Recover unposted events before starting polling
    await recover_unposted_events(database_client, discord_poster, settings)

    # Initialize and start polling service with tracked users
    polling_service = GitHubPollingService(
        client=github_client,
        state=state,
        settings=settings,
        usernames=settings.tracked_users_list,
        db=database_client,
        discord_poster=discord_poster,
    )
    await polling_service.start()

    logger.info("application.initialization.completed")


async def shutdown() -> None:
    """Cleanup on application shutdown."""
    global database_client, quote_service, stats_service, github_client, discord_bot, polling_service

    logger.info("application.shutdown.started")

    # Stop polling service
    if polling_service:
        await polling_service.stop()

    # Close Discord bot
    if discord_bot:
        await discord_bot.__aexit__(None, None, None)

    # Close GitHub client
    if github_client:
        await github_client.__aexit__(None, None, None)

    # Stop stats service
    if stats_service:
        await stats_service.stop()

    # Stop quote service
    if quote_service:
        await quote_service.stop()

    # Close database client
    if database_client:
        await database_client.__aexit__(None, None, None)

    logger.info("application.shutdown.completed")


async def main() -> None:
    """Main application loop."""
    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def signal_handler(sig: int) -> None:
        logger.info("application.signal.received", signal=signal.Signals(sig).name)
        task = loop.create_task(shutdown())

        def stop_loop(_: Any) -> None:
            loop.stop()

        task.add_done_callback(stop_loop)

    for sig in (signal.SIGINT, signal.SIGTERM):

        def make_handler(s: int = sig) -> None:
            signal_handler(s)

        loop.add_signal_handler(sig, make_handler)

    try:
        await startup()

        # Placeholder loop until Discord/GitHub integration in Phase 3
        # This keeps the application running
        while True:
            await asyncio.sleep(60)

    except KeyboardInterrupt:
        logger.info("application.interrupted")
        await shutdown()
    except Exception as e:
        logger.error("application.error.fatal", error=str(e), exc_info=True)
        await shutdown()
        raise


def run() -> None:
    """Entry point for running the bot."""
    try:
        # Load settings first to validate configuration
        settings = get_settings()

        # Setup logging with configured level
        setup_logging(log_level=settings.log_level)

        # Run the async main loop
        asyncio.run(main())

    except ConfigError as e:
        # Configuration errors should exit immediately with clear message
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        # Graceful exit on Ctrl+C
        pass
    except Exception as e:
        # Unexpected errors should be logged and exit with error code
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
