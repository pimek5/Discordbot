"""
Import scraped pros JSON file to Railway database
Run this with Railway DATABASE_URL
"""

import json
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

def import_from_json(json_file='scraped_pros_advanced.json'):
    """Import players from JSON to database"""
    
    print(f"📂 Loading {json_file}...")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    players = data.get('players', [])
    print(f"  Found {len(players)} players in JSON")
    
    if not players:
        print("  ⚠️ No players to import")
        return
    
    if not DATABASE_URL:
        print("  ❌ DATABASE_URL not set! Set it in .env file")
        return
    
    print(f"\n💾 Connecting to database...")
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Create table
        print("  Creating table if not exists...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tracked_pros (
                id SERIAL PRIMARY KEY,
                player_name TEXT NOT NULL UNIQUE,
                accounts JSONB DEFAULT '[]'::jsonb,
                source TEXT,
                team TEXT,
                role TEXT,
                region TEXT,
                enabled BOOLEAN DEFAULT true,
                last_updated TIMESTAMP DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_tracked_pros_player_name 
            ON tracked_pros(player_name)
        """)
        
        conn.commit()
        print("  ✅ Table ready")
        
        added = 0
        updated = 0
        skipped = 0
        
        for player in players:
            try:
                name = player.get('name')
                accounts = player.get('accounts', [])
                
                if not name or not accounts:
                    skipped += 1
                    continue
                
                # Check if exists
                cur.execute("SELECT id, accounts FROM tracked_pros WHERE player_name = %s", (name,))
                existing = cur.fetchone()
                
                if existing:
                    # Merge accounts
                    existing_accounts = existing[1] if existing[1] else []
                    all_accounts = list(set(existing_accounts + accounts))
                    
                    cur.execute("""
                        UPDATE tracked_pros 
                        SET accounts = %s,
                            source = %s,
                            team = COALESCE(%s, team),
                            role = COALESCE(%s, role),
                            region = COALESCE(%s, region),
                            last_updated = NOW()
                        WHERE player_name = %s
                    """, (
                        json.dumps(all_accounts),
                        player.get('source'),
                        player.get('team'),
                        player.get('role'),
                        player.get('region'),
                        name
                    ))
                    updated += 1
                    print(f"  🔄 Updated: {name} ({len(all_accounts)} accounts)")
                else:
                    # Insert new
                    cur.execute("""
                        INSERT INTO tracked_pros 
                        (player_name, accounts, source, team, role, region)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        name,
                        json.dumps(accounts),
                        player.get('source'),
                        player.get('team'),
                        player.get('role'),
                        player.get('region')
                    ))
                    added += 1
                    print(f"  ✅ Added: {name} ({len(accounts)} accounts)")
                
                # Commit every 5 players
                if (added + updated) % 5 == 0:
                    conn.commit()
            
            except Exception as e:
                print(f"  ⚠️ Error with {player.get('name', 'unknown')}: {e}")
                conn.rollback()
        
        conn.commit()
        
        # Show results
        print(f"\n📊 IMPORT COMPLETE")
        print(f"   • Added: {added}")
        print(f"   • Updated: {updated}")
        print(f"   • Skipped: {skipped}")
        
        # Show total
        cur.execute("SELECT COUNT(*) FROM tracked_pros WHERE enabled = true")
        total = cur.fetchone()[0]
        print(f"   • Total active: {total}")
        
        # Show sample
        print(f"\n📋 Sample from database:")
        cur.execute("""
            SELECT player_name, jsonb_array_length(accounts) as num_accounts, team, role
            FROM tracked_pros
            ORDER BY player_name
            LIMIT 10
        """)
        
        for row in cur.fetchall():
            print(f"   • {row[0]}: {row[1]} accounts | {row[2] or 'No team'} | {row[3] or 'No role'}")
        
        cur.close()
        conn.close()
        print(f"\n✅ Done!")
        
    except Exception as e:
        print(f"❌ Database error: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("IMPORT SCRAPED PROS TO DATABASE")
    print("=" * 60)
    print()
    
    import_from_json()
