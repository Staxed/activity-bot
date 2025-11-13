#!/usr/bin/env python3
"""Test script to generate fakeevents and post to Discord."""

import asyncio
import os
from datetime import datetime, timedelta, UTC
from pathlib import Path

# Load .env file from script directory
from dotenv import load_dotenv

script_dir = Path(__file__).parent
env_path = script_dir / ".env"
load_dotenv(env_path)

from app.core.config import get_settings
from app.discord.bot import DiscordBot
from app.discord.poster import DiscordPoster
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

# Mock the quote service to avoid needing database
class MockQuoteService:
    """Mock quote service for testing."""
    def get_random_quote(self) -> str:
        return "💻 First, solve the problem. Then, write the code. - John Johnson"

import app.discord.quotes as quotes_module
_mock_service = MockQuoteService()
quotes_module._quote_service = _mock_service
quotes_module.get_random_quote = lambda: _mock_service.get_random_quote()


def create_fake_commits(count: int = 15) -> list[CommitEvent]:
    """Generate fake commit events."""
    commits = []
    base_time = datetime.now(UTC)

    for i in range(count):
        sha = f"abc123def456{i:04d}"
        # Make at least one private (first one)
        is_public = i != 0
        commits.append(
            CommitEvent(
                sha=sha,
                short_sha=sha[:7],
                author="Staxed",
                author_email="staxed@example.com",
                author_avatar_url="https://avatars.githubusercontent.com/u/12345678",
                author_username="Staxed",
                message=f"feat: add awesome feature #{i+1}",
                message_body=f"feat: add awesome feature #{i+1}\n\nThis is a detailed description of the feature.",
                repo_owner="Staxed",
                repo_name="test-repo",
                branch="main",
                timestamp=base_time - timedelta(minutes=i),
                url=f"https://github.com/Staxed/test-repo/commit/{sha[:7]}",
                is_public=is_public,
            )
        )

    return commits


def create_fake_prs(count: int = 15) -> list[PullRequestEvent]:
    """Generate fake pull request events."""
    prs = []
    base_time = datetime.now(UTC)
    actions = ["opened", "closed", "merged", "reopened"]

    for i in range(count):
        action = actions[i % len(actions)]
        is_merged = action == "merged"
        state = "closed" if action in ["closed", "merged"] else "open"
        # Make at least one private (first one)
        is_public = i != 0

        prs.append(
            PullRequestEvent(
                event_id=f"fake_pr_{i}",
                pr_number=100 + i,
                action=action,
                title=f"Add new feature: Test PR #{i+1}",
                state=state,
                merged=is_merged,
                author_username="Staxed",
                author_avatar_url="https://avatars.githubusercontent.com/u/12345678",
                repo_owner="Staxed",
                repo_name="test-repo",
                is_public=is_public,
                url=f"https://github.com/Staxed/test-repo/pull/{100+i}",
                event_timestamp=base_time - timedelta(minutes=i),
            )
        )

    return prs


def create_fake_issues(count: int = 15) -> list[IssuesEvent]:
    """Generate fake issue events."""
    issues = []
    base_time = datetime.now(UTC)
    actions = ["opened", "closed", "reopened"]

    for i in range(count):
        action = actions[i % len(actions)]
        state = "closed" if action == "closed" else "open"
        # Make at least one private (first one)
        is_public = i != 0

        issues.append(
            IssuesEvent(
                event_id=f"fake_issue_{i}",
                issue_number=200 + i,
                action=action,
                title=f"Bug: Fix issue #{i+1}",
                state=state,
                author_username="Staxed",
                author_avatar_url="https://avatars.githubusercontent.com/u/12345678",
                repo_owner="Staxed",
                repo_name="test-repo",
                is_public=is_public,
                url=f"https://github.com/Staxed/test-repo/issues/{200+i}",
                event_timestamp=base_time - timedelta(minutes=i),
            )
        )

    return issues


