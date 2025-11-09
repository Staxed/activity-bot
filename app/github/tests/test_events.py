"""Tests for GitHub event filtering and parsing."""

from typing import Any

from app.github.events import filter_push_events, parse_commits_from_events
from app.shared.models import CommitEvent


def test_filter_push_events() -> None:
    """Test only PushEvents returned from mixed list."""
    events = [
        {"type": "PushEvent", "id": "1"},
        {"type": "WatchEvent", "id": "2"},
        {"type": "PushEvent", "id": "3"},
    ]
    result = filter_push_events(events)
    assert len(result) == 2
    assert all(e["type"] == "PushEvent" for e in result)


def test_filter_push_events_empty() -> None:
    """Test empty list when no PushEvents."""
    events = [{"type": "WatchEvent"}, {"type": "CreateEvent"}]
    assert filter_push_events(events) == []


def test_parse_commits_from_events() -> None:
    """Test commits extracted and flattened."""
    events: list[dict[str, Any]] = [
        {
            "id": "123",
            "type": "PushEvent",
            "repo": {"name": "owner/repo"},
            "payload": {
                "ref": "refs/heads/main",
                "commits": [
                    {
                        "sha": "abc123",
                        "message": "First commit",
                        "author": {
                            "name": "User1",
                            "email": "user1@example.com",
                            "date": "2025-01-09T12:00:00Z",
                        },
                    },
                    {
                        "sha": "def456",
                        "message": "Second commit",
                        "author": {
                            "name": "User2",
                            "email": "user2@example.com",
                            "date": "2025-01-09T13:00:00Z",
                        },
                    },
                ],
            },
        }
    ]

    commits = parse_commits_from_events(events)
    assert len(commits) == 2
    assert commits[0].sha == "abc123"
    assert commits[1].sha == "def456"


def test_parse_commits_multiple_commits() -> None:
    """Test multiple commits per push handled."""
    # Create event with 20 commits
    commits_data = [
        {
            "sha": f"sha{i:02d}",
            "message": f"Commit {i}",
            "author": {
                "name": "Test User",
                "email": "test@example.com",
                "date": "2025-01-09T12:00:00Z",
            },
        }
        for i in range(20)
    ]

    events: list[dict[str, Any]] = [
        {
            "id": "123",
            "type": "PushEvent",
            "repo": {"name": "owner/repo"},
            "payload": {"ref": "refs/heads/main", "commits": commits_data},
        }
    ]

    commits = parse_commits_from_events(events)
    assert len(commits) == 20
    assert commits[0].sha == "sha00"
    assert commits[19].sha == "sha19"


def test_commit_event_from_github_event() -> None:
    """Test CommitEvent model parsing from API response."""
    event: dict[str, Any] = {
        "id": "123",
        "type": "PushEvent",
        "repo": {"name": "testowner/testrepo"},
        "payload": {"ref": "refs/heads/main"},
    }

    commit: dict[str, Any] = {
        "sha": "abc123def456",
        "message": "Fix bug in parser",
        "author": {
            "name": "Test User",
            "email": "test@example.com",
            "date": "2025-01-09T12:00:00Z",
        },
    }

    commit_event = CommitEvent.from_github_event(event, commit)

    assert commit_event.sha == "abc123def456"
    assert commit_event.short_sha == "abc123d"
    assert commit_event.author == "Test User"
    assert commit_event.author_email == "test@example.com"
    assert commit_event.message == "Fix bug in parser"
    assert commit_event.repo_owner == "testowner"
    assert commit_event.repo_name == "testrepo"
    assert commit_event.branch == "main"
    assert commit_event.url == "https://github.com/testowner/testrepo/commit/abc123def456"


def test_commit_event_branch_parsing() -> None:
    """Test branch name extracted from ref."""
    # Test simple branch
    event1: dict[str, Any] = {
        "repo": {"name": "owner/repo"},
        "payload": {"ref": "refs/heads/main"},
    }
    commit: dict[str, Any] = {
        "sha": "abc123",
        "message": "Test",
        "author": {"name": "User", "email": "user@example.com", "date": "2025-01-09T12:00:00Z"},
    }

    commit_event1 = CommitEvent.from_github_event(event1, commit)
    assert commit_event1.branch == "main"

    # Test feature branch with slashes
    event2: dict[str, Any] = {
        "repo": {"name": "owner/repo"},
        "payload": {"ref": "refs/heads/feature/awesome-feature"},
    }

    commit_event2 = CommitEvent.from_github_event(event2, commit)
    assert commit_event2.branch == "feature/awesome-feature"


def test_commit_event_url_construction() -> None:
    """Test commit URL built correctly."""
    event: dict[str, Any] = {
        "repo": {"name": "myorg/myrepo"},
        "payload": {"ref": "refs/heads/develop"},
    }
    commit: dict[str, Any] = {
        "sha": "1234567890abcdef",
        "message": "Update docs",
        "author": {
            "name": "Doc Writer",
            "email": "docs@example.com",
            "date": "2025-01-09T12:00:00Z",
        },
    }

    commit_event = CommitEvent.from_github_event(event, commit)
    assert commit_event.url == "https://github.com/myorg/myrepo/commit/1234567890abcdef"
