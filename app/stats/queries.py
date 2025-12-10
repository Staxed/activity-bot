"""SQL query constants for stats calculations."""

# Get all-time totals for a user across all event types
GET_USER_TOTALS = """
    SELECT
        COALESCE(c.commit_count, 0) as total_commits,
        COALESCE(pr.pr_count, 0) as total_prs,
        COALESCE(i.issue_count, 0) as total_issues,
        COALESCE(r.review_count, 0) as total_reviews,
        COALESCE(rel.release_count, 0) as total_releases,
        COALESCE(cr.creation_count, 0) as total_creations,
        COALESCE(d.deletion_count, 0) as total_deletions,
        COALESCE(f.fork_count, 0) as total_forks
    FROM (SELECT 1) as dummy
    LEFT JOIN (
        SELECT COUNT(*) as commit_count
        FROM commits
        WHERE author_username = $1
    ) c ON TRUE
    LEFT JOIN (
        SELECT COUNT(*) as pr_count
        FROM pull_requests
        WHERE author_username = $1
    ) pr ON TRUE
    LEFT JOIN (
        SELECT COUNT(*) as issue_count
        FROM issues
        WHERE author_username = $1
    ) i ON TRUE
    LEFT JOIN (
        SELECT COUNT(*) as review_count
        FROM pr_reviews
        WHERE reviewer_username = $1
    ) r ON TRUE
    LEFT JOIN (
        SELECT COUNT(*) as release_count
        FROM releases
        WHERE author_username = $1
    ) rel ON TRUE
    LEFT JOIN (
        SELECT COUNT(*) as creation_count
        FROM creations
        WHERE author_username = $1
    ) cr ON TRUE
    LEFT JOIN (
        SELECT COUNT(*) as deletion_count
        FROM deletions
        WHERE author_username = $1
    ) d ON TRUE
    LEFT JOIN (
        SELECT COUNT(*) as fork_count
        FROM forks
        WHERE forker_username = $1
    ) f ON TRUE
"""

# Get stats for a specific time window (today/week/month)
# $1 = username, $2 = start timestamp
GET_USER_TIME_WINDOW_STATS = """
    SELECT
        COUNT(*) FILTER (WHERE commit_timestamp >= $2) as commits_count,
        MAX(commit_timestamp) as last_activity
    FROM commits
    WHERE author_username = $1
    UNION ALL
    SELECT
        COUNT(*) FILTER (WHERE event_timestamp >= $2) as pr_count,
        MAX(event_timestamp) as last_activity
    FROM pull_requests
    WHERE author_username = $1
"""

# Get most active repository for a user
GET_MOST_ACTIVE_REPO = """
    WITH all_events AS (
        SELECT repo_owner || '/' || repo_name as repo_full_name
        FROM commits WHERE author_username = $1
        UNION ALL
        SELECT repo_owner || '/' || repo_name
        FROM pull_requests WHERE author_username = $1
        UNION ALL
        SELECT repo_owner || '/' || repo_name
        FROM issues WHERE author_username = $1
        UNION ALL
        SELECT repo_owner || '/' || repo_name
        FROM pr_reviews WHERE reviewer_username = $1
    )
    SELECT repo_full_name, COUNT(*) as event_count
    FROM all_events
    GROUP BY repo_full_name
    ORDER BY event_count DESC
    LIMIT 1
"""

# Get commits by hour of day (0-23) for time pattern analysis
# $1 = username
GET_COMMITS_BY_HOUR = """
    SELECT
        EXTRACT(HOUR FROM commit_timestamp) as hour,
        COUNT(*) as count
    FROM commits
    WHERE author_username = $1
    GROUP BY hour
    ORDER BY hour
"""

# Get commits by day of week (0=Sunday, 6=Saturday)
# $1 = username
GET_COMMITS_BY_DAY = """
    SELECT
        EXTRACT(DOW FROM commit_timestamp) as dow,
        COUNT(*) as count
    FROM commits
    WHERE author_username = $1
    GROUP BY dow
    ORDER BY dow
"""

# Get count of night commits (10pm-6am)
# $1 = username, $2 = date
GET_NIGHT_OWL_COUNT = """
    SELECT COUNT(*) as night_count
    FROM commits
    WHERE author_username = $1
      AND DATE(commit_timestamp) = $2
      AND (EXTRACT(HOUR FROM commit_timestamp) >= 22 OR EXTRACT(HOUR FROM commit_timestamp) < 6)
"""

