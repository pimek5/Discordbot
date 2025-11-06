-- Migration: Add voting tables
-- Date: 2025-11-06

-- Voting sessions
CREATE TABLE IF NOT EXISTS voting_sessions (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT,
    started_by BIGINT NOT NULL,
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active'
);

-- Individual votes
CREATE TABLE IF NOT EXISTS voting_votes (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES voting_sessions(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    champion_name VARCHAR(50) NOT NULL,
    rank_position INTEGER NOT NULL,
    points INTEGER NOT NULL,
    voted_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(session_id, user_id, rank_position)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_voting_sessions_status ON voting_sessions(status);
CREATE INDEX IF NOT EXISTS idx_voting_votes_session ON voting_votes(session_id);
CREATE INDEX IF NOT EXISTS idx_voting_votes_user ON voting_votes(user_id);
