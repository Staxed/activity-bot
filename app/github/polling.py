"""GitHub event polling service with failure tracking."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.core.config import Settings
from app.core.database import DatabaseClient
from app.core.logging import get_logger
from app.core.state import StateManager
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
from app.github.events import (
    filter_events_by_type,
    parse_commit_comments_from_events,
    parse_commits_from_events,
    parse_creations_from_events,
    parse_deletions_from_events,
    parse_discussions_from_events,
    parse_forks_from_events,
    parse_issue_comments_from_events,
    parse_issues_from_events,
    parse_members_from_events,
    parse_pr_review_comments_from_events,
    parse_pr_reviews_from_events,
    parse_public_events_from_events,
    parse_pull_requests_from_events,
    parse_releases_from_events,
    parse_stars_from_events,
    parse_wiki_pages_from_events,
)
from app.github.repo_filter import should_track_repo
from app.shared.exceptions import GitHubPollingError

if TYPE_CHECKING:
    from app.discord.poster import DiscordPoster

logger = get_logger(__name__)


class GitHubPollingService:
    """Service for polling GitHub events with time-window-based deduplication.

    Uses a 12-hour time window approach instead of state-based tracking to fix
    the critical bug where rapid event sequences (PR creation, commits, merges)
    were missed due to GitHub API indexing delays.

    How it works:
    1. Every 15 minutes (configurable), fetch up to 300 events (10 pages)
    2. Filter events to those within last 12 hours
    3. Insert all filtered events into database (ON CONFLICT deduplication)
    4. Post only events marked as unposted to Discord
    5. Mark posted events to prevent duplicate Discord notifications

    This approach ensures events are seen up to 48 times (12 hours / 15 min)
    before aging out, providing high tolerance for GitHub API inconsistencies.

    Note:
    - state parameter kept for backward compatibility but not used
    - Database deduplication via ON CONFLICT (event_id) DO NOTHING is critical
    - Events may be fetched multiple times but only posted once to Discord

    Attributes:
        FAILURE_THRESHOLD: Number of consecutive failures before raising error
        MAX_PAGES: Maximum number of pages to fetch (10 pages = 300 events)
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
            state: State manager (kept for backward compatibility, not used)
            settings: Application settings
            usernames: List of GitHub usernames to poll events for
            db: Database client for event storage and deduplication
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
        cutoff_time = datetime.now(UTC) - timedelta(hours=12)

        logger.info(
            "github.fetch_recent.started",
            username=username,
            cutoff_time=cutoff_time.isoformat(),
        )

        # Fetch up to 300 events (10 pages x 30 per_page)
        all_events: list[dict[str, Any]] = []
        pages_fetched = 0

        for page in range(1, self.MAX_PAGES + 1):
            events = await self.client.fetch_user_events(username, page=page)
            pages_fetched = page

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
            pages_fetched=pages_fetched,
        )

        return filtered_events

    async def _filter_to_unposted(
        self,
        commits: list[Any],
        prs: list[Any],
        issues: list[Any],
        releases: list[Any],
        pr_reviews: list[Any],
        creations: list[Any],
        deletions: list[Any],
        forks: list[Any],
        stars: list[Any],
        issue_comments: list[Any],
        pr_review_comments: list[Any],
        commit_comments: list[Any],
        members: list[Any],
        wiki_pages: list[Any],
        public_events: list[Any],
        discussions: list[Any],
    ) -> tuple[
        list[Any],
        list[Any],
        list[Any],
        list[Any],
        list[Any],
        list[Any],
        list[Any],
        list[Any],
        list[Any],
        list[Any],
        list[Any],
        list[Any],
        list[Any],
        list[Any],
        list[Any],
        list[Any],
    ]:
        """Filter all event types to only unposted events in parallel.

        Queries the database for all unposted events of each type in parallel,
        then filters the provided event lists to only include unposted events.
        This is much faster than sequential queries (16x speedup).

        Args:
            commits: List of CommitEvent objects to filter
            prs: List of PullRequestEvent objects to filter
            issues: List of IssuesEvent objects to filter
            releases: List of ReleaseEvent objects to filter
            pr_reviews: List of PullRequestReviewEvent objects to filter
            creations: List of CreateEvent objects to filter
            deletions: List of DeleteEvent objects to filter
            forks: List of ForkEvent objects to filter
            stars: List of StarEvent objects to filter
            issue_comments: List of IssueCommentEvent objects to filter
            pr_review_comments: List of PullRequestReviewCommentEvent objects to filter
            commit_comments: List of CommitCommentEvent objects to filter
            members: List of MemberEvent objects to filter
            wiki_pages: List of WikiPageEvent objects to filter
            public_events: List of PublicEvent objects to filter
            discussions: List of DiscussionEvent objects to filter

        Returns:
            Tuple of filtered event lists in same order as inputs
        """
        # Fetch all unposted events in parallel for maximum performance
        (
            unposted_commit_shas,
            unposted_prs,
            unposted_issues,
            unposted_releases,
            unposted_reviews,
            unposted_creations,
            unposted_deletions,
            unposted_forks,
            unposted_stars,
            unposted_issue_comments,
            unposted_pr_review_comments,
            unposted_commit_comments,
            unposted_members,
            unposted_wiki_pages,
            unposted_public_events,
            unposted_discussions,
        ) = await asyncio.gather(
            self.db.get_unposted_commit_shas([c.sha for c in commits])
            if commits
            else asyncio.sleep(0, result=set()),
            self.db.get_unposted_prs(max_age_hours=12) if prs else asyncio.sleep(0, result=[]),
            self.db.get_unposted_issues(max_age_hours=12)
            if issues
            else asyncio.sleep(0, result=[]),
            self.db.get_unposted_releases(max_age_hours=12)
            if releases
            else asyncio.sleep(0, result=[]),
            self.db.get_unposted_reviews(max_age_hours=12)
            if pr_reviews
            else asyncio.sleep(0, result=[]),
            self.db.get_unposted_creations(max_age_hours=12)
            if creations
            else asyncio.sleep(0, result=[]),
            self.db.get_unposted_deletions(max_age_hours=12)
            if deletions
            else asyncio.sleep(0, result=[]),
            self.db.get_unposted_forks(max_age_hours=12) if forks else asyncio.sleep(0, result=[]),
            self.db.get_unposted_stars(max_age_hours=12) if stars else asyncio.sleep(0, result=[]),
            self.db.get_unposted_issue_comments(max_age_hours=12)
            if issue_comments
            else asyncio.sleep(0, result=[]),
            self.db.get_unposted_pr_review_comments(max_age_hours=12)
            if pr_review_comments
            else asyncio.sleep(0, result=[]),
            self.db.get_unposted_commit_comments(max_age_hours=12)
            if commit_comments
            else asyncio.sleep(0, result=[]),
            self.db.get_unposted_members(max_age_hours=12)
            if members
            else asyncio.sleep(0, result=[]),
            self.db.get_unposted_wiki_pages(max_age_hours=12)
            if wiki_pages
            else asyncio.sleep(0, result=[]),
            self.db.get_unposted_public_events(max_age_hours=12)
            if public_events
            else asyncio.sleep(0, result=[]),
            self.db.get_unposted_discussions(max_age_hours=12)
            if discussions
            else asyncio.sleep(0, result=[]),
        )

        # Filter each event type to only unposted events
        # Commits use SHA for lookup, others use event_id
        filtered_commits = [c for c in commits if c.sha in unposted_commit_shas] if commits else []

        unposted_pr_ids = {pr.event_id for pr in unposted_prs}
        filtered_prs = [pr for pr in prs if pr.event_id in unposted_pr_ids] if prs else []

        unposted_issue_ids = {i.event_id for i in unposted_issues}
        filtered_issues = [i for i in issues if i.event_id in unposted_issue_ids] if issues else []

        unposted_release_ids = {r.event_id for r in unposted_releases}
        filtered_releases = (
            [r for r in releases if r.event_id in unposted_release_ids] if releases else []
        )

        unposted_review_ids = {r.event_id for r in unposted_reviews}
        filtered_pr_reviews = (
            [r for r in pr_reviews if r.event_id in unposted_review_ids] if pr_reviews else []
        )

        unposted_creation_ids = {c.event_id for c in unposted_creations}
        filtered_creations = (
            [c for c in creations if c.event_id in unposted_creation_ids] if creations else []
        )

        unposted_deletion_ids = {d.event_id for d in unposted_deletions}
        filtered_deletions = (
            [d for d in deletions if d.event_id in unposted_deletion_ids] if deletions else []
        )

        unposted_fork_ids = {f.event_id for f in unposted_forks}
        filtered_forks = [f for f in forks if f.event_id in unposted_fork_ids] if forks else []

        unposted_star_ids = {s.event_id for s in unposted_stars}
        filtered_stars = [s for s in stars if s.event_id in unposted_star_ids] if stars else []

        unposted_issue_comment_ids = {ic.event_id for ic in unposted_issue_comments}
        filtered_issue_comments = (
            [ic for ic in issue_comments if ic.event_id in unposted_issue_comment_ids]
            if issue_comments
            else []
        )

        unposted_pr_review_comment_ids = {prc.event_id for prc in unposted_pr_review_comments}
        filtered_pr_review_comments = (
            [prc for prc in pr_review_comments if prc.event_id in unposted_pr_review_comment_ids]
            if pr_review_comments
            else []
        )

        unposted_commit_comment_ids = {cc.event_id for cc in unposted_commit_comments}
        filtered_commit_comments = (
            [cc for cc in commit_comments if cc.event_id in unposted_commit_comment_ids]
            if commit_comments
            else []
        )

        unposted_member_ids = {m.event_id for m in unposted_members}
        filtered_members = (
            [m for m in members if m.event_id in unposted_member_ids] if members else []
        )

        unposted_wiki_page_ids = {w.event_id for w in unposted_wiki_pages}
        filtered_wiki_pages = (
            [w for w in wiki_pages if w.event_id in unposted_wiki_page_ids] if wiki_pages else []
        )

        unposted_public_event_ids = {p.event_id for p in unposted_public_events}
        filtered_public_events = (
            [p for p in public_events if p.event_id in unposted_public_event_ids]
            if public_events
            else []
        )

        unposted_discussion_ids = {d.event_id for d in unposted_discussions}
        filtered_discussions = (
            [d for d in discussions if d.event_id in unposted_discussion_ids] if discussions else []
        )

        return (
            filtered_commits,
            filtered_prs,
            filtered_issues,
            filtered_releases,
            filtered_pr_reviews,
            filtered_creations,
            filtered_deletions,
            filtered_forks,
            filtered_stars,
            filtered_issue_comments,
            filtered_pr_review_comments,
            filtered_commit_comments,
            filtered_members,
            filtered_wiki_pages,
            filtered_public_events,
            filtered_discussions,
        )

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
            parse_stars_from_events(categorized["WatchEvent"]),
            parse_issue_comments_from_events(categorized["IssueCommentEvent"]),
            parse_pr_review_comments_from_events(categorized["PullRequestReviewCommentEvent"]),
            parse_commit_comments_from_events(categorized["CommitCommentEvent"]),
            parse_members_from_events(categorized["MemberEvent"]),
            parse_wiki_pages_from_events(categorized["GollumEvent"]),
            parse_public_events_from_events(categorized["PublicEvent"]),
            parse_discussions_from_events(categorized["DiscussionEvent"]),
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
        stars: list[Any] = results[8]  # type: ignore[assignment]
        issue_comments: list[Any] = results[9]  # type: ignore[assignment]
        pr_review_comments: list[Any] = results[10]  # type: ignore[assignment]
        commit_comments: list[Any] = results[11]  # type: ignore[assignment]
        members: list[Any] = results[12]  # type: ignore[assignment]
        wiki_pages: list[Any] = results[13]  # type: ignore[assignment]
        public_events: list[Any] = results[14]  # type: ignore[assignment]
        discussions: list[Any] = results[15]  # type: ignore[assignment]

        # Get user-specific ignored repos
        ignored_repos = self.settings.get_user_ignored_repos(username)

        # Apply repository filtering to all event types
        def filter_by_repo(event: Any) -> bool:  # noqa: ANN401
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
        stars = [s for s in stars if filter_by_repo(s)]
        issue_comments = [ic for ic in issue_comments if filter_by_repo(ic)]
        pr_review_comments = [prc for prc in pr_review_comments if filter_by_repo(prc)]
        commit_comments = [cc for cc in commit_comments if filter_by_repo(cc)]
        members = [m for m in members if filter_by_repo(m)]
        wiki_pages = [w for w in wiki_pages if filter_by_repo(w)]
        public_events = [p for p in public_events if filter_by_repo(p)]
        discussions = [d for d in discussions if filter_by_repo(d)]

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
        issue_comments = filter_issue_comment_actions(
            issue_comments, self.settings.issue_comment_actions_list
        )
        pr_review_comments = filter_pr_review_comment_actions(
            pr_review_comments, self.settings.pr_review_comment_actions_list
        )
        commit_comments = filter_commit_comment_actions(
            commit_comments, self.settings.commit_comment_actions_list
        )
        members = filter_member_actions(members, self.settings.member_actions_list)
        wiki_pages = filter_wiki_actions(wiki_pages, self.settings.wiki_actions_list)
        discussions = filter_discussion_actions(discussions, self.settings.discussion_actions_list)

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
            self.db.insert_stars(stars),
            self.db.insert_issue_comments(issue_comments),
            self.db.insert_pr_review_comments(pr_review_comments),
            self.db.insert_commit_comments(commit_comments),
            self.db.insert_members(members),
            self.db.insert_wiki_pages(wiki_pages),
            self.db.insert_public_events(public_events),
            self.db.insert_discussions(discussions),
        )

        # Check daily achievements if stats enabled
        if self.settings.enable_stats and commits:
            await self._check_achievements_for_user(username, self.discord_poster)

        # Filter to only unposted events before posting to Discord
        # This prevents duplicate Discord posts when events are seen in multiple poll cycles
        # within the 12-hour window. Queries are parallelized for performance.
        (
            commits,
            prs,
            issues,
            releases,
            pr_reviews,
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
        ) = await self._filter_to_unposted(
            commits=commits,
            prs=prs,
            issues=issues,
            releases=releases,
            pr_reviews=pr_reviews,
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
        )

        # Post all unposted events to Discord
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
                    stars=stars,
                    issue_comments=issue_comments,
                    pr_review_comments=pr_review_comments,
                    commit_comments=commit_comments,
                    members=members,
                    wiki_pages=wiki_pages,
                    public_events=public_events,
                    discussions=discussions,
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
                if stars:
                    await self.db.mark_stars_posted([s.event_id for s in stars])
                if issue_comments:
                    await self.db.mark_issue_comments_posted([ic.event_id for ic in issue_comments])
                if pr_review_comments:
                    await self.db.mark_pr_review_comments_posted(
                        [prc.event_id for prc in pr_review_comments]
                    )
                if commit_comments:
                    await self.db.mark_commit_comments_posted(
                        [cc.event_id for cc in commit_comments]
                    )
                if members:
                    await self.db.mark_members_posted([m.event_id for m in members])
                if wiki_pages:
                    await self.db.mark_wiki_pages_posted([w.event_id for w in wiki_pages])
                if public_events:
                    await self.db.mark_public_events_posted([p.event_id for p in public_events])
                if discussions:
                    await self.db.mark_discussions_posted([d.event_id for d in discussions])

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
            + len(stars)
            + len(issue_comments)
            + len(pr_review_comments)
            + len(commit_comments)
            + len(members)
            + len(wiki_pages)
            + len(public_events)
            + len(discussions)
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
            stars=len(stars),
            issue_comments=len(issue_comments),
            pr_review_comments=len(pr_review_comments),
            commit_comments=len(commit_comments),
            members=len(members),
            wiki_pages=len(wiki_pages),
            public_events=len(public_events),
            discussions=len(discussions),
        )

        return total_events

    async def _check_achievements_for_user(
        self, username: str, discord_poster: "DiscordPoster | None"
    ) -> None:
        """Check and announce daily achievements for a user.

        Args:
            username: GitHub username
            discord_poster: Optional Discord poster for announcements
        """
        try:
            from datetime import datetime

            import pytz

            from app.discord.stats_embeds import create_achievement_announcement_embed
            from app.stats.achievement_checker import (
                check_daily_achievements,
                get_achievement_count,
                record_achievement,
            )
            from app.stats.achievements import get_achievements

            # Check achievements for today (using configured timezone)
            try:
                tz = pytz.timezone(self.settings.stats_timezone)
            except pytz.UnknownTimeZoneError:
                tz = pytz.UTC
            today = datetime.now(tz).date()
            earned_achievements = await check_daily_achievements(self.db, username, today)

            if not earned_achievements:
                return

            logger.info(
                "achievements.earned",
                username=username,
                count=len(earned_achievements),
                date=today,
            )

            # Record and announce each achievement
            achievements_def = get_achievements()
            for earned in earned_achievements:
                # Record to database
                await record_achievement(self.db, username, earned)

                # Get total count
                total_count = await get_achievement_count(self.db, username, earned.achievement_id)

                # Announce to Discord if poster available
                if discord_poster:
                    ach = achievements_def.get(earned.achievement_id)
                    if ach:
                        embed = create_achievement_announcement_embed(
                            ach.emoji, ach.name, ach.description, total_count
                        )
                        try:
                            await discord_poster.post_custom_embed(embed)
                            logger.info(
                                "achievement.announced",
                                username=username,
                                achievement=earned.achievement_id,
                            )
                        except Exception as e:
                            logger.error(
                                "achievement.announce.failed",
                                achievement=earned.achievement_id,
                                error=str(e),
                            )

        except Exception as e:
            logger.error(
                "achievements.check.failed",
                username=username,
                error=str(e),
                exc_info=True,
            )
            # Don't fail polling if achievement check fails

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
