"""
LFG Database Module
===================
Handles all database operations for the LFG (Looking For Group) system.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    """Create and return a database connection."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        raise

def initialize_lfg_database():
    """Initialize LFG tables if they don't exist."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Read schema file
        schema_path = os.path.join(os.path.dirname(__file__), 'lfg_schema.sql')
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = f.read()
        
        # Execute schema
        cur.execute(schema)
        conn.commit()
        logger.info("✅ LFG database initialized")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize LFG database: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


# ================================
#       PROFILE OPERATIONS
# ================================

def get_lfg_profile(user_id: int) -> Optional[Dict[str, Any]]:
    """Get LFG profile for a user."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("""
            SELECT * FROM lfg_profiles WHERE user_id = %s
        """, (user_id,))
        
        profile = cur.fetchone()
        
        if profile:
            # PostgreSQL JSONB fields are already Python lists/dicts, no need to parse
            profile = dict(profile)
            # Ensure lists exist (handle NULL values)
            profile['primary_roles'] = profile['primary_roles'] if profile['primary_roles'] is not None else []
            profile['secondary_roles'] = profile['secondary_roles'] if profile['secondary_roles'] is not None else []
            profile['top_champions'] = profile['top_champions'] if profile['top_champions'] is not None else []
        
        return profile
        
    except Exception as e:
        logger.error(f"❌ Failed to get LFG profile: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def create_lfg_profile(
    user_id: int,
    riot_id_game_name: str,
    riot_id_tagline: str,
    region: str,
    primary_roles: List[str],
    puuid: Optional[str] = None,
    profile_link: Optional[str] = None
) -> bool:
    """Create a new LFG profile."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO lfg_profiles 
            (user_id, riot_id_game_name, riot_id_tagline, puuid, region, primary_roles, profile_link)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) 
            DO UPDATE SET
                riot_id_game_name = EXCLUDED.riot_id_game_name,
                riot_id_tagline = EXCLUDED.riot_id_tagline,
                puuid = EXCLUDED.puuid,
                region = EXCLUDED.region,
                primary_roles = EXCLUDED.primary_roles,
                profile_link = EXCLUDED.profile_link,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, riot_id_game_name, riot_id_tagline, puuid, region, json.dumps(primary_roles), profile_link))
        
        conn.commit()
        logger.info(f"✅ Created/updated LFG profile for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to create LFG profile: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


def update_lfg_profile(user_id: int, **kwargs) -> bool:
    """Update LFG profile fields."""
    if not kwargs:
        return False
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Build update query dynamically
        set_clauses = []
        values = []
        
        for key, value in kwargs.items():
            # Convert lists to JSON strings for JSON columns
            if key in ['primary_roles', 'secondary_roles', 'top_champions'] and isinstance(value, list):
                value = json.dumps(value)
            
            set_clauses.append(f"{key} = %s")
            values.append(value)
        
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values.append(user_id)
        
        query = f"""
            UPDATE lfg_profiles
            SET {', '.join(set_clauses)}
            WHERE user_id = %s
        """
        
        cur.execute(query, values)
        conn.commit()
        
        logger.info(f"✅ Updated LFG profile for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to update LFG profile: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


def update_saved_description(user_id: int, description: str) -> bool:
    """Update the saved description for a user (used for future posts)."""
    conn = get_db_connection()
    if not conn:
        return False
    
    cur = conn.cursor()
    
    try:
        cur.execute("""
            UPDATE lfg_profiles
            SET description = %s, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
        """, (description, user_id))
        
        conn.commit()
        logger.info(f"✅ Updated saved description for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to update saved description: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


# ================================
#       LISTING OPERATIONS
# ================================

def create_lfg_listing(
    creator_user_id: int,
    queue_type: str,
    roles_needed: List[str],
    region: str,
    spots_available: int = 1,
    **kwargs
) -> Optional[int]:
    """Create a new LFG listing. Returns listing_id."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Default expiration: 6 hours
        expires_at = kwargs.get('expires_at', datetime.now() + timedelta(hours=6))
        
        cur.execute("""
            INSERT INTO lfg_listings
            (creator_user_id, queue_type, roles_needed, region, spots_available, 
             expires_at, title, description, min_rank, max_rank, voice_required, language)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING listing_id
        """, (
            creator_user_id,
            queue_type,
            json.dumps(roles_needed),
            region,
            spots_available,
            expires_at,
            kwargs.get('title'),
            kwargs.get('description'),
            kwargs.get('min_rank'),
            kwargs.get('max_rank'),
            kwargs.get('voice_required', False),
            kwargs.get('language', 'pl')
        ))
        
        listing_id = cur.fetchone()[0]
        conn.commit()
        
        logger.info(f"✅ Created LFG listing {listing_id}")
        return listing_id
        
    except Exception as e:
        logger.error(f"❌ Failed to create LFG listing: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


def get_active_listings(
    region: Optional[str] = None,
    queue_type: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Get active LFG listings with optional filters."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        query = """
            SELECT l.*, p.riot_id_game_name, p.riot_id_tagline, p.solo_rank, p.flex_rank
            FROM lfg_listings l
            JOIN lfg_profiles p ON l.creator_user_id = p.user_id
            WHERE l.status = 'active' AND l.expires_at > CURRENT_TIMESTAMP
        """
        params = []
        
        if region:
            query += " AND l.region = %s"
            params.append(region)
        
        if queue_type:
            query += " AND l.queue_type = %s"
            params.append(queue_type)
        
        query += " ORDER BY l.created_at DESC LIMIT %s"
        params.append(limit)
        
        cur.execute(query, params)
        listings = cur.fetchall()
        
        # Parse JSON fields
        result = []
        for listing in listings:
            listing = dict(listing)
            listing['roles_needed'] = json.loads(listing['roles_needed']) if listing['roles_needed'] else []
            result.append(listing)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Failed to get active listings: {e}")
        return []
    finally:
        cur.close()
        conn.close()


def update_listing_status(listing_id: int, status: str, message_id: Optional[int] = None) -> bool:
    """Update listing status."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if message_id:
            cur.execute("""
                UPDATE lfg_listings
                SET status = %s, message_id = %s
                WHERE listing_id = %s
            """, (status, message_id, listing_id))
        else:
            cur.execute("""
                UPDATE lfg_listings
                SET status = %s
                WHERE listing_id = %s
            """, (status, listing_id))
        
        conn.commit()
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to update listing status: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


def cleanup_expired_listings() -> int:
    """Mark expired listings as expired. Returns count of expired listings."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            UPDATE lfg_listings
            SET status = 'expired'
            WHERE status = 'active' AND expires_at <= CURRENT_TIMESTAMP
            RETURNING listing_id
        """)
        
        expired_count = cur.rowcount
        conn.commit()
        
        if expired_count > 0:
            logger.info(f"✅ Marked {expired_count} listings as expired")
        
        return expired_count
        
    except Exception as e:
        logger.error(f"❌ Failed to cleanup expired listings: {e}")
        conn.rollback()
        return 0
    finally:
        cur.close()
        conn.close()


def get_all_lfg_profiles(limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
    """Get all LFG profiles with optional pagination."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        query = """
            SELECT * FROM lfg_profiles
            ORDER BY created_at DESC
        """
        params = []
        
        if limit:
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])
        
        cur.execute(query, params)
        profiles = cur.fetchall()
        
        # PostgreSQL JSONB fields are already Python lists/dicts
        result = []
        for profile in profiles:
            profile = dict(profile)
            # Ensure lists exist (handle NULL values)
            profile['primary_roles'] = profile['primary_roles'] if profile['primary_roles'] is not None else []
            profile['secondary_roles'] = profile['secondary_roles'] if profile['secondary_roles'] is not None else []
            profile['top_champions'] = profile['top_champions'] if profile['top_champions'] is not None else []
            result.append(profile)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Failed to get all profiles: {e}")
        return []
    finally:
        cur.close()
        conn.close()


def get_lfg_profiles_count() -> int:
    """Get total count of LFG profiles."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT COUNT(*) FROM lfg_profiles")
        count = cur.fetchone()[0]
        return count
        
    except Exception as e:
        logger.error(f"❌ Failed to get profiles count: {e}")
        return 0
    finally:
        cur.close()
        conn.close()
