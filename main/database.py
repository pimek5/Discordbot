"""
Database module for Kassalytics
Handles PostgreSQL connection and queries
"""

import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging
import json

logger = logging.getLogger('database')

class Database:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.connection_pool = None
        
    def initialize(self):
        """Initialize connection pool"""
        try:
            print("🔄 Creating database connection pool...")
            self._create_pool()
            print("✅ Database connection pool created")
            logger.info("✅ Database connection pool created")
            
            # Create tables if they don't exist
            print("🔄 Creating/verifying database tables...")
            self.create_tables()
            print("✅ Database tables created/verified")
            
        except Exception as e:
            print(f"❌ Failed to create connection pool: {e}")
            logger.error(f"❌ Failed to create connection pool: {e}")
            raise

    def _create_pool(self):
        """Create/recreate connection pool"""
        self.connection_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=self.database_url,
            connect_timeout=10
        )
    
    def get_connection(self):
        """Get a connection from the pool"""
        if self.connection_pool is None:
            self.initialize()

        last_error = None
        for attempt in range(1, 4):
            try:
                return self.connection_pool.getconn()
            except (psycopg2.OperationalError, psycopg2.InterfaceError, pool.PoolError) as error:
                last_error = error
                logger.warning("⚠️ DB connection attempt %s/3 failed: %s", attempt, error)

                try:
                    if self.connection_pool is not None:
                        self.connection_pool.closeall()
                except Exception:
                    pass

                self.connection_pool = None
                if attempt < 3:
                    time.sleep(1.5 * attempt)
                    try:
                        self._create_pool()
                    except Exception as pool_error:
                        last_error = pool_error
                        logger.warning("⚠️ Failed to recreate DB pool: %s", pool_error)

        raise last_error
    
    def return_connection(self, conn):
        """Return connection to the pool"""
        if conn is None:
            return

        try:
            if self.connection_pool is None:
                try:
                    conn.close()
                except Exception:
                    pass
                return

            if getattr(conn, "closed", 1) != 0:
                self.connection_pool.putconn(conn, close=True)
            else:
                self.connection_pool.putconn(conn)
        except Exception as error:
            logger.warning("⚠️ Failed to return DB connection to pool: %s", error)
    
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
                
                # Run voting exclusions migration
                try:
                    cur.execute("""
                        ALTER TABLE voting_sessions 
                        ADD COLUMN IF NOT EXISTS excluded_champions TEXT[]
                    """)
                    cur.execute("""
                        ALTER TABLE voting_sessions 
                        ADD COLUMN IF NOT EXISTS auto_exclude_previous BOOLEAN DEFAULT TRUE
                    """)
                    conn.commit()
                    logger.info("✅ Voting exclusions migration applied")
                except Exception as migration_error:
                    logger.warning(f"⚠️ Migration already applied or error: {migration_error}")
                    conn.rollback()

                # Run team system migration
                try:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS teams (
                            id SERIAL PRIMARY KEY,
                            guild_id BIGINT NOT NULL,
                            name VARCHAR(50) NOT NULL,
                            tag VARCHAR(12),
                            description VARCHAR(180),
                            recruiting BOOLEAN NOT NULL DEFAULT TRUE,
                            captain_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            created_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            created_at TIMESTAMP DEFAULT NOW(),
                            updated_at TIMESTAMP DEFAULT NOW(),
                            UNIQUE (guild_id, name)
                        )
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS team_members (
                            id SERIAL PRIMARY KEY,
                            team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            role VARCHAR(20) NOT NULL DEFAULT 'member',
                            invited_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                            joined_at TIMESTAMP DEFAULT NOW(),
                            UNIQUE (team_id, user_id)
                        )
                    """)
                    cur.execute("ALTER TABLE teams ADD COLUMN IF NOT EXISTS description VARCHAR(180)")
                    cur.execute("ALTER TABLE teams ADD COLUMN IF NOT EXISTS recruiting BOOLEAN NOT NULL DEFAULT TRUE")
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS team_profile_embeds (
                            team_id INTEGER PRIMARY KEY REFERENCES teams(id) ON DELETE CASCADE,
                            guild_id BIGINT NOT NULL,
                            channel_id BIGINT NOT NULL,
                            message_id BIGINT NOT NULL,
                            last_updated TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS team_leaderboard_embeds (
                            guild_id BIGINT PRIMARY KEY,
                            channel_id BIGINT NOT NULL,
                            message_id BIGINT NOT NULL,
                            last_updated TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS team_power_snapshots (
                            id SERIAL PRIMARY KEY,
                            team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                            power_score DOUBLE PRECISION NOT NULL,
                            created_at TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    conn.commit()
                    logger.info("✅ Team system migration applied")
                except Exception as migration_error:
                    logger.warning(f"⚠️ Team migration already applied or error: {migration_error}")
                    conn.rollback()

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
                          tagline: str, puuid: str, summoner_id: Optional[str] = None,
                          summoner_level: int = 1, verified: bool = False) -> int:
        """Add a new League account (summoner_id is optional as it's deprecated)"""
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
                        summoner_id = COALESCE(EXCLUDED.summoner_id, league_accounts.summoner_id),
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
    
    def get_visible_user_accounts(self, user_id: int) -> List[Dict]:
        """Get only visible League accounts for a user (for profile stats)"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM league_accounts 
                    WHERE user_id = %s AND show_in_profile = TRUE
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
    
    def delete_specific_account(self, user_id: int, riot_id_game_name: str, riot_id_tagline: str, region: str) -> bool:
        """Delete a specific account for a user by riot_id and region"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM league_accounts 
                    WHERE user_id = %s 
                    AND riot_id_game_name = %s 
                    AND riot_id_tagline = %s 
                    AND region = %s
                """, (user_id, riot_id_game_name, riot_id_tagline, region))
                conn.commit()
                return cur.rowcount > 0
        finally:
            self.return_connection(conn)
    
    def get_all_accounts(self, user_id: int) -> list:
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
    
    def set_primary_account(self, user_id: int, account_id: int) -> bool:
        """Set a specific account as primary for a user"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # First, set all accounts to not primary
                cur.execute("""
                    UPDATE league_accounts 
                    SET primary_account = FALSE 
                    WHERE user_id = %s
                """, (user_id,))
                
                # Then set the specified account as primary
                cur.execute("""
                    UPDATE league_accounts 
                    SET primary_account = TRUE 
                    WHERE id = %s AND user_id = %s
                """, (account_id, user_id))
                
                conn.commit()
                return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Error setting primary account: {e}")
            return False
        finally:
            self.return_connection(conn)
    
    def update_account_name(self, puuid: str, game_name: str, tagline: str) -> bool:
        """Update account Riot ID (name and tagline) by PUUID"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE league_accounts 
                    SET riot_id_game_name = %s,
                        riot_id_tagline = %s,
                        last_updated = NOW()
                    WHERE puuid = %s
                """, (game_name, tagline, puuid))
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating account name: {e}")
            return False
        finally:
            self.return_connection(conn)

    # ==================== TEAM OPERATIONS ====================

    def get_team_by_name(self, guild_id: int, team_name: str) -> Optional[Dict]:
        """Get team by exact name in guild"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM teams
                    WHERE guild_id = %s AND LOWER(name) = LOWER(%s)
                    LIMIT 1
                    """,
                    (guild_id, team_name)
                )
                return cur.fetchone()
        finally:
            self.return_connection(conn)

    def get_teams_by_tag(self, guild_id: int, team_tag: str) -> List[Dict]:
        """Get teams by exact tag in guild (case-insensitive)"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM teams
                    WHERE guild_id = %s AND LOWER(COALESCE(tag, '')) = LOWER(%s)
                    ORDER BY created_at ASC
                    """,
                    (guild_id, team_tag)
                )
                return cur.fetchall()
        finally:
            self.return_connection(conn)

    def get_user_team(self, guild_id: int, user_id: int) -> Optional[Dict]:
        """Get team for a user in guild"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT t.*
                    FROM team_members tm
                    JOIN teams t ON tm.team_id = t.id
                    WHERE t.guild_id = %s AND tm.user_id = %s
                    LIMIT 1
                    """,
                    (guild_id, user_id)
                )
                return cur.fetchone()
        finally:
            self.return_connection(conn)

    def create_team(self, guild_id: int, name: str, captain_user_id: int, created_by_user_id: int) -> int:
        """Create a team and auto-add captain as member"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO teams (guild_id, name, captain_user_id, created_by_user_id)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (guild_id, name, captain_user_id, created_by_user_id)
                )
                team_id = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO team_members (team_id, user_id, role, invited_by_user_id)
                    VALUES (%s, %s, 'captain', %s)
                    ON CONFLICT (team_id, user_id) DO NOTHING
                    """,
                    (team_id, captain_user_id, created_by_user_id)
                )
                conn.commit()
                return team_id
        except Exception:
            conn.rollback()
            raise
        finally:
            self.return_connection(conn)

    def add_team_member(self, team_id: int, user_id: int, invited_by_user_id: int) -> bool:
        """Add member to team"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO team_members (team_id, user_id, role, invited_by_user_id)
                    SELECT %s, %s, 'member', %s
                    WHERE (
                        SELECT COUNT(*)
                        FROM team_members
                        WHERE team_id = %s
                    ) < 10
                    ON CONFLICT (team_id, user_id) DO NOTHING
                    """,
                    (team_id, user_id, invited_by_user_id, team_id)
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            self.return_connection(conn)

    def get_team_member_count(self, team_id: int) -> int:
        """Get current member count for team"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM team_members WHERE team_id = %s", (team_id,))
                return int(cur.fetchone()[0] or 0)
        finally:
            self.return_connection(conn)

    def remove_team_member(self, team_id: int, user_id: int) -> bool:
        """Remove member from team"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM team_members
                    WHERE team_id = %s AND user_id = %s
                    """,
                    (team_id, user_id)
                )
                conn.commit()
                return cur.rowcount > 0
        finally:
            self.return_connection(conn)

    def update_team_config(
        self,
        team_id: int,
        name: Optional[str] = None,
        tag: Optional[str] = None,
        description: Optional[str] = None,
        recruiting: Optional[bool] = None,
    ) -> bool:
        """Update team config fields"""
        fields = []
        values: List[Any] = []
        if name is not None:
            fields.append("name = %s")
            values.append(name)
        if tag is not None:
            fields.append("tag = %s")
            values.append(tag)
        if description is not None:
            fields.append("description = %s")
            values.append(description)
        if recruiting is not None:
            fields.append("recruiting = %s")
            values.append(recruiting)
        if not fields:
            return False

        values.append(team_id)
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE teams
                    SET {', '.join(fields)}, updated_at = NOW()
                    WHERE id = %s
                    """,
                    tuple(values)
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            self.return_connection(conn)

    def get_team_members(self, team_id: int) -> List[Dict]:
        """Get all members for team"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT tm.*, u.snowflake
                    FROM team_members tm
                    JOIN users u ON u.id = tm.user_id
                    WHERE tm.team_id = %s
                    ORDER BY CASE WHEN tm.role = 'captain' THEN 0 ELSE 1 END, tm.joined_at ASC
                    """,
                    (team_id,)
                )
                return cur.fetchall()
        finally:
            self.return_connection(conn)

    def list_teams(self, guild_id: int, recruiting_only: bool = False, limit: int = 20) -> List[Dict]:
        """List teams in guild with member counts"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                params: List[Any] = [guild_id]
                where_parts = ["t.guild_id = %s"]
                if recruiting_only:
                    where_parts.append("t.recruiting = TRUE")

                params.append(limit)
                cur.execute(
                    f"""
                    SELECT
                        t.*, COUNT(tm.user_id)::int AS member_count
                    FROM teams t
                    LEFT JOIN team_members tm ON tm.team_id = t.id
                    WHERE {' AND '.join(where_parts)}
                    GROUP BY t.id
                    ORDER BY member_count DESC, t.created_at ASC
                    LIMIT %s
                    """,
                    tuple(params)
                )
                return cur.fetchall()
        finally:
            self.return_connection(conn)

    def search_teams(self, guild_id: int, query: str, limit: int = 10) -> List[Dict]:
        """Search teams by name or tag in guild"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                like_query = f"%{query}%"
                cur.execute(
                    """
                    SELECT
                        t.*, COUNT(tm.user_id)::int AS member_count
                    FROM teams t
                    LEFT JOIN team_members tm ON tm.team_id = t.id
                    WHERE t.guild_id = %s
                      AND (
                        LOWER(t.name) LIKE LOWER(%s)
                        OR LOWER(COALESCE(t.tag, '')) LIKE LOWER(%s)
                      )
                    GROUP BY t.id
                    ORDER BY
                        CASE WHEN LOWER(t.name) = LOWER(%s) THEN 0 ELSE 1 END,
                        CASE WHEN LOWER(COALESCE(t.tag, '')) = LOWER(%s) THEN 0 ELSE 1 END,
                        member_count DESC,
                        t.created_at ASC
                    LIMIT %s
                    """,
                    (guild_id, like_query, like_query, query, query, limit)
                )
                return cur.fetchall()
        finally:
            self.return_connection(conn)

    def transfer_team_captain(self, team_id: int, new_captain_user_id: int) -> bool:
        """Transfer captain role to another existing member"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE team_members
                    SET role = 'member'
                    WHERE team_id = %s AND role = 'captain'
                    """,
                    (team_id,)
                )

                cur.execute(
                    """
                    UPDATE team_members
                    SET role = 'captain'
                    WHERE team_id = %s AND user_id = %s
                    """,
                    (team_id, new_captain_user_id)
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    return False

                cur.execute(
                    """
                    UPDATE teams
                    SET captain_user_id = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (new_captain_user_id, team_id)
                )
                conn.commit()
                return True
        except Exception:
            conn.rollback()
            raise
        finally:
            self.return_connection(conn)

    def delete_team(self, team_id: int) -> bool:
        """Delete team (members are removed by FK cascade)"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM teams WHERE id = %s", (team_id,))
                conn.commit()
                return cur.rowcount > 0
        finally:
            self.return_connection(conn)

    def save_team_profile_embed(self, team_id: int, guild_id: int, channel_id: int, message_id: int):
        """Save or update persistent team profile embed message"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO team_profile_embeds (team_id, guild_id, channel_id, message_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (team_id) DO UPDATE SET
                        guild_id = EXCLUDED.guild_id,
                        channel_id = EXCLUDED.channel_id,
                        message_id = EXCLUDED.message_id,
                        last_updated = NOW()
                    """,
                    (team_id, guild_id, channel_id, message_id),
                )
                conn.commit()
        finally:
            self.return_connection(conn)

    def get_team_profile_embed(self, team_id: int) -> Optional[Dict]:
        """Get persistent team profile embed for team"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM team_profile_embeds
                    WHERE team_id = %s
                    LIMIT 1
                    """,
                    (team_id,),
                )
                return cur.fetchone()
        finally:
            self.return_connection(conn)

    def save_team_leaderboard_embed(self, guild_id: int, channel_id: int, message_id: int):
        """Save or update persistent team leaderboard embed message"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO team_leaderboard_embeds (guild_id, channel_id, message_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        channel_id = EXCLUDED.channel_id,
                        message_id = EXCLUDED.message_id,
                        last_updated = NOW()
                    """,
                    (guild_id, channel_id, message_id),
                )
                conn.commit()
        finally:
            self.return_connection(conn)

    def get_team_leaderboard_embed(self, guild_id: int) -> Optional[Dict]:
        """Get persistent team leaderboard embed by guild"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM team_leaderboard_embeds
                    WHERE guild_id = %s
                    LIMIT 1
                    """,
                    (guild_id,),
                )
                return cur.fetchone()
        finally:
            self.return_connection(conn)

    def add_team_power_snapshot(self, team_id: int, power_score: float):
        """Store team power score snapshot"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO team_power_snapshots (team_id, power_score)
                    VALUES (%s, %s)
                    """,
                    (team_id, float(power_score)),
                )
                conn.commit()
        finally:
            self.return_connection(conn)

    def get_team_power_trend(self, team_id: int, days: int = 7) -> Optional[float]:
        """Return power delta from oldest snapshot in period to latest"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT power_score, created_at
                    FROM team_power_snapshots
                    WHERE team_id = %s
                      AND created_at >= NOW() - (%s || ' days')::interval
                    ORDER BY created_at ASC
                    """,
                    (team_id, days),
                )
                rows = cur.fetchall()
                if not rows or len(rows) < 2:
                    return None
                return float(rows[-1]["power_score"] - rows[0]["power_score"])
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
                           veteran: bool = False, fresh_blood: bool = False, season: str = '15'):
        """Update ranked statistics"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_ranks 
                    (user_id, queue, tier, rank, league_points, wins, losses, 
                     hot_streak, veteran, fresh_blood, season)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, queue, season) DO UPDATE SET
                        tier = EXCLUDED.tier,
                        rank = EXCLUDED.rank,
                        league_points = EXCLUDED.league_points,
                        wins = EXCLUDED.wins,
                        losses = EXCLUDED.losses,
                        hot_streak = EXCLUDED.hot_streak,
                        veteran = EXCLUDED.veteran,
                        fresh_blood = EXCLUDED.fresh_blood,
                        last_updated = NOW()
                """, (user_id, queue, tier, rank, lp, wins, losses, hot_streak, veteran, fresh_blood, season))
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

    def save_ranked_progress_snapshot(
        self,
        guild_id: int,
        discord_user_id: int,
        puuid: str,
        tier: str,
        rank: str,
        league_points: int,
        wins: int,
        losses: int,
    ):
        """Store a ranked progress snapshot used for LP/games delta calculations."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ranked_progress_snapshots
                    (guild_id, discord_user_id, puuid, tier, rank, league_points, wins, losses)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        guild_id,
                        discord_user_id,
                        puuid,
                        tier,
                        rank,
                        int(league_points),
                        int(wins),
                        int(losses),
                    ),
                )
                conn.commit()
        finally:
            self.return_connection(conn)

    def get_latest_ranked_progress_snapshot(
        self,
        guild_id: int,
        discord_user_id: int,
        puuid: str,
        max_age_hours: int = 36,
    ) -> Optional[Dict]:
        """Get the latest ranked progress snapshot for a user/account in a guild."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM ranked_progress_snapshots
                    WHERE guild_id = %s
                      AND discord_user_id = %s
                      AND puuid = %s
                      AND snapshot_at >= NOW() - (%s || ' hours')::interval
                    ORDER BY snapshot_at DESC
                    LIMIT 1
                    """,
                    (guild_id, discord_user_id, puuid, max_age_hours),
                )
                return cur.fetchone()
        finally:
            self.return_connection(conn)

    def get_daily_baseline_ranked_progress_snapshot(
        self,
        guild_id: int,
        discord_user_id: int,
        puuid: str,
        max_age_hours: int = 24,
    ) -> Optional[Dict]:
        """Get the earliest snapshot in the current 24h window (daily baseline)."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM ranked_progress_snapshots
                    WHERE guild_id = %s
                      AND discord_user_id = %s
                      AND puuid = %s
                      AND snapshot_at >= NOW() - (%s || ' hours')::interval
                    ORDER BY snapshot_at ASC
                    LIMIT 1
                    """,
                    (guild_id, discord_user_id, puuid, max_age_hours),
                )
                return cur.fetchone()
        finally:
            self.return_connection(conn)

    def get_daily_baseline_ranked_progress_snapshots_map(
        self,
        guild_id: int,
        max_age_hours: int = 24,
    ) -> Dict[tuple, Dict]:
        """Get earliest daily snapshots map keyed by (discord_user_id, puuid)."""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (discord_user_id, puuid)
                        discord_user_id,
                        puuid,
                        tier,
                        rank,
                        league_points,
                        wins,
                        losses,
                        snapshot_at
                    FROM ranked_progress_snapshots
                    WHERE guild_id = %s
                      AND snapshot_at >= NOW() - (%s || ' hours')::interval
                    ORDER BY discord_user_id, puuid, snapshot_at ASC
                    """,
                    (guild_id, max_age_hours),
                )
                rows = cur.fetchall() or []

            result: Dict[tuple, Dict] = {}
            for row in rows:
                key = (int(row['discord_user_id']), str(row['puuid']))
                result[key] = dict(row)
            return result
        finally:
            self.return_connection(conn)

    def cleanup_ranked_progress_snapshots(self, guild_id: int, max_age_hours: int = 24) -> int:
        """Delete snapshots older than the configured window and return deleted rows count."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM ranked_progress_snapshots
                    WHERE guild_id = %s
                      AND snapshot_at < NOW() - (%s || ' hours')::interval
                    """,
                    (guild_id, max_age_hours),
                )
                deleted = cur.rowcount
                conn.commit()
                return deleted
        finally:
            self.return_connection(conn)

    def clear_ranked_progress_snapshots(self, guild_id: int) -> int:
        """Clear all ranked snapshots for a guild (daily reset)."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM ranked_progress_snapshots
                    WHERE guild_id = %s
                    """,
                    (guild_id,),
                )
                deleted = cur.rowcount
                conn.commit()
                return deleted
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
    
    def get_rank_leaderboard(self, guild_id: Optional[int] = None, 
                            queue: str = 'RANKED_SOLO_5x5', limit: int = 10) -> List[Dict]:
        """Get top ranked players - shows best rank per user with their summoner name"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Build query with optional guild filter
                guild_join = ""
                guild_where = ""
                params = [queue]
                
                if guild_id:
                    guild_join = "JOIN guild_members gm ON u.id = gm.user_id"
                    guild_where = "AND gm.guild_id = %s"
                    params.append(guild_id)
                
                params.append(limit)
                
                query = f"""
                    WITH user_best_ranks AS (
                        SELECT 
                            ur.user_id,
                            ur.tier,
                            ur.rank,
                            ur.league_points,
                            ur.wins,
                            ur.losses,
                            CASE ur.tier
                                WHEN 'CHALLENGER' THEN 9
                                WHEN 'GRANDMASTER' THEN 8
                                WHEN 'MASTER' THEN 7
                                WHEN 'DIAMOND' THEN 6
                                WHEN 'EMERALD' THEN 5
                                WHEN 'PLATINUM' THEN 4
                                WHEN 'GOLD' THEN 3
                                WHEN 'SILVER' THEN 2
                                WHEN 'BRONZE' THEN 1
                                WHEN 'IRON' THEN 0
                                ELSE -1
                            END as tier_value,
                            CASE ur.rank
                                WHEN 'I' THEN 4
                                WHEN 'II' THEN 3
                                WHEN 'III' THEN 2
                                WHEN 'IV' THEN 1
                                ELSE 0
                            END as rank_value,
                            ROW_NUMBER() OVER (
                                PARTITION BY ur.user_id 
                                ORDER BY 
                                    CASE ur.tier
                                        WHEN 'CHALLENGER' THEN 9
                                        WHEN 'GRANDMASTER' THEN 8
                                        WHEN 'MASTER' THEN 7
                                        WHEN 'DIAMOND' THEN 6
                                        WHEN 'EMERALD' THEN 5
                                        WHEN 'PLATINUM' THEN 4
                                        WHEN 'GOLD' THEN 3
                                        WHEN 'SILVER' THEN 2
                                        WHEN 'BRONZE' THEN 1
                                        WHEN 'IRON' THEN 0
                                        ELSE -1
                                    END DESC,
                                    CASE ur.rank
                                        WHEN 'I' THEN 4
                                        WHEN 'II' THEN 3
                                        WHEN 'III' THEN 2
                                        WHEN 'IV' THEN 1
                                        ELSE 0
                                    END DESC,
                                    ur.league_points DESC
                            ) as rn
                        FROM user_ranks ur
                        WHERE ur.queue = %s
                    )
                    SELECT 
                        u.snowflake,
                        ubr.tier,
                        ubr.rank,
                        ubr.league_points,
                        ubr.wins,
                        ubr.losses,
                        la.riot_id_game_name,
                        la.riot_id_tagline
                    FROM user_best_ranks ubr
                    JOIN users u ON ubr.user_id = u.id
                    {guild_join}
                    LEFT JOIN league_accounts la ON u.id = la.user_id 
                        AND (la.primary_account = TRUE OR la.id = (
                            SELECT id FROM league_accounts 
                            WHERE user_id = u.id 
                            ORDER BY primary_account DESC, id ASC 
                            LIMIT 1
                        ))
                    WHERE ubr.rn = 1 {guild_where}
                    ORDER BY 
                        ubr.tier_value DESC,
                        ubr.rank_value DESC,
                        ubr.league_points DESC
                    LIMIT %s
                """
                
                cur.execute(query, params)
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
                                expires_minutes: int = 5) -> int:
        """Create a verification code"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                expires_at = datetime.now() + timedelta(minutes=expires_minutes)
                cur.execute("""
                    INSERT INTO verification_codes 
                    (user_id, code, riot_id_game_name, riot_id_tagline, region, puuid, summoner_id, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NULL, %s)
                    RETURNING id
                """, (user_id, code, game_name, tagline, region, puuid, expires_at))
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
    
    # ==================== CHANNEL PERMISSIONS ====================
    
    def add_allowed_channel(self, guild_id: int, channel_id: int):
        """Add a channel to allowed channels list"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO allowed_channels (guild_id, channel_id)
                    VALUES (%s, %s)
                    ON CONFLICT (guild_id, channel_id) DO NOTHING
                """, (guild_id, channel_id))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def remove_allowed_channel(self, guild_id: int, channel_id: int):
        """Remove a channel from allowed channels list"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM allowed_channels 
                    WHERE guild_id = %s AND channel_id = %s
                """, (guild_id, channel_id))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def get_allowed_channels(self, guild_id: int) -> List[int]:
        """Get all allowed channel IDs for a guild"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT channel_id FROM allowed_channels 
                    WHERE guild_id = %s
                """, (guild_id,))
                return [row[0] for row in cur.fetchall()]
        finally:
            self.return_connection(conn)
    
    def is_channel_allowed(self, guild_id: int, channel_id: int) -> bool:
        """Check if a channel is in the allowed list"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM allowed_channels 
                        WHERE guild_id = %s AND channel_id = %s
                    )
                """, (guild_id, channel_id))
                return cur.fetchone()[0]
        finally:
            self.return_connection(conn)

    def get_guild_setting(self, guild_id: int, key: str) -> Optional[str]:
        """Get a guild setting value by key."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT value
                    FROM guild_settings
                    WHERE guild_id = %s AND key = %s
                    LIMIT 1
                    """,
                    (guild_id, key),
                )
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            self.return_connection(conn)

    def set_guild_setting(self, guild_id: int, key: str, value: str):
        """Create or update a guild setting value."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO guild_settings (guild_id, key, value)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (guild_id, key)
                    DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                    """,
                    (guild_id, key, value),
                )
                conn.commit()
        finally:
            self.return_connection(conn)
    
    # ==================== VOTING OPERATIONS ====================
    
    def create_voting_session(self, guild_id: int, channel_id: int, started_by: int, excluded_champions: List[str] = None) -> int:
        """Create a new voting session and return its ID"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO voting_sessions (guild_id, channel_id, started_by, status, excluded_champions)
                    VALUES (%s, %s, %s, 'active', %s)
                    RETURNING id
                """, (guild_id, channel_id, started_by, excluded_champions or []))
                session_id = cur.fetchone()[0]
                conn.commit()
                return session_id
        finally:
            self.return_connection(conn)
    
    def get_active_voting_session(self, guild_id: int) -> Optional[Dict]:
        """Get the active voting session for a guild"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM voting_sessions
                    WHERE guild_id = %s AND status = 'active'
                    ORDER BY started_at DESC
                    LIMIT 1
                """, (guild_id,))
                return cur.fetchone()
        finally:
            self.return_connection(conn)
    
    def update_voting_message_id(self, session_id: int, message_id: int):
        """Update the message ID for a voting session"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE voting_sessions
                    SET message_id = %s
                    WHERE id = %s
                """, (message_id, session_id))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def end_voting_session(self, session_id: int):
        """End a voting session"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE voting_sessions
                    SET status = 'ended', ended_at = NOW()
                    WHERE id = %s
                """, (session_id,))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def add_vote(self, session_id: int, user_id: int, champions: List[str], points: int) -> bool:
        """Add or update user's votes (5 champions). Returns True if successful."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Delete existing votes for this user in this session
                cur.execute("""
                    DELETE FROM voting_votes
                    WHERE session_id = %s AND user_id = %s
                """, (session_id, user_id))
                
                # Insert new votes (5 champions with ranks 1-5)
                for rank, champion_name in enumerate(champions, start=1):
                    cur.execute("""
                        INSERT INTO voting_votes (session_id, user_id, champion_name, rank_position, points)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (session_id, user_id, champion_name, rank, points))
                
                conn.commit()
                return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Error adding votes: {e}")
            return False
        finally:
            self.return_connection(conn)
    
    def add_vote_cumulative(self, session_id: int, user_id: int, champion_name: str, points: int) -> dict:
        """
        Add a single champion vote cumulatively (up to 5 per user per session).
        Returns: {'success': bool, 'message': str, 'current_count': int}
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Check if user already voted for this champion
                cur.execute("""
                    SELECT COUNT(*) as count FROM voting_votes
                    WHERE session_id = %s AND user_id = %s AND champion_name = %s
                """, (session_id, user_id, champion_name))
                result = cur.fetchone()
                if result[0] > 0:
                    return {'success': False, 'message': f'🔄 You already voted for **{champion_name}** in this session!', 'current_count': None}
                
                # Count current votes for this user
                cur.execute("""
                    SELECT COUNT(DISTINCT champion_name) as count FROM voting_votes
                    WHERE session_id = %s AND user_id = %s
                """, (session_id, user_id))
                result = cur.fetchone()
                current_count = result[0] if result else 0
                
                # Check if user reached limit (5 champions)
                if current_count >= 5:
                    return {'success': False, 'message': f'⛔ You already voted for 5 champions! This is the maximum per session.', 'current_count': current_count}
                
                # Add the new vote
                cur.execute("""
                    INSERT INTO voting_votes (session_id, user_id, champion_name, rank_position, points)
                    VALUES (%s, %s, %s, %s, %s)
                """, (session_id, user_id, champion_name, current_count + 1, points))
                
                conn.commit()
                return {'success': True, 'message': f'✅ Voted for **{champion_name}** ({current_count + 1}/5)', 'current_count': current_count + 1}
        except Exception as e:
            conn.rollback()
            logger.error(f"Error adding cumulative vote: {e}")
            return {'success': False, 'message': f'❌ Error recording vote: {e}', 'current_count': None}
        finally:
            self.return_connection(conn)
    
    def get_unique_voter_count(self, session_id: int) -> int:
        """Count unique users who voted in this session"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(DISTINCT user_id) as count
                    FROM voting_votes
                    WHERE session_id = %s
                """, (session_id,))
                result = cur.fetchone()
                return result[0] if result else 0
        finally:
            self.return_connection(conn)
    
    def get_voting_results(self, session_id: int) -> List[Dict]:
        """Get aggregated voting results for a session"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        champion_name,
                        SUM(points) as total_points,
                        COUNT(DISTINCT user_id) as vote_count
                    FROM voting_votes
                    WHERE session_id = %s
                    GROUP BY champion_name
                    ORDER BY total_points DESC, champion_name ASC
                """, (session_id,))
                return cur.fetchall()
        finally:
            self.return_connection(conn)
    
    def has_user_voted(self, session_id: int, user_id: int) -> bool:
        """Check if user has already voted in this session"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM voting_votes
                        WHERE session_id = %s AND user_id = %s
                    )
                """, (session_id, user_id))
                return cur.fetchone()[0]
        finally:
            self.return_connection(conn)
    
    def add_excluded_champions(self, session_id: int, champions: List[str]):
        """Add champions to the exclusion list for a session"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE voting_sessions
                    SET excluded_champions = array_cat(COALESCE(excluded_champions, ARRAY[]::TEXT[]), %s::TEXT[])
                    WHERE id = %s
                """, (champions, session_id))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def remove_excluded_champion(self, session_id: int, champion: str):
        """Remove a champion from the exclusion list"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE voting_sessions
                    SET excluded_champions = array_remove(excluded_champions, %s)
                    WHERE id = %s
                """, (champion, session_id))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def get_previous_session_winners(self, guild_id: int, limit: int = 5) -> List[str]:
        """Get top N champions from the last ended session"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get the last ended session
                cur.execute("""
                    SELECT id FROM voting_sessions
                    WHERE guild_id = %s AND status = 'ended'
                    ORDER BY ended_at DESC
                    LIMIT 1
                """, (guild_id,))
                
                last_session = cur.fetchone()
                if not last_session:
                    return []
                
                # Get top champions from that session
                cur.execute("""
                    SELECT champion_name
                    FROM voting_votes
                    WHERE session_id = %s
                    GROUP BY champion_name
                    ORDER BY SUM(points) DESC
                    LIMIT %s
                """, (last_session['id'], limit))
                
                return [row['champion_name'] for row in cur.fetchall()]
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
    
    # ==================== HELP EMBED OPERATIONS ====================
    
    def save_help_embed(self, guild_id: int, channel_id: int, message_id: int):
        """Save help embed message ID"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO help_embed (guild_id, channel_id, message_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (guild_id, channel_id) 
                    DO UPDATE SET message_id = EXCLUDED.message_id, last_updated = NOW()
                """, (guild_id, channel_id, message_id))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def get_help_embed(self, guild_id: int, channel_id: int) -> Optional[int]:
        """Get help embed message ID"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT message_id FROM help_embed
                    WHERE guild_id = %s AND channel_id = %s
                """, (guild_id, channel_id))
                result = cur.fetchone()
                return result[0] if result else None
        finally:
            self.return_connection(conn)
    
    # ==================== RANK EMBED OPERATIONS ====================
    
    def save_rank_embed(self, guild_id: int, channel_id: int, message_id: int):
        """Save rank embed message ID"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO rank_embed (guild_id, channel_id, message_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (guild_id, channel_id) 
                    DO UPDATE SET message_id = EXCLUDED.message_id, last_updated = NOW()
                """, (guild_id, channel_id, message_id))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def get_rank_embed(self, guild_id: int, channel_id: int) -> Optional[int]:
        """Get rank embed message ID"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT message_id FROM rank_embed
                    WHERE guild_id = %s AND channel_id = %s
                """, (guild_id, channel_id))
                result = cur.fetchone()
                return result[0] if result else None
        finally:
            self.return_connection(conn)

    # ==================== BETTING OPERATIONS ====================

    def create_bet(self, game_id: int, platform: str, match_id: str,
                   red_team: dict, blue_team: dict, red_odds: float,
                   blue_odds: float, channel_id: int, message_id: int) -> int:
        """Insert a new bet and return bet id"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO betting_bets
                    (game_id, platform, match_id, red_team, blue_team, red_odds, blue_odds, status, channel_id, message_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s, %s)
                    RETURNING id
                """, (game_id, platform, match_id, json.dumps(red_team), json.dumps(blue_team), red_odds, blue_odds, channel_id, message_id))
                bet_id = cur.fetchone()[0]
                conn.commit()
                return bet_id
        finally:
            self.return_connection(conn)

    def get_open_bet(self) -> Optional[dict]:
        """Get latest open bet"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, game_id, platform, match_id, red_team, blue_team, red_odds, blue_odds, channel_id, message_id, created_at
                    FROM betting_bets
                    WHERE status = 'open'
                    ORDER BY created_at DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    'id': row[0], 'game_id': row[1], 'platform': row[2], 'match_id': row[3],
                    'red_team': row[4], 'blue_team': row[5], 'red_odds': row[6], 'blue_odds': row[7],
                    'channel_id': row[8], 'message_id': row[9], 'created_at': row[10]
                }
        finally:
            self.return_connection(conn)

    def add_prediction(self, bet_id: int, user_id: int, side: str, amount: int):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO betting_predictions (bet_id, user_id, side, amount, result)
                    VALUES (%s, %s, %s, %s, 'pending')
                """, (bet_id, user_id, side, amount))
                conn.commit()
        finally:
            self.return_connection(conn)

    def update_bet_winner(self, bet_id: int, winner: str):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE betting_bets
                    SET status = 'settled', winner = %s, closed_at = NOW()
                    WHERE id = %s
                """, (winner, bet_id))
                conn.commit()
        finally:
            self.return_connection(conn)

    def settle_predictions(self, bet_id: int, winner: str, red_odds: float, blue_odds: float):
        """Compute payouts for predictions"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE betting_predictions
                    SET result = CASE WHEN side = %s THEN 'win' ELSE 'lose' END,
                        payout = CASE WHEN side = %s THEN amount * (CASE WHEN %s = 'red' THEN %s ELSE %s END) ELSE 0 END
                    WHERE bet_id = %s
                """, (winner, winner, winner, red_odds, blue_odds, bet_id))
                conn.commit()
        finally:
            self.return_connection(conn)

    def get_leaderboard(self, limit: int = 10) -> list:
        """Return top users by total payout - total stake"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT user_id,
                           COALESCE(SUM(CASE WHEN result = 'win' THEN payout ELSE 0 END),0) -
                           COALESCE(SUM(CASE WHEN result IN ('win','lose') THEN amount ELSE 0 END),0) AS profit,
                           COUNT(*) AS bets,
                           SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) AS wins
                    FROM betting_predictions
                    GROUP BY user_id
                    ORDER BY profit DESC
                    LIMIT %s
                """, (limit,))
                return cur.fetchall()
        finally:
            self.return_connection(conn)

    def save_leaderboard_embed(self, guild_id: int, channel_id: int, message_id: int):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO betting_leaderboard (guild_id, channel_id, message_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (guild_id, channel_id)
                    DO UPDATE SET message_id = EXCLUDED.message_id, last_updated = NOW()
                """, (guild_id, channel_id, message_id))
                conn.commit()
        finally:
            self.return_connection(conn)

    def get_leaderboard_embed(self, guild_id: int, channel_id: int) -> Optional[int]:
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT message_id FROM betting_leaderboard
                    WHERE guild_id = %s AND channel_id = %s
                """, (guild_id, channel_id))
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            self.return_connection(conn)
    
    # ==================== BAN SYSTEM ====================
    
    def add_ban(self, user_id: int, guild_id: int, moderator_id: int, reason: str, 
                duration_minutes: Optional[int] = None) -> int:
        """Add a new ban. Returns ban ID."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                expires_at = None
                if duration_minutes:
                    expires_at = datetime.now() + timedelta(minutes=duration_minutes)
                
                cur.execute("""
                    INSERT INTO user_bans 
                    (user_id, guild_id, moderator_id, reason, duration_minutes, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (user_id, guild_id, moderator_id, reason, duration_minutes, expires_at))
                
                ban_id = cur.fetchone()[0]
                conn.commit()
                return ban_id
        finally:
            self.return_connection(conn)
    
    def get_active_ban(self, user_id: int, guild_id: int) -> Optional[Dict]:
        """Get active ban for user in guild"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM user_bans 
                    WHERE user_id = %s AND guild_id = %s AND active = TRUE
                    AND (expires_at IS NULL OR expires_at > NOW())
                    ORDER BY banned_at DESC
                    LIMIT 1
                """, (user_id, guild_id))
                return cur.fetchone()
        finally:
            self.return_connection(conn)
    
    def unban_user(self, ban_id: int, moderator_id: int, reason: str = None):
        """Unban a user"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE user_bans 
                    SET active = FALSE, unbanned_at = NOW(), 
                        unbanned_by = %s, unban_reason = %s
                    WHERE id = %s
                """, (moderator_id, reason, ban_id))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def get_all_active_bans(self, guild_id: int) -> List[Dict]:
        """Get all active bans for a guild"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM user_bans 
                    WHERE guild_id = %s AND active = TRUE
                    AND (expires_at IS NULL OR expires_at > NOW())
                    ORDER BY banned_at DESC
                """, (guild_id,))
                return cur.fetchall()
        finally:
            self.return_connection(conn)
    
    def add_appeal(self, ban_id: int, user_id: int, appeal_text: str) -> int:
        """Submit a ban appeal. Returns appeal ID."""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ban_appeals (ban_id, user_id, appeal_text)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (ban_id, user_id, appeal_text))
                
                appeal_id = cur.fetchone()[0]
                conn.commit()
                return appeal_id
        finally:
            self.return_connection(conn)
    
    def get_pending_appeals(self, guild_id: int) -> List[Dict]:
        """Get all pending appeals for a guild"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT ba.*, ub.guild_id, ub.reason as ban_reason, 
                           ub.banned_at, ub.expires_at
                    FROM ban_appeals ba
                    JOIN user_bans ub ON ba.ban_id = ub.id
                    WHERE ub.guild_id = %s AND ba.status = 'pending'
                    ORDER BY ba.submitted_at ASC
                """, (guild_id,))
                return cur.fetchall()
        finally:
            self.return_connection(conn)
    
    def get_user_appeals(self, user_id: int, guild_id: int) -> List[Dict]:
        """Get all appeals by a user in a guild"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT ba.*, ub.guild_id, ub.reason as ban_reason
                    FROM ban_appeals ba
                    JOIN user_bans ub ON ba.ban_id = ub.id
                    WHERE ba.user_id = %s AND ub.guild_id = %s
                    ORDER BY ba.submitted_at DESC
                """, (user_id, guild_id))
                return cur.fetchall()
        finally:
            self.return_connection(conn)
    
    def review_appeal(self, appeal_id: int, reviewer_id: int, status: str, notes: str = None):
        """Review a ban appeal (approve or deny)"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE ban_appeals 
                    SET status = %s, reviewed_by = %s, reviewed_at = NOW(), review_notes = %s
                    WHERE id = %s
                """, (status, reviewer_id, notes, appeal_id))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def expire_old_bans(self):
        """Mark expired bans as inactive"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE user_bans 
                    SET active = FALSE
                    WHERE active = TRUE 
                    AND expires_at IS NOT NULL 
                    AND expires_at <= NOW()
                """)
                expired_count = cur.rowcount
                conn.commit()
                return expired_count
        finally:
            self.return_connection(conn)
    
    # ==================== LOLDLE OPERATIONS ====================
    
    def get_loldle_stats(self, user_id: int, guild_id: int) -> Optional[Dict]:
        """Get Loldle stats for a user"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM loldle_stats
                    WHERE user_id = %s AND guild_id = %s
                """, (user_id, guild_id))
                return cur.fetchone()
        finally:
            self.return_connection(conn)
    
    def update_loldle_stats(self, user_id: int, guild_id: int, won: bool, guesses: int):
        """Update Loldle statistics for a user"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Get or create stats
                cur.execute("""
                    INSERT INTO loldle_stats (user_id, guild_id, total_games, total_wins, total_guesses, current_streak, last_win_date)
                    VALUES (%s, %s, 0, 0, 0, 0, NULL)
                    ON CONFLICT (user_id, guild_id) DO NOTHING
                """, (user_id, guild_id))
                
                # Update stats
                if won:
                    cur.execute("""
                        UPDATE loldle_stats
                        SET total_games = total_games + 1,
                            total_wins = total_wins + 1,
                            total_guesses = total_guesses + %s,
                            current_streak = current_streak + 1,
                            best_streak = GREATEST(best_streak, current_streak + 1),
                            last_win_date = CURRENT_DATE,
                            updated_at = NOW()
                        WHERE user_id = %s AND guild_id = %s
                    """, (guesses, user_id, guild_id))
                else:
                    cur.execute("""
                        UPDATE loldle_stats
                        SET total_games = total_games + 1,
                            total_guesses = total_guesses + %s,
                            current_streak = 0,
                            updated_at = NOW()
                        WHERE user_id = %s AND guild_id = %s
                    """, (guesses, user_id, guild_id))
                
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def get_loldle_daily_game(self, guild_id: int, mode: str = 'classic') -> Optional[Dict]:
        """Get today's Loldle game for a guild"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM loldle_daily_games
                    WHERE guild_id = %s AND game_date = CURRENT_DATE AND mode = %s
                """, (guild_id, mode))
                return cur.fetchone()
        finally:
            self.return_connection(conn)
    
    def create_loldle_daily_game(self, guild_id: int, champion_name: str, mode: str = 'classic') -> int:
        """Create a new daily Loldle game"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO loldle_daily_games (guild_id, game_date, champion_name, mode)
                    VALUES (%s, CURRENT_DATE, %s, %s)
                    ON CONFLICT (guild_id, game_date, mode) 
                    DO UPDATE SET champion_name = EXCLUDED.champion_name
                    RETURNING id
                """, (guild_id, champion_name, mode))
                game_id = cur.fetchone()[0]
                conn.commit()
                return game_id
        finally:
            self.return_connection(conn)
    
    def get_loldle_player_progress(self, game_id: int, user_id: int) -> Optional[Dict]:
        """Get player's progress for a specific game"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM loldle_player_progress
                    WHERE game_id = %s AND user_id = %s
                """, (game_id, user_id))
                return cur.fetchone()
        finally:
            self.return_connection(conn)
    
    def update_loldle_player_progress(self, game_id: int, user_id: int, guesses: list, solved: bool):
        """Update player's progress for a game"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                if solved:
                    cur.execute("""
                        INSERT INTO loldle_player_progress (game_id, user_id, guesses, solved, attempts, solved_at)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (game_id, user_id)
                        DO UPDATE SET guesses = EXCLUDED.guesses, solved = TRUE, attempts = EXCLUDED.attempts, solved_at = NOW()
                    """, (game_id, user_id, guesses, solved, len(guesses)))
                else:
                    cur.execute("""
                        INSERT INTO loldle_player_progress (game_id, user_id, guesses, solved, attempts)
                        VALUES (%s, %s, %s, FALSE, %s)
                        ON CONFLICT (game_id, user_id)
                        DO UPDATE SET guesses = EXCLUDED.guesses, attempts = EXCLUDED.attempts
                    """, (game_id, user_id, guesses, len(guesses)))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def get_loldle_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict]:
        """Get Loldle leaderboard for a guild"""
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        user_id,
                        total_games,
                        total_wins,
                        total_guesses,
                        best_streak,
                        current_streak,
                        CASE 
                            WHEN total_wins > 0 THEN ROUND(total_guesses::numeric / total_wins, 2)
                            ELSE 999
                        END as avg_guesses,
                        CASE 
                            WHEN total_games > 0 THEN ROUND((total_wins::numeric / total_games * 100), 1)
                            ELSE 0
                        END as win_rate
                    FROM loldle_stats
                    WHERE guild_id = %s AND total_games > 0
                    ORDER BY avg_guesses ASC, total_wins DESC
                    LIMIT %s
                """, (guild_id, limit))
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


