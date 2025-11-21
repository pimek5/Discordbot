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
            cur.execute("SELECT * FROM users WHERE discord_id = %s", (discord_id,))
            row = cur.fetchone()
            if row:
                cols = [desc[0] for desc in cur.description]
                return dict(zip(cols, row))
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

# Global database instance
_tracker_db = None

def get_tracker_db():
    """Get or create the global tracker database instance"""
    global _tracker_db
    if _tracker_db is None:
        _tracker_db = TrackerDatabase()
    return _tracker_db
