"""GitHub event filtering and parsing utilities."""

from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.shared.models import (
    CommitCommentEvent,
    CommitEvent,
    CreateEvent,
    DeleteEvent,
    DiscussionEvent,
    ForkEvent,
    GollumEvent,
    IssueCommentEvent,
    IssuesEvent,
    MemberEvent,
    PublicEvent,
    PullRequestEvent,
    PullRequestReviewCommentEvent,
    PullRequestReviewEvent,
    ReleaseEvent,
    WatchEvent,
)

if TYPE_CHECKING:
    from app.github.client import GitHubClient

logger = get_logger(__name__)


def filter_push_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter events to only include PushEvents.

    Args:
        events: List of GitHub event dictionaries

    Returns:
        List of PushEvent dictionaries only

    Example:
        >>> events = [
        ...     {"type": "PushEvent", "id": "1"},
        ...     {"type": "WatchEvent", "id": "2"},
        ...     {"type": "PushEvent", "id": "3"}
        ... ]
        >>> push_events = filter_push_events(events)
        >>> len(push_events)
        2
    """
    return [e for e in events if e.get("type") == "PushEvent"]


async def parse_commits_from_events(
    events: list[dict[str, Any]], client: "GitHubClient"
) -> list[CommitEvent]:
    """Parse commit objects from PushEvent list.

    Flattens commits from multiple PushEvents into a single list.
    Each PushEvent can contain up to 20 commits inline, but some events
    may omit commits. For those, we fetch commits via comparison API.

    Args:
        events: List of PushEvent dictionaries
        client: GitHub API client for fetching missing commits

    Returns:
        List of parsed CommitEvent objects

    Example:
        >>> events = [{"payload": {"commits": [...]}, ...}]
        >>> commits = await parse_commits_from_events(events, client)
    """
    commits: list[CommitEvent] = []

    for event in events:
        payload = event.get("payload", {})
        event_commits = payload.get("commits", [])

        # If commits are present inline, use them
        if event_commits:
            for commit in event_commits:
                commits.append(CommitEvent.from_github_event(event, commit))
        else:
            # Commits not included, fetch via comparison API
            repo_name = event["repo"]["name"]  # Format: "owner/repo"
            owner, repo = repo_name.split("/")
            base_sha = payload.get("before")
            head_sha = payload.get("head")

            if not base_sha or not head_sha:
                logger.warning(
                    "github.event.missing_shas",
                    event_id=event["id"],
                    repo=repo_name,
                )
                continue

            logger.info(
                "github.event.fetching_commits",
                event_id=event["id"],
                repo=repo_name,
                base=base_sha[:7],
                head=head_sha[:7],
            )

            # Fetch commits via comparison API
            try:
                comparison_commits = await client.compare_commits(owner, repo, base_sha, head_sha)

                for commit in comparison_commits:
                    # Convert comparison API format to event format
                    commits.append(CommitEvent.from_github_comparison(event, commit))

                logger.info(
                    "github.event.fetched_commits",
                    event_id=event["id"],
                    repo=repo_name,
                    commits_count=len(comparison_commits),
                )
            except Exception as e:
                logger.error(
                    "github.event.fetch_failed",
                    event_id=event["id"],
                    repo=repo_name,
                    error=str(e),
                    exc_info=True,
                )

    return commits


def filter_events_by_type(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Filter events into categories by type.

    Args:
        events: List of GitHub event dictionaries

    Returns:
        Dictionary mapping event type to list of events
        Keys: PushEvent, PullRequestEvent, PullRequestReviewEvent, IssuesEvent,
              ReleaseEvent, CreateEvent, DeleteEvent, ForkEvent

    Example:
        >>> events = [{"type": "PushEvent"}, {"type": "IssuesEvent"}]
        >>> categorized = filter_events_by_type(events)
        >>> categorized["PushEvent"]
        [{"type": "PushEvent"}]
    """
    categorized: dict[str, list[dict[str, Any]]] = {
        "PushEvent": [],
        "PullRequestEvent": [],
        "PullRequestReviewEvent": [],
        "IssuesEvent": [],
        "ReleaseEvent": [],
        "CreateEvent": [],
        "DeleteEvent": [],
        "ForkEvent": [],
        "WatchEvent": [],
        "IssueCommentEvent": [],
        "PullRequestReviewCommentEvent": [],
        "CommitCommentEvent": [],
        "MemberEvent": [],
        "GollumEvent": [],
        "PublicEvent": [],
        "DiscussionEvent": [],
    }

    tracked_types = set(categorized.keys())

    for event in events:
        event_type = event.get("type", "")
        event_id = event.get("id", "unknown")

        if event_type in categorized:
            categorized[event_type].append(event)
        elif event_type:
            # Log unknown event types for debugging
            logger.debug(
                "github.event.unknown_type",
                event_id=event_id,
                event_type=event_type,
            )

    return categorized


