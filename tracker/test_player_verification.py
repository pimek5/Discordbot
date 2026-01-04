"""
Test player verification system locally
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import asyncio
import logging
from HEXBET.lolpros_scraper import fetch_lolpros_player, check_and_verify_player
from tracker_database import TrackerDatabase

logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more details
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_player(riot_id: str):
    """Test fetching a player from lolpros.gg"""
    print(f"\n{'='*60}")
    print(f"Testing player: {riot_id}")
    print(f"{'='*60}\n")
    
    # Test 1: Direct fetch from lolpros.gg
    print("🔍 Step 1: Fetching from lolpros.gg...")
    player_data = await fetch_lolpros_player(riot_id)
    
    if player_data:
        print("\n✅ Player found on lolpros.gg!")
        print(f"   Name: {player_data.get('player_name')}")
        print(f"   Type: {player_data.get('player_type')}")
        print(f"   Team: {player_data.get('team', 'N/A')}")
        print(f"   Platform: {player_data.get('platform', 'N/A')}")
        print(f"   LOLPros URL: {player_data.get('lolpros_url')}")
        print(f"   Leaguepedia: {player_data.get('leaguepedia_url', 'N/A')}")
    else:
        print("\n❌ Player not found on lolpros.gg")
        return
    
    # Test 2: Check database integration
    print("\n🔍 Step 2: Testing database integration...")
    db = TrackerDatabase()
    
    # Check if already in database
    cached = db.get_verified_player(riot_id)
    if cached:
        print(f"   ℹ️  Player already in database:")
        print(f"      Last seen: {cached.get('last_seen')}")
        print(f"      Last checked: {cached.get('last_checked')}")
    else:
        print("   ℹ️  Player not yet in database")
    
    # Test 3: Full verification flow
    print("\n🔍 Step 3: Testing full verification flow...")
    badge = await check_and_verify_player(riot_id, db)
    
    if badge:
        print(f"\n✅ Badge assigned: {badge}")
    else:
        print("\n❌ No badge assigned")
    
    # Test 4: Verify database entry
    print("\n🔍 Step 4: Verifying database entry...")
    cached_after = db.get_verified_player(riot_id)
    if cached_after:
        print("   ✅ Player successfully saved to database!")
        print(f"      Player name: {cached_after.get('player_name')}")
        print(f"      Type: {cached_after.get('player_type')}")
        print(f"      Verified at: {cached_after.get('verified_at')}")
    else:
        print("   ⚠️  Player not in database after verification")
    
    print(f"\n{'='*60}")
    print("Test complete!")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    import sys
    
    # Get player from command line or use default
    if len(sys.argv) > 1:
        test_riot_id = sys.argv[1]
    else:
        # Default: test with Faker
        test_riot_id = "hide on bush#kr1"
    
    print("\n🚀 Starting player verification test...")
    asyncio.run(test_player(test_riot_id))
