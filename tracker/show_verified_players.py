"""
Show verified players from static cache and database
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from HEXBET.leaguepedia_scraper import PRO_ACCOUNTS, STREAMER_ACCOUNTS, get_player_badge
from tracker_database import TrackerDatabase

print("\n" + "="*60)
print("STATIC CACHE (leaguepedia_scraper.py)")
print("="*60)

print(f"\n📊 PRO ACCOUNTS ({len(PRO_ACCOUNTS)} total):")
for riot_id, info in list(PRO_ACCOUNTS.items())[:10]:  # Show first 10
    print(f"   {riot_id:<30} - {info.get('name', 'N/A'):<20} ({info.get('team', 'N/A')})")
if len(PRO_ACCOUNTS) > 10:
    print(f"   ... and {len(PRO_ACCOUNTS) - 10} more")

print(f"\n📺 STREAMER ACCOUNTS ({len(STREAMER_ACCOUNTS)} total):")
for riot_id, info in list(STREAMER_ACCOUNTS.items())[:10]:  # Show first 10
    print(f"   {riot_id:<30} - {info.get('name', 'N/A'):<20} ({info.get('platform', 'N/A')})")
if len(STREAMER_ACCOUNTS) > 10:
    print(f"   ... and {len(STREAMER_ACCOUNTS) - 10} more")

# Test badge lookup
print("\n" + "="*60)
print("BADGE LOOKUP TEST")
print("="*60)

test_players = [
    "hide on bush#kr1",
    "thebausffs#cool",
    "chovy",
    "faker",
    "unknown#1234"
]

for riot_id in test_players:
    badge = get_player_badge(riot_id)
    status = "✅" if badge else "❌"
    print(f"{status} {riot_id:<30} -> {badge or 'No badge'}")

# Database check
print("\n" + "="*60)
print("DATABASE (hexbet_verified_players)")
print("="*60)

try:
    db = TrackerDatabase()
    all_players = db.get_all_verified_players()
    
    if all_players:
        print(f"\n📊 Total verified players in database: {len(all_players)}")
        
        pros = [p for p in all_players if p.get('player_type') == 'pro']
        streamers = [p for p in all_players if p.get('player_type') == 'streamer']
        
        print(f"   PRO: {len(pros)}")
        print(f"   STREAMER: {len(streamers)}")
        
        if all_players:
            print(f"\nFirst 5 entries:")
            for p in all_players[:5]:
                print(f"   {p.get('riot_id'):<30} - {p.get('player_name'):<20} ({p.get('player_type')})")
    else:
        print("\n⚠️  Database is empty - run migrate_verified_players.py to populate")
        
except Exception as e:
    print(f"\n❌ Database error: {e}")
    print("   Make sure PostgreSQL is running and DATABASE_URL is set")

print("\n" + "="*60 + "\n")
