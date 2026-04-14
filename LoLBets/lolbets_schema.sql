-- LoLBets professional multi-guild / global betting schema scaffold

CREATE TABLE IF NOT EXISTS lolbets_guilds (
    guild_id BIGINT PRIMARY KEY,
    brand_name TEXT DEFAULT 'LoLBets',
    default_region TEXT,
    betting_enabled BOOLEAN DEFAULT TRUE,
    streamer_markets_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lolbets_wallets (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    balance BIGINT NOT NULL DEFAULT 1000,
    lifetime_wagered BIGINT NOT NULL DEFAULT 0,
    lifetime_profit BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS lolbets_ledger (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    entry_type TEXT NOT NULL,
    amount BIGINT NOT NULL,
    reference_type TEXT,
    reference_id BIGINT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lolbets_streamers (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    display_name TEXT NOT NULL,
    riot_id TEXT,
    platform_route TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    active BOOLEAN DEFAULT TRUE,
    created_by BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lolbets_events (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    source_ref TEXT,
    title TEXT NOT NULL,
    subject_name TEXT,
    subject_riot_id TEXT,
    region TEXT,
    starts_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'draft',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_by BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lolbets_markets (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES lolbets_events(id) ON DELETE CASCADE,
    market_type TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    closes_at TIMESTAMP,
    settlement_data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lolbets_selections (
    id BIGSERIAL PRIMARY KEY,
    market_id BIGINT NOT NULL REFERENCES lolbets_markets(id) ON DELETE CASCADE,
    selection_key TEXT NOT NULL,
    selection_label TEXT NOT NULL,
    decimal_odds NUMERIC(10,2) NOT NULL,
    probability NUMERIC(6,4),
    result TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lolbets_bets (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    market_id BIGINT NOT NULL REFERENCES lolbets_markets(id) ON DELETE CASCADE,
    selection_id BIGINT NOT NULL REFERENCES lolbets_selections(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    stake BIGINT NOT NULL,
    decimal_odds NUMERIC(10,2) NOT NULL,
    potential_payout BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    settled_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_lolbets_wallets_guild_user ON lolbets_wallets(guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_lolbets_ledger_guild_user ON lolbets_ledger(guild_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lolbets_streamers_guild ON lolbets_streamers(guild_id, active);
CREATE INDEX IF NOT EXISTS idx_lolbets_events_guild_status ON lolbets_events(guild_id, status, starts_at DESC);
CREATE INDEX IF NOT EXISTS idx_lolbets_markets_event_status ON lolbets_markets(event_id, status);
CREATE INDEX IF NOT EXISTS idx_lolbets_bets_guild_user ON lolbets_bets(guild_id, user_id, created_at DESC);
