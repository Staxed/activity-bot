"""Discord summary embed creation for multi-event activity."""

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

    # Create embed with random quote as description
    embed = discord.Embed(
        title=f"GitHub Activity Summary - {username}",
        description=get_random_quote(),
        color=SUMMARY_COLOR,
        timestamp=timestamp,
    )

    # Set author with GitHub profile link and avatar
    embed.set_author(
        name=username, url=f"https://github.com/{username}", icon_url=avatar_url
    )

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
