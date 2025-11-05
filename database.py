"""
Database module for Orianna Bot
Handles PostgreSQL connection and queries
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger('database')

class Database:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.connection_pool = None
        
    def initialize(self):
        """Initialize connection pool"""
        try:
            self.connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=self.database_url
            )
            logger.info("✅ Database connection pool created")
            
            # Create tables if they don't exist
            self.create_tables()
            
        except Exception as e:
            logger.error(f"❌ Failed to create connection pool: {e}")
            raise
    
    def get_connection(self):
        """Get a connection from the pool"""
        return self.connection_pool.getconn()
    
    def return_connection(self, conn):
        """Return connection to the pool"""
        self.connection_pool.putconn(conn)
    
    def create_tables(self):
        """Create all tables from schema"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Read schema file
                schema_path = os.path.join(os.path.dirname(__file__), 'db_schema.sql')
                with open(schema_path, 'r') as f:
                    schema_sql = f.read()
                
                cur.execute(schema_sql)
                conn.commit()
                logger.info("✅ Database tables created/verified")
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error creating tables: {e}")
            raise
        finally:
            self.return_connection(conn)
    
    # ==================== USER OPERATIONS ====================
    
    def get_or_create_user(self, discord_id: int) -> int:
        """Get user ID or create new user"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (snowflake)
                    VALUES (%s)
                    ON CONFLICT (snowflake) DO UPDATE SET last_updated = NOW()
                    RETURNING id
                """, (discord_id,))
                user_id = cur.fetchone()[0]
                conn.commit()
                return user_id
        finally:
            self.return_connection(conn)
    
    def get_user_by_discord_id(self, discord_id: int) -> Optional[Dict]:
        """Get user by Discord ID"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE snowflake = %s", (discord_id,))
                return cur.fetchone()
        finally:
            self.return_connection(conn)
    
    # ==================== LEAGUE ACCOUNT OPERATIONS ====================
    
    def add_league_account(self, user_id: int, region: str, game_name: str, 
                          tagline: str, puuid: str, summoner_id: str,
                          summoner_level: int = 1, verified: bool = False) -> int:
        """Add a new League account"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Check if this is the first account
                cur.execute("SELECT COUNT(*) FROM league_accounts WHERE user_id = %s", (user_id,))
                is_first = cur.fetchone()[0] == 0
                
                cur.execute("""
                    INSERT INTO league_accounts 
                    (user_id, region, riot_id_game_name, riot_id_tagline, puuid, 
                     summoner_id, summoner_level, primary_account, verified, verified_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, puuid) DO UPDATE SET
                        summoner_id = EXCLUDED.summoner_id,
                        summoner_level = EXCLUDED.summoner_level,
                        verified = EXCLUDED.verified,
                        verified_at = EXCLUDED.verified_at,
                        last_updated = NOW()
                    RETURNING id
                """, (user_id, region, game_name, tagline, puuid, summoner_id, 
                      summoner_level, is_first, verified, datetime.now() if verified else None))
                
                account_id = cur.fetchone()[0]
                conn.commit()
                return account_id
        finally:
            self.return_connection(conn)
    
    def get_user_accounts(self, user_id: int) -> List[Dict]:
        """Get all League accounts for a user"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM league_accounts 
                    WHERE user_id = %s 
                    ORDER BY primary_account DESC, created_at ASC
                """, (user_id,))
                return cur.fetchall()
        finally:
            self.return_connection(conn)
    
    def get_primary_account(self, user_id: int) -> Optional[Dict]:
        """Get primary League account for a user"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM league_accounts 
                    WHERE user_id = %s AND primary_account = TRUE
                    LIMIT 1
                """, (user_id,))
                result = cur.fetchone()
                
                # If no primary, get first account
                if not result:
                    cur.execute("""
                        SELECT * FROM league_accounts 
                        WHERE user_id = %s 
                        ORDER BY created_at ASC
                        LIMIT 1
                    """, (user_id,))
                    result = cur.fetchone()
                
                return result
        finally:
            self.return_connection(conn)
    
    def delete_account(self, user_id: int) -> bool:
        """Delete all accounts for a user"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM league_accounts WHERE user_id = %s", (user_id,))
                conn.commit()
                return True
        finally:
            self.return_connection(conn)
    
    # ==================== CHAMPION MASTERY OPERATIONS ====================
    
    def update_champion_mastery(self, user_id: int, champion_id: int, 
                                score: int, level: int, chest_granted: bool = False,
                                tokens_earned: int = 0, last_play_time: int = None):
        """Update or insert champion mastery"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_champion_stats 
                    (user_id, champion_id, score, level, chest_granted, tokens_earned, last_play_time)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, champion_id) DO UPDATE SET
                        score = EXCLUDED.score,
                        level = EXCLUDED.level,
                        chest_granted = EXCLUDED.chest_granted,
                        tokens_earned = EXCLUDED.tokens_earned,
                        last_play_time = EXCLUDED.last_play_time,
                        last_updated = NOW()
                """, (user_id, champion_id, score, level, chest_granted, tokens_earned, last_play_time))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def get_user_champion_stats(self, user_id: int, champion_id: Optional[int] = None) -> List[Dict]:
        """Get champion stats for a user"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if champion_id:
                    cur.execute("""
                        SELECT * FROM user_champion_stats 
                        WHERE user_id = %s AND champion_id = %s
                    """, (user_id, champion_id))
                    return [cur.fetchone()] if cur.rowcount > 0 else []
                else:
                    cur.execute("""
                        SELECT * FROM user_champion_stats 
                        WHERE user_id = %s 
                        ORDER BY score DESC
                    """, (user_id,))
                    return cur.fetchall()
        finally:
            self.return_connection(conn)
    
    def add_mastery_delta(self, user_id: int, champion_id: int, delta: int, new_value: int):
        """Record a mastery point change"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_mastery_delta (user_id, champion_id, delta, value)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, champion_id, delta, new_value))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def get_mastery_history(self, user_id: int, champion_id: int, 
                           days: int = 180) -> List[Dict]:
        """Get mastery history for a champion"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cutoff = datetime.now() - timedelta(days=days)
                cur.execute("""
                    SELECT * FROM user_mastery_delta
                    WHERE user_id = %s AND champion_id = %s AND timestamp > %s
                    ORDER BY timestamp ASC
                """, (user_id, champion_id, cutoff))
                return cur.fetchall()
        finally:
            self.return_connection(conn)
    
    # ==================== RANKED STATISTICS ====================
    
    def update_ranked_stats(self, user_id: int, queue: str, tier: str, rank: str,
                           lp: int, wins: int, losses: int, hot_streak: bool = False,
                           veteran: bool = False, fresh_blood: bool = False):
        """Update ranked statistics"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_ranks 
                    (user_id, queue, tier, rank, league_points, wins, losses, 
                     hot_streak, veteran, fresh_blood)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, queue) DO UPDATE SET
                        tier = EXCLUDED.tier,
                        rank = EXCLUDED.rank,
                        league_points = EXCLUDED.league_points,
                        wins = EXCLUDED.wins,
                        losses = EXCLUDED.losses,
                        hot_streak = EXCLUDED.hot_streak,
                        veteran = EXCLUDED.veteran,
                        fresh_blood = EXCLUDED.fresh_blood,
                        last_updated = NOW()
                """, (user_id, queue, tier, rank, lp, wins, losses, hot_streak, veteran, fresh_blood))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def get_user_ranks(self, user_id: int) -> List[Dict]:
        """Get all ranked stats for a user"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM user_ranks WHERE user_id = %s", (user_id,))
                return cur.fetchall()
        finally:
            self.return_connection(conn)
    
    # ==================== LEADERBOARD QUERIES ====================
    
    def get_champion_leaderboard(self, champion_id: int, guild_id: Optional[int] = None, 
                                 limit: int = 10) -> List[Dict]:
        """Get top players for a champion"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if guild_id:
                    # Server-only leaderboard
                    cur.execute("""
                        SELECT u.snowflake, ucs.score, ucs.level, la.riot_id_game_name, la.riot_id_tagline
                        FROM user_champion_stats ucs
                        JOIN users u ON ucs.user_id = u.id
                        JOIN guild_members gm ON u.id = gm.user_id
                        JOIN league_accounts la ON u.id = la.user_id AND la.primary_account = TRUE
                        WHERE gm.guild_id = %s AND ucs.champion_id = %s
                        ORDER BY ucs.score DESC
                        LIMIT %s
                    """, (guild_id, champion_id, limit))
                else:
                    # Global leaderboard
                    cur.execute("""
                        SELECT u.snowflake, ucs.score, ucs.level, la.riot_id_game_name, la.riot_id_tagline
                        FROM user_champion_stats ucs
                        JOIN users u ON ucs.user_id = u.id
                        JOIN league_accounts la ON u.id = la.user_id AND la.primary_account = TRUE
                        WHERE ucs.champion_id = %s
                        ORDER BY ucs.score DESC
                        LIMIT %s
                    """, (champion_id, limit))
                return cur.fetchall()
        finally:
            self.return_connection(conn)
    
    # ==================== GUILD OPERATIONS ====================
    
    def add_guild_member(self, guild_id: int, user_id: int):
        """Add a guild member"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO guild_members (guild_id, user_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (guild_id, user_id))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def remove_guild_member(self, guild_id: int, user_id: int):
        """Remove a guild member"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM guild_members 
                    WHERE guild_id = %s AND user_id = %s
                """, (guild_id, user_id))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    # ==================== VERIFICATION CODES ====================
    
    def create_verification_code(self, user_id: int, code: str, game_name: str,
                                tagline: str, region: str, puuid: str, 
                                summoner_id: str, expires_minutes: int = 5) -> int:
        """Create a verification code"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                expires_at = datetime.now() + timedelta(minutes=expires_minutes)
                cur.execute("""
                    INSERT INTO verification_codes 
                    (user_id, code, riot_id_game_name, riot_id_tagline, region, puuid, summoner_id, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (user_id, code, game_name, tagline, region, puuid, summoner_id, expires_at))
                code_id = cur.fetchone()[0]
                conn.commit()
                return code_id
        finally:
            self.return_connection(conn)
    
    def get_verification_code(self, user_id: int) -> Optional[Dict]:
        """Get active verification code for user"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM verification_codes
                    WHERE user_id = %s AND expires_at > NOW()
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (user_id,))
                return cur.fetchone()
        finally:
            self.return_connection(conn)
    
    def delete_verification_code(self, user_id: int):
        """Delete verification codes for user"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM verification_codes WHERE user_id = %s", (user_id,))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    # ==================== WORKER OPERATIONS ====================
    
    def get_all_users_with_accounts(self) -> List[Dict]:
        """Get all users with their accounts for worker updates"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT u.id as user_id, u.snowflake, 
                           la.id as account_id, la.puuid, la.region, la.summoner_id
                    FROM users u
                    JOIN league_accounts la ON u.id = la.user_id
                    WHERE la.verified = TRUE
                    ORDER BY u.last_updated ASC
                """)
                return cur.fetchall()
        finally:
            self.return_connection(conn)
    
    def close(self):
        """Close all connections"""
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("✅ Database connections closed")

# Global database instance
db = None

def initialize_database(database_url: str = None):
    """Initialize the global database instance"""
    global db
    if database_url is None:
        database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment variables")
    
    db = Database(database_url)
    db.initialize()
    return db

def get_db() -> Database:
    """Get the global database instance"""
    global db
    if db is None:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    return db
