"""Tests for Discord embed creation and grouping logic."""

from datetime import UTC, datetime

from app.discord.embeds import (
    create_commit_embeds,
    format_commit_time,
    group_commits_by_author,
    truncate_message,
)
from app.shared.models import CommitEvent


def create_test_commit(
    author: str = "TestAuthor",
    repo_owner: str = "owner",
    repo_name: str = "repo",
    message: str = "Test commit",
    branch: str = "main",
    timestamp: datetime | None = None,
) -> CommitEvent:
    """Create a test commit event.

    Args:
        author: Commit author name
        repo_owner: Repository owner
        repo_name: Repository name
        message: Commit message
        branch: Branch name
        timestamp: Commit timestamp (defaults to now)

    Returns:
        CommitEvent for testing
    """
    if timestamp is None:
        timestamp = datetime.now(UTC)

    return CommitEvent(
        sha="a" * 40,
        short_sha="a" * 7,
        author=author,
        author_email=f"{author.lower()}@example.com",
        message=message,
        message_body=message,
        repo_owner=repo_owner,
        repo_name=repo_name,
        timestamp=timestamp,
        url=f"https://github.com/{repo_owner}/{repo_name}/commit/{'a' * 40}",
        branch=branch,
    )


def test_group_commits_by_author_empty_list() -> None:
    """Test grouping empty commit list returns empty dict."""
    result = group_commits_by_author([])
    assert result == {}


def test_group_commits_by_author_single_author_single_repo() -> None:
    """Test basic grouping with one author and one repo."""
    commits = [create_test_commit(author="Alice", repo_name="backend")]

    result = group_commits_by_author(commits)

    assert "Alice" in result
    assert "owner/backend" in result["Alice"]
    assert len(result["Alice"]["owner/backend"]) == 1


def test_group_commits_by_author_single_author_multiple_repos() -> None:
    """Test grouping multiple repos under one author."""
    commits = [
        create_test_commit(author="Alice", repo_name="backend"),
        create_test_commit(author="Alice", repo_name="frontend"),
    ]

    result = group_commits_by_author(commits)

    assert "Alice" in result
    assert "owner/backend" in result["Alice"]
    assert "owner/frontend" in result["Alice"]
    assert len(result["Alice"]) == 2


def test_group_commits_by_author_multiple_authors() -> None:
    """Test grouping with multiple authors and mixed repos."""
    commits = [
        create_test_commit(author="Alice", repo_name="backend"),
        create_test_commit(author="Bob", repo_name="backend"),
        create_test_commit(author="Alice", repo_name="frontend"),
    ]

    result = group_commits_by_author(commits)

    assert "Alice" in result
    assert "Bob" in result
    assert "owner/backend" in result["Alice"]
    assert "owner/frontend" in result["Alice"]
    assert "owner/backend" in result["Bob"]


def test_truncate_message_under_limit() -> None:
    """Test message unchanged if under limit."""
    message = "Short message"
    result = truncate_message(message, max_length=200)
    assert result == message


def test_truncate_message_exactly_at_limit() -> None:
    """Test no truncation at exact limit."""
    message = "x" * 200
    result = truncate_message(message, max_length=200)
    assert result == message


def test_truncate_message_over_limit() -> None:
    """Test truncation adds ellipsis and respects length."""
    message = "x" * 250
    result = truncate_message(message, max_length=200)
    assert result.endswith("...")
    assert len(result) == 200


def test_format_commit_time_today() -> None:
    """Test formatting for commits made today."""
    now = datetime.now(UTC)
    result = format_commit_time(now)

    # Should only contain time, not date
    assert ":" in result
    assert any(suffix in result for suffix in ["AM", "PM"])


def test_format_commit_time_this_year() -> None:
    """Test formatting for commits this year but not today."""
    # Create a timestamp from 30 days ago
    now = datetime.now(UTC)
    timestamp = now.replace(month=max(1, now.month - 1))

    result = format_commit_time(timestamp)

    # Should contain month and day
    assert "at" in result
    assert any(suffix in result for suffix in ["AM", "PM"])


def test_format_commit_time_past_year() -> None:
    """Test formatting for commits from past years."""
    timestamp = datetime(2023, 6, 15, 14, 30, tzinfo=UTC)
    result = format_commit_time(timestamp)

    # Should contain full date with year
    assert "2023" in result
    assert "at" in result


def test_create_commit_embeds_single_commit() -> None:
    """Test creating embed for single commit."""
    repos = {"owner/repo": [create_test_commit()]}

    embeds = create_commit_embeds("TestAuthor", repos)

    assert len(embeds) == 1
    assert "1 commit by TestAuthor" in embeds[0].title
    assert embeds[0].color.value == 0x28A745  # GitHub green


