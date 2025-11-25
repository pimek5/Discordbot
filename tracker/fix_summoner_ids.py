"""
Script to fix missing summoner_ids in league_accounts table
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main.riot_api import RiotAPI
from main.database import get_db
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def fix_summoner_ids():
    """Update all league_accounts with missing summoner_ids"""
    
    # Get API key from environment
    api_key = os.getenv('RIOT_API_KEY')
    if not api_key:
        logger.error("❌ RIOT_API_KEY not found in environment!")
        return
    
    riot_api = RiotAPI(api_key)
    db = get_db()
    
    # Get all accounts with NULL summoner_id
    conn = db.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, puuid, region, riot_id_game_name, riot_id_tagline
            FROM league_accounts
            WHERE summoner_id IS NULL
        """)
        
        accounts = cur.fetchall()
        logger.info(f"📊 Found {len(accounts)} accounts without summoner_id")
        
        updated = 0
        failed = 0
        
        for account_id, puuid, region, game_name, tagline in accounts:
            try:
                logger.info(f"🔍 Fetching summoner_id for {game_name}#{tagline} ({region})...")
                
                # Get summoner data from PUUID
                summoner_data = await riot_api.get_summoner_by_puuid(puuid, region)
                
                if not summoner_data:
                    logger.warning(f"⚠️ Could not get summoner data for {game_name}#{tagline}")
                    failed += 1
                    continue
                
                summoner_id = summoner_data.get('id')
                if not summoner_id:
                    logger.warning(f"⚠️ No summoner_id in response for {game_name}#{tagline}")
                    failed += 1
                    continue
                
                # Update database
                cur.execute("""
                    UPDATE league_accounts
                    SET summoner_id = %s, last_updated = NOW()
                    WHERE id = %s
                """, (summoner_id, account_id))
                
                conn.commit()
                updated += 1
                logger.info(f"✅ Updated {game_name}#{tagline} with summoner_id: {summoner_id[:10]}...")
                
                # Rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"❌ Error updating {game_name}#{tagline}: {e}")
                failed += 1
                continue
        
        logger.info(f"\n{'='*50}")
        logger.info(f"✅ Updated: {updated}")
        logger.info(f"❌ Failed: {failed}")
        logger.info(f"📊 Total: {len(accounts)}")
        logger.info(f"{'='*50}\n")
        
    finally:
        db.return_connection(conn)

if __name__ == "__main__":
    asyncio.run(fix_summoner_ids())