def create_fake_releases(count: int = 15) -> list[ReleaseEvent]:
    """Generate fake release events."""
    releases = []
    base_time = datetime.now(UTC)

    for i in range(count):
        # Make at least one private (first one)
        is_public = i != 0
        releases.append(
            ReleaseEvent(
                event_id=f"fake_release_{i}",
                tag_name=f"v1.{i}.0",
                release_name=f"Release v1.{i}.0 - Test Release",
                author_username="Staxed",
                author_avatar_url="https://avatars.githubusercontent.com/u/12345678",
                repo_owner="Staxed",
                repo_name="test-repo",
                is_public=is_public,
                url=f"https://github.com/Staxed/test-repo/releases/tag/v1.{i}.0",
                event_timestamp=base_time - timedelta(hours=i),
            )
        )

    return releases


def create_fake_reviews(count: int = 15) -> list[PullRequestReviewEvent]:
    """Generate fake PR review events."""
    reviews = []
    base_time = datetime.now(UTC)
    states = ["approved", "changes_requested", "commented"]

    for i in range(count):
        state = states[i % len(states)]
        # Make at least one private (first one)
        is_public = i != 0
        reviews.append(
            PullRequestReviewEvent(
                event_id=f"fake_review_{i}",
                pr_number=300 + i,
                action="created",
                pr_title=f"PR for review #{i+1}",
                review_state=state,
                reviewer_username="Staxed",
                reviewer_avatar_url="https://avatars.githubusercontent.com/u/12345678",
                repo_owner="Staxed",
                repo_name="test-repo",
                is_public=is_public,
                url=f"https://github.com/Staxed/test-repo/pull/{300+i}",
                event_timestamp=base_time - timedelta(minutes=i),
            )
        )

    return reviews


def create_fake_creations(count: int = 15) -> list[CreateEvent]:
    """Generate fake creation events."""
    creations = []
    base_time = datetime.now(UTC)
    ref_types = ["branch", "tag", "repository"]

    for i in range(count):
        ref_type = ref_types[i % len(ref_types)]
        ref_name = f"feature-{i}" if ref_type == "branch" else f"v1.{i}.0" if ref_type == "tag" else None
        # Make at least one private (first one)
        is_public = i != 0

        creations.append(
            CreateEvent(
                event_id=f"fake_creation_{i}",
                ref_type=ref_type,
                ref_name=ref_name,
                author_username="Staxed",
                author_avatar_url="https://avatars.githubusercontent.com/u/12345678",
                repo_owner="Staxed",
                repo_name=f"test-repo-{i}" if ref_type == "repository" else "test-repo",
                is_public=is_public,
                event_timestamp=base_time - timedelta(minutes=i),
            )
        )

    return creations


def create_fake_deletions(count: int = 15) -> list[DeleteEvent]:
    """Generate fake deletion events."""
    deletions = []
    base_time = datetime.now(UTC)
    ref_types = ["branch", "tag"]

    for i in range(count):
        ref_type = ref_types[i % len(ref_types)]
        ref_name = f"old-feature-{i}" if ref_type == "branch" else f"v0.{i}.0"
        # Make at least one private (first one)
        is_public = i != 0

        deletions.append(
            DeleteEvent(
                event_id=f"fake_deletion_{i}",
                ref_type=ref_type,
                ref_name=ref_name,
                author_username="Staxed",
                author_avatar_url="https://avatars.githubusercontent.com/u/12345678",
                repo_owner="Staxed",
                repo_name="test-repo",
                is_public=is_public,
                event_timestamp=base_time - timedelta(minutes=i),
            )
        )

    return deletions


def create_fake_forks(count: int = 15) -> list[ForkEvent]:
    """Generate fake fork events."""
    forks = []
    base_time = datetime.now(UTC)

    for i in range(count):
        # Make at least one private (first one)
        is_public = i != 0
        forks.append(
            ForkEvent(
                event_id=f"fake_fork_{i}",
                forker_username="Staxed",
                forker_avatar_url="https://avatars.githubusercontent.com/u/12345678",
                source_repo_owner=f"upstream-org-{i}",
                source_repo_name="awesome-repo",
                fork_repo_owner="Staxed",
                fork_repo_name="awesome-repo",
                is_public=is_public,
                fork_url=f"https://github.com/Staxed/awesome-repo",
                event_timestamp=base_time - timedelta(minutes=i),
            )
        )

    return forks


