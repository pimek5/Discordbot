"""
Tracker Bot Database Handler
Separate database connection for tracker bot
"""

import psycopg2
from psycopg2 import pool
import os
import json
from typing import Optional, List, Dict, Tuple
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger('tracker_database')

class TrackerDatabase:
    def __init__(self):
        self.connection_pool = None
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize PostgreSQL connection pool"""
        try:
            database_url = os.getenv('DATABASE_URL')
            if not database_url:
                raise ValueError("DATABASE_URL not found in environment variables")
            
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                1,  # minconn
                10,  # maxconn
                database_url
            )
            logger.info("✅ Tracker database connection pool initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize database pool: {e}")
            raise
    
    def get_connection(self):
        """Get a connection from the pool"""
        if self.connection_pool:
            return self.connection_pool.getconn()
        raise Exception("Connection pool not initialized")
    
    def return_connection(self, conn):
        """Return a connection to the pool"""
        if self.connection_pool:
            self.connection_pool.putconn(conn)
    
    def close_all_connections(self):
        """Close all connections in the pool"""
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("✅ All database connections closed")
    
    def get_user_by_discord_id(self, discord_id: int):
        """Get user by Discord ID"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            # Main bot schema uses 'snowflake' column
            cur.execute("SELECT * FROM users WHERE snowflake = %s", (discord_id,))
            row = cur.fetchone()
            if row:
                cols = [desc[0] for desc in cur.description]
                return dict(zip(cols, row))
            return None
        except Exception as e:
            logger.error(f"Error getting user by discord_id: {e}")
            conn.rollback()
            return None
        finally:
            self.return_connection(conn)

    # ================= HEXBET =================
    def ensure_hexbet_tables(self):
        """Ensure hexbet tables exist (defensive)."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hexbet_matches (
                        id SERIAL PRIMARY KEY,
                        game_id BIGINT UNIQUE NOT NULL,
                        platform VARCHAR(10) NOT NULL,
                        channel_id BIGINT NOT NULL,
                        message_id BIGINT,
                        blue_team JSONB,
                        red_team JSONB,
                        status VARCHAR(20) DEFAULT 'open',
                        winner VARCHAR(10),
                        start_time BIGINT,
                        game_start_at TIMESTAMP,
                        special_bet BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hexbet_bets (
                        id SERIAL PRIMARY KEY,
                        match_id INTEGER NOT NULL REFERENCES hexbet_matches(id) ON DELETE CASCADE,
                        user_id BIGINT NOT NULL,
                        side VARCHAR(10) NOT NULL,
                        amount INTEGER NOT NULL,
                        odds DECIMAL(6,3) DEFAULT 1.0,
                        potential_win INTEGER,
                        settled BOOLEAN DEFAULT FALSE,
                        won BOOLEAN,
                        payout INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW(),
                        UNIQUE(match_id, user_id)
                    );
                """)
                
                # Migration: add game_start_at timestamp column if it doesn't exist
                try:
                    cur.execute("ALTER TABLE hexbet_matches ADD COLUMN IF NOT EXISTS game_start_at TIMESTAMP")
                    logger.info("✅ Migrated: game_start_at column")
                except psycopg2.Error as e:
                    # Rollback failed migration to restore transaction state
                    conn.rollback()
                    if "already exists" not in str(e):
                        logger.warning(f"Migration note: {e}")
                    # Reconnect cursor after rollback
                    cur = conn.cursor()
                
                # Migration: add special_bet column if it doesn't exist
                try:
                    cur.execute("ALTER TABLE hexbet_matches ADD COLUMN IF NOT EXISTS special_bet BOOLEAN DEFAULT FALSE")
                    logger.info("✅ Migrated: special_bet column")
                except psycopg2.Error as e:
                    conn.rollback()
                    if "already exists" not in str(e):
                        logger.warning(f"Migration note: {e}")
                    cur = conn.cursor()
                
                # Migration: add last_daily_claim for daily rewards
                try:
                    cur.execute("ALTER TABLE user_balances ADD COLUMN IF NOT EXISTS last_daily_claim TIMESTAMP")
                    logger.info("✅ Migrated: last_daily_claim column")
                except psycopg2.Error as e:
                    conn.rollback()
                    if "already exists" not in str(e):
                        logger.warning(f"Migration note: {e}")
                    cur = conn.cursor()
                
                # Migration: add daily betting limit tracking
                try:
                    cur.execute("ALTER TABLE user_balances ADD COLUMN IF NOT EXISTS daily_wagered INTEGER DEFAULT 0")
                    cur.execute("ALTER TABLE user_balances ADD COLUMN IF NOT EXISTS last_wager_date DATE")
                    logger.info("✅ Migrated: daily_wagered and last_wager_date columns")
                except psycopg2.Error as e:
                    conn.rollback()
                    if "already exists" not in str(e):
                        logger.warning(f"Migration note: {e}")
                    cur = conn.cursor()
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hexbet_leaderboard_cache (
                        id SERIAL PRIMARY KEY,
                        discord_id BIGINT NOT NULL,
                        username VARCHAR(100),
                        balance INTEGER DEFAULT 0,
                        total_won INTEGER DEFAULT 0,
                        bets_won INTEGER DEFAULT 0,
                        bets_placed INTEGER DEFAULT 0,
                        win_rate DECIMAL(6,2) DEFAULT 0,
                        recorded_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hexbet_high_elo_pool (
                        puuid TEXT PRIMARY KEY,
                        region TEXT NOT NULL,
                        tier TEXT NOT NULL,
                        lp INTEGER DEFAULT 0,
                        last_checked TIMESTAMP,
                        times_featured INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()
        finally:
            self.return_connection(conn)

    def get_balance(self, discord_id: int) -> int:
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT balance FROM user_balances WHERE discord_id = %s", (discord_id,))
                row = cur.fetchone()
                if row:
                    return row[0]
                # create default balance
                cur.execute("INSERT INTO user_balances (discord_id, balance) VALUES (%s, 1000) RETURNING balance", (discord_id,))
                conn.commit()
                return 1000
        finally:
            self.return_connection(conn)

    def update_balance(self, discord_id: int, delta: int):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_balances (discord_id, balance) VALUES (%s, %s)
                    ON CONFLICT (discord_id) DO UPDATE SET balance = user_balances.balance + EXCLUDED.balance
                    RETURNING balance
                """, (discord_id, delta))
                new_balance = cur.fetchone()[0]
                conn.commit()
                return new_balance
        finally:
            self.return_connection(conn)

    def record_wager(self, discord_id: int, amount: int):
        """Increment wager counters when a bet is placed."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_balances (discord_id, balance, total_wagered, bets_placed)
                    VALUES (%s, 1000, %s, 1)
                    ON CONFLICT (discord_id) DO UPDATE SET
                        total_wagered = user_balances.total_wagered + EXCLUDED.total_wagered,
                        bets_placed = user_balances.bets_placed + 1,
                        updated_at = NOW()
                    """,
                    (discord_id, amount)
                )
                conn.commit()
        finally:
            self.return_connection(conn)

    def record_result(self, discord_id: int, amount: int, payout: int, won: bool):
        """Track bet outcome stats (amount wagered, payout)."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE user_balances
                    SET
                        total_won = total_won + %s,
                        total_lost = total_lost + %s,
                        bets_won = bets_won + CASE WHEN %s THEN 1 ELSE 0 END,
                        updated_at = NOW()
                    WHERE discord_id = %s
                    """,
                    (payout if won else 0, amount if not won else 0, won, discord_id)
                )
                conn.commit()
        finally:
            self.return_connection(conn)

    def claim_daily_reward(self, discord_id: int, amount: int = 100) -> tuple[bool, str]:
        """
        Claim daily reward if 24 hours have passed
        Returns (success, message)
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Get user's last claim time
                cur.execute("SELECT last_daily_claim FROM user_balances WHERE discord_id = %s", (discord_id,))
                row = cur.fetchone()
                
                from datetime import datetime, timezone, timedelta
                now = datetime.now(timezone.utc)
                
                if row and row[0]:
                    last_claim = row[0]
                    # Make timezone-aware if needed
                    if last_claim.tzinfo is None:
                        last_claim = last_claim.replace(tzinfo=timezone.utc)
                    
                    time_since_claim = now - last_claim
                    if time_since_claim < timedelta(hours=24):
                        hours_left = 24 - (time_since_claim.total_seconds() / 3600)
                        return (False, f"⏰ You can claim your next daily reward in {hours_left:.1f} hours")
                
                # Grant reward
                cur.execute("""
                    INSERT INTO user_balances (discord_id, balance, last_daily_claim)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (discord_id) DO UPDATE SET
                        balance = user_balances.balance + EXCLUDED.balance,
                        last_daily_claim = EXCLUDED.last_daily_claim,
                        updated_at = NOW()
                    RETURNING balance
                """, (discord_id, amount, now))
                new_balance = cur.fetchone()[0]
                conn.commit()
                return (True, f"✅ Daily reward claimed! +{amount} tokens (New balance: {new_balance})")
        finally:
            self.return_connection(conn)

    def create_hexbet_match(self, game_id: int, platform: str, channel_id: int, blue_team: dict, red_team: dict, start_time: int, special_bet: bool = False) -> int:
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Convert milliseconds to PostgreSQL TIMESTAMP
                # gameStartTime from Riot API is in milliseconds
                game_start_at = None
                if start_time and start_time > 0:
                    # TO_TIMESTAMP expects seconds, so divide milliseconds by 1000
                    game_start_at = start_time / 1000.0
                
                # Try to insert, if exists do nothing
                cur.execute("""
                    INSERT INTO hexbet_matches (game_id, platform, channel_id, blue_team, red_team, start_time, game_start_at, special_bet)
                    VALUES (%s, %s, %s, %s, %s, %s, TO_TIMESTAMP(%s), %s)
                    ON CONFLICT (game_id) DO NOTHING
                    RETURNING id
                """, (game_id, platform, channel_id, json.dumps(blue_team), json.dumps(red_team), start_time, game_start_at, special_bet))
                row = cur.fetchone()
                conn.commit()
                
                # If insert succeeded, return the ID
                if row:
                    return row[0]
                
                # If conflict happened, fetch existing match ID
                cur.execute("SELECT id FROM hexbet_matches WHERE game_id = %s", (game_id,))
                existing = cur.fetchone()
                return existing[0] if existing else None
        finally:
            self.return_connection(conn)

    def set_match_message(self, match_id: int, message_id: int):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE hexbet_matches SET message_id = %s WHERE id = %s", (message_id, match_id))
                conn.commit()
        finally:
            self.return_connection(conn)

    def get_open_match(self) -> Optional[dict]:
        """Get single open match (backwards compatibility)"""
        matches = self.get_open_matches(limit=1)
        return matches[0] if matches else None
    
    def get_open_matches(self, limit: int = 3) -> List[dict]:
        """Get all open matches up to limit"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM hexbet_matches WHERE status = 'open' ORDER BY created_at DESC LIMIT %s", (limit,))
                rows = cur.fetchall()
                if not rows:
                    return []
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in rows]
        finally:
            self.return_connection(conn)
    
    def count_open_matches(self) -> int:
        """Count number of open matches"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM hexbet_matches WHERE status = 'open'")
                return cur.fetchone()[0]
        finally:
            self.return_connection(conn)

    def add_bet(self, match_id: int, user_id: int, side: str, amount: int, odds: float, potential: int) -> bool:
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO hexbet_bets (match_id, user_id, side, amount, odds, potential_win)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (match_id, user_id) DO NOTHING
                """, (match_id, user_id, side, amount, odds, potential))
                conn.commit()
                return cur.rowcount > 0
        finally:
            self.return_connection(conn)

    def list_bets(self, match_id: int) -> list:
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id, side, amount, odds, potential_win FROM hexbet_bets WHERE match_id = %s", (match_id,))
                rows = cur.fetchall()
                return rows
        finally:
            self.return_connection(conn)

    def get_bets_for_match(self, match_id: int) -> list:
        """Get all bets for a match as list of dicts."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id, side, amount, odds, potential_win FROM hexbet_bets WHERE match_id = %s", (match_id,))
                rows = cur.fetchall()
                return [{'user_id': r[0], 'side': r[1], 'amount': r[2], 'odds': r[3], 'potential_win': r[4]} for r in rows]
        finally:
            self.return_connection(conn)

    def settle_match(self, match_id: int, winner: str) -> list:
        """Settle bets and return list of (user_id, amount, payout, won)."""
        conn = self.get_connection()
        payouts = []
        try:
            with conn.cursor() as cur:
                # Check if this is a special bet (1.5x bonus)
                cur.execute("SELECT special_bet FROM hexbet_matches WHERE id=%s", (match_id,))
                row = cur.fetchone()
                is_special = row[0] if row else False
                bonus_multiplier = 1.5 if is_special else 1.0
                
                # Update match with settlement and timestamp
                cur.execute("UPDATE hexbet_matches SET status='settled', winner=%s, updated_at=NOW() WHERE id=%s", (winner, match_id))
                # Bets snapshot
                cur.execute("SELECT user_id, side, amount, odds FROM hexbet_bets WHERE match_id=%s", (match_id,))
                for user_id, side, amount, odds in cur.fetchall():
                    won = side == winner
                    base_payout = int(amount * float(odds)) if won else 0
                    payout = int(base_payout * bonus_multiplier) if won else 0
                    payouts.append((user_id, amount, payout, won))
                # Mark settled with bonus multiplier
                cur.execute("UPDATE hexbet_bets SET settled=TRUE, won=(side=%s), payout = CASE WHEN side=%s THEN ((amount * odds)::int * %s)::int ELSE 0 END, updated_at=NOW() WHERE match_id=%s", (winner, winner, bonus_multiplier, match_id))
                conn.commit()
                return payouts
        finally:
            self.return_connection(conn)
    
    def refund_match(self, match_id: int) -> list:
        """Refund all bets on a match (remake/afk detected). Returns list of (user_id, amount) refunded."""
        conn = self.get_connection()
        refunds = []
        try:
            with conn.cursor() as cur:
                # Update match status to refunded
                cur.execute("UPDATE hexbet_matches SET status='refunded', updated_at=NOW() WHERE id=%s", (match_id,))
                
                # Get all bets for this match
                cur.execute("SELECT user_id, amount FROM hexbet_bets WHERE match_id=%s AND NOT settled", (match_id,))
                for user_id, amount in cur.fetchall():
                    # Return tokens to user
                    cur.execute("UPDATE user_balances SET balance = balance + %s WHERE discord_id = %s", (amount, user_id))
                    refunds.append((user_id, amount))
                
                # Mark bets as settled with refund (won=NULL, payout=amount)
                cur.execute("UPDATE hexbet_bets SET settled=TRUE, payout=amount, updated_at=NOW() WHERE match_id=%s", (match_id,))
                conn.commit()
                return refunds
        finally:
            self.return_connection(conn)
    
    def get_user_league_accounts(self, user_id: int):
        """Get all league accounts for a user from main bot schema"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM league_accounts WHERE user_id = %s", (user_id,))
            rows = cur.fetchall()
            if rows:
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in rows]
            return []
        finally:
            self.return_connection(conn)
    
    def get_pro_accounts(self, pro_id: int):
        """Get all accounts for a pro player"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM pro_accounts WHERE pro_id = %s", (pro_id,))
            rows = cur.fetchall()
            if rows:
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in rows]
            return []
        finally:
            self.return_connection(conn)
    
    def search_pro_players(self, query: str = None, region: str = None, role: str = None, team: str = None, limit: int = 50):
        """Search pro players with filters"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            
            sql = "SELECT * FROM tracked_pros WHERE enabled = TRUE"
            params = []
            
            if query:
                sql += " AND LOWER(player_name) LIKE %s"
                params.append(f"%{query.lower()}%")
            
            if region:
                sql += " AND LOWER(region) = %s"
                params.append(region.lower())
            
            if role:
                sql += " AND LOWER(role) = %s"
                params.append(role.lower())
            
            if team:
                sql += " AND LOWER(team) LIKE %s"
                params.append(f"%{team.lower()}%")
            
            sql += " ORDER BY player_name LIMIT %s"
            params.append(limit)
            
            cur.execute(sql, params)
            rows = cur.fetchall()
            
            if rows:
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in rows]
            return []
        finally:
            self.return_connection(conn)
    
    def get_pro_player_by_name(self, player_name: str):
        """Get pro player details by name"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM tracked_pros WHERE LOWER(player_name) = LOWER(%s) AND enabled = TRUE",
                (player_name,)
            )
            row = cur.fetchone()
            if row:
                cols = [desc[0] for desc in cur.description]
                return dict(zip(cols, row))
            return None
        finally:
            self.return_connection(conn)
    
    def get_all_tracked_pros(self, limit: int = 200):
        """Get all tracked pro players"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM tracked_pros WHERE enabled = TRUE ORDER BY player_name LIMIT %s",
                (limit,)
            )
            rows = cur.fetchall()
            if rows:
                cols = [desc[0] for desc in cur.description]
                return [dict(zip(cols, row)) for row in rows]
            return []
        finally:
            self.return_connection(conn)
    
    def update_player_stats(self, player_name: str, wins: int = None, losses: int = None, 
                          total_games: int = None, avg_kda: float = None):
        """Update player statistics"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            
            updates = []
            params = []
            
            if wins is not None:
                updates.append("wins = %s")
                params.append(wins)
            if losses is not None:
                updates.append("losses = %s")
                params.append(losses)
            if total_games is not None:
                updates.append("total_games = %s")
                params.append(total_games)
            if avg_kda is not None:
                updates.append("avg_kda = %s")
                params.append(avg_kda)
            
            if updates:
                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(player_name)
                
                sql = f"UPDATE tracked_pros SET {', '.join(updates)} WHERE LOWER(player_name) = LOWER(%s)"
                cur.execute(sql, params)
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def initialize_schema(self):
        """Initialize tracker database schema"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            
            # Read schema file
            import os
            schema_path = os.path.join(os.path.dirname(__file__), 'tracker_schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, 'r') as f:
                    schema = f.read()
                cur.execute(schema)
                conn.commit()
                logger.info("✅ Tracker schema initialized")
            else:
                logger.warning("⚠️ tracker_schema.sql not found")
        except Exception as e:
            logger.error(f"❌ Error initializing schema: {e}")
            conn.rollback()
        finally:
            self.return_connection(conn)
    
    def get_random_high_elo_puuids(self, region: str, limit: int = 50) -> List[tuple]:
        """Get random PUUIDs from high-elo pool for a specific region
        Returns list of (puuid, tier, lp) tuples
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT puuid, tier, lp 
                    FROM hexbet_high_elo_pool 
                    WHERE region = %s 
                    ORDER BY RANDOM() 
                    LIMIT %s
                """, (region, limit))
                return cur.fetchall()
        finally:
            self.return_connection(conn)
    
    def update_high_elo_last_checked(self, puuid: str):
        """Update last_checked timestamp for a PUUID"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE hexbet_high_elo_pool 
                    SET last_checked = CURRENT_TIMESTAMP 
                    WHERE puuid = %s
                """, (puuid,))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def increment_high_elo_featured(self, puuid: str):
        """Increment times_featured counter for a PUUID"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE hexbet_high_elo_pool 
                    SET times_featured = times_featured + 1 
                    WHERE puuid = %s
                """, (puuid,))
                conn.commit()
        finally:
            self.return_connection(conn)

    def cleanup_old_bets(self, minutes: int = 1):
        """Delete settled matches and their bets older than specified minutes (0 = all settled)"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Build query based on minutes
                if minutes == 0:
                    # Delete ALL settled matches immediately
                    time_filter = ""
                else:
                    time_filter = f"AND updated_at < NOW() - make_interval(mins => {minutes})"
                
                # First check what we're about to delete
                query = f"""
                    SELECT id, status, winner, updated_at 
                    FROM hexbet_matches
                    WHERE status = 'settled'
                    {time_filter}
                """
                cur.execute(query)
                to_delete = cur.fetchall()
                if to_delete:
                    logger.info(f"🗑️ About to delete {len(to_delete)} matches: {to_delete}")
                else:
                    logger.info("🗑️ No settled matches found to delete")
                
                # Delete bets for settled matches
                query = f"""
                    DELETE FROM hexbet_bets
                    WHERE match_id IN (
                        SELECT id FROM hexbet_matches
                        WHERE status = 'settled'
                        {time_filter}
                    )
                """
                cur.execute(query)
                deleted_bets = cur.rowcount
                logger.info(f"🗑️ Deleted {deleted_bets} bets")
                
                # Delete settled matches
                query = f"""
                    DELETE FROM hexbet_matches
                    WHERE status = 'settled'
                    {time_filter}
                """
                cur.execute(query)
                deleted_matches = cur.rowcount
                logger.info(f"🗑️ Deleted {deleted_matches} matches")
                
                conn.commit()
                return deleted_matches, deleted_bets
        finally:
            self.return_connection(conn)

    def get_old_settled_matches(self, minutes: int = 1):
        """Get settled matches older than specified minutes (0 = all settled matches)"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                if minutes == 0:
                    # Get ALL settled matches
                    cur.execute("""
                        SELECT id, game_id, platform, channel_id, message_id, status, winner, updated_at
                        FROM hexbet_matches
                        WHERE status = 'settled'
                    """)
                else:
                    cur.execute("""
                        SELECT id, game_id, platform, channel_id, message_id, status, winner, updated_at
                        FROM hexbet_matches
                        WHERE status = 'settled'
                        AND updated_at < NOW() - make_interval(mins => %s)
                    """, (minutes,))
                rows = cur.fetchall()
                if rows:
                    cols = [desc[0] for desc in cur.description]
                    return [dict(zip(cols, row)) for row in rows]
                return []
        finally:
            self.return_connection(conn)

    def get_user_betting_stats(self, user_id: int) -> Optional[Dict]:
        """Get comprehensive betting stats for a user"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Get total bets and wagered amount
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_bets,
                        COALESCE(SUM(amount), 0) as total_wagered
                    FROM hexbet_bets
                    WHERE user_id = %s AND settled = TRUE
                """, (user_id,))
                row = cur.fetchone()
                total_bets = row[0] if row else 0
                total_wagered = row[1] if row else 0
                
                # Get wins and payouts
                cur.execute("""
                    SELECT
                        COUNT(*) as wins,
                        COALESCE(SUM(payout), 0) as total_payout
                    FROM hexbet_bets
                    WHERE user_id = %s AND settled = TRUE AND won = TRUE
                """, (user_id,))
                row = cur.fetchone()
                wins = row[0] if row else 0
                total_payout = row[1] if row else 0
                
                losses = total_bets - wins
                win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
                roi = ((total_payout - total_wagered) / total_wagered * 100) if total_wagered > 0 else 0
                
                # Get blue side stats
                cur.execute("""
                    SELECT
                        COUNT(*) as blue_bets,
                        COUNT(*) FILTER (WHERE won = TRUE) as blue_wins
                    FROM hexbet_bets
                    WHERE user_id = %s AND side = 'blue' AND settled = TRUE
                """, (user_id,))
                row = cur.fetchone()
                blue_total = row[0] if row else 0
                blue_wins = row[1] if row else 0
                blue_wr = (blue_wins / blue_total * 100) if blue_total > 0 else 0
                
                # Get red side stats
                cur.execute("""
                    SELECT
                        COUNT(*) as red_bets,
                        COUNT(*) FILTER (WHERE won = TRUE) as red_wins
                    FROM hexbet_bets
                    WHERE user_id = %s AND side = 'red' AND settled = TRUE
                """, (user_id,))
                row = cur.fetchone()
                red_total = row[0] if row else 0
                red_wins = row[1] if row else 0
                red_wr = (red_wins / red_total * 100) if red_total > 0 else 0
                
                # Get current streak (wins or losses)
                cur.execute("""
                    SELECT won FROM hexbet_bets
                    WHERE user_id = %s AND settled = TRUE
                    ORDER BY updated_at DESC
                    LIMIT 20
                """, (user_id,))
                recent_bets = [row[0] for row in cur.fetchall()]
                
                streak = 0
                streak_type = "none"
                if recent_bets:
                    streak_type = "W" if recent_bets[0] else "L"
                    for bet_result in recent_bets:
                        if (bet_result and streak_type == "W") or (not bet_result and streak_type == "L"):
                            streak += 1
                        else:
                            break
                
                return {
                    'total_bets': total_bets,
                    'total_wagered': total_wagered,
                    'wins': wins,
                    'losses': losses,
                    'win_rate': win_rate,
                    'total_payout': total_payout,
                    'roi': roi,
                    'blue_total': blue_total,
                    'blue_wins': blue_wins,
                    'blue_wr': blue_wr,
                    'red_total': red_total,
                    'red_wins': red_wins,
                    'red_wr': red_wr,
                    'streak': streak,
                    'streak_type': streak_type
                }
        finally:
            self.return_connection(conn)
    
    def check_daily_bet_limit(self, user_id: int, bet_amount: int, daily_limit: int = 1000) -> Tuple[bool, str, int]:
        """Check if user can place bet within daily limit. Returns (can_bet, message, remaining)"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                from datetime import date
                today = date.today()
                
                # Get current daily wagered and last wager date
                cur.execute("""
                    SELECT daily_wagered, last_wager_date
                    FROM user_balances
                    WHERE discord_id = %s
                """, (user_id,))
                row = cur.fetchone()
                
                if not row:
                    # New user - allow bet
                    return (True, "", daily_limit - bet_amount)
                
                daily_wagered, last_wager_date = row
                
                # Reset counter if it's a new day
                if last_wager_date != today:
                    daily_wagered = 0
                
                # Check if this bet would exceed limit
                new_total = (daily_wagered or 0) + bet_amount
                
                if new_total > daily_limit:
                    remaining = daily_limit - (daily_wagered or 0)
                    return (False, f"❌ Daily betting limit reached! You can bet up to {remaining} more today. (Limit: {daily_limit}/day)", remaining)
                
                return (True, "", daily_limit - new_total)
        finally:
            self.return_connection(conn)
    
    def update_daily_wager(self, user_id: int, amount: int):
        """Update daily wagered amount"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                from datetime import date
                today = date.today()
                
                # Update or reset daily counter
                cur.execute("""
                    UPDATE user_balances
                    SET daily_wagered = CASE 
                        WHEN last_wager_date = %s THEN COALESCE(daily_wagered, 0) + %s
                        ELSE %s
                    END,
                    last_wager_date = %s
                    WHERE discord_id = %s
                """, (today, amount, amount, today, user_id))
                conn.commit()
        finally:
            self.return_connection(conn)

def get_tracker_db():
    """Get or create the global tracker database instance"""
    global _tracker_db
    if _tracker_db is None:
        _tracker_db = TrackerDatabase()
        _tracker_db.initialize_schema()
    return _tracker_db
