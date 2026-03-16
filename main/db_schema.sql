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
    season VARCHAR(10) DEFAULT '15',   -- Season identifier (e.g., '15', '16', etc)
    last_updated TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, queue, season)
);

-- Ranked progress snapshots (for daily LP / games delta in leaderboard)
CREATE TABLE IF NOT EXISTS ranked_progress_snapshots (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    discord_user_id BIGINT NOT NULL,
    puuid VARCHAR(100) NOT NULL,
    tier VARCHAR(20),
    rank VARCHAR(5),
    league_points INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    snapshot_at TIMESTAMP DEFAULT NOW()
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

-- Voting sessions
CREATE TABLE IF NOT EXISTS voting_sessions (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT,                 -- The embed message that gets updated
    started_by BIGINT NOT NULL,        -- User who started the vote
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'ended'
    excluded_champions TEXT[],         -- Array of excluded champion names
    auto_exclude_previous BOOLEAN DEFAULT TRUE -- Auto-exclude winners from previous session
);

-- Individual votes
CREATE TABLE IF NOT EXISTS voting_votes (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES voting_sessions(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    champion_name VARCHAR(50) NOT NULL,
    rank_position INTEGER NOT NULL,    -- 1-5 (position in user's top 5)
    points INTEGER NOT NULL,           -- 1 or 2 based on booster status
    voted_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(session_id, user_id, rank_position)
);

-- Permanent help embed (survives bot restarts)
CREATE TABLE IF NOT EXISTS help_embed (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, channel_id)
);

-- Rank statistics embed (displays member count per rank)
CREATE TABLE IF NOT EXISTS rank_embed (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, channel_id)
);

-- Betting system tables
CREATE TABLE IF NOT EXISTS betting_bets (
    id SERIAL PRIMARY KEY,
    game_id BIGINT NOT NULL,
    platform VARCHAR(10) NOT NULL,
    match_id VARCHAR(32),
    red_team JSONB NOT NULL,
    blue_team JSONB NOT NULL,
    red_odds NUMERIC(6,2) NOT NULL,
    blue_odds NUMERIC(6,2) NOT NULL,
    status VARCHAR(16) DEFAULT 'open', -- open | closed | settled
    winner VARCHAR(8), -- red | blue
    channel_id BIGINT,
    message_id BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS betting_predictions (
    id SERIAL PRIMARY KEY,
    bet_id INTEGER REFERENCES betting_bets(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    side VARCHAR(8) NOT NULL, -- red | blue
    amount INTEGER NOT NULL,
    payout NUMERIC(12,2),
    result VARCHAR(12), -- win | lose | pending
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS betting_leaderboard (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),
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
CREATE INDEX IF NOT EXISTS idx_ranked_progress_lookup
    ON ranked_progress_snapshots(guild_id, discord_user_id, puuid, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_guild_members_guild ON guild_members(guild_id);
CREATE INDEX IF NOT EXISTS idx_verification_expires ON verification_codes(expires_at);
CREATE INDEX IF NOT EXISTS idx_allowed_channels_guild ON allowed_channels(guild_id);
CREATE INDEX IF NOT EXISTS idx_voting_sessions_status ON voting_sessions(status);
CREATE INDEX IF NOT EXISTS idx_voting_votes_session ON voting_votes(session_id);
CREATE INDEX IF NOT EXISTS idx_voting_votes_user ON voting_votes(user_id);
CREATE INDEX IF NOT EXISTS idx_help_embed_guild ON help_embed(guild_id);
CREATE INDEX IF NOT EXISTS idx_betting_bets_status ON betting_bets(status);
CREATE INDEX IF NOT EXISTS idx_betting_predictions_user ON betting_predictions(user_id);
CREATE INDEX IF NOT EXISTS idx_betting_predictions_bet ON betting_predictions(bet_id);
CREATE INDEX IF NOT EXISTS idx_betting_leaderboard_guild ON betting_leaderboard(guild_id);
CREATE INDEX IF NOT EXISTS idx_rank_embed_guild ON rank_embed(guild_id);

-- ================================
--    BAN SYSTEM TABLES
-- ================================

-- User bans with reasoning
CREATE TABLE IF NOT EXISTS user_bans (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,  -- Discord user ID (snowflake)
    guild_id BIGINT NOT NULL,  -- Discord guild ID
    moderator_id BIGINT NOT NULL,  -- Discord ID of moderator who banned
    reason TEXT NOT NULL,  -- Ban reason
    duration_minutes INTEGER,  -- NULL for permanent ban, otherwise minutes
    banned_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,  -- NULL for permanent ban
    active BOOLEAN DEFAULT TRUE,  -- FALSE when unbanned or expired
    unbanned_at TIMESTAMP,
    unbanned_by BIGINT,  -- Discord ID of moderator who unbanned
    unban_reason TEXT
);

-- Ban appeals
CREATE TABLE IF NOT EXISTS ban_appeals (
    id SERIAL PRIMARY KEY,
    ban_id INTEGER NOT NULL REFERENCES user_bans(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    appeal_text TEXT NOT NULL,
    submitted_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'approved', 'denied'
    reviewed_by BIGINT,  -- Discord ID of moderator who reviewed
    reviewed_at TIMESTAMP,
    review_notes TEXT
);

-- Indexes for ban system
CREATE INDEX IF NOT EXISTS idx_user_bans_user ON user_bans(user_id);
CREATE INDEX IF NOT EXISTS idx_user_bans_guild ON user_bans(guild_id);
CREATE INDEX IF NOT EXISTS idx_user_bans_active ON user_bans(active) WHERE active = TRUE;
CREATE INDEX IF NOT EXISTS idx_user_bans_expires ON user_bans(expires_at) WHERE expires_at IS NOT NULL AND active = TRUE;
CREATE INDEX IF NOT EXISTS idx_ban_appeals_ban ON ban_appeals(ban_id);
CREATE INDEX IF NOT EXISTS idx_ban_appeals_status ON ban_appeals(status);

-- ================================
--    GUILD SETTINGS TABLE
-- ================================

-- Guild-specific configuration for all bots
CREATE TABLE IF NOT EXISTS guild_settings (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    key VARCHAR(100) NOT NULL,
    value TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, key)
);

-- Index for guild settings
CREATE INDEX IF NOT EXISTS idx_guild_settings_guild ON guild_settings(guild_id);
CREATE INDEX IF NOT EXISTS idx_guild_settings_key ON guild_settings(guild_id, key);

-- ================================
--    LOLDLE GAME TABLES
-- ================================

-- Loldle player statistics (persistent)
CREATE TABLE IF NOT EXISTS loldle_stats (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    guild_id BIGINT NOT NULL,
    total_games INTEGER DEFAULT 0,
    total_wins INTEGER DEFAULT 0,
    total_guesses INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    current_streak INTEGER DEFAULT 0,
    last_win_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, guild_id)
);

-- Loldle daily games (track daily champion and progress)
CREATE TABLE IF NOT EXISTS loldle_daily_games (
    id SERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    game_date DATE NOT NULL,
    champion_name VARCHAR(50) NOT NULL,
    mode VARCHAR(20) DEFAULT 'classic',  -- classic, quote, ability, emoji, splash
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, game_date, mode)
);

-- Loldle player progress (per daily game)
CREATE TABLE IF NOT EXISTS loldle_player_progress (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES loldle_daily_games(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    guesses TEXT[],  -- Array of champion names guessed
    solved BOOLEAN DEFAULT FALSE,
    attempts INTEGER DEFAULT 0,
    solved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(game_id, user_id)
);

-- Indexes for loldle
CREATE INDEX IF NOT EXISTS idx_loldle_stats_user ON loldle_stats(user_id);
CREATE INDEX IF NOT EXISTS idx_loldle_stats_guild ON loldle_stats(guild_id);
CREATE INDEX IF NOT EXISTS idx_loldle_daily_date ON loldle_daily_games(guild_id, game_date);
CREATE INDEX IF NOT EXISTS idx_loldle_progress_game ON loldle_player_progress(game_id);
CREATE INDEX IF NOT EXISTS idx_loldle_progress_user ON loldle_player_progress(user_id);

-- ================================
--    PRO TEAMS & PLAYERS (RL-STATS.PL)
-- ================================

-- Professional teams
CREATE TABLE IF NOT EXISTS pro_teams (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    tag VARCHAR(20) NOT NULL UNIQUE,
    rank INTEGER,
    rating INTEGER DEFAULT 0,
    rating_change INTEGER DEFAULT 0,
    url TEXT,
    last_updated TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Professional players
CREATE TABLE IF NOT EXISTS pro_players (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    role VARCHAR(20),
    team_id INTEGER REFERENCES pro_teams(id) ON DELETE SET NULL,
    kda DECIMAL(4,2),
    avg_kills DECIMAL(4,1),
    avg_deaths DECIMAL(4,1),
    avg_assists DECIMAL(4,1),
    rating DECIMAL(4,2),
    win_rate DECIMAL(5,2),
    games_played INTEGER DEFAULT 0,
    cs_per_min DECIMAL(4,1),
    url TEXT,
    last_updated TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Professional player champion statistics
CREATE TABLE IF NOT EXISTS pro_player_champions (
    id SERIAL PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES pro_players(id) ON DELETE CASCADE,
    champion VARCHAR(50) NOT NULL,
    games INTEGER DEFAULT 0,
    kda DECIMAL(4,2),
    win_rate DECIMAL(5,2),
    last_updated TIMESTAMP DEFAULT NOW(),
    UNIQUE(player_id, champion)
);

-- Indexes for pro stats
CREATE INDEX IF NOT EXISTS idx_pro_teams_tag ON pro_teams(tag);
CREATE INDEX IF NOT EXISTS idx_pro_teams_rank ON pro_teams(rank);
CREATE INDEX IF NOT EXISTS idx_pro_players_name ON pro_players(name);
CREATE INDEX IF NOT EXISTS idx_pro_players_team ON pro_players(team_id);
CREATE INDEX IF NOT EXISTS idx_pro_player_champs ON pro_player_champions(player_id);
