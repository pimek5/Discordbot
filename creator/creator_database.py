"""
Creator Database Management - Extended Version
PostgreSQL database with guild config, webhooks, and API key support
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
import logging
import hashlib
import secrets

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
                # Guild configuration per server
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS guild_config (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT UNIQUE NOT NULL,
                        notification_channel_id BIGINT,
                        random_mod_channel_id BIGINT,
                        new_mod_channel_id BIGINT,
                        webhook_url TEXT,
                        notify_new_mods BOOLEAN DEFAULT TRUE,
                        notify_updated_mods BOOLEAN DEFAULT TRUE,
                        notify_new_skins BOOLEAN DEFAULT TRUE,
                        notify_updated_skins BOOLEAN DEFAULT TRUE,
                        include_creator_avatar BOOLEAN DEFAULT TRUE,
                        include_creator_nickname BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                # Webhooks per guild for external integrations
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS webhooks (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT REFERENCES guild_config(guild_id) ON DELETE CASCADE,
                        webhook_url TEXT NOT NULL,
                        webhook_secret TEXT,
                        include_creator_avatar BOOLEAN DEFAULT TRUE,
                        include_creator_nickname BOOLEAN DEFAULT TRUE,
                        active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_used TIMESTAMP
                    )
                    """
                )
                # API keys for external API access
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS api_keys (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT REFERENCES guild_config(guild_id) ON DELETE CASCADE,
                        user_id BIGINT NOT NULL,
                        key_hash TEXT UNIQUE NOT NULL,
                        key_prefix VARCHAR(50) NOT NULL,
                        active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_used TIMESTAMP,
                        rate_limit INTEGER DEFAULT 1000
                    )
                    """
                )
                self.conn.commit()
                logger.info("✅ Database tables created/verified")
                
                # Run migrations
                self._migrate_database()
        except Exception as e:
            logger.error("❌ Error creating tables: %s", e)
            self.conn.rollback()
    
    def _migrate_database(self):
        """Apply database migrations for new columns"""
        try:
            with self.conn.cursor() as cur:
                # Add missing columns to guild_config if they don't exist
                migration_queries = [
                    "ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS random_mod_channel_id BIGINT",
                    "ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS new_mod_channel_id BIGINT",
                    "ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS notify_new_mods BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS notify_updated_mods BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS notify_new_skins BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS notify_updated_skins BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS include_creator_avatar BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS include_creator_nickname BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE webhooks ADD COLUMN IF NOT EXISTS include_creator_avatar BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE webhooks ADD COLUMN IF NOT EXISTS include_creator_nickname BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE api_keys ALTER COLUMN key_prefix TYPE VARCHAR(50)",
                ]
                
                for query in migration_queries:
                    try:
                        cur.execute(query)
                    except Exception as e:
                        if "already exists" not in str(e).lower():
                            logger.warning("⚠️ Migration warning: %s", e)
                
                self.conn.commit()
                logger.info("✅ Database migrations applied")
        except Exception as e:
            logger.warning("⚠️ Migration error (non-critical): %s", e)
            self.conn.rollback()
    # ==================== CREATORS ====================
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
    
    def get_creator_by_id(self, creator_id: int):
        """Get creator by ID"""
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM creators WHERE id = %s", (creator_id,))
                return cur.fetchone()
        except Exception as e:
            logger.error("❌ Error getting creator by ID: %s", e)
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
    
    # ==================== MODS ====================
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
    
    # ==================== GUILD CONFIG ====================
    def set_guild_config(self, guild_id: int, notification_channel_id: int = None, webhook_url: str = None, random_mod_channel_id: int = None, new_mod_channel_id: int = None):
        """Set or update guild configuration"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO guild_config (guild_id, notification_channel_id, webhook_url, random_mod_channel_id, new_mod_channel_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        notification_channel_id = COALESCE(EXCLUDED.notification_channel_id, guild_config.notification_channel_id),
                        webhook_url = COALESCE(EXCLUDED.webhook_url, guild_config.webhook_url),
                        random_mod_channel_id = COALESCE(EXCLUDED.random_mod_channel_id, guild_config.random_mod_channel_id),
                        new_mod_channel_id = COALESCE(EXCLUDED.new_mod_channel_id, guild_config.new_mod_channel_id),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (guild_id, notification_channel_id, webhook_url, random_mod_channel_id, new_mod_channel_id),
                )
                self.conn.commit()
                logger.info("✅ Guild config updated: %s", guild_id)
                return True
        except Exception as e:
            logger.error("❌ Error setting guild config: %s", e)
            self.conn.rollback()
            return False
    
    def get_guild_config(self, guild_id: int):
        """Get guild configuration"""
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM guild_config WHERE guild_id = %s", (guild_id,))
                return cur.fetchone()
        except Exception as e:
            logger.error("❌ Error getting guild config: %s", e)
            return None
    
    # ==================== WEBHOOKS ====================
    def add_webhook(self, guild_id: int, webhook_url: str, webhook_secret: str = None):
        """Add a webhook for a guild"""
        try:
            with self.conn.cursor() as cur:
                # Ensure guild_config exists
                cur.execute("INSERT INTO guild_config (guild_id) VALUES (%s) ON CONFLICT DO NOTHING", (guild_id,))
                
                cur.execute(
                    """
                    INSERT INTO webhooks (guild_id, webhook_url, webhook_secret)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (guild_id, webhook_url, webhook_secret),
                )
                webhook_id = cur.fetchone()[0]
                self.conn.commit()
                logger.info("✅ Webhook added for guild %s", guild_id)
                return webhook_id
        except Exception as e:
            logger.error("❌ Error adding webhook: %s", e)
            self.conn.rollback()
            return None
    
    def get_guild_webhooks(self, guild_id: int):
        """Get all active webhooks for a guild"""
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM webhooks WHERE guild_id = %s AND active = TRUE",
                    (guild_id,),
                )
                return cur.fetchall()
        except Exception as e:
            logger.error("❌ Error getting webhooks: %s", e)
            return []
    
    def deactivate_webhook(self, webhook_id: int):
        """Deactivate a webhook"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("UPDATE webhooks SET active = FALSE WHERE id = %s", (webhook_id,))
                self.conn.commit()
                return True
        except Exception as e:
            logger.error("❌ Error deactivating webhook: %s", e)
            self.conn.rollback()
            return False
    
    def get_all_guild_webhooks(self):
        """Get all active webhooks from all guilds (for broadcasting mod updates)"""
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT id, guild_id, webhook_url, active FROM webhooks WHERE active = TRUE"
                )
                return cur.fetchall()
        except Exception as e:
            logger.error("❌ Error getting all guild webhooks: %s", e)
            return []
    
    # ==================== API KEYS ====================
    @staticmethod
    def hash_api_key(key: str) -> str:
        """Hash an API key for secure storage"""
        return hashlib.sha256(key.encode()).hexdigest()
    
    @staticmethod
    def generate_api_key(guild_id: int, user_id: int) -> tuple:
        """Generate a new API key (returns key, prefix_for_display)"""
        prefix = f"ck_{secrets.token_hex(4).lower()}"
        key = f"{prefix}_{secrets.token_urlsafe(32)}"
        return key, prefix
    
    def create_api_key(self, guild_id: int, user_id: int) -> tuple:
        """Create and store a new API key. Returns (full_key, key_info) or (None, None)"""
        try:
            key, prefix = self.generate_api_key(guild_id, user_id)
            key_hash = self.hash_api_key(key)
            
            with self.conn.cursor() as cur:
                # Ensure guild_config exists
                cur.execute("INSERT INTO guild_config (guild_id) VALUES (%s) ON CONFLICT DO NOTHING", (guild_id,))
                
                cur.execute(
                    """
                    INSERT INTO api_keys (guild_id, user_id, key_hash, key_prefix)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, created_at
                    """,
                    (guild_id, user_id, key_hash, prefix),
                )
                result = cur.fetchone()
                self.conn.commit()
                
                if result:
                    logger.info("✅ API key created for user %s in guild %s", user_id, guild_id)
                    return key, {"id": result[0], "prefix": prefix, "created_at": result[1]}
                return None, None
        except Exception as e:
            logger.error("❌ Error creating API key: %s", e)
            self.conn.rollback()
            return None, None
    
    def get_api_keys(self, guild_id: int, user_id: int = None):
        """Get API keys for a user or guild (returns hashed keys, no full key exposed)"""
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                if user_id:
                    cur.execute(
                        "SELECT id, guild_id, user_id, key_prefix, active, created_at, last_used FROM api_keys WHERE guild_id = %s AND user_id = %s AND active = TRUE",
                        (guild_id, user_id),
                    )
                else:
                    cur.execute(
                        "SELECT id, guild_id, user_id, key_prefix, active, created_at, last_used FROM api_keys WHERE guild_id = %s AND active = TRUE",
                        (guild_id,),
                    )
                return cur.fetchall()
        except Exception as e:
            logger.error("❌ Error getting API keys: %s", e)
            return []
    
    def validate_api_key(self, key: str) -> dict:
        """Validate and retrieve API key info. Returns key info or None"""
        try:
            key_hash = self.hash_api_key(key)
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM api_keys WHERE key_hash = %s AND active = TRUE",
                    (key_hash,),
                )
                result = cur.fetchone()
                if result:
                    # Update last_used
                    cur.execute(
                        "UPDATE api_keys SET last_used = CURRENT_TIMESTAMP WHERE id = %s",
                        (result['id'],),
                    )
                    self.conn.commit()
                    return result
                return None
        except Exception as e:
            logger.error("❌ Error validating API key: %s", e)
            return None
    
    def revoke_api_key(self, api_key_id: int = None, key_prefix: str = None):
        """Revoke an API key by ID or prefix"""
        try:
            with self.conn.cursor() as cur:
                if api_key_id:
                    cur.execute("UPDATE api_keys SET active = FALSE WHERE id = %s RETURNING id", (api_key_id,))
                elif key_prefix:
                    cur.execute("UPDATE api_keys SET active = FALSE WHERE key_prefix = %s RETURNING id", (key_prefix,))
                else:
                    return False
                
                result = cur.fetchone()
                self.conn.commit()
                
                if result:
                    logger.info("✅ API key revoked: %s", api_key_id or key_prefix)
                    return True
                else:
                    logger.warning("⚠️ API key not found: %s", api_key_id or key_prefix)
                    return False
        except Exception as e:
            logger.error("❌ Error revoking API key: %s", e)
            self.conn.rollback()
            return False


_db_instance = None


def get_creator_db():
    global _db_instance
    if _db_instance is None:
        _db_instance = CreatorDatabase()
    return _db_instance
