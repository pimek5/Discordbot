-- ============================================
-- HEXBET Expansion: Database Setup
-- ============================================
-- Run these migrations to support new features
-- Achievements, Head-to-Head cache, etc.

-- 1. ACHIEVEMENTS TABLE
-- Stores which achievements users have earned
CREATE TABLE IF NOT EXISTS user_achievements (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    achievement_id VARCHAR(50) NOT NULL,
    earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, achievement_id),
    INDEX idx_user_achievements (user_id)
);

-- 2. MATCHUP HISTORY TABLE (Optional - for H2H caching)
-- Cache recent team matchups to speed up queries
CREATE TABLE IF NOT EXISTS matchup_history (
    id SERIAL PRIMARY KEY,
    match_id INT,
    blue_players TEXT,  -- JSON array or comma-separated
    red_players TEXT,   -- JSON array or comma-separated
    winner VARCHAR(10),  -- 'blue', 'red', 'cancelled'
    odds_blue FLOAT,
    odds_red FLOAT,
    duration_seconds INT,
    created_at TIMESTAMP,
    INDEX idx_matchup_history (created_at)
);

-- 3. USER FOLLOWS TABLE (Optional - for future "follow bettor" feature)
-- Let users follow and get notified of top bettors
CREATE TABLE IF NOT EXISTS user_follows (
    follower_id BIGINT,
    following_id BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(follower_id, following_id),
    INDEX idx_follower (follower_id),
    INDEX idx_following (following_id)
);

-- 4. ACHIEVEMENT TRACKER (For quick stats)
-- Optional - to speed up achievement checking
CREATE TABLE IF NOT EXISTS achievement_progress (
    user_id BIGINT PRIMARY KEY,
    total_bets INT DEFAULT 0,
    total_wins INT DEFAULT 0,
    current_streak INT DEFAULT 0,
    current_streak_type VARCHAR(1),  -- 'W' or 'L'
    highest_roi FLOAT DEFAULT 0,
    highest_wr FLOAT DEFAULT 0,
    total_profit FLOAT DEFAULT 0,
    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_progress (user_id)
);

-- ============================================
-- USEFUL VIEWS FOR LEADERBOARD
-- ============================================

