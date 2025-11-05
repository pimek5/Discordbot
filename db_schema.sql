-- Orianna Bot Database Schema
-- PostgreSQL 14+

-- Users table - Discord users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    snowflake BIGINT UNIQUE NOT NULL,  -- Discord user ID
    created_at TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW()
);

-- League of Legends accounts
CREATE TABLE IF NOT EXISTS league_accounts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    region VARCHAR(10) NOT NULL,
    riot_id_game_name VARCHAR(100) NOT NULL,
    riot_id_tagline VARCHAR(20) NOT NULL,
    puuid VARCHAR(100) UNIQUE NOT NULL,
    summoner_id VARCHAR(100),
    summoner_level INTEGER DEFAULT 1,
    profile_icon_id INTEGER,
    show_in_profile BOOLEAN DEFAULT TRUE,
    primary_account BOOLEAN DEFAULT FALSE,
    verified BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, puuid)
);

-- Champion mastery statistics
CREATE TABLE IF NOT EXISTS user_champion_stats (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    champion_id INTEGER NOT NULL,
    score INTEGER DEFAULT 0,
    level INTEGER DEFAULT 0,
    chest_granted BOOLEAN DEFAULT FALSE,
    tokens_earned INTEGER DEFAULT 0,
    last_play_time BIGINT,
    last_updated TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, champion_id)
);

-- Mastery change history (for progression tracking)
CREATE TABLE IF NOT EXISTS user_mastery_delta (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    champion_id INTEGER NOT NULL,
    delta INTEGER NOT NULL,           -- Change in points (+500, +1200, etc)
    value INTEGER NOT NULL,            -- Total points after change
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Ranked statistics
CREATE TABLE IF NOT EXISTS user_ranks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    queue VARCHAR(50) NOT NULL,        -- RANKED_SOLO_5x5, RANKED_FLEX_SR, RANKED_TFT
    tier VARCHAR(20),                  -- IRON, BRONZE, SILVER, GOLD, PLATINUM, EMERALD, DIAMOND, MASTER, GRANDMASTER, CHALLENGER
    rank VARCHAR(5),                   -- I, II, III, IV
    league_points INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    hot_streak BOOLEAN DEFAULT FALSE,
    veteran BOOLEAN DEFAULT FALSE,
    fresh_blood BOOLEAN DEFAULT FALSE,
    inactive BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, queue)
);

-- Guild membership tracking
CREATE TABLE IF NOT EXISTS guild_members (
    guild_id BIGINT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id)
);

-- Verification codes (temporary storage)
CREATE TABLE IF NOT EXISTS verification_codes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code VARCHAR(20) NOT NULL,
    riot_id_game_name VARCHAR(100),
    riot_id_tagline VARCHAR(20),
    region VARCHAR(10),
    puuid VARCHAR(100),
    summoner_id VARCHAR(100),
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Allowed channels for bot commands (per guild)
CREATE TABLE IF NOT EXISTS allowed_channels (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, channel_id)
);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_users_snowflake ON users(snowflake);
CREATE INDEX IF NOT EXISTS idx_league_accounts_user ON league_accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_league_accounts_puuid ON league_accounts(puuid);
CREATE INDEX IF NOT EXISTS idx_champion_stats_user ON user_champion_stats(user_id);
CREATE INDEX IF NOT EXISTS idx_champion_stats_score ON user_champion_stats(score DESC);
CREATE INDEX IF NOT EXISTS idx_mastery_delta_user_champ ON user_mastery_delta(user_id, champion_id);
CREATE INDEX IF NOT EXISTS idx_ranks_user ON user_ranks(user_id);
CREATE INDEX IF NOT EXISTS idx_guild_members_guild ON guild_members(guild_id);
CREATE INDEX IF NOT EXISTS idx_verification_expires ON verification_codes(expires_at);
CREATE INDEX IF NOT EXISTS idx_allowed_channels_guild ON allowed_channels(guild_id);
