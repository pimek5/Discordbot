"""Debug script to test featured game posting"""
import asyncio
import logging
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tracker'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('debug')

from tracker_database import TrackerDatabase
from riot_api import RiotAPI

async def main():
    """Debug featured game posting"""
    db = TrackerDatabase()
    riot_api = RiotAPI()
    
    # Check pool
    logger.info("🔍 Checking high-elo pool...")
    puuids = db.get_random_high_elo_puuids('euw', limit=5)
    logger.info(f"Found {len(puuids)} players in EUW pool")
    
    if not puuids:
        logger.error("❌ No players in pool!")
        return
    
    # Try to get active game for each
    for puuid, tier, lp in puuids:
        logger.info(f"🎯 Checking {tier} {lp} LP player: {puuid[:8]}...")
        game = await riot_api.get_active_game(puuid, 'euw')
        if game:
            logger.info(f"✅ Found active game! Queue: {game.get('gameQueueConfigId')}")
            break
        else:
            logger.info(f"  No active game")
    
    logger.info("✅ Debug complete")

if __name__ == "__main__":
    asyncio.run(main())