# Get count of early morning commits (5am-9am)
# $1 = username, $2 = date
GET_EARLY_BIRD_COUNT = """
    SELECT COUNT(*) as early_count
    FROM commits
    WHERE author_username = $1
      AND DATE(commit_timestamp) = $2
      AND EXTRACT(HOUR FROM commit_timestamp) >= 5
      AND EXTRACT(HOUR FROM commit_timestamp) < 9
"""

# Get count of commits on a specific date
# $1 = username, $2 = date
GET_DAILY_COMMIT_COUNT = """
    SELECT COUNT(*) as daily_count
    FROM commits
    WHERE author_username = $1
      AND DATE(commit_timestamp) = $2
"""

# Get distinct activity dates for streak calculation
# $1 = username, $2 = timezone (e.g., 'America/New_York')
GET_ACTIVITY_DATES = """
    SELECT DISTINCT DATE(commit_timestamp AT TIME ZONE 'UTC' AT TIME ZONE $2) as activity_date
    FROM commits
    WHERE author_username = $1
    ORDER BY activity_date DESC
"""

# Get weekly activity periods (week start dates)
# $1 = username
GET_WEEKLY_ACTIVITY = """
    SELECT DISTINCT DATE_TRUNC('week', commit_timestamp)::date as week_start
    FROM commits
    WHERE author_username = $1
    ORDER BY week_start DESC
"""

# Get monthly activity periods (month start dates)
# $1 = username
GET_MONTHLY_ACTIVITY = """
    SELECT DISTINCT DATE_TRUNC('month', commit_timestamp)::date as month_start
    FROM commits
    WHERE author_username = $1
    ORDER BY month_start DESC
"""

# Get yearly activity periods
# $1 = username
GET_YEARLY_ACTIVITY = """
    SELECT DISTINCT EXTRACT(YEAR FROM commit_timestamp)::int as year
    FROM commits
    WHERE author_username = $1
    ORDER BY year DESC
"""

# Get repository statistics for a user
# $1 = username, $2 = since timestamp (optional filter), $3 = until timestamp (optional filter)
GET_REPO_STATS = """
    WITH all_repo_events AS (
        SELECT
            repo_owner || '/' || repo_name as repo_full_name,
            'commit' as event_type
        FROM commits
        WHERE author_username = $1
          AND ($2::timestamp IS NULL OR commit_timestamp >= $2)
          AND ($3::timestamp IS NULL OR commit_timestamp < $3)
        UNION ALL
        SELECT
            repo_owner || '/' || repo_name,
            'pr' as event_type
        FROM pull_requests
        WHERE author_username = $1
          AND ($2::timestamp IS NULL OR event_timestamp >= $2)
          AND ($3::timestamp IS NULL OR event_timestamp < $3)
        UNION ALL
        SELECT
            repo_owner || '/' || repo_name,
            'issue' as event_type
        FROM issues
        WHERE author_username = $1
          AND ($2::timestamp IS NULL OR event_timestamp >= $2)
          AND ($3::timestamp IS NULL OR event_timestamp < $3)
        UNION ALL
        SELECT
            repo_owner || '/' || repo_name,
            'review' as event_type
        FROM pr_reviews
        WHERE reviewer_username = $1
          AND ($2::timestamp IS NULL OR event_timestamp >= $2)
          AND ($3::timestamp IS NULL OR event_timestamp < $3)
    )
    SELECT
        repo_full_name,
        COUNT(*) FILTER (WHERE event_type = 'commit') as commits,
        COUNT(*) FILTER (WHERE event_type = 'pr') as prs,
        COUNT(*) FILTER (WHERE event_type = 'issue') as issues,
        COUNT(*) FILTER (WHERE event_type = 'review') as reviews,
        COUNT(*) as total_events
    FROM all_repo_events
    GROUP BY repo_full_name
    ORDER BY total_events DESC
"""

# Check if achievement already earned
# $1 = username, $2 = achievement_id, $3 = period_type, $4 = period_date
CHECK_ACHIEVEMENT_EARNED = """
    SELECT 1
    FROM achievement_history
    WHERE username = $1
      AND achievement_id = $2
      AND period_type = $3
      AND period_date = $4
    LIMIT 1
"""

# Record a new achievement
# $1 = username, $2 = achievement_id, $3 = period_type, $4 = period_date,
# $5 = earned_at, $6 = metadata (JSONB)
INSERT_ACHIEVEMENT = """
    INSERT INTO achievement_history
        (username, achievement_id, period_type, period_date, earned_at, metadata)
    VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (username, achievement_id, period_type, period_date) DO NOTHING
"""

