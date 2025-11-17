"""Data models for stats and achievements."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class StreakInfo(BaseModel):
    """Information about a user's streak.

    Attributes:
        streak_type: Type of streak (daily, weekly, monthly, yearly)
        current_streak: Current consecutive streak count
        longest_streak: Longest streak ever achieved
        last_activity_date: Date of last activity (for grace period checking)
    """

    streak_type: str = Field(..., description="Type of streak")
    current_streak: int = Field(0, description="Current consecutive streak")
    longest_streak: int = Field(0, description="Longest streak achieved")
    last_activity_date: date | None = Field(None, description="Last activity date")


class UserStats(BaseModel):
    """Comprehensive user statistics.

    Attributes:
        username: GitHub username
        total_commits: Total commits across all time
        total_prs: Total pull requests
        total_issues: Total issues
        total_reviews: Total PR reviews
        total_releases: Total releases
        total_creations: Total creations (repos/branches/tags)
        total_deletions: Total deletions (branches/tags)
        total_forks: Total forks
        commits_today: Commits in current day
        commits_this_week: Commits in current week
        commits_this_month: Commits in current month
        prs_today: PRs in current day
        prs_this_week: PRs in current week
        prs_this_month: PRs in current month
        most_active_repo: Most active repository name
        most_active_repo_count: Event count for most active repo
        last_activity: Timestamp of most recent activity
    """

    username: str = Field(..., description="GitHub username")

    # All-time totals
    total_commits: int = Field(0, description="Total commits all time")
    total_prs: int = Field(0, description="Total pull requests all time")
    total_issues: int = Field(0, description="Total issues all time")
    total_reviews: int = Field(0, description="Total PR reviews all time")
    total_releases: int = Field(0, description="Total releases all time")
    total_creations: int = Field(0, description="Total creations all time")
    total_deletions: int = Field(0, description="Total deletions all time")
    total_forks: int = Field(0, description="Total forks all time")

    # Time window stats
    commits_today: int = Field(0, description="Commits today")
    commits_this_week: int = Field(0, description="Commits this week")
    commits_this_month: int = Field(0, description="Commits this month")
    prs_today: int = Field(0, description="PRs today")
    prs_this_week: int = Field(0, description="PRs this week")
    prs_this_month: int = Field(0, description="PRs this month")

    # Most active repo
    most_active_repo: str | None = Field(None, description="Most active repository")
    most_active_repo_count: int = Field(0, description="Event count for most active repo")

    # Last activity
    last_activity: datetime | None = Field(None, description="Most recent activity timestamp")


class RepoStats(BaseModel):
    """Statistics for a specific repository.

    Attributes:
        repo_full_name: Full repository name (owner/name)
        commits: Number of commits
        prs: Number of pull requests
        issues: Number of issues
        reviews: Number of reviews
        total_events: Total events across all types
    """

    repo_full_name: str = Field(..., description="Repository full name")
    commits: int = Field(0, description="Number of commits")
    prs: int = Field(0, description="Number of PRs")
    issues: int = Field(0, description="Number of issues")
    reviews: int = Field(0, description="Number of reviews")
    total_events: int = Field(0, description="Total events")


class TimePatternStats(BaseModel):
    """Time pattern statistics for user activity.

    Attributes:
        peak_hour: Hour of day with most activity (0-23)
        peak_day: Day of week with most activity (0=Mon, 6=Sun)
        night_commits: Number of commits between 10pm-6am
        early_commits: Number of commits between 5am-9am
        commits_by_hour: Dict mapping hour (0-23) to commit count
        commits_by_day: Dict mapping day (0-6) to commit count
    """

    peak_hour: int | None = Field(None, description="Peak hour of day (0-23)")
    peak_day: int | None = Field(None, description="Peak day of week (0=Mon)")
    night_commits: int = Field(0, description="Night commits (10pm-6am)")
    early_commits: int = Field(0, description="Early commits (5am-9am)")
    commits_by_hour: dict[int, int] = Field(default_factory=dict, description="Commits per hour")
    commits_by_day: dict[int, int] = Field(default_factory=dict, description="Commits per day")


class Achievement(BaseModel):
    """Achievement definition.

    Attributes:
        id: Unique achievement identifier
        name: Display name
        emoji: Emoji icon
        description: Description of achievement
        frequency: Frequency type (daily, weekly, monthly, milestone)
        threshold: Number required to earn
        category: Category (productivity, consistency, timing, milestone)
    """

    id: str = Field(..., description="Unique achievement ID")
    name: str = Field(..., description="Achievement display name")
    emoji: str = Field(..., description="Achievement emoji")
    description: str = Field(..., description="Achievement description")
    frequency: str = Field(..., description="Frequency type")
    threshold: int = Field(..., description="Threshold to earn")
    category: str = Field(..., description="Achievement category")


class EarnedAchievement(BaseModel):
    """Record of an earned achievement.

    Attributes:
        achievement_id: ID of the achievement
        period_type: Type of period (daily, weekly, monthly, milestone)
        period_date: Date representing the period
        earned_at: When the achievement was earned
        metadata: Additional context (count, threshold, etc.)
    """

    achievement_id: str = Field(..., description="Achievement ID")
    period_type: str = Field(..., description="Period type")
    period_date: date = Field(..., description="Period date")
    earned_at: datetime = Field(..., description="When earned")
    metadata: dict[str, int] = Field(default_factory=dict, description="Additional context")
