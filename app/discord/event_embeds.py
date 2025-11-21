"""Discord embed builders for GitHub event types."""

from datetime import UTC, datetime

import discord

from app.discord.event_colors import (
    COMMENT_COLOR,
    CREATION_COLOR,
    DELETION_COLOR,
    DISCUSSION_COLOR,
    FORK_COLOR,
    ISSUE_COLOR,
    MEMBER_COLOR,
    PR_COLOR,
    PUBLIC_COLOR,
    RELEASE_COLOR,
    REVIEW_COLOR,
    STAR_COLOR,
    WIKI_COLOR,
)
from app.shared.models import (
    CommitCommentEvent,
    CreateEvent,
    DeleteEvent,
    DiscussionEvent,
    ForkEvent,
    GollumEvent,
    IssueCommentEvent,
    IssuesEvent,
    MemberEvent,
    PublicEvent,
    PullRequestEvent,
    PullRequestReviewCommentEvent,
    PullRequestReviewEvent,
    ReleaseEvent,
    WatchEvent,
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

    # Sort by public repos first, then by timestamp (newest first)
    sorted_prs = sorted(prs, key=lambda pr: (pr.is_public, pr.event_timestamp), reverse=True)

    # Create embed
    embed = discord.Embed(
        title="🔀 Pull Requests",
        color=PR_COLOR,
    )

    # Build description with max 10 items shown
    MAX_ITEMS = 10
    description_lines = []

    for i, pr in enumerate(sorted_prs):
        if i >= MAX_ITEMS:
            break

        # Format line based on repository visibility
        unix_timestamp = int(pr.event_timestamp.timestamp())
        repo_full_name = f"{pr.repo_owner}/{pr.repo_name}"

        if pr.is_public:
            line = f"• [#{pr.pr_number}: {pr.title}]({pr.url}) ({pr.action}) in {repo_full_name} - <t:{unix_timestamp}:t>"
        else:
            line = f"• #{pr.pr_number}: {pr.title} ({pr.action}) in {repo_full_name} [Private Repo] - <t:{unix_timestamp}:t>"

        description_lines.append(line)

    # Set description
    embed.description = "\n".join(description_lines)

    # Add footer if there are more items
    overflow_count = len(sorted_prs) - MAX_ITEMS
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

    # Sort by public repos first, then by timestamp (newest first)
    sorted_issues = sorted(
        issues, key=lambda issue: (issue.is_public, issue.event_timestamp), reverse=True
    )

    # Create embed
    embed = discord.Embed(
        title="🐛 Issues",
        color=ISSUE_COLOR,
    )

    # Build description with max 10 items shown
    MAX_ITEMS = 10
    description_lines = []

    for i, issue in enumerate(sorted_issues):
        if i >= MAX_ITEMS:
            break

        # Format line based on repository visibility
        unix_timestamp = int(issue.event_timestamp.timestamp())
        repo_full_name = f"{issue.repo_owner}/{issue.repo_name}"

        if issue.is_public:
            line = f"• [#{issue.issue_number}: {issue.title}]({issue.url}) ({issue.action}) in {repo_full_name} - <t:{unix_timestamp}:t>"
        else:
            line = f"• #{issue.issue_number}: {issue.title} ({issue.action}) in {repo_full_name} [Private Repo] - <t:{unix_timestamp}:t>"

        description_lines.append(line)

    # Set description
    embed.description = "\n".join(description_lines)

    # Add footer if there are more items
    overflow_count = len(sorted_issues) - MAX_ITEMS
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

    # Sort by public repos first, then by timestamp (newest first)
    sorted_releases = sorted(
        releases, key=lambda release: (release.is_public, release.event_timestamp), reverse=True
    )

    # Create embed
    embed = discord.Embed(
        title="🚀 Releases",
        color=RELEASE_COLOR,
    )

    # Build description with max 10 items shown
    MAX_ITEMS = 10
    description_lines = []

    for i, release in enumerate(sorted_releases):
        if i >= MAX_ITEMS:
            break

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

        description_lines.append(line)

    # Set description
    embed.description = "\n".join(description_lines)

    # Add footer if there are more items
    overflow_count = len(sorted_releases) - MAX_ITEMS
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

    # Sort by public repos first, then by timestamp (newest first)
    sorted_reviews = sorted(
        reviews, key=lambda review: (review.is_public, review.event_timestamp), reverse=True
    )

    # Create embed
    embed = discord.Embed(
        title="👀 Pull Request Reviews",
        color=REVIEW_COLOR,
    )

    # Build description with max 10 items shown
    MAX_ITEMS = 10
    description_lines = []

    for i, review in enumerate(sorted_reviews):
        if i >= MAX_ITEMS:
            break

        # Format line based on repository visibility
        unix_timestamp = int(review.event_timestamp.timestamp())
        repo_full_name = f"{review.repo_owner}/{review.repo_name}"

        # Add state emoji
        state_emoji = "✅" if review.review_state == "approved" else "🔄"

        if review.is_public:
            line = f"• {state_emoji} [PR #{review.pr_number}]({review.url}) ({review.review_state}) in {repo_full_name} - <t:{unix_timestamp}:t>"
        else:
            line = f"• {state_emoji} PR #{review.pr_number} ({review.review_state}) in {repo_full_name} [Private Repo] - <t:{unix_timestamp}:t>"

        description_lines.append(line)

    # Set description
    embed.description = "\n".join(description_lines)

    # Add footer if there are more items
    overflow_count = len(sorted_reviews) - MAX_ITEMS
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

    # Sort by public repos first, then by timestamp (newest first)
    sorted_creations = sorted(
        creations, key=lambda creation: (creation.is_public, creation.event_timestamp), reverse=True
    )

    # Create embed
    embed = discord.Embed(
        title="🌱 Creations",
        color=CREATION_COLOR,
    )

    # Build description with max 10 items shown
    MAX_ITEMS = 10
    description_lines = []

    for i, creation in enumerate(sorted_creations):
        if i >= MAX_ITEMS:
            break

        # Format line based on repository visibility
        unix_timestamp = int(creation.event_timestamp.timestamp())
        repo_full_name = f"{creation.repo_owner}/{creation.repo_name}"

        if creation.is_public:
            line = f"• Created {creation.ref_type} `{creation.ref_name}` in [{repo_full_name}](https://github.com/{repo_full_name}) - <t:{unix_timestamp}:t>"
        else:
            line = f"• Created {creation.ref_type} `{creation.ref_name}` in {repo_full_name} [Private Repo] - <t:{unix_timestamp}:t>"

        description_lines.append(line)

    # Set description
    embed.description = "\n".join(description_lines)

    # Add footer if there are more items
    overflow_count = len(sorted_creations) - MAX_ITEMS
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

    # Sort by public repos first, then by timestamp (newest first)
    sorted_deletions = sorted(
        deletions, key=lambda deletion: (deletion.is_public, deletion.event_timestamp), reverse=True
    )

    # Create embed
    embed = discord.Embed(
        title="🗑️ Deletions",
        color=DELETION_COLOR,
    )

    # Build description with max 10 items shown
    MAX_ITEMS = 10
    description_lines = []

    for i, deletion in enumerate(sorted_deletions):
        if i >= MAX_ITEMS:
            break

        # Format line based on repository visibility
        unix_timestamp = int(deletion.event_timestamp.timestamp())
        repo_full_name = f"{deletion.repo_owner}/{deletion.repo_name}"

        if deletion.is_public:
            line = f"• Deleted {deletion.ref_type} `{deletion.ref_name}` in [{repo_full_name}](https://github.com/{repo_full_name}) - <t:{unix_timestamp}:t>"
        else:
            line = f"• Deleted {deletion.ref_type} `{deletion.ref_name}` in {repo_full_name} [Private Repo] - <t:{unix_timestamp}:t>"

        description_lines.append(line)

    # Set description
    embed.description = "\n".join(description_lines)

    # Add footer if there are more items
    overflow_count = len(sorted_deletions) - MAX_ITEMS
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

    # Sort by public repos first, then by timestamp (newest first)
    sorted_forks = sorted(
        forks, key=lambda fork: (fork.is_public, fork.event_timestamp), reverse=True
    )

    # Create embed
    embed = discord.Embed(
        title="🍴 Forks",
        color=FORK_COLOR,
    )

    # Build description with max 10 items shown
    MAX_ITEMS = 10
    description_lines = []

    for i, fork in enumerate(sorted_forks):
        if i >= MAX_ITEMS:
            break

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

        description_lines.append(line)

    # Set description
    embed.description = "\n".join(description_lines)

    # Add footer if there are more items
    overflow_count = len(sorted_forks) - MAX_ITEMS
    if overflow_count > 0:
        embed.set_footer(text=f"... and {overflow_count} more fork(s)")

    return embed


def create_stars_embed(events: list[WatchEvent]) -> discord.Embed | None:
    """Create Discord embed for star (watch) events.

    Args:
        events: List of star events

    Returns:
        Discord embed or None if no events
    """
    if not events:
        return None

    # Sort events: public repos first, then by timestamp
    sorted_events = sorted(
        events,
        key=lambda e: (not e.is_public, e.event_timestamp),
        reverse=True,
    )

    # Limit to 10 events
    displayed_events = sorted_events[:10]
    overflow_count = len(sorted_events) - len(displayed_events)

    embed = discord.Embed(
        title=f"⭐ {len(sorted_events)} New Stars",
        color=STAR_COLOR,
        timestamp=datetime.now(UTC),
    )

    # Group by repo to show multiple stars per repo
    from collections import defaultdict

    repo_stars: dict[str, list[WatchEvent]] = defaultdict(list)
    for event in displayed_events:
        repo_key = f"{event.repo_owner}/{event.repo_name}"
        repo_stars[repo_key].append(event)

    for repo_full_name, star_events in repo_stars.items():
        stargazers = ", ".join([e.stargazer_username for e in star_events])
        unix_timestamp = int(star_events[0].event_timestamp.timestamp())

        if star_events[0].is_public:
            field_name = f"⭐ {repo_full_name}"
            field_value = f"Starred by {stargazers} - <t:{unix_timestamp}:t>"
        else:
            field_name = f"⭐ {repo_full_name} [Private]"
            field_value = f"Starred by {stargazers} - <t:{unix_timestamp}:t>"

        embed.add_field(name=field_name, value=field_value, inline=False)

    if overflow_count > 0:
        embed.set_footer(text=f"+ {overflow_count} more not shown")

    return embed


def create_issue_comments_embed(events: list[IssueCommentEvent]) -> discord.Embed | None:
    """Create Discord embed for issue comment events.

    Args:
        events: List of issue comment events

    Returns:
        Discord embed or None if no events
    """
    if not events:
        return None

    # Sort events: public repos first, then by timestamp
    sorted_events = sorted(
        events,
        key=lambda e: (not e.is_public, e.event_timestamp),
        reverse=True,
    )

    # Limit to 10 events
    displayed_events = sorted_events[:10]
    overflow_count = len(sorted_events) - len(displayed_events)

    embed = discord.Embed(
        title=f"💬 {len(sorted_events)} Issue Comments",
        color=COMMENT_COLOR,
        timestamp=datetime.now(UTC),
    )

    for event in displayed_events:
        unix_timestamp = int(event.event_timestamp.timestamp())
        repo_full_name = f"{event.repo_owner}/{event.repo_name}"

        # Truncate comment body to 100 chars
        comment_preview = ""
        if event.comment_body:
            comment_preview = (
                event.comment_body[:100] + "..."
                if len(event.comment_body) > 100
                else event.comment_body
            )

        if event.is_public and event.url:
            field_name = f"💬 Issue #{event.issue_number} in {repo_full_name}"
            field_value = (
                f"[{event.action}]({event.url}) by {event.commenter_username}\n"
                f"{comment_preview} - <t:{unix_timestamp}:t>"
            )
        elif event.is_public:
            field_name = f"💬 Issue #{event.issue_number} in {repo_full_name}"
            field_value = (
                f"{event.action} by {event.commenter_username}\n"
                f"{comment_preview} - <t:{unix_timestamp}:t>"
            )
        else:
            field_name = f"💬 Issue #{event.issue_number} in {repo_full_name} [Private]"
            field_value = (
                f"{event.action} by {event.commenter_username}\n"
                f"{comment_preview} - <t:{unix_timestamp}:t>"
            )

        embed.add_field(name=field_name, value=field_value, inline=False)

    if overflow_count > 0:
        embed.set_footer(text=f"+ {overflow_count} more not shown")

    return embed


def create_pr_review_comments_embed(
    events: list[PullRequestReviewCommentEvent],
) -> discord.Embed | None:
    """Create Discord embed for PR review comment events.

    Args:
        events: List of PR review comment events

    Returns:
        Discord embed or None if no events
    """
    if not events:
        return None

    # Sort events: public repos first, then by timestamp
    sorted_events = sorted(
        events,
        key=lambda e: (not e.is_public, e.event_timestamp),
        reverse=True,
    )

    # Limit to 10 events
    displayed_events = sorted_events[:10]
    overflow_count = len(sorted_events) - len(displayed_events)

    embed = discord.Embed(
        title=f"💬 {len(sorted_events)} PR Review Comments",
        color=COMMENT_COLOR,
        timestamp=datetime.now(UTC),
    )

    for event in displayed_events:
        unix_timestamp = int(event.event_timestamp.timestamp())
        repo_full_name = f"{event.repo_owner}/{event.repo_name}"

        # Truncate comment body to 100 chars
        comment_preview = ""
        if event.comment_body:
            comment_preview = (
                event.comment_body[:100] + "..."
                if len(event.comment_body) > 100
                else event.comment_body
            )

        file_info = f" on `{event.file_path}`" if event.file_path else ""

        if event.is_public and event.url:
            field_name = f"💬 PR #{event.pr_number} in {repo_full_name}"
            field_value = (
                f"[{event.action}]({event.url}) by {event.commenter_username}{file_info}\n"
                f"{comment_preview} - <t:{unix_timestamp}:t>"
            )
        elif event.is_public:
            field_name = f"💬 PR #{event.pr_number} in {repo_full_name}"
            field_value = (
                f"{event.action} by {event.commenter_username}{file_info}\n"
                f"{comment_preview} - <t:{unix_timestamp}:t>"
            )
        else:
            field_name = f"💬 PR #{event.pr_number} in {repo_full_name} [Private]"
            field_value = (
                f"{event.action} by {event.commenter_username}{file_info}\n"
                f"{comment_preview} - <t:{unix_timestamp}:t>"
            )

        embed.add_field(name=field_name, value=field_value, inline=False)

    if overflow_count > 0:
        embed.set_footer(text=f"+ {overflow_count} more not shown")

    return embed


def create_commit_comments_embed(events: list[CommitCommentEvent]) -> discord.Embed | None:
    """Create Discord embed for commit comment events.

    Args:
        events: List of commit comment events

    Returns:
        Discord embed or None if no events
    """
    if not events:
        return None

    # Sort events: public repos first, then by timestamp
    sorted_events = sorted(
        events,
        key=lambda e: (not e.is_public, e.event_timestamp),
        reverse=True,
    )

    # Limit to 10 events
    displayed_events = sorted_events[:10]
    overflow_count = len(sorted_events) - len(displayed_events)

    embed = discord.Embed(
        title=f"💬 {len(sorted_events)} Commit Comments",
        color=COMMENT_COLOR,
        timestamp=datetime.now(UTC),
    )

    for event in displayed_events:
        unix_timestamp = int(event.event_timestamp.timestamp())
        repo_full_name = f"{event.repo_owner}/{event.repo_name}"

        # Truncate comment body to 100 chars
        comment_preview = ""
        if event.comment_body:
            comment_preview = (
                event.comment_body[:100] + "..."
                if len(event.comment_body) > 100
                else event.comment_body
            )

        file_info = f" on `{event.file_path}`" if event.file_path else ""

        if event.is_public and event.url:
            field_name = f"💬 Commit `{event.short_sha}` in {repo_full_name}"
            field_value = (
                f"[Comment]({event.url}) by {event.commenter_username}{file_info}\n"
                f"{comment_preview} - <t:{unix_timestamp}:t>"
            )
        elif event.is_public:
            field_name = f"💬 Commit `{event.short_sha}` in {repo_full_name}"
            field_value = (
                f"Comment by {event.commenter_username}{file_info}\n"
                f"{comment_preview} - <t:{unix_timestamp}:t>"
            )
        else:
            field_name = f"💬 Commit `{event.short_sha}` in {repo_full_name} [Private]"
            field_value = (
                f"Comment by {event.commenter_username}{file_info}\n"
                f"{comment_preview} - <t:{unix_timestamp}:t>"
            )

        embed.add_field(name=field_name, value=field_value, inline=False)

    if overflow_count > 0:
        embed.set_footer(text=f"+ {overflow_count} more not shown")

    return embed


def create_members_embed(events: list[MemberEvent]) -> discord.Embed | None:
    """Create Discord embed for member events.

    Args:
        events: List of member events

    Returns:
        Discord embed or None if no events
    """
    if not events:
        return None

    # Sort events: public repos first, then by timestamp
    sorted_events = sorted(
        events,
        key=lambda e: (not e.is_public, e.event_timestamp),
        reverse=True,
    )

    # Limit to 10 events
    displayed_events = sorted_events[:10]
    overflow_count = len(sorted_events) - len(displayed_events)

    embed = discord.Embed(
        title=f"👥 {len(sorted_events)} Member Changes",
        color=MEMBER_COLOR,
        timestamp=datetime.now(UTC),
    )

    for event in displayed_events:
        unix_timestamp = int(event.event_timestamp.timestamp())
        repo_full_name = f"{event.repo_owner}/{event.repo_name}"

        action_emoji = "➕" if event.action == "added" else "➖"  # noqa: RUF001

        if event.is_public:
            field_name = f"{action_emoji} {repo_full_name}"
            field_value = (
                f"{event.member_username} {event.action} by {event.actor_username} - "
                f"<t:{unix_timestamp}:t>"
            )
        else:
            field_name = f"{action_emoji} {repo_full_name} [Private]"
            field_value = (
                f"{event.member_username} {event.action} by {event.actor_username} - "
                f"<t:{unix_timestamp}:t>"
            )

        embed.add_field(name=field_name, value=field_value, inline=False)

    if overflow_count > 0:
        embed.set_footer(text=f"+ {overflow_count} more not shown")

    return embed


def create_wiki_pages_embed(events: list[GollumEvent]) -> discord.Embed | None:
    """Create Discord embed for wiki page (Gollum) events.

    Args:
        events: List of wiki page events

    Returns:
        Discord embed or None if no events
    """
    if not events:
        return None

    # Sort events: public repos first, then by timestamp
    sorted_events = sorted(
        events,
        key=lambda e: (not e.is_public, e.event_timestamp),
        reverse=True,
    )

    # Limit to 10 events
    displayed_events = sorted_events[:10]
    overflow_count = len(sorted_events) - len(displayed_events)

    embed = discord.Embed(
        title=f"📚 {len(sorted_events)} Wiki Page Updates",
        color=WIKI_COLOR,
        timestamp=datetime.now(UTC),
    )

    for event in displayed_events:
        unix_timestamp = int(event.event_timestamp.timestamp())
        repo_full_name = f"{event.repo_owner}/{event.repo_name}"

        action_emoji = "📝" if event.action == "edited" else "✨"
        page_display = event.page_title or event.page_name

        if event.is_public and event.url:
            field_name = f"{action_emoji} {repo_full_name}"
            field_value = (
                f"[{page_display}]({event.url}) {event.action} by {event.editor_username} - "
                f"<t:{unix_timestamp}:t>"
            )
        elif event.is_public:
            field_name = f"{action_emoji} {repo_full_name}"
            field_value = (
                f"{page_display} {event.action} by {event.editor_username} - <t:{unix_timestamp}:t>"
            )
        else:
            field_name = f"{action_emoji} {repo_full_name} [Private]"
            field_value = (
                f"{page_display} {event.action} by {event.editor_username} - <t:{unix_timestamp}:t>"
            )

        embed.add_field(name=field_name, value=field_value, inline=False)

    if overflow_count > 0:
        embed.set_footer(text=f"+ {overflow_count} more not shown")

    return embed


def create_public_events_embed(events: list[PublicEvent]) -> discord.Embed | None:
    """Create Discord embed for public events (repo made public).

    Args:
        events: List of public events

    Returns:
        Discord embed or None if no events
    """
    if not events:
        return None

    # Sort events by timestamp (all are public by definition)
    sorted_events = sorted(
        events,
        key=lambda e: e.event_timestamp,
        reverse=True,
    )

    # Limit to 10 events
    displayed_events = sorted_events[:10]
    overflow_count = len(sorted_events) - len(displayed_events)

    embed = discord.Embed(
        title=f"🌐 {len(sorted_events)} Repositories Made Public",
        color=PUBLIC_COLOR,
        timestamp=datetime.now(UTC),
    )

    for event in displayed_events:
        unix_timestamp = int(event.event_timestamp.timestamp())
        repo_full_name = f"{event.repo_owner}/{event.repo_name}"

        field_name = f"🌐 {repo_full_name}"
        field_value = (
            f"Made public by {event.actor_username} - <t:{unix_timestamp}:t>\n"
            f"[View Repository](https://github.com/{repo_full_name})"
        )

        embed.add_field(name=field_name, value=field_value, inline=False)

    if overflow_count > 0:
        embed.set_footer(text=f"+ {overflow_count} more not shown")

    return embed


def create_discussions_embed(events: list[DiscussionEvent]) -> discord.Embed | None:
    """Create Discord embed for discussion events.

    Args:
        events: List of discussion events

    Returns:
        Discord embed or None if no events
    """
    if not events:
        return None

    # Sort events: public repos first, then by timestamp
    sorted_events = sorted(
        events,
        key=lambda e: (not e.is_public, e.event_timestamp),
        reverse=True,
    )

    # Limit to 10 events
    displayed_events = sorted_events[:10]
    overflow_count = len(sorted_events) - len(displayed_events)

    embed = discord.Embed(
        title=f"💭 {len(sorted_events)} Discussion Updates",
        color=DISCUSSION_COLOR,
        timestamp=datetime.now(UTC),
    )

    for event in displayed_events:
        unix_timestamp = int(event.event_timestamp.timestamp())
        repo_full_name = f"{event.repo_owner}/{event.repo_name}"

        category_info = f" in {event.category}" if event.category else ""
        title_display = event.discussion_title or f"Discussion #{event.discussion_number}"

        if event.is_public and event.url:
            field_name = f"💭 {repo_full_name}"
            field_value = (
                f"[{title_display}]({event.url}) {event.action}{category_info}\n"
                f"by {event.author_username} - <t:{unix_timestamp}:t>"
            )
        elif event.is_public:
            field_name = f"💭 {repo_full_name}"
            field_value = (
                f"{title_display} {event.action}{category_info}\n"
                f"by {event.author_username} - <t:{unix_timestamp}:t>"
            )
        else:
            field_name = f"💭 {repo_full_name} [Private]"
            field_value = (
                f"{title_display} {event.action}{category_info}\n"
                f"by {event.author_username} - <t:{unix_timestamp}:t>"
            )

        embed.add_field(name=field_name, value=field_value, inline=False)

    if overflow_count > 0:
        embed.set_footer(text=f"+ {overflow_count} more not shown")

    return embed
