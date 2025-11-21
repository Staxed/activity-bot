"""Data models for Activity Bot."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CommitEvent(BaseModel):
    """Internal representation of a GitHub commit event.

    Attributes:
        sha: Full commit SHA hash
        short_sha: 7-character short SHA for display
        author: Commit author name
        author_email: Commit author email address
        author_avatar_url: GitHub avatar URL for the author
        author_username: GitHub username for profile link
        message: Commit message (first line only)
        message_body: Full commit message including body
        repo_owner: Repository owner username
        repo_name: Repository name
        timestamp: Commit timestamp
        url: GitHub commit URL
        branch: Branch name (extracted from ref)
        is_public: Whether the repository is public
    """

    sha: str = Field(..., description="Full commit SHA")
    short_sha: str = Field(..., description="7-character short SHA")
    author: str = Field(..., description="Commit author name")
    author_email: str = Field(..., description="Commit author email")
    author_avatar_url: str = Field(..., description="GitHub avatar URL")
    author_username: str = Field(..., description="GitHub username")
    message: str = Field(..., description="Commit message (first line)")
    message_body: str = Field(..., description="Full commit message")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    timestamp: datetime = Field(..., description="Commit timestamp")
    url: str = Field(..., description="GitHub commit URL")
    branch: str = Field(..., description="Branch name")
    is_public: bool = Field(..., description="Whether the repository is public")

    @field_validator("timestamp")
    @classmethod
    def ensure_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure timestamp is timezone-aware, adding UTC if naive."""
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v

    @classmethod
    def from_github_event(cls, event: dict[str, Any], commit: dict[str, Any]) -> "CommitEvent":
        """Parse GitHub API event response into CommitEvent.

        Args:
            event: GitHub PushEvent from Events API
            commit: Individual commit object from event payload

        Returns:
            CommitEvent instance with parsed data

        Example:
            >>> event = {"repo": {"name": "owner/repo"}, "payload": {"ref": "refs/heads/main"}}
            >>> commit = {"sha": "abc123...", "message": "Fix bug", "author": {...}}
            >>> commit_event = CommitEvent.from_github_event(event, commit)
        """
        # Parse repo owner and name from "owner/repo" format
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        # Extract branch name from ref (e.g., "refs/heads/main" -> "main")
        ref = event["payload"]["ref"]
        branch = ref.replace("refs/heads/", "")

        # Split commit message into first line and body
        message_lines = commit["message"].split("\n", 1)
        message = message_lines[0]
        message_body = commit["message"]

        # Build GitHub commit URL
        sha = commit["sha"]
        url = f"https://github.com/{repo_owner}/{repo_name}/commit/{sha}"

        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = commit["author"]["date"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        # Get actor info from event (GitHub user who pushed)
        actor = event.get("actor", {})
        author_username = actor.get("login", commit["author"]["name"])
        author_avatar_url = actor.get("avatar_url", "")

        return cls(
            sha=sha,
            short_sha=sha[:7],
            author=commit["author"]["name"],
            author_email=commit["author"]["email"],
            author_avatar_url=author_avatar_url,
            author_username=author_username,
            message=message,
            message_body=message_body,
            repo_owner=repo_owner,
            repo_name=repo_name,
            timestamp=timestamp,
            url=url,
            branch=branch,
            is_public=event.get("public", True),
        )

    @classmethod
    def from_github_comparison(cls, event: dict[str, Any], commit: dict[str, Any]) -> "CommitEvent":
        """Parse GitHub comparison API commit into CommitEvent.

        Used when PushEvent doesn't include inline commits and we fetch
        them via the comparison API (/repos/{owner}/{repo}/compare/{base}...{head}).

        Args:
            event: GitHub PushEvent from Events API (for repo/branch context)
            commit: Individual commit object from comparison API

        Returns:
            CommitEvent instance with parsed data

        Example:
            >>> event = {"repo": {"name": "owner/repo"}, "payload": {"ref": "refs/heads/main"}}
            >>> commit = {"sha": "abc123...", "commit": {"message": "Fix", "author": {...}}}
            >>> commit_event = CommitEvent.from_github_comparison(event, commit)
        """
        # Parse repo owner and name from "owner/repo" format
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        # Extract branch name from ref (e.g., "refs/heads/main" -> "main")
        ref = event["payload"]["ref"]
        branch = ref.replace("refs/heads/", "")

        # Comparison API has nested commit object
        commit_data = commit["commit"]

        # Split commit message into first line and body
        message_lines = commit_data["message"].split("\n", 1)
        message = message_lines[0]
        message_body = commit_data["message"]

        # Build GitHub commit URL
        sha = commit["sha"]
        url = commit.get("html_url") or f"https://github.com/{repo_owner}/{repo_name}/commit/{sha}"

        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = commit_data["author"]["date"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        # Get actor info from event (GitHub user who pushed)
        actor = event.get("actor", {})
        author_username = actor.get("login", commit_data["author"]["name"])
        author_avatar_url = actor.get("avatar_url", "")

        return cls(
            sha=sha,
            short_sha=sha[:7],
            author=commit_data["author"]["name"],
            author_email=commit_data["author"]["email"],
            author_avatar_url=author_avatar_url,
            author_username=author_username,
            message=message,
            message_body=message_body,
            repo_owner=repo_owner,
            repo_name=repo_name,
            timestamp=timestamp,
            url=url,
            branch=branch,
            is_public=event.get("public", True),
        )


class PullRequestEvent(BaseModel):
    """Internal representation of a GitHub pull request event.

    Attributes:
        event_id: GitHub event ID for deduplication
        pr_number: Pull request number
        action: Action performed (opened, closed, reopened, etc.)
        title: Pull request title
        state: PR state (open, closed)
        merged: Whether the PR was merged
        author_username: GitHub username who created the PR
        author_avatar_url: GitHub avatar URL
        repo_owner: Repository owner username
        repo_name: Repository name
        is_public: Whether the repository is public
        url: GitHub PR URL
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    pr_number: int = Field(..., description="Pull request number")
    action: str = Field(..., description="Action performed")
    title: str | None = Field(None, description="PR title")
    state: str = Field(..., description="PR state")
    merged: bool = Field(False, description="Whether merged")
    author_username: str = Field(..., description="PR author username")
    author_avatar_url: str = Field(..., description="Author avatar URL")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    url: str | None = Field(None, description="GitHub PR URL")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "PullRequestEvent":
        """Parse GitHub PullRequestEvent into PullRequestEvent model.

        Args:
            event: GitHub PullRequestEvent from Events API

        Returns:
            PullRequestEvent instance with parsed data

        Example:
            >>> event = {"id": "123", "type": "PullRequestEvent", "payload": {...}}
            >>> pr_event = PullRequestEvent.from_github_event(event)
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        payload = event["payload"]
        pr = payload["pull_request"]

        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return cls(
            event_id=event["id"],
            pr_number=pr["number"],
            action=payload["action"],
            title=pr.get("title"),
            state=pr["state"],
            merged=pr.get("merged", False),
            author_username=event["actor"]["login"],
            author_avatar_url=event["actor"]["avatar_url"],
            repo_owner=repo_owner,
            repo_name=repo_name,
            is_public=event.get("public", True),
            url=pr.get("html_url"),
            event_timestamp=timestamp,
        )


class PullRequestReviewEvent(BaseModel):
    """Internal representation of a GitHub pull request review event.

    Attributes:
        event_id: GitHub event ID for deduplication
        pr_number: Pull request number
        action: Action performed (submitted, edited, dismissed)
        review_state: Review state (approved, changes_requested, commented)
        reviewer_username: GitHub username who reviewed
        reviewer_avatar_url: GitHub avatar URL
        repo_owner: Repository owner username
        repo_name: Repository name
        is_public: Whether the repository is public
        url: GitHub PR URL
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    pr_number: int = Field(..., description="Pull request number")
    action: str = Field(..., description="Action performed")
    review_state: str = Field(..., description="Review state")
    reviewer_username: str = Field(..., description="Reviewer username")
    reviewer_avatar_url: str = Field(..., description="Reviewer avatar URL")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    url: str | None = Field(None, description="GitHub PR URL")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "PullRequestReviewEvent":
        """Parse GitHub PullRequestReviewEvent into model.

        Args:
            event: GitHub PullRequestReviewEvent from Events API

        Returns:
            PullRequestReviewEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        payload = event["payload"]
        pr = payload["pull_request"]
        review = payload["review"]

        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return cls(
            event_id=event["id"],
            pr_number=pr["number"],
            action=payload["action"],
            review_state=review["state"],
            reviewer_username=event["actor"]["login"],
            reviewer_avatar_url=event["actor"]["avatar_url"],
            repo_owner=repo_owner,
            repo_name=repo_name,
            is_public=event.get("public", True),
            url=pr.get("html_url"),
            event_timestamp=timestamp,
        )


class IssuesEvent(BaseModel):
    """Internal representation of a GitHub issues event.

    Attributes:
        event_id: GitHub event ID for deduplication
        issue_number: Issue number
        action: Action performed (opened, closed, reopened, etc.)
        title: Issue title
        state: Issue state (open, closed)
        author_username: GitHub username who created the issue
        author_avatar_url: GitHub avatar URL
        repo_owner: Repository owner username
        repo_name: Repository name
        is_public: Whether the repository is public
        url: GitHub issue URL
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    issue_number: int = Field(..., description="Issue number")
    action: str = Field(..., description="Action performed")
    title: str | None = Field(None, description="Issue title")
    state: str = Field(..., description="Issue state")
    author_username: str = Field(..., description="Issue author username")
    author_avatar_url: str = Field(..., description="Author avatar URL")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    url: str | None = Field(None, description="GitHub issue URL")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "IssuesEvent":
        """Parse GitHub IssuesEvent into model.

        Args:
            event: GitHub IssuesEvent from Events API

        Returns:
            IssuesEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        payload = event["payload"]
        issue = payload["issue"]

        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return cls(
            event_id=event["id"],
            issue_number=issue["number"],
            action=payload["action"],
            title=issue.get("title"),
            state=issue["state"],
            author_username=event["actor"]["login"],
            author_avatar_url=event["actor"]["avatar_url"],
            repo_owner=repo_owner,
            repo_name=repo_name,
            is_public=event.get("public", True),
            url=issue.get("html_url"),
            event_timestamp=timestamp,
        )


class ReleaseEvent(BaseModel):
    """Internal representation of a GitHub release event.

    Attributes:
        event_id: GitHub event ID for deduplication
        tag_name: Release tag name
        release_name: Release name (optional)
        is_prerelease: Whether this is a prerelease
        is_draft: Whether this is a draft
        author_username: GitHub username who created the release
        author_avatar_url: GitHub avatar URL
        repo_owner: Repository owner username
        repo_name: Repository name
        is_public: Whether the repository is public
        url: GitHub release URL
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    tag_name: str = Field(..., description="Release tag name")
    release_name: str | None = Field(None, description="Release name")
    is_prerelease: bool = Field(False, description="Whether prerelease")
    is_draft: bool = Field(False, description="Whether draft")
    author_username: str = Field(..., description="Release author username")
    author_avatar_url: str = Field(..., description="Author avatar URL")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    url: str | None = Field(None, description="GitHub release URL")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "ReleaseEvent":
        """Parse GitHub ReleaseEvent into model.

        Args:
            event: GitHub ReleaseEvent from Events API

        Returns:
            ReleaseEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        payload = event["payload"]
        release = payload["release"]

        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return cls(
            event_id=event["id"],
            tag_name=release["tag_name"],
            release_name=release.get("name"),
            is_prerelease=release.get("prerelease", False),
            is_draft=release.get("draft", False),
            author_username=event["actor"]["login"],
            author_avatar_url=event["actor"]["avatar_url"],
            repo_owner=repo_owner,
            repo_name=repo_name,
            is_public=event.get("public", True),
            url=release.get("html_url"),
            event_timestamp=timestamp,
        )


class CreateEvent(BaseModel):
    """Internal representation of a GitHub create event.

    Attributes:
        event_id: GitHub event ID for deduplication
        ref_type: Type of ref created (repository, branch, tag)
        ref_name: Name of ref created (NULL for repository)
        author_username: GitHub username who created the ref
        author_avatar_url: GitHub avatar URL
        repo_owner: Repository owner username
        repo_name: Repository name
        is_public: Whether the repository is public
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    ref_type: str = Field(..., description="Type of ref (repository, branch, tag)")
    ref_name: str | None = Field(None, description="Name of ref (NULL for repository)")
    author_username: str = Field(..., description="Author username")
    author_avatar_url: str = Field(..., description="Author avatar URL")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "CreateEvent":
        """Parse GitHub CreateEvent into model.

        Args:
            event: GitHub CreateEvent from Events API

        Returns:
            CreateEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        payload = event["payload"]
        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return cls(
            event_id=event["id"],
            ref_type=payload["ref_type"],
            ref_name=payload.get("ref"),
            author_username=event["actor"]["login"],
            author_avatar_url=event["actor"]["avatar_url"],
            repo_owner=repo_owner,
            repo_name=repo_name,
            is_public=event.get("public", True),
            event_timestamp=timestamp,
        )


class DeleteEvent(BaseModel):
    """Internal representation of a GitHub delete event.

    Attributes:
        event_id: GitHub event ID for deduplication
        ref_type: Type of ref deleted (branch, tag)
        ref_name: Name of ref deleted
        author_username: GitHub username who deleted the ref
        author_avatar_url: GitHub avatar URL
        repo_owner: Repository owner username
        repo_name: Repository name
        is_public: Whether the repository is public
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    ref_type: str = Field(..., description="Type of ref (branch, tag)")
    ref_name: str = Field(..., description="Name of ref deleted")
    author_username: str = Field(..., description="Author username")
    author_avatar_url: str = Field(..., description="Author avatar URL")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "DeleteEvent":
        """Parse GitHub DeleteEvent into model.

        Args:
            event: GitHub DeleteEvent from Events API

        Returns:
            DeleteEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        payload = event["payload"]
        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return cls(
            event_id=event["id"],
            ref_type=payload["ref_type"],
            ref_name=payload["ref"],
            author_username=event["actor"]["login"],
            author_avatar_url=event["actor"]["avatar_url"],
            repo_owner=repo_owner,
            repo_name=repo_name,
            is_public=event.get("public", True),
            event_timestamp=timestamp,
        )


class ForkEvent(BaseModel):
    """Internal representation of a GitHub fork event.

    Attributes:
        event_id: GitHub event ID for deduplication
        forker_username: GitHub username who forked
        forker_avatar_url: Forker avatar URL
        source_repo_owner: Source repository owner
        source_repo_name: Source repository name
        fork_repo_owner: Fork repository owner
        fork_repo_name: Fork repository name
        is_public: Whether the repository is public
        fork_url: Fork repository URL
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    forker_username: str = Field(..., description="Forker username")
    forker_avatar_url: str = Field(..., description="Forker avatar URL")
    source_repo_owner: str = Field(..., description="Source repository owner")
    source_repo_name: str = Field(..., description="Source repository name")
    fork_repo_owner: str = Field(..., description="Fork repository owner")
    fork_repo_name: str = Field(..., description="Fork repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    fork_url: str | None = Field(None, description="Fork repository URL")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "ForkEvent":
        """Parse GitHub ForkEvent into model.

        Args:
            event: GitHub ForkEvent from Events API

        Returns:
            ForkEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        source_repo_owner, source_repo_name = repo_full_name.split("/", 1)

        payload = event["payload"]
        forkee = payload["forkee"]

        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return cls(
            event_id=event["id"],
            forker_username=event["actor"]["login"],
            forker_avatar_url=event["actor"]["avatar_url"],
            source_repo_owner=source_repo_owner,
            source_repo_name=source_repo_name,
            fork_repo_owner=forkee["owner"]["login"],
            fork_repo_name=forkee["name"],
            is_public=event.get("public", True),
            fork_url=forkee.get("html_url"),
            event_timestamp=timestamp,
        )


class WatchEvent(BaseModel):
    """Internal representation of a GitHub watch (star) event.

    Attributes:
        event_id: GitHub event ID for deduplication
        stargazer_username: GitHub username who starred the repo
        stargazer_avatar_url: GitHub avatar URL
        repo_owner: Repository owner username
        repo_name: Repository name
        is_public: Whether the repository is public
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    stargazer_username: str = Field(..., description="Stargazer username")
    stargazer_avatar_url: str = Field(..., description="Stargazer avatar URL")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "WatchEvent":
        """Parse GitHub WatchEvent into model.

        Args:
            event: GitHub WatchEvent from Events API

        Returns:
            WatchEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return cls(
            event_id=event["id"],
            stargazer_username=event["actor"]["login"],
            stargazer_avatar_url=event["actor"]["avatar_url"],
            repo_owner=repo_owner,
            repo_name=repo_name,
            is_public=event.get("public", True),
            event_timestamp=timestamp,
        )


class IssueCommentEvent(BaseModel):
    """Internal representation of a GitHub issue comment event.

    Attributes:
        event_id: GitHub event ID for deduplication
        action: Action performed (created, edited, deleted)
        issue_number: Issue number
        issue_title: Issue title
        commenter_username: GitHub username who commented
        commenter_avatar_url: GitHub avatar URL
        comment_body: Comment text (truncated to 500 chars)
        repo_owner: Repository owner username
        repo_name: Repository name
        is_public: Whether the repository is public
        url: Comment URL
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    action: str = Field(..., description="Action (created, edited, deleted)")
    issue_number: int = Field(..., description="Issue number")
    issue_title: str | None = Field(None, description="Issue title")
    commenter_username: str = Field(..., description="Commenter username")
    commenter_avatar_url: str = Field(..., description="Commenter avatar URL")
    comment_body: str | None = Field(None, description="Comment text (truncated to 500 chars)")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    url: str | None = Field(None, description="Comment URL")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "IssueCommentEvent":
        """Parse GitHub IssueCommentEvent into model.

        Args:
            event: GitHub IssueCommentEvent from Events API

        Returns:
            IssueCommentEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        payload = event["payload"]
        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        # Truncate comment body to 500 chars
        comment_body = payload.get("comment", {}).get("body")
        if comment_body and len(comment_body) > 500:
            comment_body = comment_body[:500]

        return cls(
            event_id=event["id"],
            action=payload["action"],
            issue_number=payload["issue"]["number"],
            issue_title=payload["issue"].get("title"),
            commenter_username=event["actor"]["login"],
            commenter_avatar_url=event["actor"]["avatar_url"],
            comment_body=comment_body,
            repo_owner=repo_owner,
            repo_name=repo_name,
            is_public=event.get("public", True),
            url=payload.get("comment", {}).get("html_url"),
            event_timestamp=timestamp,
        )


class PullRequestReviewCommentEvent(BaseModel):
    """Internal representation of a GitHub PR review comment event.

    Attributes:
        event_id: GitHub event ID for deduplication
        action: Action performed (created, edited, deleted)
        pr_number: Pull request number
        pr_title: Pull request title
        commenter_username: GitHub username who commented
        commenter_avatar_url: GitHub avatar URL
        comment_body: Comment text (truncated to 500 chars)
        file_path: File path the comment is on
        repo_owner: Repository owner username
        repo_name: Repository name
        is_public: Whether the repository is public
        url: Comment URL
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    action: str = Field(..., description="Action (created, edited, deleted)")
    pr_number: int = Field(..., description="PR number")
    pr_title: str | None = Field(None, description="PR title")
    commenter_username: str = Field(..., description="Commenter username")
    commenter_avatar_url: str = Field(..., description="Commenter avatar URL")
    comment_body: str | None = Field(None, description="Comment text (truncated to 500 chars)")
    file_path: str | None = Field(None, description="File path commented on")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    url: str | None = Field(None, description="Comment URL")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "PullRequestReviewCommentEvent":
        """Parse GitHub PullRequestReviewCommentEvent into model.

        Args:
            event: GitHub PullRequestReviewCommentEvent from Events API

        Returns:
            PullRequestReviewCommentEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        payload = event["payload"]
        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        # Truncate comment body to 500 chars
        comment_body = payload.get("comment", {}).get("body")
        if comment_body and len(comment_body) > 500:
            comment_body = comment_body[:500]

        return cls(
            event_id=event["id"],
            action=payload["action"],
            pr_number=payload["pull_request"]["number"],
            pr_title=payload["pull_request"].get("title"),
            commenter_username=event["actor"]["login"],
            commenter_avatar_url=event["actor"]["avatar_url"],
            comment_body=comment_body,
            file_path=payload.get("comment", {}).get("path"),
            repo_owner=repo_owner,
            repo_name=repo_name,
            is_public=event.get("public", True),
            url=payload.get("comment", {}).get("html_url"),
            event_timestamp=timestamp,
        )


class CommitCommentEvent(BaseModel):
    """Internal representation of a GitHub commit comment event.

    Attributes:
        event_id: GitHub event ID for deduplication
        action: Action performed (created)
        commit_sha: Full commit SHA
        short_sha: Short (7-char) commit SHA
        commenter_username: GitHub username who commented
        commenter_avatar_url: GitHub avatar URL
        comment_body: Comment text (truncated to 500 chars)
        file_path: File path the comment is on
        repo_owner: Repository owner username
        repo_name: Repository name
        is_public: Whether the repository is public
        url: Comment URL
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    action: str = Field(..., description="Action (created)")
    commit_sha: str = Field(..., description="Full commit SHA")
    short_sha: str = Field(..., description="Short (7-char) commit SHA")
    commenter_username: str = Field(..., description="Commenter username")
    commenter_avatar_url: str = Field(..., description="Commenter avatar URL")
    comment_body: str | None = Field(None, description="Comment text (truncated to 500 chars)")
    file_path: str | None = Field(None, description="File path commented on")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    url: str | None = Field(None, description="Comment URL")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "CommitCommentEvent":
        """Parse GitHub CommitCommentEvent into model.

        Args:
            event: GitHub CommitCommentEvent from Events API

        Returns:
            CommitCommentEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        payload = event["payload"]
        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        # Truncate comment body to 500 chars
        comment_body = payload.get("comment", {}).get("body")
        if comment_body and len(comment_body) > 500:
            comment_body = comment_body[:500]

        commit_sha = payload["comment"]["commit_id"]

        return cls(
            event_id=event["id"],
            action="created",  # CommitCommentEvent only has 'created' action
            commit_sha=commit_sha,
            short_sha=commit_sha[:7],
            commenter_username=event["actor"]["login"],
            commenter_avatar_url=event["actor"]["avatar_url"],
            comment_body=comment_body,
            file_path=payload.get("comment", {}).get("path"),
            repo_owner=repo_owner,
            repo_name=repo_name,
            is_public=event.get("public", True),
            url=payload.get("comment", {}).get("html_url"),
            event_timestamp=timestamp,
        )


class MemberEvent(BaseModel):
    """Internal representation of a GitHub member event.

    Attributes:
        event_id: GitHub event ID for deduplication
        action: Action performed (added, removed, edited)
        member_username: GitHub username of member being managed
        member_avatar_url: Member's avatar URL
        actor_username: GitHub username who performed the action
        repo_owner: Repository owner username
        repo_name: Repository name
        is_public: Whether the repository is public
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    action: str = Field(..., description="Action (added, removed, edited)")
    member_username: str = Field(..., description="Member username")
    member_avatar_url: str = Field(..., description="Member avatar URL")
    actor_username: str = Field(..., description="Actor username")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "MemberEvent":
        """Parse GitHub MemberEvent into model.

        Args:
            event: GitHub MemberEvent from Events API

        Returns:
            MemberEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        payload = event["payload"]
        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return cls(
            event_id=event["id"],
            action=payload["action"],
            member_username=payload["member"]["login"],
            member_avatar_url=payload["member"]["avatar_url"],
            actor_username=event["actor"]["login"],
            repo_owner=repo_owner,
            repo_name=repo_name,
            is_public=event.get("public", True),
            event_timestamp=timestamp,
        )


class GollumEvent(BaseModel):
    """Internal representation of a GitHub Gollum (wiki) event.

    Attributes:
        event_id: GitHub event ID for deduplication
        action: Action performed (created, edited)
        page_name: Wiki page name
        page_title: Wiki page title
        editor_username: GitHub username who edited the wiki
        editor_avatar_url: Editor's avatar URL
        repo_owner: Repository owner username
        repo_name: Repository name
        is_public: Whether the repository is public
        url: Wiki page URL
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    action: str = Field(..., description="Action (created, edited)")
    page_name: str = Field(..., description="Wiki page name")
    page_title: str | None = Field(None, description="Wiki page title")
    editor_username: str = Field(..., description="Editor username")
    editor_avatar_url: str = Field(..., description="Editor avatar URL")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    url: str | None = Field(None, description="Wiki page URL")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "GollumEvent":
        """Parse GitHub GollumEvent into model.

        Args:
            event: GitHub GollumEvent from Events API

        Returns:
            GollumEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        payload = event["payload"]
        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        # GollumEvent can have multiple pages - take first page only
        pages = payload.get("pages", [])
        if not pages:
            raise ValueError("GollumEvent has no pages")

        first_page = pages[0]

        return cls(
            event_id=event["id"],
            action=first_page["action"],
            page_name=first_page["page_name"],
            page_title=first_page.get("title"),
            editor_username=event["actor"]["login"],
            editor_avatar_url=event["actor"]["avatar_url"],
            repo_owner=repo_owner,
            repo_name=repo_name,
            is_public=event.get("public", True),
            url=first_page.get("html_url"),
            event_timestamp=timestamp,
        )


class PublicEvent(BaseModel):
    """Internal representation of a GitHub public event (repo made public).

    Attributes:
        event_id: GitHub event ID for deduplication
        actor_username: GitHub username who made repo public
        actor_avatar_url: Actor's avatar URL
        repo_owner: Repository owner username
        repo_name: Repository name
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    actor_username: str = Field(..., description="Actor username")
    actor_avatar_url: str = Field(..., description="Actor avatar URL")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "PublicEvent":
        """Parse GitHub PublicEvent into model.

        Args:
            event: GitHub PublicEvent from Events API

        Returns:
            PublicEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return cls(
            event_id=event["id"],
            actor_username=event["actor"]["login"],
            actor_avatar_url=event["actor"]["avatar_url"],
            repo_owner=repo_owner,
            repo_name=repo_name,
            event_timestamp=timestamp,
        )


class DiscussionEvent(BaseModel):
    """Internal representation of a GitHub discussion event.

    Attributes:
        event_id: GitHub event ID for deduplication
        action: Action performed (created, edited, deleted, answered, etc.)
        discussion_number: Discussion number
        discussion_title: Discussion title
        category: Discussion category
        author_username: GitHub username who created/modified the discussion
        author_avatar_url: Author's avatar URL
        repo_owner: Repository owner username
        repo_name: Repository name
        is_public: Whether the repository is public
        url: Discussion URL
        event_timestamp: Event timestamp
    """

    event_id: str = Field(..., description="GitHub event ID")
    action: str = Field(..., description="Action (created, edited, deleted, answered, etc.)")
    discussion_number: int = Field(..., description="Discussion number")
    discussion_title: str | None = Field(None, description="Discussion title")
    category: str | None = Field(None, description="Discussion category")
    author_username: str = Field(..., description="Author username")
    author_avatar_url: str = Field(..., description="Author avatar URL")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    is_public: bool = Field(True, description="Whether repository is public")
    url: str | None = Field(None, description="Discussion URL")
    event_timestamp: datetime = Field(..., description="Event timestamp")

    @classmethod
    def from_github_event(cls, event: dict[str, Any]) -> "DiscussionEvent":
        """Parse GitHub DiscussionEvent into model.

        Args:
            event: GitHub DiscussionEvent from Events API

        Returns:
            DiscussionEvent instance with parsed data
        """
        repo_full_name = event["repo"]["name"]
        repo_owner, repo_name = repo_full_name.split("/", 1)

        payload = event["payload"]
        # Parse timestamp from ISO format and ensure it's timezone-aware
        timestamp_str = event["created_at"].replace("Z", "+00:00")
        timestamp = datetime.fromisoformat(timestamp_str)
        # Ensure timezone-aware by adding UTC if naive
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        discussion = payload.get("discussion", {})

        return cls(
            event_id=event["id"],
            action=payload["action"],
            discussion_number=discussion.get("number", 0),
            discussion_title=discussion.get("title"),
            category=discussion.get("category", {}).get("name"),
            author_username=event["actor"]["login"],
            author_avatar_url=event["actor"]["avatar_url"],
            repo_owner=repo_owner,
            repo_name=repo_name,
            is_public=event.get("public", True),
            url=discussion.get("html_url"),
            event_timestamp=timestamp,
        )
