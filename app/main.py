"""Activity Bot main entry point."""

import asyncio
import signal
import sys
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.state import StateManager
from app.github.client import GitHubClient
from app.github.polling import GitHubPollingService
from app.shared.exceptions import ConfigError, GitHubAPIError

logger = get_logger(__name__)

# Module-level variables for lifecycle management
github_client: GitHubClient | None = None
polling_service: GitHubPollingService | None = None


async def startup() -> None:
    """Initialize application on startup."""
    global github_client, polling_service

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

    # Initialize GitHub client
    github_client = GitHubClient(settings.github_token)
    await github_client.__aenter__()

    # Validate GitHub token and get username
    try:
        username = await github_client.get_authenticated_user()
        logger.info("github.auth.validated", username=username)
    except GitHubAPIError as e:
        logger.error("github.auth.failed", error=str(e))
        await github_client.__aexit__(None, None, None)
        raise ConfigError(f"Invalid GitHub token: {e}") from e

    # Initialize state manager
    state = StateManager(settings.state_file_path)

    # Initialize and start polling service
    polling_service = GitHubPollingService(
        client=github_client,
        state=state,
        settings=settings,
        username=username,
    )
    await polling_service.start()

    logger.info("application.initialization.completed")


async def shutdown() -> None:
    """Cleanup on application shutdown."""
    global github_client, polling_service

    logger.info("application.shutdown.started")

    # Stop polling service
    if polling_service:
        await polling_service.stop()

    # Close GitHub client
    if github_client:
        await github_client.__aexit__(None, None, None)

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