async def main() -> None:
    """Generate and post fake events to Discord."""
    print("🚀 Generating fake events...")

    # Generate 3 of each event type (24 total)
    # First one of each type will be private
    commits = create_fake_commits(3)
    prs = create_fake_prs(3)
    issues = create_fake_issues(3)
    releases = create_fake_releases(3)
    reviews = create_fake_reviews(3)
    creations = create_fake_creations(3)
    deletions = create_fake_deletions(3)
    forks = create_fake_forks(3)

    print(f"✅ Generated {len(commits)} commits")
    print(f"✅ Generated {len(prs)} pull requests")
    print(f"✅ Generated {len(issues)} issues")
    print(f"✅ Generated {len(releases)} releases")
    print(f"✅ Generated {len(reviews)} reviews")
    print(f"✅ Generated {len(creations)} creations")
    print(f"✅ Generated {len(deletions)} deletions")
    print(f"✅ Generated {len(forks)} forks")
    print(f"📊 Total: {len(commits) + len(prs) + len(issues) + len(releases) + len(reviews) + len(creations) + len(deletions) + len(forks)} events")

    # Load settings
    settings = get_settings()

    print("\n🤖 Initializing Discord bot...")

    # Initialize Discord bot
    discord_bot = DiscordBot(settings.discord_token, settings.discord_channel_id)
    await discord_bot.__aenter__()

    try:
        # Create poster
        poster = DiscordPoster(discord_bot)

        print("📤 Posting events to Discord...")
        print(f"📍 Channel ID: {settings.discord_channel_id}")

        # Pre-calculate embed sizes by importing the embed creation functions
        from app.discord.event_embeds import (
            create_prs_embed,
            create_issues_embed,
            create_releases_embed,
            create_reviews_embed,
            create_creations_embed,
            create_deletions_embed,
            create_forks_embed,
        )
        from app.discord.embeds import create_commits_embed
        from app.discord.summary_embed import create_summary_embed

        # Calculate total size
        test_embeds = []

        # Build event counts dict
        event_counts = {}
        if commits:
            event_counts['commits'] = len(commits)
        if prs:
            event_counts['pull_requests'] = len(prs)
        if issues:
            event_counts['issues'] = len(issues)
        if releases:
            event_counts['releases'] = len(releases)
        if reviews:
            event_counts['reviews'] = len(reviews)
        if creations:
            event_counts['creations'] = len(creations)
        if deletions:
            event_counts['deletions'] = len(deletions)
        if forks:
            event_counts['forks'] = len(forks)

        # Get affected repos (simplified for test)
        affected_repos = [("Staxed/test-repo", True)]

        test_embeds.append(create_summary_embed(
            username="Staxed",
            avatar_url="https://avatars.githubusercontent.com/u/12345678",
            event_counts=event_counts,
            affected_repos=affected_repos,
            timestamp=datetime.now(UTC)
        ))
        if commits:
            test_embeds.append(create_commits_embed(commits))
        if prs:
            test_embeds.append(create_prs_embed(prs))
        if issues:
            test_embeds.append(create_issues_embed(issues))
        if releases:
            test_embeds.append(create_releases_embed(releases))
        if reviews:
            test_embeds.append(create_reviews_embed(reviews))
        if creations:
            test_embeds.append(create_creations_embed(creations))
        if deletions:
            test_embeds.append(create_deletions_embed(deletions))
        if forks:
            test_embeds.append(create_forks_embed(forks))

        total_chars = sum(len(str(embed.to_dict())) for embed in test_embeds if embed)
        print(f"📊 About to send {len([e for e in test_embeds if e])} embeds with ~{total_chars} total characters (limit: 6000)")

        # Post all events
        await poster.post_all_events(
            commits=commits,
            prs=prs,
            issues=issues,
            releases=releases,
            reviews=reviews,
            creations=creations,
            deletions=deletions,
            forks=forks,
            settings=settings,
        )

        print("✅ All events posted successfully!")
        print("\n💡 Check your Discord channel to see what a maxed-out message looks like!")

    except Exception as e:
        print(f"❌ Error posting events: {e}")
        raise

    finally:
        # Cleanup
        print("\n🧹 Cleaning up...")
        await discord_bot.__aexit__(None, None, None)
        print("👋 Done!")


if __name__ == "__main__":
    asyncio.run(main())