# Get achievement count for a specific achievement
# $1 = username, $2 = achievement_id
GET_ACHIEVEMENT_COUNT = """
    SELECT COUNT(*) as earn_count
    FROM achievement_history
    WHERE username = $1
      AND achievement_id = $2
"""

# Get all achievements for a user in a time period
# $1 = username, $2 = start_date, $3 = end_date
GET_ACHIEVEMENTS_IN_PERIOD = """
    SELECT achievement_id, period_type, period_date, earned_at, metadata
    FROM achievement_history
    WHERE username = $1
      AND period_date >= $2
      AND period_date <= $3
    ORDER BY earned_at DESC
"""

# Get all milestone achievements for a user
# $1 = username
GET_MILESTONE_ACHIEVEMENTS = """
    SELECT achievement_id, period_date, earned_at, metadata
    FROM achievement_history
    WHERE username = $1
      AND period_type = 'milestone'
    ORDER BY earned_at DESC
"""

# Get commit with longest message on a specific date
# $1 = username, $2 = date
GET_LONGEST_COMMIT_MESSAGE = """
    SELECT LENGTH(message_body) as msg_length
    FROM commits
    WHERE author_username = $1
      AND DATE(commit_timestamp) = $2
    ORDER BY msg_length DESC
    LIMIT 1
"""

# Get weekend commit count (Saturday=6, Sunday=0)
# $1 = username, $2 = week_start_date
GET_WEEKEND_COMMITS = """
    SELECT COUNT(*) as weekend_count
    FROM commits
    WHERE author_username = $1
      AND DATE(commit_timestamp) >= $2
      AND DATE(commit_timestamp) < $2 + INTERVAL '7 days'
      AND EXTRACT(DOW FROM commit_timestamp) IN (0, 6)
"""

# Get weekday activity count (unique days Mon-Fri with commits)
# $1 = username, $2 = week_start_date
GET_WEEKDAY_ACTIVITY_DAYS = """
    SELECT COUNT(DISTINCT DATE(commit_timestamp)) as weekday_days
    FROM commits
    WHERE author_username = $1
      AND DATE(commit_timestamp) >= $2
      AND DATE(commit_timestamp) < $2 + INTERVAL '7 days'
      AND EXTRACT(DOW FROM commit_timestamp) BETWEEN 1 AND 5
"""

# Get weekly commit count
# $1 = username, $2 = week_start_date
GET_WEEKLY_COMMIT_COUNT = """
    SELECT COUNT(*) as week_count
    FROM commits
    WHERE author_username = $1
      AND DATE(commit_timestamp) >= $2
      AND DATE(commit_timestamp) < $2 + INTERVAL '7 days'
"""

# Get monthly commit count
# $1 = username, $2 = month_start_date
GET_MONTHLY_COMMIT_COUNT = """
    SELECT COUNT(*) as month_count
    FROM commits
    WHERE author_username = $1
      AND DATE_TRUNC('month', commit_timestamp)::date = $2
"""

# Get monthly PR count
# $1 = username, $2 = month_start_date
GET_MONTHLY_PR_COUNT = """
    SELECT COUNT(*) as month_pr_count
    FROM pull_requests
    WHERE author_username = $1
      AND DATE_TRUNC('month', event_timestamp)::date = $2
"""

# Get unique commit days in a month
# $1 = username, $2 = month_start_date
GET_MONTHLY_ACTIVE_DAYS = """
    SELECT COUNT(DISTINCT DATE(commit_timestamp)) as active_days
    FROM commits
    WHERE author_username = $1
      AND DATE_TRUNC('month', commit_timestamp)::date = $2
"""

# Update streak tracking
# $1 = username, $2 = streak_type, $3 = current_streak, $4 = longest_streak,
# $5 = last_activity_date
UPSERT_STREAK = """
    INSERT INTO streak_tracking
        (username, streak_type, current_streak, longest_streak, last_activity_date, last_updated)
    VALUES ($1, $2, $3, $4, $5, NOW())
    ON CONFLICT (username, streak_type)
    DO UPDATE SET
        current_streak = $3,
        longest_streak = GREATEST(streak_tracking.longest_streak, $4),
        last_activity_date = $5,
        last_updated = NOW()
"""

# Get current streak info
# $1 = username, $2 = streak_type
GET_STREAK_INFO = """
    SELECT current_streak, longest_streak, last_activity_date
    FROM streak_tracking
    WHERE username = $1
      AND streak_type = $2
"""
