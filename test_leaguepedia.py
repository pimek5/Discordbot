"""
Test Leaguepedia scraper directly
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tracker'))

from HEXBET.leaguepedia_scraper import (
    fetch_leaguepedia_player,
    parse_soloqueue_ids,
    load_major_pro_players,
    LEAGUEPEDIA_CACHE
)

async def test_leaguepedia():
    print("="*60)
    print("🔍 Testing Leaguepedia Scraper")
    print("="*60)
    
    # Test fetching Faker
    print("\n⏳ Fetching Faker from Leaguepedia...")
    faker_data = await fetch_leaguepedia_player("Faker")
    
    if faker_data:
        print(f"✅ Faker data retrieved:")
        print(f"   Name: {faker_data['name']}")
        print(f"   Team: {faker_data.get('team', 'N/A')}")
        print(f"   Is Pro: {faker_data.get('is_pro', False)}")
        print(f"   Is Streamer: {faker_data.get('is_streamer', False)}")
        print(f"   Accounts: {faker_data.get('accounts', [])}")
    else:
        print("❌ Failed to fetch Faker data")
    
    # Load all major players
    print("\n⏳ Loading major pro players...")
    await load_major_pro_players()
    
    print(f"\n📊 Loaded {len(LEAGUEPEDIA_CACHE['pro'])} pro accounts")
    print(f"📊 Loaded {len(LEAGUEPEDIA_CACHE['streamer'])} streamer accounts")
    
    print("\n🎯 Sample pro accounts:")
    for i, (account, info) in enumerate(list(LEAGUEPEDIA_CACHE['pro'].items())[:5]):
        print(f"   {i+1}. {account} → {info['name']} ({info.get('team', 'N/A')})")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    asyncio.run(test_leaguepedia())
