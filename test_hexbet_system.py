"""
Test script to verify HEXBET system is working
Run this to check database and API connectivity
"""
import asyncio
import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tracker'))

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('test')

from tracker_database import TrackerDatabase
from riot_api import RiotAPI

async def test_api_connectivity():
    """Test Riot API connectivity"""
    logger.info("=" * 50)
    logger.info("Testing Riot API connectivity...")
    logger.info("=" * 50)
    
    riot_api = RiotAPI()
    
    # Check if API key is set
    if not riot_api.api_key:
        logger.error("❌ No API key configured!")
        return False
    
    logger.info(f"✅ API key is configured (length: {len(riot_api.api_key)})")
    
    # Try to get summoner by name (should work even if rate limited)
    try:
        result = await riot_api.get_summoner_by_name('Faker', 'kr')
        if result:
            logger.info(f"✅ API working: Found summoner with {result.get('summonerLevel')} level")
        else:
            logger.warning("⚠️ API returned None (might be rate limited)")
    except Exception as e:
        logger.error(f"❌ API error: {e}")
        return False
    
    return True

async def test_database():
    """Test database connectivity"""
    logger.info("=" * 50)
    logger.info("Testing database connectivity...")
    logger.info("=" * 50)
    
    try:
        db = TrackerDatabase()
        
        # Test count_open_matches
        open_count = db.count_open_matches()
        logger.info(f"✅ Open matches: {open_count}")
        
        # Test getting pool
        puuids = db.get_random_high_elo_puuids('euw', limit=1)
        logger.info(f"✅ High-elo pool: {len(puuids)} players available")
        
        if not puuids:
            logger.warning("⚠️ No players in high-elo pool!")
            return False
        
        # Check if we can query matches
        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM hexbet_matches")
            total_matches = cur.fetchone()[0]
            logger.info(f"✅ Total matches in DB: {total_matches}")
        db.return_connection(conn)
        
        return True
    except Exception as e:
        logger.error(f"❌ Database error: {e}", exc_info=True)
        return False

async def test_active_game_detection():
    """Try to find an active game"""
    logger.info("=" * 50)
    logger.info("Testing active game detection...")
    logger.info("=" * 50)
    
    db = TrackerDatabase()
    riot_api = RiotAPI()
    
    # Get some PUUIDs from pool
    puuids = db.get_random_high_elo_puuids('euw', limit=10)
    
    if not puuids:
        logger.error("❌ No PUUIDs in pool")
        return False
    
    logger.info(f"🔍 Checking {len(puuids)} players for active games...")
    
    found_game = False
    for i, (puuid, tier, lp) in enumerate(puuids):
        logger.info(f"  Checking player {i+1}/10: {tier} {lp} LP...")
        game = await riot_api.get_active_game(puuid, 'euw')
        if game:
            logger.info(f"✅ FOUND ACTIVE GAME!")
            logger.info(f"   Game ID: {game.get('gameId')}")
            logger.info(f"   Queue: {game.get('gameQueueConfigId')}")
            logger.info(f"   Players: {len(game.get('participants', []))} total")
            found_game = True
            break
        await asyncio.sleep(0.5)  # Small delay to avoid rate limits
    
    if not found_game:
        logger.warning("⚠️ No active games found among checked players")
        logger.info("   (This might be normal if high-elo is not active)")
    
    return True

async def main():
    """Run all tests"""
    logger.info("\n" + "=" * 50)
    logger.info("HEXBET SYSTEM DIAGNOSTICS")
    logger.info("=" * 50 + "\n")
    
    # Test database
    db_ok = await test_database()
    
    # Test API
    api_ok = await test_api_connectivity()
    
    # Test game detection
    game_ok = await test_active_game_detection()
    
    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("SUMMARY")
    logger.info("=" * 50)
    logger.info(f"Database: {'✅' if db_ok else '❌'}")
    logger.info(f"API: {'✅' if api_ok else '❌'}")
    logger.info(f"Game Detection: {'✅' if game_ok else '❌'}")
    
    if all([db_ok, api_ok, game_ok]):
        logger.info("\n✅ All systems operational!")
    else:
        logger.warning("\n⚠️ Some systems have issues")

if __name__ == "__main__":
    asyncio.run(main())
