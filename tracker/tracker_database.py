"""
Tracker Bot Database Handler
Separate database connection for tracker bot
"""

import psycopg2
from psycopg2 import pool
import os
import json
from typing import Optional, List, Dict
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

    def create_hexbet_match(self, game_id: int, platform: str, channel_id: int, blue_team: dict, red_team: dict, start_time: int) -> int:
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO hexbet_matches (game_id, platform, channel_id, blue_team, red_team, start_time)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (game_id) DO NOTHING
                    RETURNING id
                """, (game_id, platform, channel_id, json.dumps(blue_team), json.dumps(red_team), start_time))
                row = cur.fetchone()
                conn.commit()
                return row[0] if row else None
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
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM hexbet_matches WHERE status = 'open' ORDER BY created_at DESC LIMIT 1")
                row = cur.fetchone()
                if not row:
                    return None
                cols = [desc[0] for desc in cur.description]
                return dict(zip(cols, row))
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
                # Update match
                cur.execute("UPDATE hexbet_matches SET status='settled', winner=%s WHERE id=%s", (winner, match_id))
                # Bets snapshot
                cur.execute("SELECT user_id, side, amount, odds FROM hexbet_bets WHERE match_id=%s", (match_id,))
                for user_id, side, amount, odds in cur.fetchall():
                    won = side == winner
                    payout = int(amount * float(odds)) if won else 0
                    payouts.append((user_id, amount, payout, won))
                # Mark settled
                cur.execute("UPDATE hexbet_bets SET settled=TRUE, won=(side=%s), payout = CASE WHEN side=%s THEN (amount * odds)::int ELSE 0 END WHERE match_id=%s", (winner, winner, match_id))
                conn.commit()
                return payouts
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

# Global database instance
_tracker_db = None

def get_tracker_db():
    """Get or create the global tracker database instance"""
    global _tracker_db
    if _tracker_db is None:
        _tracker_db = TrackerDatabase()
        _tracker_db.initialize_schema()
    return _tracker_db
