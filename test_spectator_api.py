"""
Test Spectator API to check available fields
"""
import asyncio
import os
from tracker.riot_api import RiotAPI
import json

async def test_spectator():
    api_key = os.getenv('RIOT_API_KEY')
    if not api_key:
        print("❌ RIOT_API_KEY not set")
        return
    
    riot_api = RiotAPI(api_key)
    
    # Test with known high-elo player (Faker's account)
    test_puuids = [
        # Add some known PUUIDs here
    ]
    
    print("🔍 Testing Spectator API fields...\n")
    
    # Try to find any active game
    regions = ['kr', 'euw', 'na']
    
    for region in regions:
        print(f"\n📍 Checking {region.upper()}...")
        # You would need actual PUUIDs here
        # This is just to show the structure
        
    print("\n" + "="*60)
    print("Spectator-V5 API returns:")
    print("="*60)
    
    example_participant = {
        "championId": 266,
        "perks": {
            "perkIds": [8021, 8009, 9104, 8014, 8237, 8236, 5005, 5008, 5002],
            "perkStyle": 8000,
            "perkSubStyle": 8200
        },
        "profileIconId": 5373,
        "bot": False,
        "teamId": 100,
        "summonerName": "Hide on bush",
        "summonerId": "...",
        "puuid": "...",
        "spell1Id": 4,
        "spell2Id": 11,
        "gameCustomizationObjects": []
    }
    
    print(json.dumps(example_participant, indent=2))
    print("\n⚠️ Note: Live game API does NOT include:")
    print("  - Items (itemId0-6)")
    print("  - Gold, CS, KDA")
    print("  - teamPosition")
    print("\n✅ Available for role detection:")
    print("  - spell1Id, spell2Id (Smite = 11)")
    print("  - championId (can hint at role)")
    print("  - gameCustomizationObjects (might include starting items?)")

if __name__ == "__main__":
    asyncio.run(test_spectator())
