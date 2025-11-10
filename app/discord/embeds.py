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
    # Flatten all commits and sort by timestamp (newest first)
    all_commits: list[CommitEvent] = []
    for repo_commits in repos.values():
        all_commits.extend(repo_commits)
    all_commits.sort(key=lambda c: c.timestamp, reverse=True)

    total_commits = len(all_commits)

    # Re-group commits by repo (we'll cap during field building to respect Discord limits)
    repos_by_name: dict[str, list[CommitEvent]] = defaultdict(list)
    for commit in all_commits:
        repo_key = f"{commit.repo_owner}/{commit.repo_name}"
        repos_by_name[repo_key].append(commit)

    # Build field data (one field per repo) and track commits displayed
    fields: list[tuple[str, str]] = []
    commits_displayed = 0

    for repo_name, repo_commits in repos_by_name.items():
        # Sort commits within repo by timestamp (newest first)
        repo_commits.sort(key=lambda c: c.timestamp, reverse=True)

        # Check if repo is private (all commits in same repo have same privacy)
        is_private = not repo_commits[0].is_public

        # Build commit lines: • [msg](url) (branch) - time (public repos only get links)
        lines = []

        # Add repo name as header (clickable for public, plain text for private)
        if is_private:
            lines.append(f"**{repo_name} [Private]**")
            field_name = "\u200b"  # Zero-width space (invisible field name)
        else:
            repo_url = f"https://github.com/{repo_name}"
            lines.append(f"**[{repo_name}]({repo_url})**")
            field_name = "\u200b"  # Zero-width space (invisible field name)

        # Add commits to field value, stopping if we exceed 1024 char limit
        commits_in_field = 0
        for commit in repo_commits:
            truncated_msg = truncate_message(commit.message)
            time_str = format_commit_time(commit.timestamp)

            # Only link public repos (private repos aren't accessible to others)
            if commit.is_public:
                line = f"• [{truncated_msg}]({commit.url}) (`{commit.branch}`) - {time_str}"
            else:
                line = f"• {truncated_msg} (`{commit.branch}`) - {time_str}"

            # Check if adding this line would exceed Discord's 1024 char limit
            test_value = "\n".join([*lines, line])
            if len(test_value) > 1024:
                # Can't fit this commit, stop adding to this field
                break

            lines.append(line)
            commits_in_field += 1
            commits_displayed += 1

        field_value = "\n".join(lines)
        fields.append((field_name, field_value))

    # Calculate overflow (commits that couldn't fit in the embed)
    overflow_count = total_commits - commits_displayed

    # Split fields into chunks of 25 (Discord limit)
    embeds: list[discord.Embed] = []

    # Get author info from first commit (all commits have same author)
    first_commit = all_commits[0]
    author_username = first_commit.author_username
    author_avatar_url = first_commit.author_avatar_url
    author_profile_url = f"https://github.com/{author_username}"

    for chunk_idx, chunk_start in enumerate(range(0, len(fields), 25)):
        chunk_fields = fields[chunk_start : chunk_start + 25]

        # Build author line with total commit count
        commit_word = "commit" if total_commits == 1 else "commits"
        author_line = f"{author} made {total_commits} {commit_word}"

        # Add multipart indicator if multiple embeds
        if len(fields) > 25:
            part_num = chunk_idx + 1
            total_parts = (len(fields) + 24) // 25
            author_line += f" ({part_num}/{total_parts})"

        # Create embed with quote in description (with quotes and italics)
        quote = get_random_quote()
        embed = discord.Embed(
            description=f'*"{quote}"*',
            color=0xFF8C00,  # Orange
            timestamp=all_commits[
                0
            ].timestamp,  # Latest commit timestamp (first since sorted newest first)
        )

        # Set author with avatar, profile link, and commit count
        embed.set_author(
            name=author_line,
            url=author_profile_url,
            icon_url=author_avatar_url,
        )

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
