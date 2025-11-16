-- Activity Bot Stats and Achievements Migration
-- Creates tables for achievement tracking, streak tracking, and statistics
-- Runs automatically on first postgres startup via docker-entrypoint-initdb.d

-- Table 1: Achievement History (repeatable achievements with period tracking)
CREATE TABLE IF NOT EXISTS achievement_history (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    achievement_id TEXT NOT NULL,
    period_type TEXT NOT NULL CHECK (period_type IN ('daily', 'weekly', 'monthly', 'milestone')),
    period_date DATE NOT NULL,  -- Date representing the period (e.g., 2025-01-15 for daily, 2025-01-13 for week starting Mon)
    earned_at TIMESTAMP NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,  -- Additional context (e.g., count, threshold met)
    UNIQUE (username, achievement_id, period_type, period_date)
);

-- Indexes for achievement history
CREATE INDEX IF NOT EXISTS idx_achievement_history_user ON achievement_history(username);
CREATE INDEX IF NOT EXISTS idx_achievement_history_period ON achievement_history(period_date);
CREATE INDEX IF NOT EXISTS idx_achievement_history_lookup ON achievement_history(username, achievement_id, period_type, period_date);

-- Table 2: Streak Tracking (independent daily/weekly/monthly/yearly streaks)
CREATE TABLE IF NOT EXISTS streak_tracking (
    username TEXT NOT NULL,
    streak_type TEXT NOT NULL CHECK (streak_type IN ('daily', 'weekly', 'monthly', 'yearly')),
    current_streak INT DEFAULT 0,
    longest_streak INT DEFAULT 0,
    last_activity_date DATE,  -- Last date with activity (for grace period checking)
    last_updated TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (username, streak_type)
);

-- Indexes for streak tracking
CREATE INDEX IF NOT EXISTS idx_streak_tracking_user ON streak_tracking(username);
CREATE INDEX IF NOT EXISTS idx_streak_tracking_type ON streak_tracking(streak_type, current_streak DESC);

-- ON CONFLICT DO NOTHING allows safe re-run (idempotent)
