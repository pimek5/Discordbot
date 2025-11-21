"""
Tracker Bot Database Handler
Separate database connection for tracker bot
"""

import psycopg2
from psycopg2 import pool
import os
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
            # Try user_discord_id first (main bot schema)
            try:
                cur.execute("SELECT * FROM users WHERE user_discord_id = %s", (discord_id,))
            except:
                # Rollback failed transaction
                conn.rollback()
                # Fallback to discord_id if column doesn't exist
                cur.execute("SELECT * FROM users WHERE discord_id = %s", (discord_id,))
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
    
    def get_user_accounts(self, user_id: int):
        """Get all accounts for a user"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM accounts WHERE user_id = %s", (user_id,))
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

# Global database instance
_tracker_db = None

def get_tracker_db():
    """Get or create the global tracker database instance"""
    global _tracker_db
    if _tracker_db is None:
        _tracker_db = TrackerDatabase()
    return _tracker_db
