"""
Migration script to fix encrypted PUUIDs in database
Fetches fresh PUUIDs from Riot API using riot_id + tagline

Run on Railway:
railway run python migrate_puuids.py
"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_db
from riot_api import RiotAPI

async def migrate_puuids():
    """Update all encrypted PUUIDs to plain text format"""
    
    # Get API key
    api_key = os.getenv('RIOT_API_KEY')
    if not api_key:
        print("❌ RIOT_API_KEY not found in environment!")
        return
    
    riot_api = RiotAPI(api_key)
    db = get_db()
    
    print("=" * 80)
    print("🔄 PUUID MIGRATION - Fixing encrypted PUUIDs")
    print("=" * 80)
    print()
    
    # Get all users
    cursor = db.conn.cursor()
    cursor.execute("SELECT id, discord_id FROM users")
    users = cursor.fetchall()
    
    print(f"📊 Found {len(users)} users in database")
    print()
    
    total_accounts = 0
    updated_accounts = 0
    failed_accounts = 0
    
    for user in users:
        user_id = user[0]
        discord_id = user[1]
        
        # Get all accounts for this user
        cursor.execute("""
            SELECT id, riot_id_game_name, riot_id_tagline, region, puuid 
            FROM league_accounts 
            WHERE user_id = %s
        """, (user_id,))
        accounts = cursor.fetchall()
        
        if not accounts:
            continue
        
        print(f"👤 User ID {user_id} (Discord: {discord_id})")
        print(f"   Accounts: {len(accounts)}")
        
        for account in accounts:
            account_id, game_name, tagline, region, old_puuid = account
            total_accounts += 1
            
            if not game_name or not tagline:
                print(f"   ⚠️  Account {account_id}: Missing riot_id (game_name: {game_name}, tagline: {tagline})")
                failed_accounts += 1
                continue
            
            print(f"   🔍 Fetching PUUID for {game_name}#{tagline}...")
            
            # Fetch fresh PUUID from Riot API
            account_data = await riot_api.get_account_by_riot_id(game_name, tagline, region)
            
            if account_data and 'puuid' in account_data:
                new_puuid = account_data['puuid']
                
                # Check if it's different
                if new_puuid != old_puuid:
                    # Update in database
                    cursor.execute("""
                        UPDATE league_accounts 
                        SET puuid = %s 
                        WHERE id = %s
                    """, (new_puuid, account_id))
                    db.conn.commit()
                    
                    print(f"   ✅ Updated PUUID for {game_name}#{tagline}")
                    print(f"      Old: {old_puuid[:20]}...")
                    print(f"      New: {new_puuid[:20]}...")
                    updated_accounts += 1
                else:
                    print(f"   ℹ️  PUUID already correct for {game_name}#{tagline}")
            else:
                print(f"   ❌ Failed to fetch PUUID for {game_name}#{tagline}")
                failed_accounts += 1
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)
        
        print()
    
    print("=" * 80)
    print("📊 MIGRATION SUMMARY")
    print("=" * 80)
    print(f"Total accounts processed: {total_accounts}")
    print(f"✅ Successfully updated: {updated_accounts}")
    print(f"❌ Failed to update: {failed_accounts}")
    print(f"ℹ️  Already correct: {total_accounts - updated_accounts - failed_accounts}")
    print()
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(migrate_puuids())
