"""Discord posting service with retry logic and queue management."""

import asyncio
from datetime import datetime

import discord

from app.core.config import Settings
from app.core.logging import get_logger
from app.discord.bot import DiscordBot
from app.discord.embeds import create_commits_embed
from app.discord.event_embeds import (
    create_creations_embed,
    create_deletions_embed,
    create_forks_embed,
    create_issues_embed,
    create_prs_embed,
    create_releases_embed,
    create_reviews_embed,
)
from app.discord.event_grouping import UserEvents, group_events_by_user
from app.discord.summary_embed import create_summary_embed
from app.shared.exceptions import DiscordAPIError
from app.shared.models import (
    CommitEvent,
    CreateEvent,
    DeleteEvent,
    ForkEvent,
    IssuesEvent,
    PullRequestEvent,
    PullRequestReviewEvent,
    ReleaseEvent,
)

logger = get_logger(__name__)


class DiscordPoster:
    """Discord posting service with retry logic and failure queue.

    Handles posting commit embeds to Discord with automatic retry on failure.
    Failed posts are queued and merged by author on next attempt.
    """

    MAX_RETRIES = 2
    RETRY_DELAYS = [2, 4]  # Exponential backoff: 2s, 4s

    def __init__(self, bot: DiscordBot) -> None:
        """Initialize Discord poster with bot instance.

        Args:
            bot: Initialized DiscordBot instance
        """
        self.bot = bot
        self.queue: list[CommitEvent] = []

    async def post_commits(self, commits: list[CommitEvent]) -> None:
        """Post commits to Discord (backward compatibility wrapper).

        Args:
            commits: List of commit events to post
        """
        # Call post_all_events with only commits
        await self.post_all_events(
            commits=commits,
            prs=[],
            issues=[],
            releases=[],
            reviews=[],
            creations=[],
            deletions=[],
            forks=[],
            settings=Settings(),  # type: ignore[call-arg]
        )

    async def post_all_events(
        self,
        commits: list[CommitEvent],
        prs: list[PullRequestEvent],
        issues: list[IssuesEvent],
        releases: list[ReleaseEvent],
        reviews: list[PullRequestReviewEvent],
        creations: list[CreateEvent],
        deletions: list[DeleteEvent],
        forks: list[ForkEvent],
        settings: Settings,
    ) -> None:
        """Post all event types to Discord, grouped by user.

        Args:
            commits: List of commit events
            prs: List of pull request events
            issues: List of issue events
            releases: List of release events
            reviews: List of review events
            creations: List of creation events
            deletions: List of deletion events
            forks: List of fork events
            settings: Settings instance for event toggles
        """
        # Group events by user
        grouped_events = group_events_by_user(
            commits, prs, issues, releases, reviews, creations, deletions, forks
        )

        if not grouped_events:
            logger.info("discord.post.skip", reason="no_events")
            return

        logger.info("discord.post.started", users=len(grouped_events))

        # Post each user's events
        for username, events in grouped_events.items():
            try:
                # Build embeds list
                embeds: list[discord.Embed] = []

                # Get user metadata
                affected_repos = self._extract_affected_repos(events)
                latest_timestamp = self._get_latest_timestamp(events)
                avatar_url = self._get_user_avatar(events)

                # Build event counts for summary
                event_counts = {
                    "commits": len(events.commits),
                    "pull_requests": len(events.pull_requests),
                    "issues": len(events.issues),
                    "releases": len(events.releases),
                    "reviews": len(events.reviews),
                    "creations": len(events.creations),
                    "deletions": len(events.deletions),
                    "forks": len(events.forks),
                }

                # Add summary embed
                summary = create_summary_embed(
                    username, avatar_url, event_counts, affected_repos, latest_timestamp
                )
                embeds.append(summary)

                # Add event type embeds (if enabled) - ordered by priority
                if settings.post_releases:
                    release_embed = create_releases_embed(events.releases)
                    if release_embed:
                        embeds.append(release_embed)

                if settings.post_pull_requests:
                    pr_embed = create_prs_embed(events.pull_requests)
                    if pr_embed:
                        embeds.append(pr_embed)

                if settings.post_commits:
                    commit_embed = create_commits_embed(events.commits)
                    if commit_embed:
                        embeds.append(commit_embed)

                if settings.post_reviews:
                    review_embed = create_reviews_embed(events.reviews)
                    if review_embed:
                        embeds.append(review_embed)

                if settings.post_issues:
                    issue_embed = create_issues_embed(events.issues)
                    if issue_embed:
                        embeds.append(issue_embed)

                if settings.post_forks:
                    fork_embed = create_forks_embed(events.forks)
                    if fork_embed:
                        embeds.append(fork_embed)

                if settings.post_creations:
                    creation_embed = create_creations_embed(events.creations)
                    if creation_embed:
                        embeds.append(creation_embed)

                if settings.post_deletions:
                    deletion_embed = create_deletions_embed(events.deletions)
                    if deletion_embed:
                        embeds.append(deletion_embed)

                # Enforce 10-embed limit
                if len(embeds) > 10:
                    logger.warning(
                        "discord.post.embed_limit_exceeded",
                        username=username,
                        total_embeds=len(embeds),
                        truncated_to=10,
                    )
                    embeds = embeds[:10]

                # Send single message with all embeds
                channel = self.bot.get_channel()
                await channel.send(embeds=embeds)

                logger.info(
                    "discord.post.user.success",
                    username=username,
                    embeds=len(embeds),
                    total_events=sum(event_counts.values()),
                )

            except Exception as e:
                logger.error(
                    "discord.post.user.failed",
                    username=username,
                    error=str(e),
                    exc_info=True,
                )

        logger.info("discord.post.complete")

    def _extract_affected_repos(self, events: UserEvents) -> list[tuple[str, bool]]:
        """Extract unique repositories from all event types.

        Args:
            events: UserEvents containing all event types

        Returns:
            List of (repo_full_name, is_public) tuples
        """
        repos: dict[str, bool] = {}

        # Extract from commits
        for commit in events.commits:
            repo_key = f"{commit.repo_owner}/{commit.repo_name}"
            repos[repo_key] = commit.is_public

        # Extract from PRs
        for pr in events.pull_requests:
            repo_key = f"{pr.repo_owner}/{pr.repo_name}"
            repos[repo_key] = pr.is_public

        # Extract from issues
        for issue in events.issues:
            repo_key = f"{issue.repo_owner}/{issue.repo_name}"
            repos[repo_key] = issue.is_public

        # Extract from releases
        for release in events.releases:
            repo_key = f"{release.repo_owner}/{release.repo_name}"
            repos[repo_key] = release.is_public

        # Extract from reviews
        for review in events.reviews:
            repo_key = f"{review.repo_owner}/{review.repo_name}"
            repos[repo_key] = review.is_public

        # Extract from creations
        for creation in events.creations:
            repo_key = f"{creation.repo_owner}/{creation.repo_name}"
            repos[repo_key] = creation.is_public

        # Extract from deletions
        for deletion in events.deletions:
            repo_key = f"{deletion.repo_owner}/{deletion.repo_name}"
            repos[repo_key] = deletion.is_public

        # Extract from forks (source repo)
        for fork in events.forks:
            repo_key = f"{fork.source_repo_owner}/{fork.source_repo_name}"
            repos[repo_key] = fork.is_public

        # Sort: public repos first, then private repos (alphabetically within each group)
        sorted_repos = sorted(repos.items(), key=lambda x: (not x[1], x[0]))
        return sorted_repos

    def _get_latest_timestamp(self, events: UserEvents) -> datetime:
        """Get the latest timestamp across all events.

        Args:
            events: UserEvents containing all event types

        Returns:
            Latest timestamp found, or current time if no events
        """
        timestamps: list[datetime] = []

        for commit in events.commits:
            timestamps.append(commit.timestamp)
        for pr in events.pull_requests:
            timestamps.append(pr.event_timestamp)
        for issue in events.issues:
            timestamps.append(issue.event_timestamp)
        for release in events.releases:
            timestamps.append(release.event_timestamp)
        for review in events.reviews:
            timestamps.append(review.event_timestamp)
        for creation in events.creations:
            timestamps.append(creation.event_timestamp)
        for deletion in events.deletions:
            timestamps.append(deletion.event_timestamp)
        for fork in events.forks:
            timestamps.append(fork.event_timestamp)

        return max(timestamps) if timestamps else datetime.now()

    def _get_user_avatar(self, events: UserEvents) -> str:
        """Get user avatar URL from first available event.

        Args:
            events: UserEvents containing all event types

        Returns:
            Avatar URL, or default GitHub avatar if none found
        """
        # Try commits first
        if events.commits:
            return events.commits[0].author_avatar_url

        # Try PRs
        if events.pull_requests:
            return events.pull_requests[0].author_avatar_url

        # Try issues
        if events.issues:
            return events.issues[0].author_avatar_url

        # Try releases
        if events.releases:
            return events.releases[0].author_avatar_url

        # Try reviews
        if events.reviews:
            return events.reviews[0].reviewer_avatar_url

        # Try creations
        if events.creations:
            return events.creations[0].author_avatar_url

        # Try deletions
        if events.deletions:
            return events.deletions[0].author_avatar_url

        # Try forks
        if events.forks:
            return events.forks[0].forker_avatar_url

        # Fallback
        return "https://github.com/github.png"

    async def _post_embed_with_retry(self, embed: discord.Embed) -> None:
        """Post a single embed with retry logic.

        Args:
            embed: Discord embed to post

        Raises:
            DiscordAPIError: If posting fails after all retries
        """
        channel = self.bot.get_channel()

        for attempt in range(self.MAX_RETRIES):
            try:
                await channel.send(embed=embed)
                return

            except discord.HTTPException as e:
                # Handle rate limiting (429)
                if e.status == 429:
                    retry_after = getattr(e, "retry_after", self.RETRY_DELAYS[min(attempt, 1)])
                    logger.warning(
                        "discord.ratelimit.hit",
                        retry_after=retry_after,
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(retry_after)

                elif attempt < self.MAX_RETRIES - 1:
                    # Generic HTTP error with retry
                    delay = self.RETRY_DELAYS[attempt]
                    logger.warning(
                        "discord.post.retry",
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

                else:
                    # Max retries exhausted
                    logger.error(
                        "discord.post.failed",
                        attempts=self.MAX_RETRIES,
                        error=str(e),
                        exc_info=True,
                    )
                    raise DiscordAPIError(
                        f"Failed to post embed after {self.MAX_RETRIES} retries"
                    ) from e

            except Exception as e:
                # Non-HTTP exception
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    logger.warning(
                        "discord.post.retry",
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "discord.post.failed",
                        attempts=self.MAX_RETRIES,
                        error=str(e),
                        exc_info=True,
                    )
                    raise DiscordAPIError(
                        f"Failed to post embed after {self.MAX_RETRIES} retries"
                    ) from e
