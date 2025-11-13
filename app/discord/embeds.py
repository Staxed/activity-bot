"""Discord embed creation for commit events."""

from datetime import datetime

import discord

from app.discord.event_colors import COMMIT_COLOR
from app.shared.models import CommitEvent

# Discord embed description limit
MAX_DESCRIPTION_LENGTH = 4096


def format_commit_time(timestamp: datetime) -> str:
    """Format commit timestamp using Discord's dynamic timestamp.

    Discord timestamps automatically show in the user's local timezone.

    Args:
        timestamp: Commit timestamp

    Returns:
        Discord timestamp string that renders in user's local time
        Format: <t:UNIX_TIMESTAMP:t> shows short time (e.g., "1:18 PM")
    """
    unix_timestamp = int(timestamp.timestamp())
    return f"<t:{unix_timestamp}:t>"


def truncate_message(message: str, max_length: int = 200) -> str:
    """Truncate message if it exceeds max length.

    Args:
        message: Commit message to truncate
        max_length: Maximum length before truncation (default: 200)

    Returns:
        Truncated message with "..." if needed
    """
    if len(message) > max_length:
        return message[: max_length - 3] + "..."
    return message


def create_commits_embed(commits: list[CommitEvent]) -> discord.Embed | None:
    """Create Discord embed for commit events.

    Args:
        commits: List of commit events

    Returns:
        Discord embed or None if list is empty

    Example:
        >>> embed = create_commits_embed([commit1, commit2, commit3])
        >>> # Embed with commit activity sorted by timestamp
    """
    if not commits:
        return None

    # Sort by timestamp, newest first
    sorted_commits = sorted(commits, key=lambda c: c.timestamp, reverse=True)

    # Create embed
    embed = discord.Embed(
        title="📝 Commits",
        color=COMMIT_COLOR,
        timestamp=sorted_commits[0].timestamp,
    )

    # Build description with overflow tracking
    description_lines = []
    current_length = 0
    overflow_count = 0

    for commit in sorted_commits:
        # Format line based on repository visibility
        unix_timestamp = int(commit.timestamp.timestamp())
        repo_full_name = f"{commit.repo_owner}/{commit.repo_name}"
        truncated_msg = truncate_message(commit.message)

        if commit.is_public:
            line = f"• [{truncated_msg}]({commit.url}) (`{commit.branch}`) in {repo_full_name} - <t:{unix_timestamp}:t>"
        else:
            line = f"• {truncated_msg} (`{commit.branch}`) in {repo_full_name} [Private Repo] - <t:{unix_timestamp}:t>"

        # Check if adding this line would exceed limit
        line_length = len(line) + 1  # +1 for newline
        if current_length + line_length > MAX_DESCRIPTION_LENGTH:
            overflow_count += 1
        else:
            description_lines.append(line)
            current_length += line_length

    # Set description
    embed.description = "\n".join(description_lines)

    # Add footer if overflow
    if overflow_count > 0:
        embed.set_footer(text=f"... and {overflow_count} more commit(s)")

    return embed
