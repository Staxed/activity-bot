"""GitHub event polling service with failure tracking."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from app.core.config import Settings
from app.core.database import DatabaseClient
from app.core.logging import get_logger
from app.core.state import StateManager
from app.github.action_filter import (
    filter_issue_actions,
    filter_pr_actions,
    filter_review_states,
)
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
from app.github.repo_filter import should_track_repo
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
        usernames: list[str],
        db: DatabaseClient,
        discord_poster: "DiscordPoster | None" = None,
    ) -> None:
        """Initialize polling service with dependencies.

        Args:
            client: GitHub API client instance
            state: State manager for persistence
            settings: Application settings
            usernames: List of GitHub usernames to poll events for
            db: Database client for event storage
            discord_poster: Optional Discord poster for event notifications
        """
        self.client = client
        self.state = state
        self.settings = settings
        self.usernames = usernames
        self.db = db
        self.discord_poster = discord_poster
        self.consecutive_failures = 0
        self.running = False
        self.task: asyncio.Task[None] | None = None

    async def _fetch_recent_events(self, username: str) -> list[dict[str, Any]]:
        """Fetch GitHub events from last 12 hours.

        Fetches up to 300 events (10 pages) and filters to those within
        the last 12 hours. Relies on database deduplication via ON CONFLICT.

        This approach fixes the bug where rapid event sequences (e.g., create branch,
        commit, open PR, merge) were missed due to GitHub API indexing delays.
        By fetching a wide time window and relying on database deduplication,
        we ensure all events are eventually captured even if they appear in the
        API response after subsequent polls.

        Args:
            username: GitHub username to fetch events for

        Returns:
            List of events within 12-hour window, newest first
        """
        # Calculate 12-hour cutoff time
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=12)

        logger.info(
            "github.fetch_recent.started",
            username=username,
            cutoff_time=cutoff_time.isoformat(),
        )

        # Fetch up to 300 events (10 pages × 30 per_page)
        all_events: list[dict[str, Any]] = []

        for page in range(1, self.MAX_PAGES + 1):
            events = await self.client.fetch_user_events(username, page=page)

            if not events:
                # No more events available
                break

            all_events.extend(events)

        # Filter events to 12-hour window
        filtered_events: list[dict[str, Any]] = []

        for event in all_events:
            # Parse event timestamp
            created_at_str = event.get("created_at")
            if not created_at_str:
                logger.warning(
                    "github.fetch_recent.missing_timestamp",
                    event_id=event.get("id"),
                    event_type=event.get("type"),
                )
                continue

            try:
                # GitHub timestamps are in ISO 8601 format with 'Z' suffix
                event_time = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))

                if event_time >= cutoff_time:
                    filtered_events.append(event)
            except (ValueError, AttributeError) as e:
                logger.warning(
                    "github.fetch_recent.invalid_timestamp",
                    event_id=event.get("id"),
                    timestamp=created_at_str,
                    error=str(e),
                )
                continue

        logger.info(
            "github.fetch_recent.complete",
            username=username,
            total_fetched=len(all_events),
            within_window=len(filtered_events),
            pages_fetched=min(page, self.MAX_PAGES),
        )

        return filtered_events

    async def poll_once(self) -> int:
        """Poll GitHub events for all users and store events in database.

        Returns:
            Total number of events processed

        Raises:
            GitHubPollingError: If consecutive failures exceed threshold

        Note:
            - Loops over all tracked users
            - Applies per-user repo filtering
            - Posts all events via post_all_events
            - Success resets consecutive_failures counter
        """
        try:
            total_events = 0

            # Poll each user
            for username in self.usernames:
                user_events = await self._poll_user(username)
                total_events += user_events

            # Reset failure counter on success
            self.consecutive_failures = 0
            return total_events

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

    async def _poll_user(self, username: str) -> int:
        """Poll GitHub events for a single user using time-window approach.

        Fetches all events from last 12 hours and relies on database deduplication
        to prevent duplicate processing. This fixes the bug where rapid event
        sequences were missed due to GitHub API indexing delays.

        Args:
            username: GitHub username to poll

        Returns:
            Number of events processed for this user
        """
        logger.info(
            "github.poll.user.started",
            username=username,
            window_hours=12,
        )

        # Fetch events from last 12 hours
        events = await self._fetch_recent_events(username)

        # No events in time window
        if not events:
            logger.info("github.poll.user.no_events_in_window", username=username)
            return 0

        # Filter events by type
        categorized = filter_events_by_type(events)

        # Parse all event types in parallel
        results = await asyncio.gather(
            parse_commits_from_events(categorized["PushEvent"], self.client),
            parse_pull_requests_from_events(categorized["PullRequestEvent"]),
            parse_pr_reviews_from_events(categorized["PullRequestReviewEvent"]),
            parse_issues_from_events(categorized["IssuesEvent"]),
            parse_releases_from_events(categorized["ReleaseEvent"]),
            parse_creations_from_events(categorized["CreateEvent"]),
            parse_deletions_from_events(categorized["DeleteEvent"]),
            parse_forks_from_events(categorized["ForkEvent"]),
        )

        # Unpack results with type hints
        commits: list[Any] = results[0]  # type: ignore[assignment]
        prs: list[Any] = results[1]  # type: ignore[assignment]
        pr_reviews: list[Any] = results[2]  # type: ignore[assignment]
        issues: list[Any] = results[3]  # type: ignore[assignment]
        releases: list[Any] = results[4]  # type: ignore[assignment]
        creations: list[Any] = results[5]  # type: ignore[assignment]
        deletions: list[Any] = results[6]  # type: ignore[assignment]
        forks: list[Any] = results[7]  # type: ignore[assignment]

        # Get user-specific ignored repos
        ignored_repos = self.settings.get_user_ignored_repos(username)

        # Apply repository filtering to all event types
        def filter_by_repo(event: Any) -> bool:
            repo_full_name = f"{event.repo_owner}/{event.repo_name}"
            return should_track_repo(repo_full_name, ignored_repos)

        commits = [c for c in commits if filter_by_repo(c)]
        prs = [pr for pr in prs if filter_by_repo(pr)]
        pr_reviews = [r for r in pr_reviews if filter_by_repo(r)]
        issues = [i for i in issues if filter_by_repo(i)]
        releases = [r for r in releases if filter_by_repo(r)]
        creations = [c for c in creations if filter_by_repo(c)]
        deletions = [d for d in deletions if filter_by_repo(d)]
        # Forks use source_repo_owner/source_repo_name
        forks = [
            f
            for f in forks
            if should_track_repo(f"{f.source_repo_owner}/{f.source_repo_name}", ignored_repos)
        ]

        # Apply branch filtering to commits
        commits = [
            c
            for c in commits
            if should_track_branch(
                c.branch,
                self.settings.tracked_branches_list,
                self.settings.ignore_branch_patterns_list,
            )
        ]

        # Apply action filtering
        prs = filter_pr_actions(prs, self.settings.pr_actions_list)
        issues = filter_issue_actions(issues, self.settings.issue_actions_list)
        pr_reviews = filter_review_states(pr_reviews, self.settings.review_states_list)

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

        # Post all events to Discord
        if self.discord_poster:
            try:
                await self.discord_poster.post_all_events(
                    commits=commits,
                    prs=prs,
                    issues=issues,
                    releases=releases,
                    reviews=pr_reviews,
                    creations=creations,
                    deletions=deletions,
                    forks=forks,
                    settings=self.settings,
                )

                # Mark all events as posted
                if commits:
                    await self.db.mark_commits_posted([f"commit_{c.sha}" for c in commits])
                if prs:
                    await self.db.mark_prs_posted([pr.event_id for pr in prs])
                if issues:
                    await self.db.mark_issues_posted([i.event_id for i in issues])
                if releases:
                    await self.db.mark_releases_posted([r.event_id for r in releases])
                if pr_reviews:
                    await self.db.mark_reviews_posted([r.event_id for r in pr_reviews])
                if creations:
                    await self.db.mark_creations_posted([c.event_id for c in creations])
                if deletions:
                    await self.db.mark_deletions_posted([d.event_id for d in deletions])
                if forks:
                    await self.db.mark_forks_posted([f.event_id for f in forks])

            except Exception as e:
                logger.error(
                    "discord.post.user.error", username=username, error=str(e), exc_info=True
                )

        total_events = (
            len(commits)
            + len(prs)
            + len(issues)
            + len(releases)
            + len(pr_reviews)
            + len(creations)
            + len(deletions)
            + len(forks)
        )

        logger.info(
            "github.poll.user.complete",
            username=username,
            total_events=total_events,
            commits=len(commits),
            prs=len(prs),
            issues=len(issues),
            releases=len(releases),
            reviews=len(pr_reviews),
            creations=len(creations),
            deletions=len(deletions),
            forks=len(forks),
        )

        return total_events

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
            usernames=self.usernames,
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
