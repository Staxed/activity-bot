"""Tests for Discord event embed builders."""

from datetime import UTC, datetime

from app.discord.event_colors import (
    CREATION_COLOR,
    DELETION_COLOR,
    FORK_COLOR,
    ISSUE_COLOR,
    PR_COLOR,
    RELEASE_COLOR,
    REVIEW_COLOR,
)
from app.discord.event_embeds import (
    MAX_DESCRIPTION_LENGTH,
    create_creations_embed,
    create_deletions_embed,
    create_forks_embed,
    create_issues_embed,
    create_prs_embed,
    create_releases_embed,
    create_reviews_embed,
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


# Test helpers for creating model instances
def create_test_pr(
    pr_number: int = 1,
    action: str = "opened",
    title: str = "Test PR",
    is_public: bool = True,
    timestamp: datetime | None = None,
) -> PullRequestEvent:
    """Create a test pull request event."""
    if timestamp is None:
        timestamp = datetime.now(UTC)

    return PullRequestEvent(
        event_id=f"pr_{pr_number}",
        pr_number=pr_number,
        action=action,
        title=title,
        state="open",
        merged=False,
        author_username="testuser",
        author_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=is_public,
        url=f"https://github.com/owner/repo/pull/{pr_number}",
        event_timestamp=timestamp,
    )


def create_test_issue(
    issue_number: int = 1,
    action: str = "opened",
    title: str = "Test Issue",
    is_public: bool = True,
    timestamp: datetime | None = None,
) -> IssuesEvent:
    """Create a test issue event."""
    if timestamp is None:
        timestamp = datetime.now(UTC)

    return IssuesEvent(
        event_id=f"issue_{issue_number}",
        issue_number=issue_number,
        action=action,
        title=title,
        state="open",
        author_username="testuser",
        author_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=is_public,
        url=f"https://github.com/owner/repo/issues/{issue_number}",
        event_timestamp=timestamp,
    )


def create_test_release(
    tag_name: str = "v1.0.0",
    release_name: str | None = "Release 1.0.0",
    is_prerelease: bool = False,
    is_public: bool = True,
    timestamp: datetime | None = None,
) -> ReleaseEvent:
    """Create a test release event."""
    if timestamp is None:
        timestamp = datetime.now(UTC)

    return ReleaseEvent(
        event_id=f"release_{tag_name}",
        tag_name=tag_name,
        release_name=release_name,
        author_username="testuser",
        author_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=is_public,
        is_prerelease=is_prerelease,
        url=f"https://github.com/owner/repo/releases/tag/{tag_name}",
        event_timestamp=timestamp,
    )


def create_test_review(
    pr_number: int = 1,
    review_state: str = "approved",
    is_public: bool = True,
    timestamp: datetime | None = None,
) -> PullRequestReviewEvent:
    """Create a test review event."""
    if timestamp is None:
        timestamp = datetime.now(UTC)

    return PullRequestReviewEvent(
        event_id=f"review_{pr_number}",
        pr_number=pr_number,
        action="created",
        review_state=review_state,
        reviewer_username="reviewer",
        reviewer_avatar_url="https://github.com/reviewer.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=is_public,
        url=f"https://github.com/owner/repo/pull/{pr_number}",
        event_timestamp=timestamp,
    )


def create_test_creation(
    ref_type: str = "branch",
    ref_name: str = "feature",
    is_public: bool = True,
    timestamp: datetime | None = None,
) -> CreateEvent:
    """Create a test creation event."""
    if timestamp is None:
        timestamp = datetime.now(UTC)

    return CreateEvent(
        event_id=f"create_{ref_name}",
        ref_type=ref_type,
        ref_name=ref_name,
        author_username="testuser",
        author_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=is_public,
        event_timestamp=timestamp,
    )


def create_test_deletion(
    ref_type: str = "branch",
    ref_name: str = "feature",
    is_public: bool = True,
    timestamp: datetime | None = None,
) -> DeleteEvent:
    """Create a test deletion event."""
    if timestamp is None:
        timestamp = datetime.now(UTC)

    return DeleteEvent(
        event_id=f"delete_{ref_name}",
        ref_type=ref_type,
        ref_name=ref_name,
        author_username="testuser",
        author_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=is_public,
        event_timestamp=timestamp,
    )


def create_test_fork(
    fork_repo_name: str = "forked-repo",
    is_public: bool = True,
    timestamp: datetime | None = None,
) -> ForkEvent:
    """Create a test fork event."""
    if timestamp is None:
        timestamp = datetime.now(UTC)

    return ForkEvent(
        event_id=f"fork_{fork_repo_name}",
        forker_username="testuser",
        forker_avatar_url="https://github.com/testuser.png",
        source_repo_owner="original",
        source_repo_name="repo",
        fork_repo_owner="testuser",
        fork_repo_name=fork_repo_name,
        fork_url=f"https://github.com/testuser/{fork_repo_name}",
        event_timestamp=timestamp,
    )


# Pull Request Embed Tests
def test_create_prs_embed_empty_list() -> None:
    """Test that empty PR list returns None."""
    result = create_prs_embed([])
    assert result is None


def test_create_prs_embed_single_pr() -> None:
    """Test creating embed for single PR."""
    prs = [create_test_pr()]
    embed = create_prs_embed(prs)

    assert embed is not None
    assert embed.title == "🔀 Pull Requests"
    assert embed.color.value == PR_COLOR
    assert "#1: Test PR" in embed.description
    assert "(opened)" in embed.description


def test_create_prs_embed_multiple_prs() -> None:
    """Test multiple PRs sorted by timestamp."""
    older = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    newer = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)

    prs = [
        create_test_pr(pr_number=1, timestamp=older),
        create_test_pr(pr_number=2, timestamp=newer),
    ]

    embed = create_prs_embed(prs)

    assert embed is not None
    # Newer PR should appear first in description
    assert embed.description.index("#2") < embed.description.index("#1")


