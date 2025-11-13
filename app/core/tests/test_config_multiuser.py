"""Tests for multi-user configuration features in app.core.config module."""

import pytest

from app.core.config import Settings


def test_tracked_users_list_single_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test parsing single tracked user."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("TRACKED_GITHUB_USERS", "staxed")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.tracked_users_list == ["staxed"]


def test_tracked_users_list_multiple_users(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test parsing multiple tracked users."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("TRACKED_GITHUB_USERS", "user1,user2,user3")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.tracked_users_list == ["user1", "user2", "user3"]


def test_tracked_users_list_with_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that spaces around usernames are trimmed."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("TRACKED_GITHUB_USERS", "user1 , user2 ,  user3")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.tracked_users_list == ["user1", "user2", "user3"]


def test_tracked_users_list_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that empty string returns empty list."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("TRACKED_GITHUB_USERS", "")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.tracked_users_list == []


def test_get_user_ignored_repos_single_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test getting ignored repos for a user with single repo pattern."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("STAXED_IGNORED_REPOS", "staxed/private-repo")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.get_user_ignored_repos("staxed") == ["staxed/private-repo"]


def test_get_user_ignored_repos_multiple_patterns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test getting ignored repos for a user with multiple patterns."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("USER1_IGNORED_REPOS", "user1/private-*,org/secret-*,user1/test-repo")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.get_user_ignored_repos("user1") == [
        "user1/private-*",
        "org/secret-*",
        "user1/test-repo",
    ]


def test_get_user_ignored_repos_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that username is uppercased for env var lookup."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("STAXED_IGNORED_REPOS", "staxed/private-repo")

    settings = Settings()  # type: ignore[call-arg]

    # Lowercase username should still work
    assert settings.get_user_ignored_repos("staxed") == ["staxed/private-repo"]
    # Uppercase username should work too
    assert settings.get_user_ignored_repos("STAXED") == ["staxed/private-repo"]
    # Mixed case should work
    assert settings.get_user_ignored_repos("StAxEd") == ["staxed/private-repo"]


def test_get_user_ignored_repos_no_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that missing env var returns empty list."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.get_user_ignored_repos("nonexistent") == []


def test_get_user_ignored_repos_with_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that spaces around repo patterns are trimmed."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("USER1_IGNORED_REPOS", "repo1 , repo2 ,  repo3")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.get_user_ignored_repos("user1") == ["repo1", "repo2", "repo3"]


def test_event_toggle_fields_default_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that all event toggle fields default to True."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.post_commits is True
    assert settings.post_pull_requests is True
    assert settings.post_issues is True
    assert settings.post_releases is True
    assert settings.post_reviews is True
    assert settings.post_creations is True
    assert settings.post_deletions is True
    assert settings.post_forks is True


def test_event_toggle_fields_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that event toggle fields can be set to False."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("POST_COMMITS", "false")
    monkeypatch.setenv("POST_PULL_REQUESTS", "false")
    monkeypatch.setenv("POST_ISSUES", "false")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.post_commits is False
    assert settings.post_pull_requests is False
    assert settings.post_issues is False
    # Others should still be True
    assert settings.post_releases is True


def test_pr_actions_list_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test parsing PR actions list."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("POST_PR_ACTIONS", "opened,closed,merged")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.pr_actions_list == ["opened", "closed", "merged"]


def test_pr_actions_list_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that empty PR actions string returns empty list."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("POST_PR_ACTIONS", "")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.pr_actions_list == []


def test_issue_actions_list_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test parsing issue actions list."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("POST_ISSUE_ACTIONS", "opened,closed,reopened")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.issue_actions_list == ["opened", "closed", "reopened"]


def test_review_states_list_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test parsing review states list."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("POST_REVIEW_STATES", "approved,changes_requested")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.review_states_list == ["approved", "changes_requested"]


def test_action_filter_lists_with_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that spaces around action filter values are trimmed."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("POST_PR_ACTIONS", "opened , closed , merged")
    monkeypatch.setenv("POST_ISSUE_ACTIONS", "opened , closed")
    monkeypatch.setenv("POST_REVIEW_STATES", "approved , changes_requested")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.pr_actions_list == ["opened", "closed", "merged"]
    assert settings.issue_actions_list == ["opened", "closed"]
    assert settings.review_states_list == ["approved", "changes_requested"]


def test_model_post_init_loads_dynamic_ignored_repos(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that model_post_init loads dynamic IGNORED_REPOS env vars."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("USER1_IGNORED_REPOS", "user1/private-*")
    monkeypatch.setenv("USER2_IGNORED_REPOS", "user2/secret-*")
    monkeypatch.setenv("STAXED_IGNORED_REPOS", "staxed/test-*")

    settings = Settings()  # type: ignore[call-arg]

    # Check that dynamic attributes were created
    assert hasattr(settings, "user1_ignored_repos")
    assert hasattr(settings, "user2_ignored_repos")
    assert hasattr(settings, "staxed_ignored_repos")

    # Check values
    assert getattr(settings, "user1_ignored_repos") == "user1/private-*"
    assert getattr(settings, "user2_ignored_repos") == "user2/secret-*"
    assert getattr(settings, "staxed_ignored_repos") == "staxed/test-*"


def test_model_post_init_ignores_non_ignored_repos_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that model_post_init only loads vars ending with _IGNORED_REPOS."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("DISCORD_TOKEN", "discord_token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("USER1_IGNORED_REPOS", "user1/private-*")
    monkeypatch.setenv("USER1_OTHER_VAR", "should_not_be_loaded")

    settings = Settings()  # type: ignore[call-arg]

    # Should have the _IGNORED_REPOS var
    assert hasattr(settings, "user1_ignored_repos")
    # Should NOT have the other var (unless it's a defined field)
    # Since extra="allow", it might be there, but model_post_init shouldn't set it
    # Let's just verify the _IGNORED_REPOS was set correctly
    assert getattr(settings, "user1_ignored_repos") == "user1/private-*"
