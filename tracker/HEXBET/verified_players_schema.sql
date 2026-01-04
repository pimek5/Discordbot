-- Schema for verified players (PRO/STRM badges)
-- Stores player verification data from lolpros.gg

CREATE TABLE IF NOT EXISTS hexbet_verified_players (
    id SERIAL PRIMARY KEY,
    riot_id VARCHAR(50) UNIQUE NOT NULL,  -- gameName#tagLine
    player_name VARCHAR(100),              -- Display name (e.g., "Faker", "Thebausffs")
    player_type VARCHAR(20) NOT NULL,      -- 'pro' or 'streamer'
    team VARCHAR(100),                     -- Team name (for pros)
    platform VARCHAR(50),                  -- Twitch/YouTube (for streamers)
    lolpros_url VARCHAR(255),              -- lolpros.gg profile URL
    leaguepedia_url VARCHAR(255),          -- Leaguepedia profile URL (if exists)
    verified_at TIMESTAMP DEFAULT NOW(),   -- When first verified
    last_seen TIMESTAMP DEFAULT NOW(),     -- Last time seen in a game
    CONSTRAINT check_player_type CHECK (player_type IN ('pro', 'streamer'))
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_verified_players_riot_id ON hexbet_verified_players(riot_id);
CREATE INDEX IF NOT EXISTS idx_verified_players_type ON hexbet_verified_players(player_type);

-- Add last_checked column to track when we last scraped lolpros.gg for each player
ALTER TABLE hexbet_verified_players ADD COLUMN IF NOT EXISTS last_checked TIMESTAMP;
