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
    filter_commit_comment_actions,
    filter_discussion_actions,
    filter_issue_actions,
    filter_issue_comment_actions,
    filter_member_actions,
    filter_pr_actions,
    filter_pr_review_comment_actions,
    filter_review_states,
    filter_wiki_actions,
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
summary_scheduler: Any | None = None  # Avoid circular import, type is SummaryScheduler
github_client: GitHubClient | None = None
discord_bot: DiscordBot | None = None
discord_poster: DiscordPoster | None = None
polling_service: GitHubPollingService | None = None

# NFT tracking module-level variables
nft_webhook_server: Any | None = None  # WebhookServer
nft_marketplace_poller: Any | None = None  # MarketplacePollingService
nft_poster: Any | None = None  # NFTPoster


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
        Recovers all 16 event types within 12-hour window with filtering applied.
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
            stars,
            issue_comments,
            pr_review_comments,
            commit_comments,
            members,
            wiki_pages,
            public_events,
            discussions,
        ) = await asyncio.gather(
            db.get_unposted_commits(max_age_hours=12),
            db.get_unposted_prs(max_age_hours=12),
            db.get_unposted_issues(max_age_hours=12),
            db.get_unposted_releases(max_age_hours=12),
            db.get_unposted_reviews(max_age_hours=12),
            db.get_unposted_creations(max_age_hours=12),
            db.get_unposted_deletions(max_age_hours=12),
            db.get_unposted_forks(max_age_hours=12),
            db.get_unposted_stars(max_age_hours=12),
            db.get_unposted_issue_comments(max_age_hours=12),
            db.get_unposted_pr_review_comments(max_age_hours=12),
            db.get_unposted_commit_comments(max_age_hours=12),
            db.get_unposted_members(max_age_hours=12),
            db.get_unposted_wiki_pages(max_age_hours=12),
            db.get_unposted_public_events(max_age_hours=12),
            db.get_unposted_discussions(max_age_hours=12),
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
        issue_comments = filter_issue_comment_actions(
            issue_comments, settings.issue_comment_actions_list
        )
        pr_review_comments = filter_pr_review_comment_actions(
            pr_review_comments, settings.pr_review_comment_actions_list
        )
        commit_comments = filter_commit_comment_actions(
            commit_comments, settings.commit_comment_actions_list
        )
        members = filter_member_actions(members, settings.member_actions_list)
        wiki_pages = filter_wiki_actions(wiki_pages, settings.wiki_actions_list)
        discussions = filter_discussion_actions(discussions, settings.discussion_actions_list)

        total_events = (
            len(commits)
            + len(prs)
            + len(issues)
            + len(releases)
            + len(reviews)
            + len(creations)
            + len(deletions)
            + len(forks)
            + len(stars)
            + len(issue_comments)
            + len(pr_review_comments)
            + len(commit_comments)
            + len(members)
            + len(wiki_pages)
            + len(public_events)
            + len(discussions)
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
            stars=len(stars),
            issue_comments=len(issue_comments),
            pr_review_comments=len(pr_review_comments),
            commit_comments=len(commit_comments),
            members=len(members),
            wiki_pages=len(wiki_pages),
            public_events=len(public_events),
            discussions=len(discussions),
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
            stars=stars,
            issue_comments=issue_comments,
            pr_review_comments=pr_review_comments,
            commit_comments=commit_comments,
            members=members,
            wiki_pages=wiki_pages,
            public_events=public_events,
            discussions=discussions,
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
            db.mark_stars_posted([s.event_id for s in stars]) if stars else asyncio.sleep(0),
            db.mark_issue_comments_posted([ic.event_id for ic in issue_comments])
            if issue_comments
            else asyncio.sleep(0),
            db.mark_pr_review_comments_posted([prc.event_id for prc in pr_review_comments])
            if pr_review_comments
            else asyncio.sleep(0),
            db.mark_commit_comments_posted([cc.event_id for cc in commit_comments])
            if commit_comments
            else asyncio.sleep(0),
            db.mark_members_posted([m.event_id for m in members]) if members else asyncio.sleep(0),
            db.mark_wiki_pages_posted([w.event_id for w in wiki_pages])
            if wiki_pages
            else asyncio.sleep(0),
            db.mark_public_events_posted([pe.event_id for pe in public_events])
            if public_events
            else asyncio.sleep(0),
            db.mark_discussions_posted([d.event_id for d in discussions])
            if discussions
            else asyncio.sleep(0),
        )

        logger.info("recovery.completed", posted=total_events)

    except Exception as e:
        # Log error but don't fail startup
        logger.error("recovery.failed", error=str(e), exc_info=True)


async def recover_unposted_nft_events(
    db: DatabaseClient,
    nft_poster: Any,  # NFTPoster type
) -> None:
    """Recover and post unposted NFT events from database on startup.

    Args:
        db: Database client
        nft_poster: NFT poster for Discord notifications

    Note:
        Recovers all NFT event types within 12-hour window.
        Errors are logged but don't fail startup.
    """
    try:
        logger.info("nft.recovery.started", max_age_hours=12)

        # Fetch all unposted NFT events from database in parallel
        (
            mints,
            transfers,
            burns,
            listings,
            sales,
            delistings,
        ) = await asyncio.gather(
            db.get_unposted_nft_mints(max_age_hours=12),
            db.get_unposted_nft_transfers(max_age_hours=12),
            db.get_unposted_nft_burns(max_age_hours=12),
            db.get_unposted_nft_listings(max_age_hours=12),
            db.get_unposted_nft_sales(max_age_hours=12),
            db.get_unposted_nft_delistings(max_age_hours=12),
        )

        total_events = (
            len(mints) + len(transfers) + len(burns) + len(listings) + len(sales) + len(delistings)
        )

        if total_events == 0:
            logger.info("nft.recovery.no_events")
            return

        logger.info(
            "nft.recovery.posting_events",
            total=total_events,
            mints=len(mints),
            transfers=len(transfers),
            burns=len(burns),
            listings=len(listings),
            sales=len(sales),
            delistings=len(delistings),
        )

        # Post mint events
        for db_id, event, collection_name, channel_id in mints:
            try:
                await nft_poster.post_mint(event, collection_name, channel_id)
                await db.mark_nft_mint_posted(
                    event.collection_id, event.token_id, event.transaction_hash
                )
            except Exception as e:
                logger.warning("nft.recovery.mint.failed", error=str(e), token_id=event.token_id)

        # Post transfer events
        for db_id, event, collection_name, channel_id in transfers:
            try:
                await nft_poster.post_transfer(event, collection_name, channel_id)
                await db.mark_nft_transfer_posted(
                    event.collection_id, event.token_id, event.transaction_hash
                )
            except Exception as e:
                logger.warning(
                    "nft.recovery.transfer.failed", error=str(e), token_id=event.token_id
                )

        # Post burn events
        for db_id, event, collection_name, channel_id in burns:
            try:
                await nft_poster.post_burn(event, collection_name, channel_id)
                await db.mark_nft_burn_posted(
                    event.collection_id, event.token_id, event.transaction_hash
                )
            except Exception as e:
                logger.warning("nft.recovery.burn.failed", error=str(e), token_id=event.token_id)

        # Post listing events
        for db_id, event, collection_name, channel_id, chain, contract_address in listings:
            try:
                await nft_poster.post_listing(
                    event, collection_name, channel_id, chain=chain, contract_address=contract_address
                )
                await db.mark_nft_listing_posted(
                    event.collection_id, event.marketplace, event.listing_id
                )
            except Exception as e:
                logger.warning("nft.recovery.listing.failed", error=str(e), token_id=event.token_id)

        # Post sale events
        for db_id, event, collection_name, channel_id, chain in sales:
            try:
                await nft_poster.post_sale(event, collection_name, channel_id, chain=chain)
                await db.mark_nft_sale_posted(event.collection_id, event.marketplace, event.sale_id)
            except Exception as e:
                logger.warning("nft.recovery.sale.failed", error=str(e), token_id=event.token_id)

        # Post delisting events
        for db_id, event, collection_name, channel_id in delistings:
            try:
                await nft_poster.post_delisting(event, collection_name, channel_id)
                await db.mark_nft_delisting_posted(
                    event.collection_id, event.marketplace, event.delisting_id
                )
            except Exception as e:
                logger.warning(
                    "nft.recovery.delisting.failed", error=str(e), token_id=event.token_id
                )

        logger.info("nft.recovery.completed", posted=total_events)

    except Exception as e:
        # Log error but don't fail startup
        logger.error("nft.recovery.failed", error=str(e), exc_info=True)


async def startup() -> None:
    """Initialize application on startup."""
    global \
        database_client, \
        quote_service, \
        stats_service, \
        summary_scheduler, \
        github_client, \
        discord_bot, \
        discord_poster, \
        polling_service, \
        nft_webhook_server, \
        nft_marketplace_poller, \
        nft_poster

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

    # Initialize Discord bot (with database client for slash commands)
    discord_bot = DiscordBot(
        settings.discord_token,
        settings.discord_channel_id,
        enable_commands=settings.enable_stats,  # Only enable commands if stats enabled
        db_client=database_client,
    )
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

    # Initialize summary scheduler if stats enabled
    if settings.enable_stats:
        from app.discord.summary_scheduler import SummaryScheduler, set_summary_scheduler

        summary_scheduler = SummaryScheduler(db=database_client, discord_poster=discord_poster)
        await summary_scheduler.start()
        set_summary_scheduler(summary_scheduler)
        logger.info("summary.scheduler.initialized")

    # Initialize NFT tracking if enabled
    if settings.nft_enabled:
        from app.discord.nft_poster import NFTPoster
        from app.nft.config import load_collections_config
        from app.nft.marketplaces.poller import MarketplacePollingService
        from app.nft.thirdweb.handler import ThirdwebEventHandler
        from app.nft.webhook_server import WebhookServer

        # Load NFT collections config
        nft_config = load_collections_config(settings.nft_collections_config)
        logger.info(
            "nft.config.loaded",
            total=len(nft_config.collections),
            active=len(nft_config.active_collections),
        )

        # Sync collections to database
        for collection in nft_config.collections:
            await database_client.sync_nft_collection(
                collection_id=collection.id,
                name=collection.name,
                chain=collection.chain,
                contract_address=collection.contract_address,
                discord_channel_id=collection.discord_channel_id,
                is_active=collection.is_active,
            )

        # Create NFT poster
        nft_poster = NFTPoster(discord_bot)

        # Recover unposted NFT events before starting services
        await recover_unposted_nft_events(database_client, nft_poster)

        # Start webhook server for Thirdweb events (if webhook secret configured)
        if settings.thirdweb_webhook_secret:
            event_handler = ThirdwebEventHandler(
                db=database_client,
                poster=nft_poster,
                company_wallets=settings.nft_company_wallets_list,
            )
            nft_webhook_server = WebhookServer(
                host=settings.webhook_server_host,
                port=settings.webhook_server_port,
                webhook_secret=settings.thirdweb_webhook_secret,
                event_handler=event_handler,
            )
            await nft_webhook_server.start()
            logger.info(
                "nft.webhook_server.started",
                host=settings.webhook_server_host,
                port=settings.webhook_server_port,
            )

        # Start marketplace polling service (Magic Eden aggregates all marketplaces)
        nft_marketplace_poller = MarketplacePollingService(
            db=database_client,
            poster=nft_poster,
            poll_interval_minutes=settings.nft_marketplace_poll_interval_minutes,
        )
        await nft_marketplace_poller.start()
        logger.info("nft.marketplace_poller.started")

    logger.info("application.initialization.completed")


async def shutdown() -> None:
    """Cleanup on application shutdown."""
    global \
        database_client, \
        quote_service, \
        stats_service, \
        summary_scheduler, \
        github_client, \
        discord_bot, \
        polling_service, \
        nft_webhook_server, \
        nft_marketplace_poller

    logger.info("application.shutdown.started")

    # Stop NFT marketplace poller
    if nft_marketplace_poller:
        await nft_marketplace_poller.stop()

    # Stop NFT webhook server
    if nft_webhook_server:
        await nft_webhook_server.stop()

    # Stop polling service
    if polling_service:
        await polling_service.stop()

    # Stop summary scheduler
    if summary_scheduler:
        await summary_scheduler.stop()

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

        def stop_loop(_: asyncio.Task[None]) -> None:
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
