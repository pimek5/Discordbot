"""
Fix PUUID column length in league_accounts table
PUUID is 78 characters but column was too short, causing truncation
Run this with: railway run python fix_puuid_column.py
"""
import psycopg2.pool
import os

def fix_puuid_column():
    """Alter league_accounts.puuid column to support full PUUID length"""
    
    db_url = "postgresql://postgres:VeNZZTCabRnROGyGHQbVSBcLlIIhYDuB@shinkansen.proxy.rlwy.net:23983/railway"
    
    print("🔧 Connecting to database...")
    conn = psycopg2.pool.SimpleConnectionPool(1, 1, db_url).getconn()
    
    try:
        cur = conn.cursor()
        
        # Check current column size
        cur.execute("""
            SELECT character_maximum_length 
            FROM information_schema.columns 
            WHERE table_name = 'league_accounts' 
            AND column_name = 'puuid'
        """)
        result = cur.fetchone()
        if result:
            current_length = result[0]
            print(f"📊 Current PUUID column length: {current_length}")
        else:
            print("⚠️ Could not determine current column length")
        
        # Alter column to VARCHAR(100) to support full PUUID (78 chars + buffer)
        print("🔧 Altering puuid column to VARCHAR(100)...")
        cur.execute("""
            ALTER TABLE league_accounts 
            ALTER COLUMN puuid TYPE VARCHAR(100)
        """)
        
        conn.commit()
        print("✅ Successfully altered puuid column to VARCHAR(100)")
        
        # Count accounts with NULL or short PUUID
        cur.execute("""
            SELECT COUNT(*) 
            FROM league_accounts 
            WHERE puuid IS NULL OR LENGTH(puuid) < 78
        """)
        count = cur.fetchone()[0]
        print(f"📊 Accounts needing PUUID update: {count}")
        
        if count > 0:
            print("ℹ️ Run /fixaccounts command in Discord to update PUUIDs")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()
        print("🔒 Database connection closed")

if __name__ == "__main__":
    fix_puuid_column()
