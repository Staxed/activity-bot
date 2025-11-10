"""GitHub event filtering and parsing utilities."""

from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.shared.models import (
    CommitEvent,
    CreateEvent,
    DeleteEvent,
    ForkEvent,
    IssuesEvent,
    PullRequestEvent,
    PullRequestReviewEvent,
    ReleaseEvent,
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
    }

    for event in events:
        event_type = event.get("type", "")
        if event_type in categorized:
            categorized[event_type].append(event)

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
            prs.append(PullRequestEvent.from_github_event(event))
        except Exception as e:
            logger.warning(
                "github.event.parse_pr_failed",
                event_id=event.get("id"),
                error=str(e),
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
