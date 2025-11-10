"""GitHub event polling service with failure tracking."""

import asyncio
from typing import TYPE_CHECKING, Any

from app.core.config import Settings
from app.core.database import DatabaseClient
from app.core.logging import get_logger
from app.core.state import StateManager, get_last_event_id_async, set_last_event_id_async
from app.github.branch_filter import should_track_branch
from app.github.client import GitHubClient
from app.github.events import (
    filter_events_by_type,
    filter_push_events,
    parse_commits_from_events,
    parse_creations_from_events,
    parse_deletions_from_events,
    parse_forks_from_events,
    parse_issues_from_events,
    parse_pr_reviews_from_events,
    parse_pull_requests_from_events,
    parse_releases_from_events,
)
from app.shared.exceptions import GitHubPollingError

if TYPE_CHECKING:
    from app.discord.poster import DiscordPoster

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
        db: DatabaseClient,
        discord_poster: "DiscordPoster | None" = None,
    ) -> None:
        """Initialize polling service with dependencies.

        Args:
            client: GitHub API client instance
            state: State manager for persistence
            settings: Application settings
            username: GitHub username to poll events for
            db: Database client for event storage
            discord_poster: Optional Discord poster for commit notifications
        """
        self.client = client
        self.state = state
        self.settings = settings
        self.username = username
        self.db = db
        self.discord_poster = discord_poster
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
                event_id = event.get("id")
                if not event_id:
                    logger.warning(
                        "github.poll.event_missing_id",
                        page=page,
                        event_type=event.get("type", "Unknown"),
                    )
                    continue
                
                try:
                    event_id_int = int(event_id)
                except (ValueError, TypeError):
                    logger.warning(
                        "github.poll.invalid_event_id",
                        event_id=event_id,
                        page=page,
                    )
                    continue

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
        """Poll GitHub events once and store all events in database.

        Returns:
            Number of commits processed and posted to Discord

        Raises:
            GitHubPollingError: If consecutive failures exceed threshold

        Note:
            - First run: Stores newest event ID without processing
            - Subsequent runs: Stores ALL 8 event types, posts commits only
            - Success resets consecutive_failures counter
        """
        try:
            # Get last event ID from database
            last_event_id = await get_last_event_id_async(self.db)

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
                    await set_last_event_id_async(self.db, newest_id)
                    logger.info("github.poll.first_run", event_id=newest_id)
                else:
                    # No events at all, fetch first page to get latest ID
                    first_page = await self.client.fetch_user_events(self.username, page=1)
                    if first_page:
                        newest_id = first_page[0]["id"]
                        await set_last_event_id_async(self.db, newest_id)
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

            # Log event types received for debugging
            event_types = [e.get("type", "Unknown") for e in events]
            logger.info(
                "github.poll.event_types",
                total=len(events),
                types=event_types,
            )

            # Filter events by type
            categorized = filter_events_by_type(events)

            # Parse all event types in parallel
            commits_task = parse_commits_from_events(categorized["PushEvent"], self.client)
            prs_task = parse_pull_requests_from_events(categorized["PullRequestEvent"])
            pr_reviews_task = parse_pr_reviews_from_events(categorized["PullRequestReviewEvent"])
            issues_task = parse_issues_from_events(categorized["IssuesEvent"])
            releases_task = parse_releases_from_events(categorized["ReleaseEvent"])
            creations_task = parse_creations_from_events(categorized["CreateEvent"])
            deletions_task = parse_deletions_from_events(categorized["DeleteEvent"])
            forks_task = parse_forks_from_events(categorized["ForkEvent"])

            # Await all parsing in parallel
            (
                commits,
                prs,
                pr_reviews,
                issues,
                releases,
                creations,
                deletions,
                forks,
            ) = await asyncio.gather(
                commits_task,
                prs_task,
                pr_reviews_task,
                issues_task,
                releases_task,
                creations_task,
                deletions_task,
                forks_task,
            )

            # Bulk insert all events to database in parallel
            await asyncio.gather(
                self.db.insert_commits(commits),
                self.db.insert_pull_requests(prs),
                self.db.insert_pr_reviews(pr_reviews),
                self.db.insert_issues(issues),
                self.db.insert_releases(releases),
                self.db.insert_creations(creations),
                self.db.insert_deletions(deletions),
                self.db.insert_forks(forks),
            )

            # Reverse commits to process oldest first (chronological order)
            commits.reverse()

            # Filter commits by branch and collect tracked commits for Discord posting
            tracked_commits = []
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
                tracked_commits.append(commit)

            # Post tracked commits to Discord (only if not already posted)
            if self.discord_poster and tracked_commits:
                try:
                    # Get list of commits that haven't been posted yet
                    commit_shas = [c.sha for c in tracked_commits]
                    unposted_shas = await self.db.get_unposted_commit_shas(commit_shas)

                    # Filter to only unposted commits
                    unposted_commits = [c for c in tracked_commits if c.sha in unposted_shas]

                    if unposted_commits:
                        await self.discord_poster.post_commits(unposted_commits)

                        # Mark posted commits in database
                        event_ids = [f"commit_{c.sha}" for c in unposted_commits]
                        await self.db.mark_commits_posted(event_ids)
                    else:
                        logger.info("discord.post.skipped", reason="all_already_posted")
                except Exception as e:
                    logger.error("discord.post.error", error=str(e), exc_info=True)

            # Update state with newest event ID in database
            newest_event_id = events[0]["id"]
            await set_last_event_id_async(self.db, newest_event_id)

            logger.info(
                "github.poll.complete",
                commits_total=len(commits),
                commits_tracked=len(tracked_commits),
                commits_filtered=len(commits) - len(tracked_commits),
                prs_total=len(prs),
                pr_reviews_total=len(pr_reviews),
                issues_total=len(issues),
                releases_total=len(releases),
                creations_total=len(creations),
                deletions_total=len(deletions),
                forks_total=len(forks),
                newest_event_id=newest_event_id,
            )
            
            # Log categorized counts for debugging
            logger.debug(
                "github.poll.categorized",
                push_events=len(categorized["PushEvent"]),
                pr_events=len(categorized["PullRequestEvent"]),
                pr_review_events=len(categorized["PullRequestReviewEvent"]),
                issue_events=len(categorized["IssuesEvent"]),
                release_events=len(categorized["ReleaseEvent"]),
                create_events=len(categorized["CreateEvent"]),
                delete_events=len(categorized["DeleteEvent"]),
                fork_events=len(categorized["ForkEvent"]),
            )

            # Reset failure counter on success
            self.consecutive_failures = 0
            return len(tracked_commits)

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
