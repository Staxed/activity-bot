"""Discord embed creation with commit grouping logic."""

from collections import defaultdict
from datetime import datetime

import discord

from app.discord.quotes import get_random_quote
from app.shared.models import CommitEvent


def group_commits_by_author(commits: list[CommitEvent]) -> dict[str, dict[str, list[CommitEvent]]]:
    """Group commits by author, then by repository.

    Args:
        commits: List of commit events to group

    Returns:
        Nested dict: {author: {repo: [commits]}}

    Example:
        >>> commits = [CommitEvent(..., author="Alice", repo_name="backend"), ...]
        >>> grouped = group_commits_by_author(commits)
        >>> # {"Alice": {"backend": [commit1, commit2]}}
    """
    grouped: dict[str, dict[str, list[CommitEvent]]] = defaultdict(lambda: defaultdict(list))

    for commit in commits:
        grouped[commit.author][f"{commit.repo_owner}/{commit.repo_name}"].append(commit)

    return dict(grouped)


def format_commit_time(timestamp: datetime) -> str:
    """Format commit timestamp based on recency.

    Args:
        timestamp: Commit timestamp

    Returns:
        Formatted time string:
        - Today: "2:30 PM"
        - This year: "Nov 9 at 2:30 PM"
        - Other years: "Nov 9, 2025 at 2:30 PM"
    """
    now = datetime.now(timestamp.tzinfo)
    same_day = now.date() == timestamp.date()
    same_year = now.year == timestamp.year

    if same_day:
        return timestamp.strftime("%-I:%M %p")
    elif same_year:
        return timestamp.strftime("%b %-d at %-I:%M %p")
    else:
        return timestamp.strftime("%b %-d, %Y at %-I:%M %p")


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


def create_commit_embeds(author: str, repos: dict[str, list[CommitEvent]]) -> list[discord.Embed]:
    """Create Discord embeds for an author's commits.

    Groups commits by repository, handles Discord field limits (25 fields/embed),
    and caps total commits at 50 with overflow notice.

    Args:
        author: Author name for the embed title
        repos: Dict mapping repo names to commit lists

    Returns:
        List of Discord embeds (split if >25 fields or for readability)

    Discord Limits:
        - 25 fields per embed (hard limit)
        - 1024 chars per field value
        - 256 chars per field name
    """
    # Flatten all commits and sort by timestamp (oldest first)
    all_commits: list[CommitEvent] = []
    for repo_commits in repos.values():
        all_commits.extend(repo_commits)
    all_commits.sort(key=lambda c: c.timestamp)

    # Cap at 50 commits, track overflow
    overflow_count = max(0, len(all_commits) - 50)
    if overflow_count > 0:
        all_commits = all_commits[:50]

    # Re-group capped commits by repo
    capped_repos: dict[str, list[CommitEvent]] = defaultdict(list)
    for commit in all_commits:
        repo_key = f"{commit.repo_owner}/{commit.repo_name}"
        capped_repos[repo_key].append(commit)

    # Build field data (one field per repo)
    fields: list[tuple[str, str]] = []
    for repo_name, repo_commits in capped_repos.items():
        # Sort commits within repo by timestamp (oldest first)
        repo_commits.sort(key=lambda c: c.timestamp)

        # Build commit lines: • [msg](url) (branch) - time
        lines = []
        for commit in repo_commits:
            truncated_msg = truncate_message(commit.message)
            time_str = format_commit_time(commit.timestamp)
            line = f"• [{truncated_msg}]({commit.url}) (`{commit.branch}`) - {time_str}"
            lines.append(line)

        field_value = "\n".join(lines)

        # Ensure field value doesn't exceed Discord limit
        if len(field_value) > 1024:
            field_value = field_value[:1021] + "..."

        fields.append((repo_name, field_value))

    # Split fields into chunks of 25 (Discord limit)
    embeds: list[discord.Embed] = []
    total_commits = len(all_commits)

    for chunk_idx, chunk_start in enumerate(range(0, len(fields), 25)):
        chunk_fields = fields[chunk_start : chunk_start + 25]

        # Create embed
        embed = discord.Embed(
            title=f"{total_commits} commit{'s' if total_commits != 1 else ''} by {author}",
            description=get_random_quote(),
            color=0x28A745,  # GitHub green
            timestamp=all_commits[-1].timestamp,  # Latest commit timestamp
        )

        # Add multipart indicator if multiple embeds
        if len(fields) > 25:
            part_num = chunk_idx + 1
            total_parts = (len(fields) + 24) // 25
            embed.title = f"{total_commits} commit{'s' if total_commits != 1 else ''} by {author} ({part_num}/{total_parts})"

        # Add fields
        for field_name, field_value in chunk_fields:
            embed.add_field(name=field_name, value=field_value, inline=False)

        # Add overflow footer on last embed
        if overflow_count > 0 and chunk_idx == (len(fields) - 1) // 25:
            embed.set_footer(
                text=f"... and {overflow_count} more commit{'s' if overflow_count != 1 else ''}"
            )

        embeds.append(embed)

    return embeds
