"""Action filtering for PR, issue, and review events."""

from app.shared.models import IssuesEvent, PullRequestEvent, PullRequestReviewEvent


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
