"""
HEXBET Configuration Database
Manages per-guild configuration for HEXBET bot
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
import logging
from typing import Optional, Dict, List, Tuple
import hashlib
import secrets

logger = logging.getLogger('hexbet_config')

DATABASE_URL = os.getenv('DATABASE_URL')


class HexbetConfigDB:
    """Database manager for HEXBET guild configurations"""
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or DATABASE_URL
        self._ensure_tables()
    
    def get_connection(self):
        """Get database connection"""
        return psycopg2.connect(self.database_url)
    
    def _ensure_tables(self):
        """Create necessary tables if they don't exist"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Guild configuration table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hexbet_guild_config (
                        guild_id BIGINT PRIMARY KEY,
                        bet_channel_id BIGINT,
                        leaderboard_channel_id BIGINT,
                        bet_logs_channel_id BIGINT,
                        webhook_url TEXT,
                        webhook_enabled BOOLEAN DEFAULT FALSE,
                        notify_new_bets BOOLEAN DEFAULT TRUE,
                        notify_bet_results BOOLEAN DEFAULT TRUE,
                        notify_leaderboard_updates BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Webhooks table for multiple webhook support
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hexbet_webhooks (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        webhook_url TEXT NOT NULL,
                        webhook_secret TEXT,
                        active BOOLEAN DEFAULT TRUE,
                        notify_new_bets BOOLEAN DEFAULT TRUE,
                        notify_bet_results BOOLEAN DEFAULT TRUE,
                        notify_leaderboard BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (guild_id) REFERENCES hexbet_guild_config(guild_id) ON DELETE CASCADE
                    )
                """)
                
                # API keys table (optional for external integrations)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hexbet_api_keys (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        key_prefix TEXT NOT NULL,
                        key_hash TEXT NOT NULL,
                        description TEXT,
                        active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_used_at TIMESTAMP,
                        FOREIGN KEY (guild_id) REFERENCES hexbet_guild_config(guild_id) ON DELETE CASCADE
                    )
                """)
                
                conn.commit()
                logger.info("✅ HEXBET config tables ensured")
    
    # ==================== GUILD CONFIG ====================
    
    def get_guild_config(self, guild_id: int) -> Optional[Dict]:
        """Get guild configuration"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM hexbet_guild_config WHERE guild_id = %s
                """, (guild_id,))
                return cur.fetchone()
    
    def set_guild_config(
        self,
        guild_id: int,
        bet_channel_id: Optional[int] = None,
        leaderboard_channel_id: Optional[int] = None,
        bet_logs_channel_id: Optional[int] = None,
        webhook_url: Optional[str] = None,
        webhook_enabled: Optional[bool] = None,
        notify_new_bets: Optional[bool] = None,
        notify_bet_results: Optional[bool] = None,
        notify_leaderboard_updates: Optional[bool] = None
    ):
        """Set or update guild configuration"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Check if config exists
                cur.execute("SELECT 1 FROM hexbet_guild_config WHERE guild_id = %s", (guild_id,))
                exists = cur.fetchone()
                
                if exists:
                    # Build update query dynamically
                    updates = []
                    params = []
                    
                    if bet_channel_id is not None:
                        updates.append("bet_channel_id = %s")
                        params.append(bet_channel_id)
                    if leaderboard_channel_id is not None:
                        updates.append("leaderboard_channel_id = %s")
                        params.append(leaderboard_channel_id)
                    if bet_logs_channel_id is not None:
                        updates.append("bet_logs_channel_id = %s")
                        params.append(bet_logs_channel_id)
                    if webhook_url is not None:
                        updates.append("webhook_url = %s")
                        params.append(webhook_url)
                    if webhook_enabled is not None:
                        updates.append("webhook_enabled = %s")
                        params.append(webhook_enabled)
                    if notify_new_bets is not None:
                        updates.append("notify_new_bets = %s")
                        params.append(notify_new_bets)
                    if notify_bet_results is not None:
                        updates.append("notify_bet_results = %s")
                        params.append(notify_bet_results)
                    if notify_leaderboard_updates is not None:
                        updates.append("notify_leaderboard_updates = %s")
                        params.append(notify_leaderboard_updates)
                    
                    updates.append("updated_at = CURRENT_TIMESTAMP")
                    params.append(guild_id)
                    
                    if updates:
                        query = f"UPDATE hexbet_guild_config SET {', '.join(updates)} WHERE guild_id = %s"
                        cur.execute(query, params)
                else:
                    # Insert new config
                    cur.execute("""
                        INSERT INTO hexbet_guild_config (
                            guild_id, bet_channel_id, leaderboard_channel_id, 
                            bet_logs_channel_id, webhook_url, webhook_enabled,
                            notify_new_bets, notify_bet_results, notify_leaderboard_updates
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        guild_id, bet_channel_id, leaderboard_channel_id,
                        bet_logs_channel_id, webhook_url, webhook_enabled or False,
                        notify_new_bets if notify_new_bets is not None else True,
                        notify_bet_results if notify_bet_results is not None else True,
                        notify_leaderboard_updates or False
                    ))
                
                conn.commit()
    
    # ==================== WEBHOOKS ====================
    
    def add_webhook(
        self,
        guild_id: int,
        webhook_url: str,
        webhook_secret: Optional[str] = None,
        notify_new_bets: bool = True,
        notify_bet_results: bool = True,
        notify_leaderboard: bool = False
    ) -> int:
        """Add a webhook for the guild"""
        # Ensure guild config exists
        if not self.get_guild_config(guild_id):
            self.set_guild_config(guild_id)
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO hexbet_webhooks (
                        guild_id, webhook_url, webhook_secret,
                        notify_new_bets, notify_bet_results, notify_leaderboard
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (guild_id, webhook_url, webhook_secret, notify_new_bets, notify_bet_results, notify_leaderboard))
                webhook_id = cur.fetchone()[0]
                conn.commit()
                return webhook_id
    
    def get_guild_webhooks(self, guild_id: int) -> List[Dict]:
        """Get all webhooks for a guild"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM hexbet_webhooks 
                    WHERE guild_id = %s AND active = TRUE
                    ORDER BY created_at DESC
                """, (guild_id,))
                return cur.fetchall()
    
    def get_all_webhooks(self) -> List[Dict]:
        """Get all active webhooks across all guilds"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM hexbet_webhooks 
                    WHERE active = TRUE
                    ORDER BY guild_id, created_at DESC
                """)
                return cur.fetchall()
    
    def remove_webhook(self, webhook_id: int, guild_id: int) -> bool:
        """Remove a webhook"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE hexbet_webhooks 
                    SET active = FALSE 
                    WHERE id = %s AND guild_id = %s
                """, (webhook_id, guild_id))
                conn.commit()
                return cur.rowcount > 0
    
    # ==================== API KEYS ====================
    
    def create_api_key(self, guild_id: int, user_id: int, description: str = "") -> Tuple[str, Dict]:
        """Create a new API key"""
        # Ensure guild config exists
        if not self.get_guild_config(guild_id):
            self.set_guild_config(guild_id)
        
        # Generate key
        raw_key = secrets.token_urlsafe(32)
        key_prefix = f"hxb_{raw_key[:8]}"
        full_key = f"{key_prefix}_{raw_key[8:]}"
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO hexbet_api_keys (
                        guild_id, user_id, key_prefix, key_hash, description
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, key_prefix, created_at
                """, (guild_id, user_id, key_prefix, key_hash, description))
                key_info = cur.fetchone()
                conn.commit()
                return full_key, key_info
    
    def get_user_api_keys(self, guild_id: int, user_id: int) -> List[Dict]:
        """Get all API keys for a user in a guild"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, key_prefix, description, active, created_at, last_used_at
                    FROM hexbet_api_keys
                    WHERE guild_id = %s AND user_id = %s AND active = TRUE
                    ORDER BY created_at DESC
                """, (guild_id, user_id))
                return cur.fetchall()
    
    def revoke_api_key(self, key_id: int, guild_id: int, user_id: int) -> bool:
        """Revoke an API key"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE hexbet_api_keys 
                    SET active = FALSE 
                    WHERE id = %s AND guild_id = %s AND user_id = %s
                """, (key_id, guild_id, user_id))
                conn.commit()
                return cur.rowcount > 0


def get_hexbet_config_db() -> HexbetConfigDB:
    """Get singleton instance of config database"""
    return HexbetConfigDB()