def test_create_commit_embeds_multiple_commits_same_repo() -> None:
    """Test multiple commits in same repo create single field."""
    commits = [
        create_test_commit(message="First commit"),
        create_test_commit(message="Second commit"),
    ]
    repos = {"owner/repo": commits}

    embeds = create_commit_embeds("TestAuthor", repos)

    assert len(embeds) == 1
    assert len(embeds[0].fields) == 1  # One field for the repo
    assert "owner/repo" in embeds[0].fields[0].name


def test_create_commit_embeds_multiple_repos() -> None:
    """Test multiple repos create multiple fields."""
    repos = {
        "owner/backend": [create_test_commit(repo_name="backend")],
        "owner/frontend": [create_test_commit(repo_name="frontend")],
    }

    embeds = create_commit_embeds("TestAuthor", repos)

    assert len(embeds) == 1
    assert len(embeds[0].fields) == 2


def test_create_commit_embeds_exactly_25_commits() -> None:
    """Test exactly 25 commits fit in one embed."""
    commits = [create_test_commit(repo_name=f"repo{i}") for i in range(25)]
    repos = {f"owner/repo{i}": [commits[i]] for i in range(25)}

    embeds = create_commit_embeds("TestAuthor", repos)

    assert len(embeds) == 1
    assert len(embeds[0].fields) == 25


def test_create_commit_embeds_26_commits() -> None:
    """Test 26 commits split into two embeds."""
    commits = [create_test_commit(repo_name=f"repo{i}") for i in range(26)]
    repos = {f"owner/repo{i}": [commits[i]] for i in range(26)}

    embeds = create_commit_embeds("TestAuthor", repos)

    assert len(embeds) == 2
    assert "(1/2)" in embeds[0].title
    assert "(2/2)" in embeds[1].title


def test_create_commit_embeds_50_commits() -> None:
    """Test 50 commits handled without overflow."""
    commits = [create_test_commit(repo_name=f"repo{i}") for i in range(50)]
    repos = {f"owner/repo{i}": [commits[i]] for i in range(50)}

    embeds = create_commit_embeds("TestAuthor", repos)

    assert len(embeds) == 2  # 25 + 25
    # No overflow footer
    assert embeds[-1].footer.text is None or "and" not in str(embeds[-1].footer.text)


def test_create_commit_embeds_over_50_commits() -> None:
    """Test commits over 50 are capped with overflow notice."""
    commits = [create_test_commit(repo_name=f"repo{i}") for i in range(60)]
    repos = {f"owner/repo{i}": [commits[i]] for i in range(60)}

    embeds = create_commit_embeds("TestAuthor", repos)

    # Should cap at 50 commits (50 repos with 1 commit each = 50 fields = 2 embeds)
    assert len(embeds) == 2

    # Last embed should have overflow footer
    footer_text = embeds[-1].footer.text
    assert footer_text is not None
    assert "10 more" in footer_text


def test_create_commit_embeds_title_includes_count() -> None:
    """Test embed title includes commit count."""
    repos = {"owner/repo": [create_test_commit(), create_test_commit()]}

    embeds = create_commit_embeds("Alice", repos)

    assert "2 commits by Alice" in embeds[0].title


def test_create_commit_embeds_multipart_title() -> None:
    """Test multipart embeds include part indicator."""
    commits = [create_test_commit(repo_name=f"repo{i}") for i in range(26)]
    repos = {f"owner/repo{i}": [commits[i]] for i in range(26)}

    embeds = create_commit_embeds("TestAuthor", repos)

    assert "(1/2)" in embeds[0].title
    assert "(2/2)" in embeds[1].title


def test_create_commit_embeds_has_random_quote() -> None:
    """Test embed description contains a quote."""
    repos = {"owner/repo": [create_test_commit()]}

    embeds = create_commit_embeds("TestAuthor", repos)

    assert embeds[0].description is not None
    assert len(embeds[0].description) > 0


def test_create_commit_embeds_color_is_github_green() -> None:
    """Test embed uses GitHub green color."""
    repos = {"owner/repo": [create_test_commit()]}

    embeds = create_commit_embeds("TestAuthor", repos)

    assert embeds[0].color.value == 0x28A745


def test_create_commit_embeds_timestamp_is_latest() -> None:
    """Test embed timestamp matches newest commit."""
    older = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    newer = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)

    commits = [
        create_test_commit(timestamp=older),
        create_test_commit(timestamp=newer),
    ]
    repos = {"owner/repo": commits}

    embeds = create_commit_embeds("TestAuthor", repos)

    assert embeds[0].timestamp == newer
