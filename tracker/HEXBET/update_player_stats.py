#!/usr/bin/env python3
"""
Update all placeholder players with real riot IDs and stats via Riot API
"""
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_database import TrackerDatabase
from riot_api import RiotAPI
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('update_players')

# Override DATABASE_URL to Railway
railway_url = "postgresql://postgres:VeNZZTCabRnROGyGHQbVSBcLlIIhYDuB@shinkansen.proxy.rlwy.net:23983/railway"
os.environ['DATABASE_URL'] = railway_url

async def update_player(db: TrackerDatabase, riot_api: RiotAPI, player_id: int, player_name: str, player_type: str):
    """
    Update single player with real Riot ID and stats
    """
    try:
        logger.info(f"[{player_type}] Updating: {player_name}")
        
        # Search for player on Riot API (try multiple regions)
        regions = ['euw1', 'eun1', 'kr', 'na1']
        summoner = None
        
        for region in regions:
            try:
                summoner = await riot_api.get_summoner_by_name(player_name, region)
                if summoner:
                    logger.info(f"  Found on {region}")
                    break
            except Exception as e:
                logger.debug(f"  Not found on {region}: {e}")
                continue
        
        if not summoner:
            logger.warning(f"  NOT FOUND on any region")
            return False
        
        # Get PUUID
        puuid = summoner.get('puuid')
        riot_id = summoner.get('name', '') + '#' + summoner.get('tagLine', '')
        
        logger.info(f"  Found: {riot_id}")
        
        # Update riot_id in database
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE hexbet_verified_players 
               SET riot_id = %s 
               WHERE id = %s""",
            (riot_id, player_id)
        )
        conn.commit()
        cursor.close()
        db.return_connection(conn)
        
        logger.info(f"  Updated riot_id to: {riot_id}")
        
        # Get ranked stats for all regions (to find best one)
        best_stats = None
        best_rank = {'tier': 'UNRANKED', 'rank': '', 'leaguePoints': 0}
        rank_order = {'GRANDMASTER': 8, 'MASTER': 7, 'DIAMOND': 6, 'PLATINUM': 5, 'GOLD': 4, 'SILVER': 3, 'BRONZE': 2, 'IRON': 1, 'UNRANKED': 0}
        
        for region in regions:
            try:
                stats = await riot_api.get_ranked_stats_by_puuid(puuid, region)
                if stats:
                    for entry in stats:
                        tier = entry.get('tier', 'UNRANKED').upper()
                        rank = entry.get('rank', '')
                        lp = entry.get('leaguePoints', 0)
                        tier_value = rank_order.get(tier, 0)
                        best_tier_value = rank_order.get(best_rank.get('tier', 'UNRANKED'), 0)
                        
                        if tier_value > best_tier_value or (tier_value == best_tier_value and lp > best_rank.get('leaguePoints', 0)):
                            best_rank = entry
                    logger.debug(f"  Stats found on {region}")
            except Exception as e:
                logger.debug(f"  No stats on {region}: {e}")
                continue
        
        if best_rank != {'tier': 'UNRANKED', 'rank': '', 'leaguePoints': 0}:
            # Update stats
            tier = best_rank.get('tier', 'UNRANKED').upper()
            rank = best_rank.get('rank', '').upper()
            lp = best_rank.get('leaguePoints', 0)
            wins = best_rank.get('wins', 0)
            losses = best_rank.get('losses', 0)
            
            conn = db.get_connection()
            cursor = conn.cursor()
            
            # Try to insert account stats
            try:
                cursor.execute(
                    """INSERT INTO hexbet_pro_accounts (player_id, riot_id, tier, rank, lp, wins, losses)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (player_id, riot_id) DO UPDATE SET
                       tier = %s, rank = %s, lp = %s, wins = %s, losses = %s, updated_at = NOW()""",
                    (player_id, riot_id, tier, rank, lp, wins, losses,
                     tier, rank, lp, wins, losses)
                )
                conn.commit()
                logger.info(f"  Stats: {tier} {rank} {lp}LP ({wins}W {losses}L)")
            except Exception as e:
                logger.warning(f"  Could not insert stats: {e}")
                conn.rollback()
            finally:
                cursor.close()
                db.return_connection(conn)
        else:
            logger.warning(f"  No ranked stats found")
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating {player_name}: {e}", exc_info=True)
        return False

async def main():
    """Main update function"""
    db = TrackerDatabase()
    riot_api = RiotAPI(api_key=os.getenv('RIOT_API_KEY'))
    
    print("\n" + "="*60)
    print("HEXBET PLAYER UPDATE - Fetching real Riot IDs and stats")
    print("="*60)
    
    # Get all players from database
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, player_name, player_type 
           FROM hexbet_verified_players 
           ORDER BY id DESC"""
    )
    players = cursor.fetchall()
    cursor.close()
    db.return_connection(conn)
    
    print(f"\nTotal players to update: {len(players)}\n")
    
    updated = 0
    failed = 0
    
    for player_id, player_name, player_type in players:
        if await update_player(db, riot_api, player_id, player_name, player_type):
            updated += 1
        else:
            failed += 1
        await asyncio.sleep(0.3)  # Rate limit
    
    print("\n" + "="*60)
    print(f">> Updated: {updated} | FAILED: {failed}")
    print("="*60 + "\n")

if __name__ == '__main__':
    asyncio.run(main())
