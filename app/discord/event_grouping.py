"""Event grouping logic for multi-user activity posting."""

from dataclasses import dataclass, field

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
    stars: list[WatchEvent] = field(default_factory=list)
    issue_comments: list[IssueCommentEvent] = field(default_factory=list)
    pr_review_comments: list[PullRequestReviewCommentEvent] = field(default_factory=list)
    commit_comments: list[CommitCommentEvent] = field(default_factory=list)
    members: list[MemberEvent] = field(default_factory=list)
    wiki_pages: list[GollumEvent] = field(default_factory=list)
    public_events: list[PublicEvent] = field(default_factory=list)
    discussions: list[DiscussionEvent] = field(default_factory=list)


def group_events_by_user(
    commits: list[CommitEvent],
    prs: list[PullRequestEvent],
    issues: list[IssuesEvent],
    releases: list[ReleaseEvent],
    reviews: list[PullRequestReviewEvent],
    creations: list[CreateEvent],
    deletions: list[DeleteEvent],
    forks: list[ForkEvent],
    stars: list[WatchEvent],
    issue_comments: list[IssueCommentEvent],
    pr_review_comments: list[PullRequestReviewCommentEvent],
    commit_comments: list[CommitCommentEvent],
    members: list[MemberEvent],
    wiki_pages: list[GollumEvent],
    public_events: list[PublicEvent],
    discussions: list[DiscussionEvent],
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
        stars: List of star (watch) events
        issue_comments: List of issue comment events
        pr_review_comments: List of PR review comment events
        commit_comments: List of commit comment events
        members: List of member events
        wiki_pages: List of wiki page (Gollum) events
        public_events: List of public events
        discussions: List of discussion events

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
        ...     forks=[],
        ...     stars=[],
        ...     issue_comments=[],
        ...     pr_review_comments=[],
        ...     commit_comments=[],
        ...     members=[],
        ...     wiki_pages=[],
        ...     public_events=[],
        ...     discussions=[]
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

    # Group stars by stargazer
    for star in stars:
        username = star.stargazer_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].stars.append(star)

    # Group issue comments by commenter
    for comment in issue_comments:
        username = comment.commenter_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].issue_comments.append(comment)

    # Group PR review comments by commenter
    for comment in pr_review_comments:
        username = comment.commenter_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].pr_review_comments.append(comment)

    # Group commit comments by commenter
    for comment in commit_comments:
        username = comment.commenter_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].commit_comments.append(comment)

    # Group members by actor (who performed the action)
    for member in members:
        username = member.actor_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].members.append(member)

    # Group wiki pages by editor
    for wiki in wiki_pages:
        username = wiki.editor_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].wiki_pages.append(wiki)

    # Group public events by actor
    for public_event in public_events:
        username = public_event.actor_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].public_events.append(public_event)

    # Group discussions by author
    for discussion in discussions:
        username = discussion.author_username
        if username not in user_events:
            user_events[username] = UserEvents()
        user_events[username].discussions.append(discussion)

    return user_events
