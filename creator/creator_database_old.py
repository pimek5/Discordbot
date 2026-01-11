"""
Creator Database Management
PostgreSQL database for tracking creators and their mods
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
import logging

logger = logging.getLogger('creator_database')

DATABASE_URL = os.getenv('DATABASE_URL')


class CreatorDatabase:
    def __init__(self):
        self.conn = None
        self.connect()
        self.create_tables()
    
    def connect(self):
        try:
            self.conn = psycopg2.connect(DATABASE_URL)
            logger.info("✅ Connected to database")
        except Exception as e:
            logger.error("❌ Database connection failed: %s", e)
            raise
    
    def create_tables(self):
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS creators (
                        id SERIAL PRIMARY KEY,
                        discord_user_id BIGINT NOT NULL,
                        platform VARCHAR(20) NOT NULL,
                        profile_url TEXT NOT NULL,
                        username VARCHAR(255) NOT NULL,
                        rank VARCHAR(50),
                        total_mods INTEGER DEFAULT 0,
                        total_downloads BIGINT DEFAULT 0,
                        total_views BIGINT DEFAULT 0,
                        followers INTEGER DEFAULT 0,
                        following INTEGER DEFAULT 0,
                        joined_date TEXT,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(discord_user_id, platform, username)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS mods (
                        id SERIAL PRIMARY KEY,
                        creator_id INTEGER REFERENCES creators(id) ON DELETE CASCADE,
                        mod_id TEXT NOT NULL,
                        mod_name TEXT NOT NULL,
                        mod_url TEXT NOT NULL,
                        platform VARCHAR(20) NOT NULL,
                        updated_at TEXT,
                        notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_update BOOLEAN DEFAULT FALSE,
                        UNIQUE(mod_id, platform)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS notification_log (
                        id SERIAL PRIMARY KEY,
                        creator_id INTEGER REFERENCES creators(id) ON DELETE CASCADE,
                        mod_id TEXT NOT NULL,
                        action VARCHAR(50) NOT NULL,
                        notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                self.conn.commit()
                logger.info("✅ Database tables created/verified")
        except Exception as e:
            logger.error("❌ Error creating tables: %s", e)
            self.conn.rollback()
    
    def add_creator(self, discord_user_id: int, platform: str, profile_url: str, profile_data: dict):
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO creators 
                    (discord_user_id, platform, profile_url, username, rank, total_mods, total_downloads, total_views, followers, following, joined_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (discord_user_id, platform, username)
                    DO UPDATE SET
                        rank = EXCLUDED.rank,
                        total_mods = EXCLUDED.total_mods,
                        total_downloads = EXCLUDED.total_downloads,
                        total_views = EXCLUDED.total_views,
                        followers = EXCLUDED.followers,
                        following = EXCLUDED.following,
                        last_updated = CURRENT_TIMESTAMP
                    RETURNING id
                    """,
                    (
                        discord_user_id,
                        platform,
                        profile_url,
                        profile_data.get('username'),
                        profile_data.get('rank'),
                        profile_data.get('total_mods', 0),
                        profile_data.get('total_downloads', 0),
                        profile_data.get('total_views', 0),
                        profile_data.get('followers', 0),
                        profile_data.get('following', 0),
                        profile_data.get('joined_date')
                    ),
                )
                creator_id = cur.fetchone()[0]
                self.conn.commit()
                logger.info("✅ Creator added/updated: %s (ID: %s)", profile_data.get('username'), creator_id)
                return creator_id
        except Exception as e:
            logger.error("❌ Error adding creator: %s", e)
            self.conn.rollback()
            return None
    
    def get_creator(self, discord_user_id: int, platform: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM creators WHERE discord_user_id = %s AND platform = %s
                    """,
                    (discord_user_id, platform),
                )
                return cur.fetchone()
        except Exception as e:
            logger.error("❌ Error getting creator: %s", e)
            return None
    
    def get_all_creators(self):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM creators ORDER BY added_at DESC")
                return cur.fetchall()
        except Exception as e:
            logger.error("❌ Error getting creators: %s", e)
            return []
    
    def remove_creator(self, discord_user_id: int, platform: str):
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM creators 
                    WHERE discord_user_id = %s AND platform = %s
                    RETURNING id
                    """,
                    (discord_user_id, platform),
                )
                result = cur.fetchone()
                self.conn.commit()
                return bool(result)
        except Exception as e:
            logger.error("❌ Error removing creator: %s", e)
            self.conn.rollback()
            return False
    
    def add_mod(self, creator_id: int, mod_id: str, mod_name: str, mod_url: str, updated_at: str, platform: str):
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO mods (creator_id, mod_id, mod_name, mod_url, platform, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (mod_id, platform) DO NOTHING
                    """,
                    (creator_id, mod_id, mod_name, mod_url, platform, updated_at),
                )
                self.conn.commit()
        except Exception as e:
            logger.error("❌ Error adding mod: %s", e)
            self.conn.rollback()
    
    def get_mod(self, mod_id: str, platform: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM mods WHERE mod_id = %s AND platform = %s
                    """,
                    (mod_id, platform),
                )
                return cur.fetchone()
        except Exception as e:
            logger.error("❌ Error getting mod: %s", e)
            return None
    
    def update_mod(self, mod_id: str, updated_at: str, platform: str):
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE mods 
                    SET updated_at = %s, is_update = TRUE, notified_at = CURRENT_TIMESTAMP
                    WHERE mod_id = %s AND platform = %s
                    """,
                    (updated_at, mod_id, platform),
                )
                self.conn.commit()
        except Exception as e:
            logger.error("❌ Error updating mod: %s", e)
            self.conn.rollback()
    
    def get_creator_mods(self, creator_id: int):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM mods WHERE creator_id = %s ORDER BY notified_at DESC
                    """,
                    (creator_id,),
                )
                return cur.fetchall()
        except Exception as e:
            logger.error("❌ Error getting creator mods: %s", e)
            return []
    
    def log_notification(self, creator_id: int, mod_id: str, action: str):
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO notification_log (creator_id, mod_id, action)
                    VALUES (%s, %s, %s)
                    """,
                    (creator_id, mod_id, action),
                )
                self.conn.commit()
        except Exception as e:
            logger.error("❌ Error logging notification: %s", e)
            self.conn.rollback()
    
    def get_random_mod(self):
        """Get a random mod from all tracked creators"""
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT m.*, c.username, c.platform, c.discord_user_id
                    FROM mods m
                    JOIN creators c ON m.creator_id = c.id
                    ORDER BY RANDOM()
                    LIMIT 1
                    """
                )
                return cur.fetchone()
        except Exception as e:
            logger.error("❌ Error getting random mod: %s", e)
            return None


_db_instance = None


def get_creator_db():
    global _db_instance
    if _db_instance is None:
        _db_instance = CreatorDatabase()
    return _db_instance