def test_create_prs_embed_private_repo() -> None:
    """Test private repo labeling."""
    prs = [create_test_pr(is_public=False)]
    embed = create_prs_embed(prs)

    assert embed is not None
    assert "[Private Repo]" in embed.description


def test_create_prs_embed_overflow() -> None:
    """Test overflow footer when description exceeds limit."""
    # Create PRs with very long titles to trigger overflow
    long_title = "A" * 500
    prs = [create_test_pr(pr_number=i, title=long_title) for i in range(20)]

    embed = create_prs_embed(prs)

    assert embed is not None
    # Should have overflow footer
    if embed.footer and embed.footer.text:
        assert "more pull request(s)" in embed.footer.text


# Issue Embed Tests
def test_create_issues_embed_empty_list() -> None:
    """Test that empty issue list returns None."""
    result = create_issues_embed([])
    assert result is None


def test_create_issues_embed_single_issue() -> None:
    """Test creating embed for single issue."""
    issues = [create_test_issue()]
    embed = create_issues_embed(issues)

    assert embed is not None
    assert embed.title == "🐛 Issues"
    assert embed.color.value == ISSUE_COLOR
    assert "#1: Test Issue" in embed.description
    assert "(opened)" in embed.description


def test_create_issues_embed_multiple_actions() -> None:
    """Test issues with different actions."""
    issues = [
        create_test_issue(issue_number=1, action="opened"),
        create_test_issue(issue_number=2, action="closed"),
        create_test_issue(issue_number=3, action="reopened"),
    ]

    embed = create_issues_embed(issues)

    assert embed is not None
    assert "(opened)" in embed.description
    assert "(closed)" in embed.description
    assert "(reopened)" in embed.description


def test_create_issues_embed_private_repo() -> None:
    """Test private repo labeling for issues."""
    issues = [create_test_issue(is_public=False)]
    embed = create_issues_embed(issues)

    assert embed is not None
    assert "[Private Repo]" in embed.description


# Release Embed Tests
def test_create_releases_embed_empty_list() -> None:
    """Test that empty release list returns None."""
    result = create_releases_embed([])
    assert result is None


