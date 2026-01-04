"""
Test PRO/STRM badge system
"""
import asyncio
import sys
import os

# Add tracker to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tracker'))

from HEXBET.pro_players import (
    load_pro_players_from_api,
    is_pro_player,
    is_streamer_player,
    get_player_badge_emoji,
    LEAGUEPEDIA_AVAILABLE
)

async def test_pro_system():
    print("="*60)
    print("🔍 Testing PRO/STRM Badge System")
    print("="*60)
    
    print(f"\n📊 Leaguepedia Available: {LEAGUEPEDIA_AVAILABLE}")
    
    # Load pro players
    print("\n⏳ Loading pro players database...")
    try:
        await load_pro_players_from_api()
        print("✅ Pro players loaded successfully")
    except Exception as e:
        print(f"❌ Error loading: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test known players
    test_players = [
        "Faker#KR1",
        "Hide on bush#KR1",
        "Chovy#KR1",
        "Caps#EUW1",
        "Agurin#EUW1",
        "RandomPlayer#1234"
    ]
    
    print("\n" + "="*60)
    print("🎯 Testing Player Recognition")
    print("="*60)
    
    for player in test_players:
        is_pro = is_pro_player(player)
        is_streamer = is_streamer_player(player)
        badge = get_player_badge_emoji(player)
        
        print(f"\n👤 {player}")
        print(f"   PRO: {is_pro}")
        print(f"   STRM: {is_streamer}")
        print(f"   Badge: {badge or 'None'}")
    
    print("\n" + "="*60)
    print("✅ Test Complete")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_pro_system())