async def parse_pull_requests_from_events(events: list[dict[str, Any]]) -> list[PullRequestEvent]:
    """Parse PullRequestEvent list into PullRequestEvent models.

    Args:
        events: List of PullRequestEvent dictionaries

    Returns:
        List of parsed PullRequestEvent objects
    """
    prs: list[PullRequestEvent] = []

    for event in events:
        try:
            # Validate event structure before parsing
            if not event.get("payload"):
                logger.warning(
                    "github.event.parse_pr_failed",
                    event_id=event.get("id"),
                    error="Missing payload",
                )
                continue

            payload = event.get("payload", {})
            if not payload.get("pull_request"):
                logger.warning(
                    "github.event.parse_pr_failed",
                    event_id=event.get("id"),
                    error="Missing pull_request in payload",
                )
                continue

            prs.append(PullRequestEvent.from_github_event(event))
        except KeyError as e:
            logger.warning(
                "github.event.parse_pr_failed",
                event_id=event.get("id"),
                error=f"Missing required field: {e}",
                exc_info=True,
            )
        except Exception as e:
            logger.warning(
                "github.event.parse_pr_failed",
                event_id=event.get("id"),
                error=str(e),
                exc_info=True,
            )

    return prs


async def parse_pr_reviews_from_events(
    events: list[dict[str, Any]],
) -> list[PullRequestReviewEvent]:
    """Parse PullRequestReviewEvent list into models."""
    reviews: list[PullRequestReviewEvent] = []

    for event in events:
        try:
            reviews.append(PullRequestReviewEvent.from_github_event(event))
        except Exception as e:
            logger.warning(
                "github.event.parse_pr_review_failed",
                event_id=event.get("id"),
                error=str(e),
            )

    return reviews


async def parse_issues_from_events(events: list[dict[str, Any]]) -> list[IssuesEvent]:
    """Parse IssuesEvent list into IssuesEvent models."""
    issues: list[IssuesEvent] = []

    for event in events:
        try:
            issues.append(IssuesEvent.from_github_event(event))
        except Exception as e:
            logger.warning(
                "github.event.parse_issue_failed",
                event_id=event.get("id"),
                error=str(e),
            )

    return issues


async def parse_releases_from_events(events: list[dict[str, Any]]) -> list[ReleaseEvent]:
    """Parse ReleaseEvent list into ReleaseEvent models."""
    releases: list[ReleaseEvent] = []

    for event in events:
        try:
            releases.append(ReleaseEvent.from_github_event(event))
        except Exception as e:
            logger.warning(
                "github.event.parse_release_failed",
                event_id=event.get("id"),
                error=str(e),
            )

    return releases


async def parse_creations_from_events(events: list[dict[str, Any]]) -> list[CreateEvent]:
    """Parse CreateEvent list into CreateEvent models."""
    creations: list[CreateEvent] = []

    for event in events:
        try:
            creations.append(CreateEvent.from_github_event(event))
        except Exception as e:
            logger.warning(
                "github.event.parse_creation_failed",
                event_id=event.get("id"),
                error=str(e),
            )

    return creations


async def parse_deletions_from_events(events: list[dict[str, Any]]) -> list[DeleteEvent]:
    """Parse DeleteEvent list into DeleteEvent models."""
    deletions: list[DeleteEvent] = []

    for event in events:
        try:
            deletions.append(DeleteEvent.from_github_event(event))
        except Exception as e:
            logger.warning(
                "github.event.parse_deletion_failed",
                event_id=event.get("id"),
                error=str(e),
            )

    return deletions


async def parse_forks_from_events(events: list[dict[str, Any]]) -> list[ForkEvent]:
    """Parse ForkEvent list into ForkEvent models."""
    forks: list[ForkEvent] = []

    for event in events:
        try:
            forks.append(ForkEvent.from_github_event(event))
        except Exception as e:
            logger.warning(
                "github.event.parse_fork_failed",
                event_id=event.get("id"),
                error=str(e),
            )

    return forks


async def parse_stars_from_events(events: list[dict[str, Any]]) -> list[WatchEvent]:
    """Parse WatchEvent from GitHub events.

    Args:
        events: List of raw GitHub event dictionaries

    Returns:
        List of parsed WatchEvent objects
    """
    star_events = []
    for event in events:
        if event.get("type") == "WatchEvent":
            try:
                star_event = WatchEvent.from_github_event(event)
                star_events.append(star_event)
            except Exception as e:
                logger.warning(
                    "github.parse.star.failed",
                    event_id=event.get("id"),
                    error=str(e),
                )
                continue

    logger.info("github.parse.star.success", count=len(star_events))
    return star_events


