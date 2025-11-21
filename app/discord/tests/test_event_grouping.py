"""Tests for event grouping logic."""

from datetime import UTC, datetime

from app.discord.event_grouping import UserEvents, group_events_by_user
from app.shared.models import (
    CommitCommentEvent,
    CommitEvent,
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


# Test helpers
def create_test_commit(username: str = "testuser") -> CommitEvent:
    """Create a test commit event."""
    return CommitEvent(
        sha="a" * 40,
        short_sha="a" * 7,
        author="Test Author",
        author_email="test@example.com",
        author_avatar_url="https://github.com/testuser.png",
        author_username=username,
        message="Test commit",
        message_body="Test commit",
        repo_owner="owner",
        repo_name="repo",
        timestamp=datetime.now(UTC),
        url="https://github.com/owner/repo/commit/a" * 40,
        branch="main",
        is_public=True,
    )


def create_test_pr(username: str = "testuser") -> PullRequestEvent:
    """Create a test pull request event."""
    return PullRequestEvent(
        event_id="pr_1",
        pr_number=1,
        action="opened",
        title="Test PR",
        state="open",
        merged=False,
        author_username=username,
        author_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=True,
        url="https://github.com/owner/repo/pull/1",
        event_timestamp=datetime.now(UTC),
    )


def create_test_issue(username: str = "testuser") -> IssuesEvent:
    """Create a test issue event."""
    return IssuesEvent(
        event_id="issue_1",
        issue_number=1,
        action="opened",
        title="Test Issue",
        state="open",
        author_username=username,
        author_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=True,
        url="https://github.com/owner/repo/issues/1",
        event_timestamp=datetime.now(UTC),
    )


def create_test_release(username: str = "testuser") -> ReleaseEvent:
    """Create a test release event."""
    return ReleaseEvent(
        event_id="release_1",
        tag_name="v1.0.0",
        release_name="Release 1.0.0",
        author_username=username,
        author_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=True,
        is_prerelease=False,
        is_draft=False,
        url="https://github.com/owner/repo/releases/tag/v1.0.0",
        event_timestamp=datetime.now(UTC),
    )


def create_test_review(reviewer_username: str = "reviewer") -> PullRequestReviewEvent:
    """Create a test review event."""
    return PullRequestReviewEvent(
        event_id="review_1",
        pr_number=1,
        action="created",
        review_state="approved",
        reviewer_username=reviewer_username,
        reviewer_avatar_url="https://github.com/reviewer.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=True,
        url="https://github.com/owner/repo/pull/1",
        event_timestamp=datetime.now(UTC),
    )


def create_test_creation(username: str = "testuser") -> CreateEvent:
    """Create a test creation event."""
    return CreateEvent(
        event_id="create_1",
        ref_type="branch",
        ref_name="feature",
        author_username=username,
        author_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=True,
        event_timestamp=datetime.now(UTC),
    )


def create_test_deletion(username: str = "testuser") -> DeleteEvent:
    """Create a test deletion event."""
    return DeleteEvent(
        event_id="delete_1",
        ref_type="branch",
        ref_name="old-feature",
        author_username=username,
        author_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=True,
        event_timestamp=datetime.now(UTC),
    )


def create_test_fork(forker_username: str = "forker") -> ForkEvent:
    """Create a test fork event."""
    return ForkEvent(
        event_id="fork_1",
        forker_username=forker_username,
        forker_avatar_url="https://github.com/forker.png",
        source_repo_owner="original",
        source_repo_name="repo",
        fork_repo_owner=forker_username,
        fork_repo_name="forked-repo",
        fork_url=f"https://github.com/{forker_username}/forked-repo",
        is_public=True,
        event_timestamp=datetime.now(UTC),
    )


def create_test_star(username: str = "testuser") -> WatchEvent:
    """Create a test star event."""
    return WatchEvent(
        event_id="star_1",
        stargazer_username=username,
        stargazer_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=True,
        event_timestamp=datetime.now(UTC),
    )


def create_test_issue_comment(username: str = "testuser") -> IssueCommentEvent:
    """Create a test issue comment event."""
    return IssueCommentEvent(
        event_id="ic_1",
        action="created",
        issue_number=1,
        issue_title="Test Issue",
        commenter_username=username,
        commenter_avatar_url="https://github.com/testuser.png",
        comment_body="Test comment",
        repo_owner="owner",
        repo_name="repo",
        is_public=True,
        url="https://github.com/owner/repo/issues/1#issuecomment-1",
        event_timestamp=datetime.now(UTC),
    )


def create_test_pr_review_comment(username: str = "testuser") -> PullRequestReviewCommentEvent:
    """Create a test PR review comment event."""
    return PullRequestReviewCommentEvent(
        event_id="prc_1",
        action="created",
        pr_number=1,
        commenter_username=username,
        commenter_avatar_url="https://github.com/testuser.png",
        comment_body="Test PR comment",
        repo_owner="owner",
        repo_name="repo",
        is_public=True,
        url="https://github.com/owner/repo/pull/1#discussion_r1",
        event_timestamp=datetime.now(UTC),
    )


def create_test_commit_comment(username: str = "testuser") -> CommitCommentEvent:
    """Create a test commit comment event."""
    return CommitCommentEvent(
        event_id="cc_1",
        action="created",
        commit_sha="a" * 40,
        short_sha="a" * 7,
        commenter_username=username,
        commenter_avatar_url="https://github.com/testuser.png",
        comment_body="Test commit comment",
        repo_owner="owner",
        repo_name="repo",
        is_public=True,
        url="https://github.com/owner/repo/commit/aaaaaaa#commitcomment-1",
        event_timestamp=datetime.now(UTC),
    )


def create_test_member(username: str = "testuser") -> MemberEvent:
    """Create a test member event."""
    return MemberEvent(
        event_id="member_1",
        action="added",
        member_username="newmember",
        member_avatar_url="https://github.com/newmember.png",
        actor_username=username,
        actor_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=True,
        event_timestamp=datetime.now(UTC),
    )


def create_test_wiki_page(username: str = "testuser") -> GollumEvent:
    """Create a test wiki page event."""
    return GollumEvent(
        event_id="wiki_1",
        page_name="Home",
        action="edited",
        editor_username=username,
        editor_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=True,
        url="https://github.com/owner/repo/wiki/Home",
        event_timestamp=datetime.now(UTC),
    )


def create_test_public_event(username: str = "testuser") -> PublicEvent:
    """Create a test public event."""
    return PublicEvent(
        event_id="public_1",
        actor_username=username,
        actor_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        event_timestamp=datetime.now(UTC),
    )


def create_test_discussion(username: str = "testuser") -> DiscussionEvent:
    """Create a test discussion event."""
    return DiscussionEvent(
        event_id="discussion_1",
        action="created",
        discussion_number=1,
        discussion_title="Test Discussion",
        author_username=username,
        author_avatar_url="https://github.com/testuser.png",
        repo_owner="owner",
        repo_name="repo",
        is_public=True,
        url="https://github.com/owner/repo/discussions/1",
        event_timestamp=datetime.now(UTC),
    )


# UserEvents dataclass tests
def test_user_events_default_initialization() -> None:
    """Test that UserEvents initializes with empty lists."""
    events = UserEvents()

    assert events.commits == []
    assert events.pull_requests == []
    assert events.issues == []
    assert events.releases == []
    assert events.reviews == []
    assert events.creations == []
    assert events.deletions == []
    assert events.forks == []
    assert events.stars == []
    assert events.issue_comments == []
    assert events.pr_review_comments == []
    assert events.commit_comments == []
    assert events.members == []
    assert events.wiki_pages == []
    assert events.public_events == []
    assert events.discussions == []


def test_user_events_field_assignment() -> None:
    """Test that UserEvents fields can be assigned."""
    commit = create_test_commit()
    pr = create_test_pr()

    events = UserEvents(commits=[commit], pull_requests=[pr])

    assert len(events.commits) == 1
    assert len(events.pull_requests) == 1
    assert events.commits[0] == commit
    assert events.pull_requests[0] == pr


# Empty list tests
def test_group_events_empty_lists() -> None:
    """Test that empty lists return empty dict."""
    result = group_events_by_user(
        commits=[],
        prs=[],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert result == {}


def test_group_events_all_empty_except_one() -> None:
    """Test grouping with only one event type populated."""
    commit = create_test_commit(username="alice")

    result = group_events_by_user(
        commits=[commit],
        prs=[],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 1
    assert "alice" in result
    assert len(result["alice"].commits) == 1
    assert len(result["alice"].pull_requests) == 0


# Single user tests
def test_group_events_single_user_single_event_type() -> None:
    """Test grouping single user with one event type."""
    commits = [create_test_commit(username="alice")]

    result = group_events_by_user(
        commits=commits,
        prs=[],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 1
    assert "alice" in result
    assert len(result["alice"].commits) == 1


def test_group_events_single_user_multiple_commits() -> None:
    """Test grouping multiple commits for same user."""
    commits = [
        create_test_commit(username="alice"),
        create_test_commit(username="alice"),
        create_test_commit(username="alice"),
    ]

    result = group_events_by_user(
        commits=commits,
        prs=[],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 1
    assert "alice" in result
    assert len(result["alice"].commits) == 3


def test_group_events_single_user_all_event_types() -> None:
    """Test grouping single user with all event types."""
    username = "alice"

    result = group_events_by_user(
        commits=[create_test_commit(username)],
        prs=[create_test_pr(username)],
        issues=[create_test_issue(username)],
        releases=[create_test_release(username)],
        reviews=[create_test_review(reviewer_username=username)],
        creations=[create_test_creation(username)],
        deletions=[create_test_deletion(username)],
        forks=[create_test_fork(forker_username=username)],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 1
    assert username in result
    assert len(result[username].commits) == 1
    assert len(result[username].pull_requests) == 1
    assert len(result[username].issues) == 1
    assert len(result[username].releases) == 1
    assert len(result[username].reviews) == 1
    assert len(result[username].creations) == 1
    assert len(result[username].deletions) == 1
    assert len(result[username].forks) == 1


# Multiple user tests
def test_group_events_multiple_users_commits() -> None:
    """Test grouping commits from multiple users."""
    commits = [
        create_test_commit(username="alice"),
        create_test_commit(username="bob"),
        create_test_commit(username="alice"),
    ]

    result = group_events_by_user(
        commits=commits,
        prs=[],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 2
    assert "alice" in result
    assert "bob" in result
    assert len(result["alice"].commits) == 2
    assert len(result["bob"].commits) == 1


def test_group_events_multiple_users_mixed_event_types() -> None:
    """Test grouping multiple users with mixed event types."""
    result = group_events_by_user(
        commits=[
            create_test_commit(username="alice"),
            create_test_commit(username="bob"),
        ],
        prs=[
            create_test_pr(username="alice"),
            create_test_pr(username="charlie"),
        ],
        issues=[create_test_issue(username="bob")],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 3
    assert "alice" in result
    assert "bob" in result
    assert "charlie" in result

    # Alice: 1 commit, 1 PR
    assert len(result["alice"].commits) == 1
    assert len(result["alice"].pull_requests) == 1
    assert len(result["alice"].issues) == 0

    # Bob: 1 commit, 1 issue
    assert len(result["bob"].commits) == 1
    assert len(result["bob"].pull_requests) == 0
    assert len(result["bob"].issues) == 1

    # Charlie: 1 PR only
    assert len(result["charlie"].commits) == 0
    assert len(result["charlie"].pull_requests) == 1


# Reviewer/Forker username tests
def test_group_events_reviews_use_reviewer_username() -> None:
    """Test that reviews are grouped by reviewer_username."""
    reviews = [
        create_test_review(reviewer_username="alice"),
        create_test_review(reviewer_username="bob"),
        create_test_review(reviewer_username="alice"),
    ]

    result = group_events_by_user(
        commits=[],
        prs=[],
        issues=[],
        releases=[],
        reviews=reviews,
        creations=[],
        deletions=[],
        forks=[],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 2
    assert "alice" in result
    assert "bob" in result
    assert len(result["alice"].reviews) == 2
    assert len(result["bob"].reviews) == 1


def test_group_events_forks_use_forker_username() -> None:
    """Test that forks are grouped by forker_username."""
    forks = [
        create_test_fork(forker_username="alice"),
        create_test_fork(forker_username="bob"),
        create_test_fork(forker_username="alice"),
    ]

    result = group_events_by_user(
        commits=[],
        prs=[],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=forks,
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 2
    assert "alice" in result
    assert "bob" in result
    assert len(result["alice"].forks) == 2
    assert len(result["bob"].forks) == 1


def test_group_events_user_as_author_and_reviewer() -> None:
    """Test that same user can appear as both author and reviewer."""
    username = "alice"

    result = group_events_by_user(
        commits=[create_test_commit(username)],
        prs=[],
        issues=[],
        releases=[],
        reviews=[create_test_review(reviewer_username=username)],
        creations=[],
        deletions=[],
        forks=[],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 1
    assert username in result
    assert len(result[username].commits) == 1
    assert len(result[username].reviews) == 1


def test_group_events_user_as_author_and_forker() -> None:
    """Test that same user can appear as both author and forker."""
    username = "alice"

    result = group_events_by_user(
        commits=[create_test_commit(username)],
        prs=[],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[create_test_fork(forker_username=username)],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 1
    assert username in result
    assert len(result[username].commits) == 1
    assert len(result[username].forks) == 1


# Complex scenarios
def test_group_events_three_users_all_event_types() -> None:
    """Test complex scenario with multiple users and all event types."""
    result = group_events_by_user(
        commits=[
            create_test_commit(username="alice"),
            create_test_commit(username="bob"),
        ],
        prs=[
            create_test_pr(username="alice"),
            create_test_pr(username="charlie"),
        ],
        issues=[create_test_issue(username="bob")],
        releases=[create_test_release(username="alice")],
        reviews=[
            create_test_review(reviewer_username="bob"),
            create_test_review(reviewer_username="charlie"),
        ],
        creations=[create_test_creation(username="alice")],
        deletions=[create_test_deletion(username="bob")],
        forks=[create_test_fork(forker_username="charlie")],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 3

    # Alice: 1 commit, 1 PR, 1 release, 1 creation
    assert len(result["alice"].commits) == 1
    assert len(result["alice"].pull_requests) == 1
    assert len(result["alice"].releases) == 1
    assert len(result["alice"].creations) == 1

    # Bob: 1 commit, 1 issue, 1 review, 1 deletion
    assert len(result["bob"].commits) == 1
    assert len(result["bob"].issues) == 1
    assert len(result["bob"].reviews) == 1
    assert len(result["bob"].deletions) == 1

    # Charlie: 1 PR, 1 review, 1 fork
    assert len(result["charlie"].pull_requests) == 1
    assert len(result["charlie"].reviews) == 1
    assert len(result["charlie"].forks) == 1


def test_group_events_preserves_event_objects() -> None:
    """Test that original event objects are preserved in grouping."""
    commit = create_test_commit(username="alice")
    pr = create_test_pr(username="alice")

    result = group_events_by_user(
        commits=[commit],
        prs=[pr],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    # Check that the exact same objects are in the result
    assert result["alice"].commits[0] is commit
    assert result["alice"].pull_requests[0] is pr


def test_group_events_username_case_sensitivity() -> None:
    """Test that usernames are case-sensitive in grouping."""
    commits = [
        create_test_commit(username="Alice"),
        create_test_commit(username="alice"),
    ]

    result = group_events_by_user(
        commits=commits,
        prs=[],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    # Should create separate groups for different cases
    assert len(result) == 2
    assert "Alice" in result
    assert "alice" in result
    assert len(result["Alice"].commits) == 1
    assert len(result["alice"].commits) == 1


# New event type tests
def test_group_events_stars_use_stargazer_username() -> None:
    """Test that stars are grouped by stargazer_username."""
    stars = [
        create_test_star(username="alice"),
        create_test_star(username="bob"),
        create_test_star(username="alice"),
    ]

    result = group_events_by_user(
        commits=[],
        prs=[],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[],
        stars=stars,
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 2
    assert "alice" in result
    assert "bob" in result
    assert len(result["alice"].stars) == 2
    assert len(result["bob"].stars) == 1


def test_group_events_comments_use_commenter_username() -> None:
    """Test that all comment types are grouped by commenter_username."""
    issue_comments = [
        create_test_issue_comment(username="alice"),
        create_test_issue_comment(username="bob"),
    ]
    pr_comments = [
        create_test_pr_review_comment(username="alice"),
        create_test_pr_review_comment(username="charlie"),
    ]
    commit_comments = [
        create_test_commit_comment(username="bob"),
        create_test_commit_comment(username="alice"),
    ]

    result = group_events_by_user(
        commits=[],
        prs=[],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[],
        stars=[],
        issue_comments=issue_comments,
        pr_review_comments=pr_comments,
        commit_comments=commit_comments,
        members=[],
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 3
    assert "alice" in result
    assert "bob" in result
    assert "charlie" in result

    # Alice: 1 issue comment, 1 PR comment, 1 commit comment
    assert len(result["alice"].issue_comments) == 1
    assert len(result["alice"].pr_review_comments) == 1
    assert len(result["alice"].commit_comments) == 1

    # Bob: 1 issue comment, 1 commit comment
    assert len(result["bob"].issue_comments) == 1
    assert len(result["bob"].commit_comments) == 1

    # Charlie: 1 PR comment only
    assert len(result["charlie"].pr_review_comments) == 1


def test_group_events_members_use_actor_username() -> None:
    """Test that member events are grouped by actor_username."""
    members = [
        create_test_member(username="alice"),
        create_test_member(username="bob"),
        create_test_member(username="alice"),
    ]

    result = group_events_by_user(
        commits=[],
        prs=[],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=members,
        wiki_pages=[],
        public_events=[],
        discussions=[],
    )

    assert len(result) == 2
    assert "alice" in result
    assert "bob" in result
    assert len(result["alice"].members) == 2
    assert len(result["bob"].members) == 1


def test_group_events_wiki_use_editor_username() -> None:
    """Test that wiki page events are grouped by editor_username."""
    wiki_pages = [
        create_test_wiki_page(username="alice"),
        create_test_wiki_page(username="bob"),
        create_test_wiki_page(username="alice"),
    ]

    result = group_events_by_user(
        commits=[],
        prs=[],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[],
        stars=[],
        issue_comments=[],
        pr_review_comments=[],
        commit_comments=[],
        members=[],
        wiki_pages=wiki_pages,
        public_events=[],
        discussions=[],
    )

    assert len(result) == 2
    assert "alice" in result
    assert "bob" in result
    assert len(result["alice"].wiki_pages) == 2
    assert len(result["bob"].wiki_pages) == 1


def test_group_events_new_types_all_users() -> None:
    """Test all 8 new event types with multiple users."""
    result = group_events_by_user(
        commits=[],
        prs=[],
        issues=[],
        releases=[],
        reviews=[],
        creations=[],
        deletions=[],
        forks=[],
        stars=[
            create_test_star(username="alice"),
            create_test_star(username="bob"),
        ],
        issue_comments=[
            create_test_issue_comment(username="alice"),
            create_test_issue_comment(username="charlie"),
        ],
        pr_review_comments=[create_test_pr_review_comment(username="bob")],
        commit_comments=[create_test_commit_comment(username="alice")],
        members=[create_test_member(username="charlie")],
        wiki_pages=[create_test_wiki_page(username="bob")],
        public_events=[
            create_test_public_event(username="alice"),
            create_test_public_event(username="bob"),
        ],
        discussions=[create_test_discussion(username="charlie")],
    )

    assert len(result) == 3

    # Alice: 1 star, 1 issue comment, 1 commit comment, 1 public event
    assert len(result["alice"].stars) == 1
    assert len(result["alice"].issue_comments) == 1
    assert len(result["alice"].commit_comments) == 1
    assert len(result["alice"].public_events) == 1

    # Bob: 1 star, 1 PR comment, 1 wiki page, 1 public event
    assert len(result["bob"].stars) == 1
    assert len(result["bob"].pr_review_comments) == 1
    assert len(result["bob"].wiki_pages) == 1
    assert len(result["bob"].public_events) == 1

    # Charlie: 1 issue comment, 1 member event, 1 discussion
    assert len(result["charlie"].issue_comments) == 1
    assert len(result["charlie"].members) == 1
    assert len(result["charlie"].discussions) == 1
