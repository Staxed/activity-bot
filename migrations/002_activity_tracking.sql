-- Activity Bot Activity Tracking Migration
-- Creates tables for tracking 8 GitHub event types + processing state
-- Runs automatically on first postgres startup via docker-entrypoint-initdb.d

-- Table 1: Commits (from PushEvent)
CREATE TABLE IF NOT EXISTS commits (
    event_id TEXT PRIMARY KEY,
    sha TEXT NOT NULL,
    short_sha TEXT NOT NULL,
    author_name TEXT NOT NULL,
    author_email TEXT NOT NULL,
    author_username TEXT NOT NULL,
    author_avatar_url TEXT,
    message TEXT NOT NULL,
    message_body TEXT NOT NULL,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    branch TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    commit_timestamp TIMESTAMP NOT NULL,
    url TEXT NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_commits_posted ON commits(posted_to_discord, created_at) WHERE posted_to_discord = FALSE;
CREATE INDEX IF NOT EXISTS idx_commits_repo ON commits(repo_owner, repo_name, commit_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_commits_branch ON commits(branch, commit_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_commits_author ON commits(author_username, commit_timestamp DESC);

-- Table 2: Pull Requests (from PullRequestEvent)
CREATE TABLE IF NOT EXISTS pull_requests (
    event_id TEXT PRIMARY KEY,
    pr_number INTEGER NOT NULL,
    action TEXT NOT NULL,
    title TEXT,
    state TEXT NOT NULL,
    merged BOOLEAN DEFAULT FALSE,
    author_username TEXT NOT NULL,
    author_avatar_url TEXT,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    url TEXT,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pull_requests_repo ON pull_requests(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pull_requests_author ON pull_requests(author_username, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pull_requests_state ON pull_requests(state, event_timestamp DESC);

-- Table 3: Pull Request Reviews (from PullRequestReviewEvent)
CREATE TABLE IF NOT EXISTS pr_reviews (
    event_id TEXT PRIMARY KEY,
    pr_number INTEGER NOT NULL,
    action TEXT NOT NULL,
    review_state TEXT NOT NULL,
    reviewer_username TEXT NOT NULL,
    reviewer_avatar_url TEXT,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    url TEXT,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pr_reviews_repo ON pr_reviews(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pr_reviews_reviewer ON pr_reviews(reviewer_username, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pr_reviews_state ON pr_reviews(review_state, event_timestamp DESC);

-- Table 4: Issues (from IssuesEvent)
CREATE TABLE IF NOT EXISTS issues (
    event_id TEXT PRIMARY KEY,
    issue_number INTEGER NOT NULL,
    action TEXT NOT NULL,
    title TEXT,
    state TEXT NOT NULL,
    author_username TEXT NOT NULL,
    author_avatar_url TEXT,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    url TEXT,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_issues_repo ON issues(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_issues_author ON issues(author_username, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_issues_state ON issues(state, event_timestamp DESC);

-- Table 5: Releases (from ReleaseEvent)
CREATE TABLE IF NOT EXISTS releases (
    event_id TEXT PRIMARY KEY,
    tag_name TEXT NOT NULL,
    release_name TEXT,
    is_prerelease BOOLEAN DEFAULT FALSE,
    is_draft BOOLEAN DEFAULT FALSE,
    author_username TEXT NOT NULL,
    author_avatar_url TEXT,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    url TEXT,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_releases_repo ON releases(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_releases_author ON releases(author_username, event_timestamp DESC);

-- Table 6: Creations (from CreateEvent - repo/branch/tag)
CREATE TABLE IF NOT EXISTS creations (
    event_id TEXT PRIMARY KEY,
    ref_type TEXT NOT NULL,  -- repository, branch, or tag
    ref_name TEXT,  -- NULL for repository type
    author_username TEXT NOT NULL,
    author_avatar_url TEXT,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_creations_repo ON creations(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_creations_type ON creations(ref_type, event_timestamp DESC);

-- Table 7: Deletions (from DeleteEvent - branch/tag)
CREATE TABLE IF NOT EXISTS deletions (
    event_id TEXT PRIMARY KEY,
    ref_type TEXT NOT NULL,  -- branch or tag
    ref_name TEXT NOT NULL,
    author_username TEXT NOT NULL,
    author_avatar_url TEXT,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_deletions_repo ON deletions(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_deletions_type ON deletions(ref_type, event_timestamp DESC);

-- Table 8: Forks (from ForkEvent)
CREATE TABLE IF NOT EXISTS forks (
    event_id TEXT PRIMARY KEY,
    forker_username TEXT NOT NULL,
    forker_avatar_url TEXT,
    source_repo_owner TEXT NOT NULL,
    source_repo_name TEXT NOT NULL,
    fork_repo_owner TEXT NOT NULL,
    fork_repo_name TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    fork_url TEXT,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_forks_source_repo ON forks(source_repo_owner, source_repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_forks_forker ON forks(forker_username, event_timestamp DESC);

-- Table 9: Processing State (tracks last processed event ID)
CREATE TABLE IF NOT EXISTS processing_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ON CONFLICT DO NOTHING allows safe re-run (idempotent)