def test_create_releases_embed_single_release() -> None:
    """Test creating embed for single release."""
    releases = [create_test_release()]
    embed = create_releases_embed(releases)

    assert embed is not None
    assert embed.title == "🚀 Releases"
    assert embed.color.value == RELEASE_COLOR
    assert "v1.0.0" in embed.description
    assert "Release 1.0.0" in embed.description


def test_create_releases_embed_prerelease() -> None:
    """Test prerelease labeling."""
    releases = [create_test_release(tag_name="v2.0.0-beta", is_prerelease=True)]
    embed = create_releases_embed(releases)

    assert embed is not None
    assert "(prerelease)" in embed.description


def test_create_releases_embed_no_release_name() -> None:
    """Test release with only tag name."""
    releases = [create_test_release(release_name=None)]
    embed = create_releases_embed(releases)

    assert embed is not None
    # Should use tag_name as fallback
    assert "v1.0.0" in embed.description


def test_create_releases_embed_private_repo() -> None:
    """Test private repo labeling for releases."""
    releases = [create_test_release(is_public=False)]
    embed = create_releases_embed(releases)

    assert embed is not None
    assert "[Private Repo]" in embed.description


# Review Embed Tests
def test_create_reviews_embed_empty_list() -> None:
    """Test that empty review list returns None."""
    result = create_reviews_embed([])
    assert result is None


def test_create_reviews_embed_single_review() -> None:
    """Test creating embed for single review."""
    reviews = [create_test_review()]
    embed = create_reviews_embed(reviews)

    assert embed is not None
    assert embed.title == "👀 Pull Request Reviews"
    assert embed.color.value == REVIEW_COLOR
    assert "PR #1" in embed.description
    assert "(approved)" in embed.description


def test_create_reviews_embed_approved_emoji() -> None:
    """Test that approved reviews have checkmark emoji."""
    reviews = [create_test_review(review_state="approved")]
    embed = create_reviews_embed(reviews)

    assert embed is not None
    assert "✅" in embed.description


def test_create_reviews_embed_changes_requested_emoji() -> None:
    """Test that changes_requested reviews have cycle emoji."""
    reviews = [create_test_review(review_state="changes_requested")]
    embed = create_reviews_embed(reviews)

    assert embed is not None
    assert "🔄" in embed.description


def test_create_reviews_embed_private_repo() -> None:
    """Test private repo labeling for reviews."""
    reviews = [create_test_review(is_public=False)]
    embed = create_reviews_embed(reviews)

    assert embed is not None
    assert "[Private Repo]" in embed.description


# Creation Embed Tests
def test_create_creations_embed_empty_list() -> None:
    """Test that empty creation list returns None."""
    result = create_creations_embed([])
    assert result is None


def test_create_creations_embed_single_creation() -> None:
    """Test creating embed for single creation."""
    creations = [create_test_creation()]
    embed = create_creations_embed(creations)

    assert embed is not None
    assert embed.title == "🌱 Creations"
    assert embed.color.value == CREATION_COLOR
    assert "Created branch `feature`" in embed.description


def test_create_creations_embed_different_ref_types() -> None:
    """Test creations with different ref types."""
    creations = [
        create_test_creation(ref_type="branch", ref_name="feature"),
        create_test_creation(ref_type="tag", ref_name="v1.0.0"),
    ]

    embed = create_creations_embed(creations)

    assert embed is not None
    assert "Created branch `feature`" in embed.description
    assert "Created tag `v1.0.0`" in embed.description


def test_create_creations_embed_private_repo() -> None:
    """Test private repo labeling for creations."""
    creations = [create_test_creation(is_public=False)]
    embed = create_creations_embed(creations)

    assert embed is not None
    assert "[Private Repo]" in embed.description


# Deletion Embed Tests
def test_create_deletions_embed_empty_list() -> None:
    """Test that empty deletion list returns None."""
    result = create_deletions_embed([])
    assert result is None


def test_create_deletions_embed_single_deletion() -> None:
    """Test creating embed for single deletion."""
    deletions = [create_test_deletion()]
    embed = create_deletions_embed(deletions)

    assert embed is not None
    assert embed.title == "🗑️ Deletions"
    assert embed.color.value == DELETION_COLOR
    assert "Deleted branch `feature`" in embed.description


