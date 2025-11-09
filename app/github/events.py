"""GitHub event filtering and parsing utilities."""

from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.shared.models import CommitEvent

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
