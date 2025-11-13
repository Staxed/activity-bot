"""Event grouping logic for multi-user activity posting."""

from dataclasses import dataclass, field

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


@dataclass
class UserEvents:
    """Container for all event types for a single user."""

    commits: list[CommitEvent] = field(default_factory=list)
    pull_requests: list[PullRequestEvent] = field(default_factory=list)
    issues: list[IssuesEvent] = field(default_factory=list)
    releases: list[ReleaseEvent] = field(default_factory=list)
    reviews: list[PullRequestReviewEvent] = field(default_factory=list)
    creations: list[CreateEvent] = field(default_factory=list)
    deletions: list[DeleteEvent] = field(default_factory=list)
    forks: list[ForkEvent] = field(default_factory=list)


def group_events_by_user(
    commits: list[CommitEvent],
    prs: list[PullRequestEvent],
    issues: list[IssuesEvent],
    releases: list[ReleaseEvent],
    reviews: list[PullRequestReviewEvent],
    creations: list[CreateEvent],
    deletions: list[DeleteEvent],
    forks: list[ForkEvent],
) -> dict[str, UserEvents]:
    """Group all event types by user.

    Args:
        commits: List of commit events
        prs: List of pull request events
        issues: List of issue events
        releases: List of release events
        reviews: List of pull request review events
        creations: List of creation events
        deletions: List of deletion events
        forks: List of fork events

    Returns:
        Dict mapping username to UserEvents containing all their events

    Example:
        >>> events = group_events_by_user(
        ...     commits=[commit1, commit2],
        ...     prs=[pr1],
        ...     issues=[],
        ...     releases=[],
        ...     reviews=[],
        ...     creations=[],
        ...     deletions=[],
        ...     forks=[]
        ... )
        >>> # {"staxed": UserEvents(commits=[...], prs=[...], ...)}
    """
    user_events: dict[str, UserEvents] = {}

    # Group commits by author
    for commit in commits:
        username = commit.author_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].commits.append(commit)

    # Group pull requests by author
    for pr in prs:
        username = pr.author_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].pull_requests.append(pr)

    # Group issues by author
    for issue in issues:
        username = issue.author_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].issues.append(issue)

    # Group releases by author
    for release in releases:
        username = release.author_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].releases.append(release)

    # Group reviews by reviewer
    for review in reviews:
        username = review.reviewer_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].reviews.append(review)

    # Group creations by author
    for creation in creations:
        username = creation.author_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].creations.append(creation)

    # Group deletions by author
    for deletion in deletions:
        username = deletion.author_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].deletions.append(deletion)

    # Group forks by forker
    for fork in forks:
        username = fork.forker_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].forks.append(fork)

    return user_events
