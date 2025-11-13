"""Discord embed builders for GitHub event types."""

from datetime import datetime

import discord

from app.discord.event_colors import (
    CREATION_COLOR,
    DELETION_COLOR,
    FORK_COLOR,
    ISSUE_COLOR,
    PR_COLOR,
    RELEASE_COLOR,
    REVIEW_COLOR,
)
from app.shared.models import (
    CreateEvent,
    DeleteEvent,
    ForkEvent,
    IssuesEvent,
    PullRequestEvent,
    PullRequestReviewEvent,
    ReleaseEvent,
)

# Discord embed description limit
MAX_DESCRIPTION_LENGTH = 4096


def create_prs_embed(prs: list[PullRequestEvent]) -> discord.Embed | None:
    """Create Discord embed for pull request events.

    Args:
        prs: List of pull request events

    Returns:
        Discord embed or None if list is empty

    Example:
        >>> embed = create_prs_embed([pr1, pr2, pr3])
        >>> # Embed with PR activity sorted by timestamp
    """
    if not prs:
        return None

    # Sort by timestamp, newest first
    sorted_prs = sorted(prs, key=lambda pr: pr.event_timestamp, reverse=True)

    # Create embed
    embed = discord.Embed(
        title="🔀 Pull Requests",
        color=PR_COLOR,
        timestamp=sorted_prs[0].event_timestamp,
    )

    # Build description with overflow tracking
    description_lines = []
    current_length = 0
    overflow_count = 0

    for pr in sorted_prs:
        # Format line based on repository visibility
        unix_timestamp = int(pr.event_timestamp.timestamp())
        repo_full_name = f"{pr.repo_owner}/{pr.repo_name}"

        if pr.is_public:
            line = f"• [#{pr.pr_number}: {pr.title}]({pr.url}) ({pr.action}) in {repo_full_name} - <t:{unix_timestamp}:t>"
        else:
            line = f"• #{pr.pr_number}: {pr.title} ({pr.action}) in {repo_full_name} [Private Repo] - <t:{unix_timestamp}:t>"

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
        embed.set_footer(text=f"... and {overflow_count} more pull request(s)")

    return embed


def create_issues_embed(issues: list[IssuesEvent]) -> discord.Embed | None:
    """Create Discord embed for issue events.

    Args:
        issues: List of issue events

    Returns:
        Discord embed or None if list is empty
    """
    if not issues:
        return None

    # Sort by timestamp, newest first
    sorted_issues = sorted(issues, key=lambda issue: issue.event_timestamp, reverse=True)

    # Create embed
    embed = discord.Embed(
        title="🐛 Issues",
        color=ISSUE_COLOR,
        timestamp=sorted_issues[0].event_timestamp,
    )

    # Build description with overflow tracking
    description_lines = []
    current_length = 0
    overflow_count = 0

    for issue in sorted_issues:
        # Format line based on repository visibility
        unix_timestamp = int(issue.event_timestamp.timestamp())
        repo_full_name = f"{issue.repo_owner}/{issue.repo_name}"

        if issue.is_public:
            line = f"• [#{issue.issue_number}: {issue.title}]({issue.url}) ({issue.action}) in {repo_full_name} - <t:{unix_timestamp}:t>"
        else:
            line = f"• #{issue.issue_number}: {issue.title} ({issue.action}) in {repo_full_name} [Private Repo] - <t:{unix_timestamp}:t>"

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
        embed.set_footer(text=f"... and {overflow_count} more issue(s)")

    return embed


def create_releases_embed(releases: list[ReleaseEvent]) -> discord.Embed | None:
    """Create Discord embed for release events.

    Args:
        releases: List of release events

    Returns:
        Discord embed or None if list is empty
    """
    if not releases:
        return None

    # Sort by timestamp, newest first
    sorted_releases = sorted(releases, key=lambda release: release.event_timestamp, reverse=True)

    # Create embed
    embed = discord.Embed(
        title="🚀 Releases",
        color=RELEASE_COLOR,
        timestamp=sorted_releases[0].event_timestamp,
    )

    # Build description with overflow tracking
    description_lines = []
    current_length = 0
    overflow_count = 0

    for release in sorted_releases:
        # Format line based on repository visibility
        unix_timestamp = int(release.event_timestamp.timestamp())
        repo_full_name = f"{release.repo_owner}/{release.repo_name}"

        # Add prerelease label if applicable
        prerelease_label = " (prerelease)" if release.is_prerelease else ""
        release_display_name = release.release_name or release.tag_name

        if release.is_public and release.url:
            line = f"• [{release.tag_name}: {release_display_name}]({release.url}){prerelease_label} in {repo_full_name} - <t:{unix_timestamp}:t>"
        elif release.is_public:
            line = f"• {release.tag_name}: {release_display_name}{prerelease_label} in {repo_full_name} - <t:{unix_timestamp}:t>"
        else:
            line = f"• {release.tag_name}: {release_display_name}{prerelease_label} in {repo_full_name} [Private Repo] - <t:{unix_timestamp}:t>"

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
        embed.set_footer(text=f"... and {overflow_count} more release(s)")

    return embed


