"""Discord summary embed creation for multi-event activity."""

import re
from datetime import datetime

import discord

from app.discord.event_colors import SUMMARY_COLOR
from app.discord.quotes import get_random_quote


def create_summary_embed(
    username: str,
    avatar_url: str,
    event_counts: dict[str, int],
    affected_repos: list[tuple[str, bool]],
    timestamp: datetime,
) -> discord.Embed:
    """Create a summary embed for a user's GitHub activity.

    Args:
        username: GitHub username
        avatar_url: User's avatar URL
        event_counts: Dict mapping event types to counts (e.g., {'commits': 5, 'pull_requests': 2})
        affected_repos: List of (repo_full_name, is_public) tuples
        timestamp: Latest activity timestamp

    Returns:
        Discord embed with activity summary

    Example:
        >>> embed = create_summary_embed(
        ...     "staxed",
        ...     "https://github.com/staxed.png",
        ...     {"commits": 5, "pull_requests": 2},
        ...     [("staxed/activity-bot", True)],
        ...     datetime.now()
        ... )
    """
    # Emoji mapping for event types
    emoji_map = {
        "commits": "📝",
        "pull_requests": "🔀",
        "issues": "🐛",
        "releases": "🚀",
        "reviews": "👀",
        "creations": "🌱",
        "deletions": "🗑️",
        "forks": "🍴",
    }

    # Get quote and format it (remove leading emoji, add quotes and italics)
    raw_quote = get_random_quote()
    # Remove any leading emoji (Unicode emoji pattern)
    cleaned_quote = re.sub(r'^[\U0001F300-\U0001F9FF\s]+', '', raw_quote).strip()
    formatted_quote = f'*"{cleaned_quote}"*'

    # Create embed with title as clickable link and formatted quote as description
    embed = discord.Embed(
        title=f"{username} on Github",
        url=f"https://github.com/{username}",
        description=formatted_quote,
        color=SUMMARY_COLOR,
        timestamp=timestamp,
    )

    # Set user avatar as thumbnail
    embed.set_thumbnail(url=avatar_url)

    # Add spacing to push fields below avatar thumbnail
    # The description gets extra newlines to create vertical space
    embed.description = embed.description + "\n\n\u200b"  # Zero-width space for extra padding

    # Build activity summary field (skip zero counts)
    activity_lines = []
    for event_type, count in event_counts.items():
        if count > 0:
            emoji = emoji_map.get(event_type, "•")
            activity_lines.append(f"{emoji} {count} {event_type.replace('_', ' ')}")

    if activity_lines:
        embed.add_field(
            name="Activity Summary",
            value="\n".join(activity_lines),
            inline=True,
        )

    # Add spacing field between columns
    embed.add_field(
        name="\u200b",  # Zero-width space for invisible field name
        value="\u200b",  # Zero-width space for invisible field value
        inline=True,
    )

    # Build affected repositories field
    if affected_repos:
        repo_lines = []
        for repo_full_name, is_public in affected_repos:
            if is_public:
                repo_lines.append(f"[{repo_full_name}](https://github.com/{repo_full_name})")
            else:
                repo_lines.append(f"{repo_full_name} [Private Repo]")

        embed.add_field(
            name="Affected Repositories",
            value="\n".join(repo_lines),
            inline=True,
        )

    return embed