# ==================== PRO STATS OPERATIONS ====================

class ProStatsDatabase:
    """Database operations for professional teams and players"""
    
    def __init__(self, database: Database):
        self.db = database
    
    def add_or_update_team(self, name: str, tag: str, rank: int, rating: int, rating_change: int, url: str) -> int:
        """Add or update a professional team"""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO pro_teams (name, tag, rank, rating, rating_change, url, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (tag) DO UPDATE SET
                        name = EXCLUDED.name,
                        rank = EXCLUDED.rank,
                        rating = EXCLUDED.rating,
                        rating_change = EXCLUDED.rating_change,
                        url = EXCLUDED.url,
                        last_updated = NOW()
                    RETURNING id
                """, (name, tag, rank, rating, rating_change, url))
                team_id = cur.fetchone()[0]
                conn.commit()
                return team_id
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error adding/updating team {tag}: {e}")
            raise
        finally:
            self.db.return_connection(conn)
    
    def add_or_update_player(self, name: str, role: str, team_tag: str = None, **stats) -> int:
        """Add or update a professional player"""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                # Get team_id if team_tag provided
                team_id = None
                if team_tag:
                    cur.execute("SELECT id FROM pro_teams WHERE tag = %s", (team_tag,))
                    result = cur.fetchone()
                    if result:
                        team_id = result[0]
                
                cur.execute("""
                    INSERT INTO pro_players 
                    (name, role, team_id, kda, avg_kills, avg_deaths, avg_assists, rating, 
                     win_rate, games_played, cs_per_min, url, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (name) DO UPDATE SET
                        role = EXCLUDED.role,
                        team_id = EXCLUDED.team_id,
                        kda = EXCLUDED.kda,
                        avg_kills = EXCLUDED.avg_kills,
                        avg_deaths = EXCLUDED.avg_deaths,
                        avg_assists = EXCLUDED.avg_assists,
                        rating = EXCLUDED.rating,
                        win_rate = EXCLUDED.win_rate,
                        games_played = EXCLUDED.games_played,
                        cs_per_min = EXCLUDED.cs_per_min,
                        url = EXCLUDED.url,
                        last_updated = NOW()
                    RETURNING id
                """, (
                    name, role, team_id,
                    stats.get('kda'), stats.get('avg_kills'), stats.get('avg_deaths'),
                    stats.get('avg_assists'), stats.get('rating'), stats.get('win_rate'),
                    stats.get('games_played'), stats.get('cs_per_min'), stats.get('url')
                ))
                player_id = cur.fetchone()[0]
                conn.commit()
                return player_id
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error adding/updating player {name}: {e}")
            raise
        finally:
            self.db.return_connection(conn)
    
    def add_player_champion(self, player_name: str, champion: str, games: int, kda: float, win_rate: float):
        """Add or update player champion statistics"""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                # Get player_id
                cur.execute("SELECT id FROM pro_players WHERE name = %s", (player_name,))
                result = cur.fetchone()
                if not result:
                    logger.warning(f"⚠️ Player {player_name} not found for champion stats")
                    return
                player_id = result[0]
                
                cur.execute("""
                    INSERT INTO pro_player_champions (player_id, champion, games, kda, win_rate, last_updated)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (player_id, champion) DO UPDATE SET
                        games = EXCLUDED.games,
                        kda = EXCLUDED.kda,
                        win_rate = EXCLUDED.win_rate,
                        last_updated = NOW()
                """, (player_id, champion, games, kda, win_rate))
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error adding player champion: {e}")
            raise
        finally:
            self.db.return_connection(conn)
    
    def get_team_by_tag(self, tag: str) -> Optional[Dict]:
        """Get team information by tag"""
        conn = self.db.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM pro_teams WHERE UPPER(tag) = UPPER(%s)
                """, (tag,))
                return cur.fetchone()
        finally:
            self.db.return_connection(conn)
    
    def get_team_roster(self, tag: str) -> List[Dict]:
        """Get all players in a team"""
        conn = self.db.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT p.* FROM pro_players p
                    JOIN pro_teams t ON p.team_id = t.id
                    WHERE UPPER(t.tag) = UPPER(%s)
                    ORDER BY 
                        CASE p.role
                            WHEN 'Top' THEN 1
                            WHEN 'Jungle' THEN 2
                            WHEN 'Mid' THEN 3
                            WHEN 'ADC' THEN 4
                            WHEN 'Support' THEN 5
                            ELSE 6
                        END
                """, (tag,))
                return cur.fetchall()
        finally:
            self.db.return_connection(conn)
    
    def get_player_by_name(self, name: str) -> Optional[Dict]:
        """Get player information by name"""
        conn = self.db.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT p.*, t.name as team_name, t.tag as team_tag
                    FROM pro_players p
                    LEFT JOIN pro_teams t ON p.team_id = t.id
                    WHERE LOWER(p.name) = LOWER(%s)
                """, (name,))
                return cur.fetchone()
        finally:
            self.db.return_connection(conn)
    
    def get_player_champions(self, name: str) -> List[Dict]:
        """Get player's champion statistics"""
        conn = self.db.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT c.* FROM pro_player_champions c
                    JOIN pro_players p ON c.player_id = p.id
                    WHERE LOWER(p.name) = LOWER(%s)
                    ORDER BY c.games DESC
                    LIMIT 10
                """, (name,))
                return cur.fetchall()
        finally:
            self.db.return_connection(conn)
    
    def get_top_teams(self, limit: int = 10) -> List[Dict]:
        """Get top ranked teams"""
        conn = self.db.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM pro_teams
                    WHERE rank IS NOT NULL
                    ORDER BY rank ASC
                    LIMIT %s
                """, (limit,))
                return cur.fetchall()
        finally:
            self.db.return_connection(conn)
    
    def search_teams(self, query: str, limit: int = 5) -> List[Dict]:
        """Search teams by name or tag"""
        conn = self.db.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM pro_teams
                    WHERE LOWER(name) LIKE LOWER(%s) OR LOWER(tag) LIKE LOWER(%s)
                    ORDER BY rank ASC NULLS LAST
                    LIMIT %s
                """, (f'%{query}%', f'%{query}%', limit))
                return cur.fetchall()
        finally:
            self.db.return_connection(conn)
    
    def search_players(self, query: str, limit: int = 5) -> List[Dict]:
        """Search players by name"""
        conn = self.db.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT p.*, t.name as team_name, t.tag as team_tag
                    FROM pro_players p
                    LEFT JOIN pro_teams t ON p.team_id = t.id
                    WHERE LOWER(p.name) LIKE LOWER(%s)
                    LIMIT %s
                """, (f'%{query}%', limit))
                return cur.fetchall()
        finally:
            self.db.return_connection(conn)


def get_pro_stats_db() -> ProStatsDatabase:
    """Get ProStatsDatabase instance"""
    return ProStatsDatabase(get_db())

