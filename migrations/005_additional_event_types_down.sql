-- Activity Bot Additional Event Types Rollback Migration
-- Drops 8 new GitHub event types: stars, issue comments, PR review comments, commit comments, members, wiki pages, public events, discussions
-- Use this to rollback migration 005 if needed

-- Drop discussions table and indexes
DROP INDEX IF EXISTS idx_discussions_posted;
DROP INDEX IF EXISTS idx_discussions_author;
DROP INDEX IF EXISTS idx_discussions_repo;
DROP TABLE IF EXISTS discussions;

-- Drop public_events table and indexes
DROP INDEX IF EXISTS idx_public_events_posted;
DROP INDEX IF EXISTS idx_public_events_actor;
DROP INDEX IF EXISTS idx_public_events_repo;
DROP TABLE IF EXISTS public_events;

-- Drop wiki_pages table and indexes
DROP INDEX IF EXISTS idx_wiki_pages_posted;
DROP INDEX IF EXISTS idx_wiki_pages_editor;
DROP INDEX IF EXISTS idx_wiki_pages_repo;
DROP TABLE IF EXISTS wiki_pages;

-- Drop members table and indexes
DROP INDEX IF EXISTS idx_members_posted;
DROP INDEX IF EXISTS idx_members_actor;
DROP INDEX IF EXISTS idx_members_repo;
DROP TABLE IF EXISTS members;

-- Drop commit_comments table and indexes
DROP INDEX IF EXISTS idx_commit_comments_posted;
DROP INDEX IF EXISTS idx_commit_comments_commenter;
DROP INDEX IF EXISTS idx_commit_comments_repo;
DROP TABLE IF EXISTS commit_comments;

-- Drop pr_review_comments table and indexes
DROP INDEX IF EXISTS idx_pr_review_comments_posted;
DROP INDEX IF EXISTS idx_pr_review_comments_commenter;
DROP INDEX IF EXISTS idx_pr_review_comments_repo;
DROP TABLE IF EXISTS pr_review_comments;

-- Drop issue_comments table and indexes
DROP INDEX IF EXISTS idx_issue_comments_posted;
DROP INDEX IF EXISTS idx_issue_comments_commenter;
DROP INDEX IF EXISTS idx_issue_comments_repo;
DROP TABLE IF EXISTS issue_comments;

-- Drop stars table and indexes
DROP INDEX IF EXISTS idx_stars_posted;
DROP INDEX IF EXISTS idx_stars_stargazer;
DROP INDEX IF EXISTS idx_stars_repo;
DROP TABLE IF EXISTS stars;
