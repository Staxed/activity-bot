"""Repository filtering logic using fnmatch patterns."""

import fnmatch


def should_track_repo(repo_full_name: str, ignored_repos: list[str]) -> bool:
    """Check if a repository should be tracked based on ignored patterns.

    Args:
        repo_full_name: Full repository name (e.g., 'owner/repo')
        ignored_repos: List of repository patterns to ignore (supports fnmatch wildcards)

    Returns:
        True if repository should be tracked, False if it matches an ignore pattern

    Example:
        >>> should_track_repo('user/public-repo', [])
        True
        >>> should_track_repo('user/private-repo', ['user/private-*'])
        False
        >>> should_track_repo('org/secret-api', ['org/secret-*', 'org/internal-*'])
        False
        >>> should_track_repo('org/public-api', ['org/secret-*'])
        True
    """
    # If no ignore patterns, track everything
    if not ignored_repos:
        return True

    # Check if repo matches any ignore pattern
    for pattern in ignored_repos:
        if fnmatch.fnmatch(repo_full_name, pattern):
            return False

    # Repo doesn't match any ignore pattern, so track it
    return True