-- Get ROI leaders for past N days
CREATE OR REPLACE VIEW leaderboard_roi_7d AS
SELECT 
    b.user_id,
    COUNT(*) as total_bets,
    SUM(CASE WHEN b.result = 'win' THEN 1 ELSE 0 END) as wins,
    ROUND(100.0 * SUM(CASE WHEN b.result = 'win' THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
    ROUND(100.0 * (SUM(CASE WHEN b.result = 'win' THEN b.potential_win ELSE -b.amount END) / NULLIF(SUM(b.amount), 0) - 1), 1) as roi
FROM hexbet_bets b
WHERE b.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY b.user_id
HAVING total_bets >= 3
ORDER BY roi DESC
LIMIT 50;

-- Get high win rate players (min 20 bets all time)
CREATE OR REPLACE VIEW leaderboard_high_wr AS
SELECT 
    b.user_id,
    COUNT(*) as total_bets,
    SUM(CASE WHEN b.result = 'win' THEN 1 ELSE 0 END) as wins,
    ROUND(100.0 * SUM(CASE WHEN b.result = 'win' THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate
FROM hexbet_bets b
GROUP BY b.user_id
HAVING total_bets >= 20
ORDER BY win_rate DESC
LIMIT 50;

-- Get profit leaders (all time)
CREATE OR REPLACE VIEW leaderboard_profit AS
SELECT 
    b.user_id,
    COUNT(*) as total_bets,
    SUM(CASE WHEN b.result = 'win' THEN b.potential_win ELSE -b.amount END) as total_profit,
    SUM(b.amount) as total_wagered
FROM hexbet_bets b
WHERE b.result IN ('win', 'loss')
GROUP BY b.user_id
HAVING total_profit > 0
ORDER BY total_profit DESC
LIMIT 50;

-- ============================================
-- REQUIRED DATABASE METHOD UPDATES
-- ============================================
-- Add these methods to TrackerDatabase class:

/*
def get_user_achievements(self, user_id: int) -> List[Dict]:
    conn = self.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT achievement_id, earned_at FROM user_achievements WHERE user_id = %s", (user_id,))
    results = cursor.fetchall()
    cursor.close()
    self.return_connection(conn)
    return [{'achievement_id': r[0], 'earned_at': r[1]} for r in results]

def add_user_achievement(self, user_id: int, achievement_id: str) -> bool:
    conn = self.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO user_achievements (user_id, achievement_id) VALUES (%s, %s)",
            (user_id, achievement_id)
        )
        conn.commit()
        cursor.close()
        self.return_connection(conn)
        return True
    except Exception as e:
        logger.error(f"Failed to add achievement: {e}")
        cursor.close()
        self.return_connection(conn)
        return False

def get_user_bet_history(self, user_id: int, **filters) -> List[Dict]:
    # filters: side, outcome, min_amount, max_amount, min_odds, max_odds, days, sort, limit, offset
    conn = self.get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM hexbet_bets WHERE user_id = %s"
    params = [user_id]
    
    days = filters.get('days', 30)
    query += f" AND created_at >= DATE_SUB(NOW(), INTERVAL {days} DAY)"
    
    if filters.get('side'):
        query += " AND side = %s"
        params.append(filters['side'])
    
    if filters.get('outcome'):
        query += " AND result = %s"
        params.append(filters['outcome'])
    
    if filters.get('min_amount'):
        query += " AND amount >= %s"
        params.append(filters['min_amount'])
    
    if filters.get('max_amount'):
        query += " AND amount <= %s"
        params.append(filters['max_amount'])
    
    sort_map = {
        'date_desc': 'created_at DESC',
        'date_asc': 'created_at ASC',
        'profit': 'profit_loss DESC',
        'amount': 'amount DESC',
        'odds': 'odds DESC'
    }
    query += f" ORDER BY {sort_map.get(filters.get('sort', 'date_desc'), 'created_at DESC')}"
    
    limit = filters.get('limit', 10)
    offset = filters.get('offset', 0)
    query += f" LIMIT {limit} OFFSET {offset}"
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    cursor.close()
    self.return_connection(conn)
    
    # Convert to dicts
    columns = ['id', 'user_id', 'match_id', 'side', 'amount', 'odds', 'result', 'profit_loss', 'created_at']
    return [dict(zip(columns, r)) for r in results]

def get_matching_history(self, blue_players: List[int], red_players: List[int], days: int = 90, limit: int = 50) -> List[Dict]:
    # Get historical matchups between two specific teams
    conn = self.get_connection()
    cursor = conn.cursor()
    
    # This would require storing player IDs in match data or a separate junction table
    # For now, returns empty - implement based on your schema
    cursor.close()
    self.return_connection(conn)
    return []

def get_composition_winrate(self, champions: List[str], days: int = 90, limit: int = 50) -> Dict:
    # Get win rate for specific champion compositions
    conn = self.get_connection()
    cursor = conn.cursor()
    
    # This would require champion data in match records
    # For now, returns empty - implement based on your schema
    cursor.close()
    self.return_connection(conn)
    return {}

def get_daily_betting_analytics(self, user_id: int, days: int = 30) -> List[Dict]:
    conn = self.get_connection()
    cursor = conn.cursor()
    query = """
    SELECT 
        DATE(created_at) as date,
        COUNT(*) as bets,
        SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
        ROUND(SUM(CASE WHEN result = 'win' THEN potential_win ELSE -amount END), 0) as profit
    FROM hexbet_bets
    WHERE user_id = %s AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
    GROUP BY DATE(created_at)
    ORDER BY date DESC
    """
    cursor.execute(query, (user_id, days))
    results = cursor.fetchall()
    cursor.close()
    self.return_connection(conn)
    
    return [{'date': r[0], 'bets': r[1], 'wins': r[2], 'profit': r[3]} for r in results]
*/

-- ============================================
-- INDEXES FOR PERFORMANCE
-- ============================================

CREATE INDEX IF NOT EXISTS idx_user_achievements_user ON user_achievements(user_id);
CREATE INDEX IF NOT EXISTS idx_matchup_history_created ON matchup_history(created_at);
CREATE INDEX IF NOT EXISTS idx_user_follows_follower ON user_follows(follower_id);
CREATE INDEX IF NOT EXISTS idx_user_follows_following ON user_follows(following_id);
