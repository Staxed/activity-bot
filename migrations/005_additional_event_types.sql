-- Activity Bot Additional Event Types Migration
-- Adds 8 new GitHub event types: stars, issue comments, PR review comments, commit comments, members, wiki pages, public events, discussions
-- Runs automatically on first postgres startup via docker-entrypoint-initdb.d

-- Table 1: Stars (from WatchEvent)
CREATE TABLE IF NOT EXISTS stars (
    event_id TEXT PRIMARY KEY,
    stargazer_username TEXT NOT NULL,
    stargazer_avatar_url TEXT,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stars_repo ON stars(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_stars_stargazer ON stars(stargazer_username, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_stars_posted ON stars(posted_to_discord, created_at) WHERE posted_to_discord = FALSE;

-- Table 2: Issue Comments (from IssueCommentEvent)
CREATE TABLE IF NOT EXISTS issue_comments (
    event_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    issue_number INTEGER NOT NULL,
    issue_title TEXT,
    commenter_username TEXT NOT NULL,
    commenter_avatar_url TEXT,
    comment_body TEXT,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    url TEXT,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_issue_comments_repo ON issue_comments(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_issue_comments_commenter ON issue_comments(commenter_username, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_issue_comments_posted ON issue_comments(posted_to_discord, created_at) WHERE posted_to_discord = FALSE;

-- Table 3: Pull Request Review Comments (from PullRequestReviewCommentEvent)
CREATE TABLE IF NOT EXISTS pr_review_comments (
    event_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    pr_title TEXT,
    commenter_username TEXT NOT NULL,
    commenter_avatar_url TEXT,
    comment_body TEXT,
    file_path TEXT,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    url TEXT,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pr_review_comments_repo ON pr_review_comments(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pr_review_comments_commenter ON pr_review_comments(commenter_username, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pr_review_comments_posted ON pr_review_comments(posted_to_discord, created_at) WHERE posted_to_discord = FALSE;

-- Table 4: Commit Comments (from CommitCommentEvent)
CREATE TABLE IF NOT EXISTS commit_comments (
    event_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    short_sha TEXT NOT NULL,
    commenter_username TEXT NOT NULL,
    commenter_avatar_url TEXT,
    comment_body TEXT,
    file_path TEXT,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    url TEXT,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_commit_comments_repo ON commit_comments(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_commit_comments_commenter ON commit_comments(commenter_username, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_commit_comments_posted ON commit_comments(posted_to_discord, created_at) WHERE posted_to_discord = FALSE;

-- Table 5: Members (from MemberEvent)
CREATE TABLE IF NOT EXISTS members (
    event_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    member_username TEXT NOT NULL,
    member_avatar_url TEXT,
    actor_username TEXT NOT NULL,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_members_repo ON members(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_members_actor ON members(actor_username, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_members_posted ON members(posted_to_discord, created_at) WHERE posted_to_discord = FALSE;

-- Table 6: Wiki Pages (from GollumEvent)
CREATE TABLE IF NOT EXISTS wiki_pages (
    event_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    page_name TEXT NOT NULL,
    page_title TEXT,
    editor_username TEXT NOT NULL,
    editor_avatar_url TEXT,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    is_public BOOLEAN DEFAULT TRUE,
    url TEXT,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wiki_pages_repo ON wiki_pages(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_wiki_pages_editor ON wiki_pages(editor_username, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_wiki_pages_posted ON wiki_pages(posted_to_discord, created_at) WHERE posted_to_discord = FALSE;

-- Table 7: Public Events (from PublicEvent)
CREATE TABLE IF NOT EXISTS public_events (
    event_id TEXT PRIMARY KEY,
    actor_username TEXT NOT NULL,
    actor_avatar_url TEXT,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    event_timestamp TIMESTAMP NOT NULL,
    posted_to_discord BOOLEAN DEFAULT FALSE,
    posted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_public_events_repo ON public_events(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_public_events_actor ON public_events(actor_username, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_public_events_posted ON public_events(posted_to_discord, created_at) WHERE posted_to_discord = FALSE;

-- Table 8: Discussions (from DiscussionEvent - GitHub Discussions)
CREATE TABLE IF NOT EXISTS discussions (
    event_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    discussion_number INTEGER NOT NULL,
    discussion_title TEXT,
    category TEXT,
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

CREATE INDEX IF NOT EXISTS idx_discussions_repo ON discussions(repo_owner, repo_name, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_discussions_author ON discussions(author_username, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_discussions_posted ON discussions(posted_to_discord, created_at) WHERE posted_to_discord = FALSE;
