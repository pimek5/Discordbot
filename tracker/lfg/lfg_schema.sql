-- ============================================
-- LFG (Looking For Group) System Schema
-- ============================================

-- Tabela profili graczy LFG
CREATE TABLE IF NOT EXISTS lfg_profiles (
    user_id BIGINT PRIMARY KEY,
    riot_id_game_name VARCHAR(50),
    riot_id_tagline VARCHAR(10),
    puuid VARCHAR(100),
    region VARCHAR(10) NOT NULL,
    
    -- Role preferences (JSON array: ["top", "jungle", "mid", "adc", "support"])
    primary_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    secondary_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    -- Current ranks (JSON object per queue type)
    solo_rank VARCHAR(20),
    flex_rank VARCHAR(20),
    arena_rank VARCHAR(20),
    
    -- Top champions (JSON array of champion names)
    top_champions JSONB DEFAULT '[]'::jsonb,
    
    -- Profile info
    description TEXT,
    voice_required BOOLEAN DEFAULT FALSE,
    language VARCHAR(10) DEFAULT 'pl',
    
    -- Activity preferences
    playstyle VARCHAR(20), -- 'casual', 'competitive', 'mixed'
    availability TEXT, -- Free text or JSON
    
    -- Stats (auto-updated from Riot API)
    total_mastery_score INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela ogłoszeń LFG
CREATE TABLE IF NOT EXISTS lfg_listings (
    listing_id SERIAL PRIMARY KEY,
    creator_user_id BIGINT NOT NULL,
    
    -- What they're looking for
    queue_type VARCHAR(30) NOT NULL, -- 'ranked_solo', 'ranked_flex', 'normal', 'aram', 'arena'
    roles_needed JSONB NOT NULL, -- ["adc", "support"]
    spots_available INTEGER NOT NULL DEFAULT 1,
    
    -- Requirements
    min_rank VARCHAR(20),
    max_rank VARCHAR(20),
    region VARCHAR(10) NOT NULL,
    voice_required BOOLEAN DEFAULT FALSE,
    language VARCHAR(10) DEFAULT 'pl',
    
    -- Description
    title VARCHAR(100),
    description TEXT,
    
    -- Discord message info
    message_id BIGINT,
    channel_id BIGINT,
    
    -- Status
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'filled', 'expired', 'cancelled'
    expires_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (creator_user_id) REFERENCES lfg_profiles(user_id) ON DELETE CASCADE
);

-- Tabela aplikacji do grup
CREATE TABLE IF NOT EXISTS lfg_applications (
    application_id SERIAL PRIMARY KEY,
    listing_id INTEGER NOT NULL,
    applicant_user_id BIGINT NOT NULL,
    
    role VARCHAR(20), -- Role they want to play
    message TEXT, -- Optional message
    
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'accepted', 'declined'
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (listing_id) REFERENCES lfg_listings(listing_id) ON DELETE CASCADE,
    FOREIGN KEY (applicant_user_id) REFERENCES lfg_profiles(user_id) ON DELETE CASCADE
);

-- Tabela statystyk grup (do przyszłego matchmaking)
CREATE TABLE IF NOT EXISTS lfg_group_history (
    group_id SERIAL PRIMARY KEY,
    listing_id INTEGER NOT NULL,
    
    -- Members (JSON array of user_ids)
    members JSONB NOT NULL,
    
    -- Game info (if available)
    game_id BIGINT,
    game_result VARCHAR(20), -- 'win', 'loss', 'remake'
    game_duration INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (listing_id) REFERENCES lfg_listings(listing_id) ON DELETE CASCADE
);

-- Indeksy dla wydajności
CREATE INDEX idx_lfg_listings_status ON lfg_listings(status);
CREATE INDEX idx_lfg_listings_queue_type ON lfg_listings(queue_type);
CREATE INDEX idx_lfg_listings_region ON lfg_listings(region);
CREATE INDEX idx_lfg_listings_expires_at ON lfg_listings(expires_at);
CREATE INDEX idx_lfg_applications_listing ON lfg_applications(listing_id);
CREATE INDEX idx_lfg_applications_status ON lfg_applications(status);
