"""Data models for Activity Bot."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CommitEvent(BaseModel):
    """Internal representation of a GitHub commit event.

    Attributes:
        sha: Full commit SHA hash
        short_sha: 7-character short SHA for display
        author: Commit author name
        author_email: Commit author email address
        message: Commit message (first line only)
        message_body: Full commit message including body
        repo_owner: Repository owner username
        repo_name: Repository name
        timestamp: Commit timestamp
        url: GitHub commit URL
        branch: Branch name (extracted from ref)
    """

    sha: str = Field(..., description="Full commit SHA")
    short_sha: str = Field(..., description="7-character short SHA")
    author: str = Field(..., description="Commit author name")
    author_email: str = Field(..., description="Commit author email")
    message: str = Field(..., description="Commit message (first line)")
    message_body: str = Field(..., description="Full commit message")
    repo_owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    timestamp: datetime = Field(..., description="Commit timestamp")
    url: str = Field(..., description="GitHub commit URL")
    branch: str = Field(..., description="Branch name")

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

        # Parse timestamp from ISO format
        timestamp = datetime.fromisoformat(
            commit["author"]["date"].replace("Z", "+00:00")
        )

        return cls(
            sha=sha,
            short_sha=sha[:7],
            author=commit["author"]["name"],
            author_email=commit["author"]["email"],
            message=message,
            message_body=message_body,
            repo_owner=repo_owner,
            repo_name=repo_name,
            timestamp=timestamp,
            url=url,
            branch=branch,
        )
