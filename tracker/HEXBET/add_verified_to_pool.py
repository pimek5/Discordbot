"""
Add all verified pro/streamer players to the high-elo pool with priority boost
"""
import asyncio
import aiohttp
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tracker_database import TrackerDatabase
from riot_api import RiotAPI

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('add_verified_to_pool')

DB = TrackerDatabase()
RIOT_API = RiotAPI(os.getenv('RIOT_API_KEY', ''))

async def add_verified_players_to_pool():
    """Add all verified players to pool with priority boost"""
    
    # First, add priority_boost column if it doesn't exist
    try:
        conn = DB.get_connection()
        cur = conn.cursor()
        
        # Check if column exists
        cur.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name='hexbet_high_elo_pool' AND column_name='priority_boost'
        """)
        
        if not cur.fetchone():
            logger.info("🔧 Adding priority_boost column...")
            cur.execute("""
                ALTER TABLE hexbet_high_elo_pool 
                ADD COLUMN priority_boost FLOAT DEFAULT 1.0
            """)
            conn.commit()
            logger.info("✅ Column added")
        
        cur.close()
        DB.return_connection(conn)
    except Exception as e:
        logger.warning(f"⚠️ Could not add column: {e}")
    
    # Get all verified players
    conn = DB.get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, riot_id, player_name, player_type 
        FROM hexbet_verified_players 
        ORDER BY player_type DESC, player_name
    """)
    
    verified_players = cur.fetchall()
    logger.info(f"📊 Found {len(verified_players)} verified players")
    
    added = 0
    failed = 0
    updated_priority = 0
    
    for idx, (player_id, riot_id, player_name, player_type) in enumerate(verified_players, 1):
        if idx % 20 == 0:
            await asyncio.sleep(1)  # Rate limit
        
        try:
            # Get PUUID from stats
            cur.execute("""
                SELECT DISTINCT riot_id FROM hexbet_pro_accounts 
                WHERE player_id = %s 
                LIMIT 1
            """, (player_id,))
            
            result = cur.fetchone()
            if not result:
                logger.warning(f"⚠️ {player_name} ({riot_id}): No stats found")
                failed += 1
                continue
            
            account_riot_id = result[0]
            game_name, tag_line = account_riot_id.split('#', 1)
            
            # Get PUUID
            account_url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
            headers = {'X-Riot-Token': RIOT_API.api_key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(account_url, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning(f"⚠️ {player_name}: Failed to get PUUID ({resp.status})")
                        failed += 1
                        continue
                    
                    account_data = await resp.json()
                    puuid = account_data.get('puuid')
            
            if not puuid:
                logger.warning(f"⚠️ {player_name}: No PUUID returned")
                failed += 1
                continue
            
            # Get region and rank
            rank_url = f"https://europe.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
            async with aiohttp.ClientSession() as session:
                async with session.get(rank_url, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning(f"⚠️ {player_name}: Failed to get summoner")
                        failed += 1
                        continue
                    
                    summoner_data = await resp.json()
            
            summoner_id = summoner_data.get('id')
            region = 'euw'  # Default
            
            # Get ranked stats
            ranked_url = f"https://euw1.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
            stats = None
            
            async with aiohttp.ClientSession() as session:
                async with session.get(ranked_url, headers=headers) as resp:
                    if resp.status == 200:
                        stats_data = await resp.json()
                        if stats_data:
                            ranked = [s for s in stats_data if s.get('queueType') == 'RANKED_SOLO_5x5']
                            stats = ranked[0] if ranked else stats_data[0]
            
            tier = stats.get('tier', 'DIAMOND') if stats else 'DIAMOND'
            lp = stats.get('leaguePoints', 0) if stats else 0
            
            # Calculate priority boost
            # PRO = +1% boost, STREAMER = +0.5% boost
            priority_boost = 1.01 if player_type == 'pro' else 1.005
            
            # Insert or update in pool
            cur.execute("""
                INSERT INTO hexbet_high_elo_pool (puuid, region, tier, lp, priority_boost)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (puuid) DO UPDATE SET
                    tier = EXCLUDED.tier,
                    lp = EXCLUDED.lp,
                    priority_boost = EXCLUDED.priority_boost
            """, (puuid, region, tier, lp, priority_boost))
            conn.commit()
            
            badge = "🎖️ PRO" if player_type == 'pro' else "📺 STRM"
            logger.info(f"✅ {idx}/148 {badge} {player_name} ({tier} {lp}LP) - boost x{priority_boost}")
            added += 1
            
        except Exception as e:
            logger.error(f"❌ {player_name}: {e}")
            failed += 1
            continue
    
    cur.close()
    DB.return_connection(conn)
    
    logger.info(f"""
    
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ POOL UPDATE COMPLETE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Added: {added}/148
Failed: {failed}
🎖️ PRO players: +1% boost
📺 STREAMER players: +0.5% boost
    """)

if __name__ == '__main__':
    asyncio.run(add_verified_players_to_pool())
