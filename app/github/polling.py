"""GitHub event polling service with failure tracking."""

import asyncio
from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.state import StateManager
from app.github.branch_filter import should_track_branch
from app.github.client import GitHubClient
from app.github.events import filter_push_events, parse_commits_from_events
from app.shared.exceptions import GitHubPollingError

logger = get_logger(__name__)


class GitHubPollingService:
    """Service for polling GitHub events with failure tracking.

    Polls GitHub Events API at regular intervals, tracks processed events,
    and raises GitHubPollingError after consecutive failures exceed threshold.

    Attributes:
        FAILURE_THRESHOLD: Number of consecutive failures before raising error
        MAX_PAGES: Maximum number of pages to fetch when looking for last event
    """

    FAILURE_THRESHOLD = 2
    MAX_PAGES = 10

    def __init__(
        self,
        client: GitHubClient,
        state: StateManager,
        settings: Settings,
        username: str,
    ) -> None:
        """Initialize polling service with dependencies.

        Args:
            client: GitHub API client instance
            state: State manager for persistence
            settings: Application settings
            username: GitHub username to poll events for
        """
        self.client = client
        self.state = state
        self.settings = settings
        self.username = username
        self.consecutive_failures = 0
        self.running = False
        self.task: asyncio.Task[None] | None = None

    async def _fetch_events_until_last_id(self, last_event_id: str | None) -> list[dict[str, Any]]:
        """Fetch events from GitHub API until last_event_id is found.

        Args:
            last_event_id: Last processed event ID (None on first run)

        Returns:
            List of new events (empty on first run or if last_event_id not found)

        Note:
            - First run (last_event_id is None): Fetches page 1 only, returns []
            - Subsequent runs: Fetches pages until last_event_id found
            - Logs warning if last_event_id never found (>300 events missed)
        """
        # First run: fetch latest events but don't process
        if last_event_id is None:
            await self.client.fetch_user_events(self.username, page=1)
            return []

        collected_events: list[dict[str, Any]] = []
        last_event_id_int = int(last_event_id)

        for page in range(1, self.MAX_PAGES + 1):
            events = await self.client.fetch_user_events(self.username, page=page)

            if not events:
                # No more events available
                break

            # Collect events newer than last_event_id
            for event in events:
                event_id_int = int(event["id"])

                if event_id_int > last_event_id_int:
                    collected_events.append(event)
                else:
                    # Found the last processed event, stop here
                    logger.info(
                        "github.poll.found_last_event",
                        last_event_id=last_event_id,
                        page=page,
                        new_events=len(collected_events),
                    )
                    return collected_events

        # If we get here, we never found last_event_id
        if collected_events:
            logger.warning(
                "github.poll.missed_events",
                last_event_id=last_event_id,
                pages_fetched=self.MAX_PAGES,
                collected=len(collected_events),
            )

        return collected_events

    async def poll_once(self) -> int:
        """Poll GitHub events once and process new commits.

        Returns:
            Number of commits processed

        Raises:
            GitHubPollingError: If consecutive failures exceed threshold

        Note:
            - First run: Stores newest event ID without processing
            - Subsequent runs: Processes only new events
            - Success resets consecutive_failures counter
        """
        try:
            last_event_id = self.state.get_last_event_id()

            logger.info(
                "github.poll.started",
                username=self.username,
                last_event_id=last_event_id,
            )

            # Fetch events since last poll
            events = await self._fetch_events_until_last_id(last_event_id)

            # First run: store newest event ID without processing
            if last_event_id is None:
                if events:
                    newest_id = events[0]["id"]
                    self.state.set_last_event_id(newest_id)
                    logger.info("github.poll.first_run", event_id=newest_id)
                else:
                    # No events at all, fetch first page to get latest ID
                    first_page = await self.client.fetch_user_events(self.username, page=1)
                    if first_page:
                        newest_id = first_page[0]["id"]
                        self.state.set_last_event_id(newest_id)
                        logger.info("github.poll.first_run", event_id=newest_id)
                    else:
                        logger.info("github.poll.first_run.no_events")

                self.consecutive_failures = 0
                return 0

            # No new events
            if not events:
                logger.info("github.poll.no_new_events")
                self.consecutive_failures = 0
                return 0

            # Filter and parse PushEvents
            push_events = filter_push_events(events)
            commits = parse_commits_from_events(push_events)

            # Reverse to process oldest first (chronological order)
            commits.reverse()

            # Filter commits by branch and log each tracked commit
            tracked_count = 0
            for commit in commits:
                # Check if this branch should be tracked
                if not should_track_branch(
                    commit.branch,
                    self.settings.tracked_branches_list,
                    self.settings.ignore_branch_patterns_list,
                ):
                    logger.debug(
                        "github.commit.skipped",
                        sha=commit.short_sha,
                        repo=f"{commit.repo_owner}/{commit.repo_name}",
                        branch=commit.branch,
                        reason="branch_filtered",
                    )
                    continue

                # Log tracked commit
                logger.info(
                    "github.commit.discovered",
                    sha=commit.short_sha,
                    repo=f"{commit.repo_owner}/{commit.repo_name}",
                    branch=commit.branch,
                    author=commit.author,
                    message=commit.message,
                    timestamp=commit.timestamp.isoformat(),
                    url=commit.url,
                )
                tracked_count += 1

            # Update state with newest event ID
            newest_event_id = events[0]["id"]
            self.state.set_last_event_id(newest_event_id)

            logger.info(
                "github.poll.complete",
                commits_total=len(commits),
                commits_tracked=tracked_count,
                commits_filtered=len(commits) - tracked_count,
                newest_event_id=newest_event_id,
            )

            # Reset failure counter on success
            self.consecutive_failures = 0
            return tracked_count

        except Exception as e:
            self.consecutive_failures += 1
            logger.error(
                "github.poll.failed",
                error=str(e),
                consecutive_failures=self.consecutive_failures,
                exc_info=True,
            )

            if self.consecutive_failures >= self.FAILURE_THRESHOLD:
                raise GitHubPollingError(
                    f"Polling failed {self.consecutive_failures} times consecutively"
                ) from e

            return 0

    async def _poll_loop(self) -> None:
        """Background task loop for polling at regular intervals."""
        while self.running:
            try:
                await self.poll_once()
            except GitHubPollingError:
                # Fatal error, stop polling
                logger.error("github.poll.threshold_exceeded")
                self.running = False
                raise

            # Sleep for configured interval (convert minutes to seconds)
            await asyncio.sleep(self.settings.poll_interval_minutes * 60)

    async def start(self) -> None:
        """Start the polling service.

        Creates and starts the background polling task.
        """
        if self.running:
            logger.warning("github.polling.already_running")
            return

        self.running = True
        self.task = asyncio.create_task(self._poll_loop())
        logger.info(
            "github.polling.started",
            username=self.username,
            interval_minutes=self.settings.poll_interval_minutes,
        )

    async def stop(self) -> None:
        """Stop the polling service.

        Cancels the background polling task and waits for cleanup.
        """
        if not self.running:
            logger.warning("github.polling.not_running")
            return

        self.running = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        logger.info("github.polling.stopped")
