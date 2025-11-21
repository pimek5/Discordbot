-- Tracker Bot Database Schema
-- Tables for pro player tracking and betting system

-- Pro players tracking
CREATE TABLE IF NOT EXISTS tracked_pros (
    id SERIAL PRIMARY KEY,
    player_name VARCHAR(100) UNIQUE NOT NULL,
    real_name VARCHAR(100),
    team VARCHAR(100),
    region VARCHAR(20),
    role VARCHAR(20),
    country VARCHAR(100),
    twitter_url TEXT,
    twitch_url TEXT,
    youtube_url TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    total_games INTEGER DEFAULT 0,
    avg_kda DECIMAL(5,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Pro player accounts (Riot accounts)
CREATE TABLE IF NOT EXISTS pro_accounts (
    id SERIAL PRIMARY KEY,
    pro_id INTEGER NOT NULL REFERENCES tracked_pros(id) ON DELETE CASCADE,
    game_name VARCHAR(100) NOT NULL,
    tag_line VARCHAR(20) NOT NULL,
    region VARCHAR(10) NOT NULL,
    puuid VARCHAR(100) UNIQUE,
    summoner_id VARCHAR(100),
    account_id VARCHAR(100),
    tier VARCHAR(20),
    rank VARCHAR(5),
    league_points INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(game_name, tag_line, region)
);

-- Active game tracking
CREATE TABLE IF NOT EXISTS active_games (
    id SERIAL PRIMARY KEY,
    game_id BIGINT UNIQUE NOT NULL,
    pro_id INTEGER NOT NULL REFERENCES tracked_pros(id) ON DELETE CASCADE,
    account_id INTEGER REFERENCES pro_accounts(id),
    region VARCHAR(10) NOT NULL,
    game_mode VARCHAR(50),
    game_start_time BIGINT,
    notification_message_id BIGINT,
    notification_channel_id BIGINT,
    betting_open BOOLEAN DEFAULT TRUE,
    resolved BOOLEAN DEFAULT FALSE,
    result VARCHAR(10),  -- 'win', 'loss', 'remake'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Betting system
CREATE TABLE IF NOT EXISTS bets (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES active_games(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,  -- Discord user ID
    bet_amount INTEGER NOT NULL,
    bet_on VARCHAR(10) NOT NULL,  -- 'win' or 'loss'
    multiplier DECIMAL(5,2) DEFAULT 1.0,
    potential_win INTEGER,
    resolved BOOLEAN DEFAULT FALSE,
    won BOOLEAN,
    payout INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(game_id, user_id)
);

-- User balances for betting
CREATE TABLE IF NOT EXISTS user_balances (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT UNIQUE NOT NULL,
    balance INTEGER DEFAULT 1000,  -- Starting balance
    total_wagered INTEGER DEFAULT 0,
    total_won INTEGER DEFAULT 0,
    total_lost INTEGER DEFAULT 0,
    bets_placed INTEGER DEFAULT 0,
    bets_won INTEGER DEFAULT 0,
    last_daily TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Bet leaderboard history
CREATE TABLE IF NOT EXISTS bet_leaderboard (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL,
    username VARCHAR(100),
    balance INTEGER NOT NULL,
    total_won INTEGER DEFAULT 0,
    bets_won INTEGER DEFAULT 0,
    win_rate DECIMAL(5,2) DEFAULT 0,
    recorded_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_tracked_pros_name ON tracked_pros(LOWER(player_name));
CREATE INDEX IF NOT EXISTS idx_tracked_pros_enabled ON tracked_pros(enabled);
CREATE INDEX IF NOT EXISTS idx_pro_accounts_pro_id ON pro_accounts(pro_id);
CREATE INDEX IF NOT EXISTS idx_pro_accounts_puuid ON pro_accounts(puuid);
CREATE INDEX IF NOT EXISTS idx_active_games_game_id ON active_games(game_id);
CREATE INDEX IF NOT EXISTS idx_active_games_pro_id ON active_games(pro_id);
CREATE INDEX IF NOT EXISTS idx_active_games_resolved ON active_games(resolved);
CREATE INDEX IF NOT EXISTS idx_bets_game_id ON bets(game_id);
CREATE INDEX IF NOT EXISTS idx_bets_user_id ON bets(user_id);
CREATE INDEX IF NOT EXISTS idx_user_balances_discord_id ON user_balances(discord_id);
CREATE INDEX IF NOT EXISTS idx_bet_leaderboard_discord_id ON bet_leaderboard(discord_id);
CREATE INDEX IF NOT EXISTS idx_bet_leaderboard_recorded_at ON bet_leaderboard(recorded_at);

-- Guild settings for configuration (shared with main bot)
CREATE TABLE IF NOT EXISTS guild_settings (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    key VARCHAR(100) NOT NULL,
    value TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, key)
);

CREATE INDEX IF NOT EXISTS idx_guild_settings_guild_id ON guild_settings(guild_id);
CREATE INDEX IF NOT EXISTS idx_guild_settings_guild_key ON guild_settings(guild_id, key);
