"""Tests for branch filtering utilities."""


from app.github.branch_filter import should_track_branch


class TestShouldTrackBranch:
    """Test branch filtering logic with various configurations."""

    def test_ignore_patterns_take_precedence_over_tracked_branches(self) -> None:
        """Test that ignore patterns override tracked branches."""
        # Even though "main" is in tracked_branches, ignore pattern blocks it
        assert not should_track_branch(
            branch="main",
            tracked_branches=["main", "develop"],
            ignore_patterns=["main"],
        )

    def test_tracked_branches_exact_match_allows_branch(self) -> None:
        """Test that branches in tracked list are allowed."""
        assert should_track_branch(
            branch="main",
            tracked_branches=["main", "develop"],
            ignore_patterns=[],
        )

        assert should_track_branch(
            branch="develop",
            tracked_branches=["main", "develop"],
            ignore_patterns=[],
        )

    def test_tracked_branches_exact_match_blocks_others(self) -> None:
        """Test that branches not in tracked list are blocked."""
        assert not should_track_branch(
            branch="feature/new-feature",
            tracked_branches=["main", "develop"],
            ignore_patterns=[],
        )

    def test_wildcard_patterns_match_correctly(self) -> None:
        """Test that wildcard patterns (fnmatch) work as expected."""
        # Block all feature/* branches
        assert not should_track_branch(
            branch="feature/add-auth",
            tracked_branches=[],
            ignore_patterns=["feature/*"],
        )

        assert not should_track_branch(
            branch="feature/fix-bug",
            tracked_branches=[],
            ignore_patterns=["feature/*", "hotfix/*"],
        )

        # Block all hotfix/* branches
        assert not should_track_branch(
            branch="hotfix/critical-fix",
            tracked_branches=[],
            ignore_patterns=["hotfix/*"],
        )

    def test_wildcard_patterns_dont_block_non_matching_branches(self) -> None:
        """Test that wildcard patterns only block matching branches."""
        assert should_track_branch(
            branch="main",
            tracked_branches=[],
            ignore_patterns=["feature/*", "hotfix/*"],
        )

        assert should_track_branch(
            branch="develop",
            tracked_branches=[],
            ignore_patterns=["feature/*"],
        )

    def test_no_tracked_branches_allows_all_except_ignored(self) -> None:
        """Test that empty tracked_branches list allows all branches."""
        # No tracked branches = track everything
        assert should_track_branch(
            branch="main",
            tracked_branches=[],
            ignore_patterns=[],
        )

        assert should_track_branch(
            branch="feature/new",
            tracked_branches=[],
            ignore_patterns=[],
        )

        # But still respect ignore patterns
        assert not should_track_branch(
            branch="feature/new",
            tracked_branches=[],
            ignore_patterns=["feature/*"],
        )

    def test_complex_scenario_with_multiple_patterns(self) -> None:
        """Test complex configuration with multiple tracked branches and patterns."""
        # Track only main and develop, but ignore anything matching test/*
        tracked = ["main", "develop"]
        ignore = ["test/*", "experimental/*"]

        # Tracked branches should work
        assert should_track_branch("main", tracked, ignore)
        assert should_track_branch("develop", tracked, ignore)

        # Non-tracked branches should be blocked
        assert not should_track_branch("feature/new", tracked, ignore)

        # Ignored patterns should block even tracked branches
        assert not should_track_branch("test/unit", tracked, ignore)
        assert not should_track_branch("experimental/new-arch", tracked, ignore)

    def test_edge_case_empty_branch_name(self) -> None:
        """Test that empty branch name is handled gracefully."""
        # Empty branch name should not match any pattern
        assert not should_track_branch(
            branch="",
            tracked_branches=["main"],
            ignore_patterns=[],
        )

        # Empty branch with no tracked branches should be allowed
        assert should_track_branch(
            branch="",
            tracked_branches=[],
            ignore_patterns=[],
        )

    def test_edge_case_special_characters_in_branch_name(self) -> None:
        """Test branches with special characters."""
        # Branch with slashes and hyphens (common in Git)
        assert should_track_branch(
            branch="feature/add-user-auth",
            tracked_branches=[],
            ignore_patterns=["hotfix/*"],
        )

        assert not should_track_branch(
            branch="feature/add-user-auth",
            tracked_branches=[],
            ignore_patterns=["feature/*"],
        )

    def test_precedence_order_ignore_before_tracked(self) -> None:
        """Test that ignore patterns are checked before tracked branches."""
        # Scenario: User wants to track "main" but accidentally added "m*" to ignore
        # The ignore pattern should take precedence
        assert not should_track_branch(
            branch="main",
            tracked_branches=["main", "develop"],
            ignore_patterns=["m*"],
        )

        # But "develop" should still work
        assert should_track_branch(
            branch="develop",
            tracked_branches=["main", "develop"],
            ignore_patterns=["m*"],
        )

    def test_case_sensitive_matching(self) -> None:
        """Test that branch matching is case-sensitive."""
        # "Main" != "main"
        assert not should_track_branch(
            branch="Main",
            tracked_branches=["main"],
            ignore_patterns=[],
        )

        # "FEATURE/test" != "feature/*"
        assert should_track_branch(
            branch="FEATURE/test",
            tracked_branches=[],
            ignore_patterns=["feature/*"],
        )