async def parse_issue_comments_from_events(events: list[dict[str, Any]]) -> list[IssueCommentEvent]:
    """Parse IssueCommentEvent from GitHub events.

    Args:
        events: List of raw GitHub event dictionaries

    Returns:
        List of parsed IssueCommentEvent objects
    """
    issue_comment_events = []
    for event in events:
        if event.get("type") == "IssueCommentEvent":
            try:
                issue_comment_event = IssueCommentEvent.from_github_event(event)
                issue_comment_events.append(issue_comment_event)
            except Exception as e:
                logger.warning(
                    "github.parse.issue_comment.failed",
                    event_id=event.get("id"),
                    error=str(e),
                )
                continue

    logger.info("github.parse.issue_comment.success", count=len(issue_comment_events))
    return issue_comment_events


async def parse_pr_review_comments_from_events(
    events: list[dict[str, Any]],
) -> list[PullRequestReviewCommentEvent]:
    """Parse PullRequestReviewCommentEvent from GitHub events.

    Args:
        events: List of raw GitHub event dictionaries

    Returns:
        List of parsed PullRequestReviewCommentEvent objects
    """
    pr_review_comment_events = []
    for event in events:
        if event.get("type") == "PullRequestReviewCommentEvent":
            try:
                pr_review_comment_event = PullRequestReviewCommentEvent.from_github_event(event)
                pr_review_comment_events.append(pr_review_comment_event)
            except Exception as e:
                logger.warning(
                    "github.parse.pr_review_comment.failed",
                    event_id=event.get("id"),
                    error=str(e),
                )
                continue

    logger.info("github.parse.pr_review_comment.success", count=len(pr_review_comment_events))
    return pr_review_comment_events


async def parse_commit_comments_from_events(
    events: list[dict[str, Any]],
) -> list[CommitCommentEvent]:
    """Parse CommitCommentEvent from GitHub events.

    Args:
        events: List of raw GitHub event dictionaries

    Returns:
        List of parsed CommitCommentEvent objects
    """
    commit_comment_events = []
    for event in events:
        if event.get("type") == "CommitCommentEvent":
            try:
                commit_comment_event = CommitCommentEvent.from_github_event(event)
                commit_comment_events.append(commit_comment_event)
            except Exception as e:
                logger.warning(
                    "github.parse.commit_comment.failed",
                    event_id=event.get("id"),
                    error=str(e),
                )
                continue

    logger.info("github.parse.commit_comment.success", count=len(commit_comment_events))
    return commit_comment_events


async def parse_members_from_events(events: list[dict[str, Any]]) -> list[MemberEvent]:
    """Parse MemberEvent from GitHub events.

    Args:
        events: List of raw GitHub event dictionaries

    Returns:
        List of parsed MemberEvent objects
    """
    member_events = []
    for event in events:
        if event.get("type") == "MemberEvent":
            try:
                member_event = MemberEvent.from_github_event(event)
                member_events.append(member_event)
            except Exception as e:
                logger.warning(
                    "github.parse.member.failed",
                    event_id=event.get("id"),
                    error=str(e),
                )
                continue

    logger.info("github.parse.member.success", count=len(member_events))
    return member_events


async def parse_wiki_pages_from_events(events: list[dict[str, Any]]) -> list[GollumEvent]:
    """Parse GollumEvent from GitHub events.

    Args:
        events: List of raw GitHub event dictionaries

    Returns:
        List of parsed GollumEvent objects
    """
    wiki_page_events = []
    for event in events:
        if event.get("type") == "GollumEvent":
            try:
                wiki_page_event = GollumEvent.from_github_event(event)
                wiki_page_events.append(wiki_page_event)
            except Exception as e:
                logger.warning(
                    "github.parse.wiki_page.failed",
                    event_id=event.get("id"),
                    error=str(e),
                )
                continue

    logger.info("github.parse.wiki_page.success", count=len(wiki_page_events))
    return wiki_page_events


async def parse_public_events_from_events(events: list[dict[str, Any]]) -> list[PublicEvent]:
    """Parse PublicEvent from GitHub events.

    Args:
        events: List of raw GitHub event dictionaries

    Returns:
        List of parsed PublicEvent objects
    """
    public_events = []
    for event in events:
        if event.get("type") == "PublicEvent":
            try:
                public_event = PublicEvent.from_github_event(event)
                public_events.append(public_event)
            except Exception as e:
                logger.warning(
                    "github.parse.public.failed",
                    event_id=event.get("id"),
                    error=str(e),
                )
                continue

    logger.info("github.parse.public.success", count=len(public_events))
    return public_events


async def parse_discussions_from_events(events: list[dict[str, Any]]) -> list[DiscussionEvent]:
    """Parse DiscussionEvent from GitHub events.

    Args:
        events: List of raw GitHub event dictionaries

    Returns:
        List of parsed DiscussionEvent objects
    """
    discussion_events = []
    for event in events:
        if event.get("type") == "DiscussionEvent":
            try:
                discussion_event = DiscussionEvent.from_github_event(event)
                discussion_events.append(discussion_event)
            except Exception as e:
                logger.warning(
                    "github.parse.discussion.failed",
                    event_id=event.get("id"),
                    error=str(e),
                )
                continue

    logger.info("github.parse.discussion.success", count=len(discussion_events))
    return discussion_events
