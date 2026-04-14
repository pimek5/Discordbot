"""LoLBets configuration database for per-guild setup and external integrations."""

import hashlib
import logging
import os
import secrets
from typing import Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("lolbets_config")

DATABASE_URL = os.getenv("DATABASE_URL")


class LoLBetsConfigDB:
    def __init__(self, database_url: str = None):
        self.database_url = database_url or DATABASE_URL
        self._ensure_tables()

    def get_connection(self):
        return psycopg2.connect(self.database_url)

    def _ensure_tables(self):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lolbets_guild_config (
                        guild_id BIGINT PRIMARY KEY,
                        bet_channel_id BIGINT,
                        leaderboard_channel_id BIGINT,
                        bet_logs_channel_id BIGINT,
                        webhook_url TEXT,
                        webhook_enabled BOOLEAN DEFAULT FALSE,
                        notify_new_bets BOOLEAN DEFAULT TRUE,
                        notify_bet_results BOOLEAN DEFAULT TRUE,
                        notify_leaderboard_updates BOOLEAN DEFAULT FALSE,
                        allow_streamer_markets BOOLEAN DEFAULT TRUE,
                        brand_name TEXT DEFAULT 'LoLBets',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lolbets_webhooks (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        webhook_url TEXT NOT NULL,
                        webhook_secret TEXT,
                        active BOOLEAN DEFAULT TRUE,
                        notify_new_bets BOOLEAN DEFAULT TRUE,
                        notify_bet_results BOOLEAN DEFAULT TRUE,
                        notify_leaderboard BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (guild_id) REFERENCES lolbets_guild_config(guild_id) ON DELETE CASCADE
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lolbets_api_keys (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        key_prefix TEXT NOT NULL,
                        key_hash TEXT NOT NULL,
                        description TEXT,
                        active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_used_at TIMESTAMP,
                        FOREIGN KEY (guild_id) REFERENCES lolbets_guild_config(guild_id) ON DELETE CASCADE
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lolbets_streamer_registry (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        display_name TEXT NOT NULL,
                        riot_id TEXT,
                        platform_route TEXT,
                        enabled BOOLEAN DEFAULT TRUE,
                        created_by BIGINT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.commit()

    def get_guild_config(self, guild_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM lolbets_guild_config WHERE guild_id = %s", (guild_id,))
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
        notify_leaderboard_updates: Optional[bool] = None,
        allow_streamer_markets: Optional[bool] = None,
        brand_name: Optional[str] = None,
    ):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM lolbets_guild_config WHERE guild_id = %s", (guild_id,))
                exists = cur.fetchone()

                if exists:
                    updates = []
                    params = []
                    for field, value in [
                        ("bet_channel_id", bet_channel_id),
                        ("leaderboard_channel_id", leaderboard_channel_id),
                        ("bet_logs_channel_id", bet_logs_channel_id),
                        ("webhook_url", webhook_url),
                        ("webhook_enabled", webhook_enabled),
                        ("notify_new_bets", notify_new_bets),
                        ("notify_bet_results", notify_bet_results),
                        ("notify_leaderboard_updates", notify_leaderboard_updates),
                        ("allow_streamer_markets", allow_streamer_markets),
                        ("brand_name", brand_name),
                    ]:
                        if value is not None:
                            updates.append(f"{field} = %s")
                            params.append(value)
                    updates.append("updated_at = CURRENT_TIMESTAMP")
                    params.append(guild_id)
                    if updates:
                        cur.execute(f"UPDATE lolbets_guild_config SET {', '.join(updates)} WHERE guild_id = %s", params)
                else:
                    cur.execute(
                        """
                        INSERT INTO lolbets_guild_config (
                            guild_id, bet_channel_id, leaderboard_channel_id, bet_logs_channel_id,
                            webhook_url, webhook_enabled, notify_new_bets, notify_bet_results,
                            notify_leaderboard_updates, allow_streamer_markets, brand_name
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            guild_id,
                            bet_channel_id,
                            leaderboard_channel_id,
                            bet_logs_channel_id,
                            webhook_url,
                            webhook_enabled or False,
                            True if notify_new_bets is None else notify_new_bets,
                            True if notify_bet_results is None else notify_bet_results,
                            False if notify_leaderboard_updates is None else notify_leaderboard_updates,
                            True if allow_streamer_markets is None else allow_streamer_markets,
                            brand_name or "LoLBets",
                        ),
                    )
                conn.commit()

    def add_webhook(
        self,
        guild_id: int,
        webhook_url: str,
        webhook_secret: Optional[str] = None,
        notify_new_bets: bool = True,
        notify_bet_results: bool = True,
        notify_leaderboard: bool = False,
    ) -> int:
        if not self.get_guild_config(guild_id):
            self.set_guild_config(guild_id)
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO lolbets_webhooks (
                        guild_id, webhook_url, webhook_secret,
                        notify_new_bets, notify_bet_results, notify_leaderboard
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (guild_id, webhook_url, webhook_secret, notify_new_bets, notify_bet_results, notify_leaderboard),
                )
                webhook_id = cur.fetchone()[0]
                conn.commit()
                return webhook_id

    def get_guild_webhooks(self, guild_id: int) -> List[Dict]:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM lolbets_webhooks WHERE guild_id = %s AND active = TRUE ORDER BY created_at DESC",
                    (guild_id,),
                )
                return cur.fetchall()

    def remove_webhook(self, webhook_id: int, guild_id: int) -> bool:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE lolbets_webhooks SET active = FALSE WHERE id = %s AND guild_id = %s",
                    (webhook_id, guild_id),
                )
                conn.commit()
                return cur.rowcount > 0

    def create_api_key(self, guild_id: int, user_id: int, description: str = "") -> Tuple[str, Dict]:
        if not self.get_guild_config(guild_id):
            self.set_guild_config(guild_id)
        raw_key = secrets.token_urlsafe(32)
        key_prefix = f"llb_{raw_key[:8]}"
        full_key = f"{key_prefix}_{raw_key[8:]}"
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO lolbets_api_keys (guild_id, user_id, key_prefix, key_hash, description)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, key_prefix, created_at
                    """,
                    (guild_id, user_id, key_prefix, key_hash, description),
                )
                key_info = cur.fetchone()
                conn.commit()
                return full_key, key_info

    def get_user_api_keys(self, guild_id: int, user_id: int) -> List[Dict]:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, key_prefix, description, active, created_at, last_used_at
                    FROM lolbets_api_keys
                    WHERE guild_id = %s AND user_id = %s AND active = TRUE
                    ORDER BY created_at DESC
                    """,
                    (guild_id, user_id),
                )
                return cur.fetchall()

    def revoke_api_key(self, key_id: int, guild_id: int, user_id: int) -> bool:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE lolbets_api_keys SET active = FALSE WHERE id = %s AND guild_id = %s AND user_id = %s",
                    (key_id, guild_id, user_id),
                )
                conn.commit()
                return cur.rowcount > 0

    def upsert_streamer(self, guild_id: int, display_name: str, riot_id: Optional[str], platform_route: Optional[str], created_by: Optional[int]):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO lolbets_streamer_registry (guild_id, display_name, riot_id, platform_route, created_by)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (guild_id, display_name, riot_id, platform_route, created_by),
                )
                conn.commit()

    def get_streamers(self, guild_id: int) -> List[Dict]:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM lolbets_streamer_registry WHERE guild_id = %s AND enabled = TRUE ORDER BY display_name ASC",
                    (guild_id,),
                )
                return cur.fetchall()


def get_lolbets_config_db() -> LoLBetsConfigDB:
    return LoLBetsConfigDB()
