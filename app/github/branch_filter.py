"""Branch filtering utilities for smart commit tracking."""

from fnmatch import fnmatch


def should_track_branch(
    branch: str,
    tracked_branches: list[str],
    ignore_patterns: list[str],
) -> bool:
    """Determine if a branch should be tracked based on configuration.

    Implements smart branch filtering with the following precedence:
    1. Ignore patterns take precedence (if matched, always ignore)
    2. If tracked_branches specified, only track those (exact match)
    3. If no tracked_branches, track all (except ignored)

    Args:
        branch: Branch name to check (e.g., "main", "feature/add-auth")
        tracked_branches: List of branches to explicitly track (e.g., ["main", "develop"])
        ignore_patterns: List of patterns to ignore (e.g., ["feature/*", "hotfix/*"])

    Returns:
        True if branch should be tracked, False otherwise

    Examples:
        >>> should_track_branch("main", ["main"], ["feature/*"])
        True
        >>> should_track_branch("feature/new", ["main"], ["feature/*"])
        False
        >>> should_track_branch("develop", ["main", "develop"], [])
        True
        >>> should_track_branch("hotfix/bug", [], ["hotfix/*"])
        False
    """
    # Rule 1: Check ignore patterns first (highest priority)
    for pattern in ignore_patterns:
        if fnmatch(branch, pattern):
            return False

    # Rule 2: If tracked_branches specified, only allow those
    if tracked_branches:
        return branch in tracked_branches

    # Rule 3: If no tracked_branches specified, allow all (except ignored)
    return True