def create_reviews_embed(reviews: list[PullRequestReviewEvent]) -> discord.Embed | None:
    """Create Discord embed for pull request review events.

    Args:
        reviews: List of review events

    Returns:
        Discord embed or None if list is empty
    """
    if not reviews:
        return None

    # Sort by timestamp, newest first
    sorted_reviews = sorted(reviews, key=lambda review: review.event_timestamp, reverse=True)

    # Create embed
    embed = discord.Embed(
        title="👀 Pull Request Reviews",
        color=REVIEW_COLOR,
        timestamp=sorted_reviews[0].event_timestamp,
    )

    # Build description with overflow tracking
    description_lines = []
    current_length = 0
    overflow_count = 0

    for review in sorted_reviews:
        # Format line based on repository visibility
        unix_timestamp = int(review.event_timestamp.timestamp())
        repo_full_name = f"{review.repo_owner}/{review.repo_name}"

        # Add state emoji
        state_emoji = "✅" if review.review_state == "approved" else "🔄"

        if review.is_public:
            line = f"• {state_emoji} [PR #{review.pr_number}]({review.url}) ({review.review_state}) in {repo_full_name} - <t:{unix_timestamp}:t>"
        else:
            line = f"• {state_emoji} PR #{review.pr_number} ({review.review_state}) in {repo_full_name} [Private Repo] - <t:{unix_timestamp}:t>"

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
        embed.set_footer(text=f"... and {overflow_count} more review(s)")

    return embed


def create_creations_embed(creations: list[CreateEvent]) -> discord.Embed | None:
    """Create Discord embed for creation events.

    Args:
        creations: List of creation events

    Returns:
        Discord embed or None if list is empty
    """
    if not creations:
        return None

    # Sort by timestamp, newest first
    sorted_creations = sorted(
        creations, key=lambda creation: creation.event_timestamp, reverse=True
    )

    # Create embed
    embed = discord.Embed(
        title="🌱 Creations",
        color=CREATION_COLOR,
        timestamp=sorted_creations[0].event_timestamp,
    )

    # Build description with overflow tracking
    description_lines = []
    current_length = 0
    overflow_count = 0

    for creation in sorted_creations:
        # Format line based on repository visibility
        unix_timestamp = int(creation.event_timestamp.timestamp())
        repo_full_name = f"{creation.repo_owner}/{creation.repo_name}"

        if creation.is_public:
            line = f"• Created {creation.ref_type} `{creation.ref_name}` in [{repo_full_name}](https://github.com/{repo_full_name}) - <t:{unix_timestamp}:t>"
        else:
            line = f"• Created {creation.ref_type} `{creation.ref_name}` in {repo_full_name} [Private Repo] - <t:{unix_timestamp}:t>"

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
        embed.set_footer(text=f"... and {overflow_count} more creation(s)")

    return embed


def create_deletions_embed(deletions: list[DeleteEvent]) -> discord.Embed | None:
    """Create Discord embed for deletion events.

    Args:
        deletions: List of deletion events

    Returns:
        Discord embed or None if list is empty
    """
    if not deletions:
        return None

    # Sort by timestamp, newest first
    sorted_deletions = sorted(
        deletions, key=lambda deletion: deletion.event_timestamp, reverse=True
    )

    # Create embed
    embed = discord.Embed(
        title="🗑️ Deletions",
        color=DELETION_COLOR,
        timestamp=sorted_deletions[0].event_timestamp,
    )

    # Build description with overflow tracking
    description_lines = []
    current_length = 0
    overflow_count = 0

    for deletion in sorted_deletions:
        # Format line based on repository visibility
        unix_timestamp = int(deletion.event_timestamp.timestamp())
        repo_full_name = f"{deletion.repo_owner}/{deletion.repo_name}"

        if deletion.is_public:
            line = f"• Deleted {deletion.ref_type} `{deletion.ref_name}` in [{repo_full_name}](https://github.com/{repo_full_name}) - <t:{unix_timestamp}:t>"
        else:
            line = f"• Deleted {deletion.ref_type} `{deletion.ref_name}` in {repo_full_name} [Private Repo] - <t:{unix_timestamp}:t>"

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
        embed.set_footer(text=f"... and {overflow_count} more deletion(s)")

    return embed


def create_forks_embed(forks: list[ForkEvent]) -> discord.Embed | None:
    """Create Discord embed for fork events.

    Args:
        forks: List of fork events

    Returns:
        Discord embed or None if list is empty
    """
    if not forks:
        return None

    # Sort by timestamp, newest first
    sorted_forks = sorted(forks, key=lambda fork: fork.event_timestamp, reverse=True)

    # Create embed
    embed = discord.Embed(
        title="🍴 Forks",
        color=FORK_COLOR,
        timestamp=sorted_forks[0].event_timestamp,
    )

    # Build description with overflow tracking
    description_lines = []
    current_length = 0
    overflow_count = 0

    for fork in sorted_forks:
        # Format line
        unix_timestamp = int(fork.event_timestamp.timestamp())
        source_repo = f"{fork.source_repo_owner}/{fork.source_repo_name}"
        fork_repo = f"{fork.fork_repo_owner}/{fork.fork_repo_name}"

        # Both source and fork should be public (GitHub API behavior)
        if fork.fork_url:
            line = (
                f"• Forked {source_repo} → [{fork_repo}]({fork.fork_url}) - <t:{unix_timestamp}:t>"
            )
        else:
            line = f"• Forked {source_repo} → {fork_repo} - <t:{unix_timestamp}:t>"

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
        embed.set_footer(text=f"... and {overflow_count} more fork(s)")

    return embed
