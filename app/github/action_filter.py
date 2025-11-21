"""Action filtering for PR, issue, and review events."""

from app.shared.models import (
    CommitCommentEvent,
    DiscussionEvent,
    GollumEvent,
    IssueCommentEvent,
    IssuesEvent,
    MemberEvent,
    PullRequestEvent,
    PullRequestReviewCommentEvent,
    PullRequestReviewEvent,
)


def filter_pr_actions(
    prs: list[PullRequestEvent], allowed_actions: list[str]
) -> list[PullRequestEvent]:
    """Filter pull requests by allowed actions.

    Args:
        prs: List of pull request events
        allowed_actions: List of allowed actions (e.g., ['opened', 'closed', 'merged'])

    Returns:
        Filtered list of PRs matching allowed actions, or all PRs if list is empty

    Example:
        >>> prs = [pr1, pr2, pr3]
        >>> filtered = filter_pr_actions(prs, ['opened', 'closed'])
        >>> # Returns only PRs with action='opened' or action='closed'
    """
    # Return all if no filters specified
    if not allowed_actions:
        return prs

    # Filter by action
    return [pr for pr in prs if pr.action in allowed_actions]


def filter_issue_actions(
    issues: list[IssuesEvent], allowed_actions: list[str]
) -> list[IssuesEvent]:
    """Filter issues by allowed actions.

    Args:
        issues: List of issue events
        allowed_actions: List of allowed actions (e.g., ['opened', 'closed', 'reopened'])

    Returns:
        Filtered list of issues matching allowed actions, or all issues if list is empty

    Example:
        >>> issues = [issue1, issue2, issue3]
        >>> filtered = filter_issue_actions(issues, ['opened', 'closed'])
        >>> # Returns only issues with action='opened' or action='closed'
    """
    # Return all if no filters specified
    if not allowed_actions:
        return issues

    # Filter by action
    return [issue for issue in issues if issue.action in allowed_actions]


def filter_review_states(
    reviews: list[PullRequestReviewEvent], allowed_states: list[str]
) -> list[PullRequestReviewEvent]:
    """Filter reviews by allowed review states.

    Args:
        reviews: List of review events
        allowed_states: List of allowed review states (e.g., ['approved', 'changes_requested'])

    Returns:
        Filtered list of reviews matching allowed states, or all reviews if list is empty

    Example:
        >>> reviews = [review1, review2, review3]
        >>> filtered = filter_review_states(reviews, ['approved'])
        >>> # Returns only reviews with review_state='approved'
    """
    # Return all if no filters specified
    if not allowed_states:
        return reviews

    # Filter by review_state
    return [review for review in reviews if review.review_state in allowed_states]


def filter_issue_comment_actions(
    comments: list[IssueCommentEvent], allowed_actions: list[str]
) -> list[IssueCommentEvent]:
    """Filter issue comments by allowed actions.

    Args:
        comments: List of issue comment events
        allowed_actions: List of allowed actions (e.g., ['created', 'edited', 'deleted'])

    Returns:
        Filtered list of comments matching allowed actions, or all comments if list is empty

    Example:
        >>> comments = [comment1, comment2, comment3]
        >>> filtered = filter_issue_comment_actions(comments, ['created'])
        >>> # Returns only comments with action='created'
    """
    # Return all if no filters specified
    if not allowed_actions:
        return comments

    # Filter by action
    return [comment for comment in comments if comment.action in allowed_actions]


def filter_pr_review_comment_actions(
    comments: list[PullRequestReviewCommentEvent], allowed_actions: list[str]
) -> list[PullRequestReviewCommentEvent]:
    """Filter PR review comments by allowed actions.

    Args:
        comments: List of PR review comment events
        allowed_actions: List of allowed actions (e.g., ['created', 'edited', 'deleted'])

    Returns:
        Filtered list of comments matching allowed actions, or all comments if list is empty

    Example:
        >>> comments = [comment1, comment2, comment3]
        >>> filtered = filter_pr_review_comment_actions(comments, ['created'])
        >>> # Returns only comments with action='created'
    """
    # Return all if no filters specified
    if not allowed_actions:
        return comments

    # Filter by action
    return [comment for comment in comments if comment.action in allowed_actions]


def filter_commit_comment_actions(
    comments: list[CommitCommentEvent], allowed_actions: list[str]
) -> list[CommitCommentEvent]:
    """Filter commit comments by allowed actions.

    Args:
        comments: List of commit comment events
        allowed_actions: List of allowed actions (e.g., ['created'])

    Returns:
        Filtered list of comments matching allowed actions, or all comments if list is empty

    Example:
        >>> comments = [comment1, comment2, comment3]
        >>> filtered = filter_commit_comment_actions(comments, ['created'])
        >>> # Returns only comments with action='created'
    """
    # Return all if no filters specified
    if not allowed_actions:
        return comments

    # Filter by action
    return [comment for comment in comments if comment.action in allowed_actions]


def filter_member_actions(
    members: list[MemberEvent], allowed_actions: list[str]
) -> list[MemberEvent]:
    """Filter member events by allowed actions.

    Args:
        members: List of member events
        allowed_actions: List of allowed actions (e.g., ['added', 'removed', 'edited'])

    Returns:
        Filtered list of member events matching allowed actions, or all members if list is empty

    Example:
        >>> members = [member1, member2, member3]
        >>> filtered = filter_member_actions(members, ['added'])
        >>> # Returns only member events with action='added'
    """
    # Return all if no filters specified
    if not allowed_actions:
        return members

    # Filter by action
    return [member for member in members if member.action in allowed_actions]


def filter_wiki_actions(
    wiki_pages: list[GollumEvent], allowed_actions: list[str]
) -> list[GollumEvent]:
    """Filter wiki page events by allowed actions.

    Args:
        wiki_pages: List of wiki page (Gollum) events
        allowed_actions: List of allowed actions (e.g., ['created', 'edited'])

    Returns:
        Filtered list of wiki events matching allowed actions, or all wiki pages if list is empty

    Example:
        >>> wiki_pages = [page1, page2, page3]
        >>> filtered = filter_wiki_actions(wiki_pages, ['created'])
        >>> # Returns only wiki pages with action='created'
    """
    # Return all if no filters specified
    if not allowed_actions:
        return wiki_pages

    # Filter by action
    return [page for page in wiki_pages if page.action in allowed_actions]


def filter_discussion_actions(
    discussions: list[DiscussionEvent], allowed_actions: list[str]
) -> list[DiscussionEvent]:
    """Filter discussion events by allowed actions.

    Args:
        discussions: List of discussion events
        allowed_actions: List of allowed actions (e.g., ['created', 'edited', 'deleted', 'answered'])

    Returns:
        Filtered list of discussions matching allowed actions, or all discussions if list is empty

    Example:
        >>> discussions = [disc1, disc2, disc3]
        >>> filtered = filter_discussion_actions(discussions, ['created', 'answered'])
        >>> # Returns only discussions with action='created' or action='answered'
    """
    # Return all if no filters specified
    if not allowed_actions:
        return discussions

    # Filter by action
    return [discussion for discussion in discussions if discussion.action in allowed_actions]
