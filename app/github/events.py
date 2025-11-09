"""GitHub event filtering and parsing utilities."""

from typing import Any

from app.shared.models import CommitEvent


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


def parse_commits_from_events(events: list[dict[str, Any]]) -> list[CommitEvent]:
    """Parse commit objects from PushEvent list.

    Flattens commits from multiple PushEvents into a single list.
    Each PushEvent can contain up to 20 commits.

    Args:
        events: List of PushEvent dictionaries

    Returns:
        List of parsed CommitEvent objects

    Example:
        >>> events = [{"payload": {"commits": [...]}, ...}]
        >>> commits = parse_commits_from_events(events)
    """
    commits: list[CommitEvent] = []

    for event in events:
        payload = event.get("payload", {})
        event_commits = payload.get("commits", [])

        for commit in event_commits:
            commits.append(CommitEvent.from_github_event(event, commit))

    return commits