def test_create_deletions_embed_different_ref_types() -> None:
    """Test deletions with different ref types."""
    deletions = [
        create_test_deletion(ref_type="branch", ref_name="old-feature"),
        create_test_deletion(ref_type="tag", ref_name="v0.9.0"),
    ]

    embed = create_deletions_embed(deletions)

    assert embed is not None
    assert "Deleted branch `old-feature`" in embed.description
    assert "Deleted tag `v0.9.0`" in embed.description


def test_create_deletions_embed_private_repo() -> None:
    """Test private repo labeling for deletions."""
    deletions = [create_test_deletion(is_public=False)]
    embed = create_deletions_embed(deletions)

    assert embed is not None
    assert "[Private Repo]" in embed.description


# Fork Embed Tests
def test_create_forks_embed_empty_list() -> None:
    """Test that empty fork list returns None."""
    result = create_forks_embed([])
    assert result is None


def test_create_forks_embed_single_fork() -> None:
    """Test creating embed for single fork."""
    forks = [create_test_fork()]
    embed = create_forks_embed(forks)

    assert embed is not None
    assert embed.title == "🍴 Forks"
    assert embed.color.value == FORK_COLOR
    assert "Forked original/repo" in embed.description
    assert "testuser/forked-repo" in embed.description


def test_create_forks_embed_with_url() -> None:
    """Test fork with URL creates link."""
    forks = [create_test_fork()]
    embed = create_forks_embed(forks)

    assert embed is not None
    assert "[testuser/forked-repo]" in embed.description


def test_create_forks_embed_no_url() -> None:
    """Test fork without URL."""
    fork = create_test_fork()
    fork.fork_url = None
    forks = [fork]

    embed = create_forks_embed(forks)

    assert embed is not None
    # Should not have link brackets
    assert "→ testuser/forked-repo" in embed.description


# Timestamp Tests
def test_all_embeds_use_latest_timestamp() -> None:
    """Test that all embeds use the newest event timestamp."""
    older = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    newer = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)

    # Test PRs
    prs = [create_test_pr(timestamp=older), create_test_pr(timestamp=newer)]
    pr_embed = create_prs_embed(prs)
    assert pr_embed is not None
    assert pr_embed.timestamp == newer

    # Test Issues
    issues = [create_test_issue(timestamp=older), create_test_issue(timestamp=newer)]
    issue_embed = create_issues_embed(issues)
    assert issue_embed is not None
    assert issue_embed.timestamp == newer

    # Test Releases
    releases = [
        create_test_release(tag_name="v1.0", timestamp=older),
        create_test_release(tag_name="v2.0", timestamp=newer),
    ]
    release_embed = create_releases_embed(releases)
    assert release_embed is not None
    assert release_embed.timestamp == newer


# Overflow Tests
def test_prs_embed_description_length_limit() -> None:
    """Test that PR embed description doesn't exceed Discord limit."""
    # Create many PRs with long titles
    long_title = "X" * 200
    prs = [create_test_pr(pr_number=i, title=long_title) for i in range(100)]

    embed = create_prs_embed(prs)

    assert embed is not None
    assert len(embed.description) <= MAX_DESCRIPTION_LENGTH


def test_issues_embed_description_length_limit() -> None:
    """Test that issue embed description doesn't exceed Discord limit."""
    long_title = "X" * 200
    issues = [create_test_issue(issue_number=i, title=long_title) for i in range(100)]

    embed = create_issues_embed(issues)

    assert embed is not None
    assert len(embed.description) <= MAX_DESCRIPTION_LENGTH


def test_creations_embed_description_length_limit() -> None:
    """Test that creation embed description doesn't exceed Discord limit."""
    long_name = "X" * 200
    creations = [create_test_creation(ref_name=f"{long_name}-{i}") for i in range(100)]

    embed = create_creations_embed(creations)

    assert embed is not None
    assert len(embed.description) <= MAX_DESCRIPTION_LENGTH
