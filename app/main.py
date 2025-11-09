"""Activity Bot main entry point."""

import asyncio
import signal
import sys

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.shared.exceptions import ConfigError

logger = get_logger(__name__)


async def startup() -> None:
    """Initialize application on startup."""
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

    logger.info("application.initialization.completed")


async def shutdown() -> None:
    """Cleanup on application shutdown."""
    logger.info("application.shutdown.started")
    # TODO: Add cleanup for Discord bot, GitHub client, etc. in future phases
    logger.info("application.shutdown.completed")


async def main() -> None:
    """Main application loop."""
    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def signal_handler(sig: int) -> None:
        logger.info("application.signal.received", signal=signal.Signals(sig).name)
        loop.create_task(shutdown())
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

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
