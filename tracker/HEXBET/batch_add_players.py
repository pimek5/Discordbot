#!/usr/bin/env python3
"""
Batch add pro/streamer players to HEXBET database
"""
import asyncio
import logging
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker_database import TrackerDatabase
from riot_api import RiotAPI
from HEXBET.dpm_scraper import scrape_dpm_pro_accounts

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('batch_add')

# Pro players (known from esports and high-elo recognized players)
PRO_PLAYERS = [
    # LEC/Pro Players
    'Rekkles',
    'Nemesis',
    'Hans Sama',
    'Wunder',
    'Markoon',
    'UNF0RGIVEN',
    'Vladi',
    'Nisqy',
    'Vizicsacsi',
    'Steeelback',
    # High-elo known/team-affiliated
    'Lyncas',
    'RoyalKanin',
    'Kenal',
    'Kozi',
    'Fleshy',
    'Gordinho',
    'Potent',
    'Prime',
    'Pun1sher',
    'Kunduz',
    'Maynter',
    'Jopa',
    'NightSlayer',
    'DenVoksne',
    'SkewMond',
    'Gakgos',
    'Eckas',
    'Escik',
    'Unkn0wn',
    'iLEVI',
    'Shift',
    'TAMA',
    'Koldo',
    'Boda',
    'NattyNatt',
    'Thayger',
    'adi1',
    'Lot',
    'NoName',
    'Soldier',
    'ISMA',
    'Seal',
    'Ryuk',
    # Grandmaster tier - verified/known
    'Backlund',
    'Metroflox',
    'Fresskowy',
    'Facen',
    'Carnage',
    'Rozpier',
    'Speedy1',
    'Blazteurs',
    'Robenong',
    'Velja',
    'Suna',
    'Serin',
    'Keria Prime',
    'CPM',
    'Aymen',
    'ardaffler',
    'Mako',
    'Creepano',
    'Robertoos',
    'Erdote',
    'PropaPandah',
    'Abner',
    'nilsog',
    'Rybson',
    'Marbirius',
    'Vizzpers',
    'Numandiel',
    'Sinmivak',
    'Mahonix',
    'Nawa',
    'PiskHello',
    'Satto',
    'Peaker',
    'Desti',
    'Yen',
    'Mita',
    'JinXedd',
    'Doki',
    'Vander',
    'MKL',
    'Frost',
    # High-elo known players from latest batch
    'Baus',
    'Vetheo',
    'Attila',
    'Decay',
]

# Streamers (confirmed with tags like STREAMER, TTV, TWTV)
STREAMER_PLAYERS = [
    'Agurin',
    'Kaos_Angel',
    'Toast',
    'TryHardEkko',
    'Kekseres',
    'Guli',
    'Peng',
    # New streamers from Grandmaster tier
    'NoWay',
    'TTV Emploid',
    'Dealersz',
    'EkkoSuna',
    'Veigarv2',
    'Engage',
    'Satorius',
    'BZ',
    'Husum',
    'Raiko',
    'IvanDragovic',
    'PoEs_Tk',
    'RustySniper',
    # Latest batch
    'Shunrim',
    'DesperateNasus',
    'Dragdar',
    'Ninkey',
    'Hawkella',
    'Splinter',
    'Caedrel',
    'Bibou',
    # DPM.LOL verified (pages 1-20) - ALL FOUND STREAMERS
    'Viper.',
    'Phantasm',
    'Cupic',
    'xDavemon',
    'Ariziinho',
    'Lathyrus',
    'PzZZang',
    'Guaxi',
    'Witt',
    'crawl2r',
    'dusk__lol',
    'Arthur Lanches',
    'Hedon',
    'Odysseus',
    'day1',
    'Drututt',
    'Biotic',
    'Brunox1001',
    '3in1warrior',
    'Nyxes',
    'peki',
    'Plank',
    'Shending Help',
    'Quindinho',
    'Azhy',
    'Raveydemon',
    'Nikkone',
    'Detdert',
    'Pentaless',
    'balagan_lol',
    'Malice',
    'PoEs_Tk',
    'RekSaiKing',
]

async def add_player(db: TrackerDatabase, riot_api: RiotAPI, name: str, player_type: str):
    """Add a single player to database"""
    try:
        logger.info(f"Adding {player_type}: {name}")
        
        # Scrape DPM.LOL
        scraped_accounts = await scrape_dpm_pro_accounts(name)
        
        if not scraped_accounts:
            logger.warning(f"❌ No accounts found on DPM.LOL for {name}")
            return False
        
        logger.info(f"🔍 Found {len(scraped_accounts)} accounts for {name}")
        
        # Check if already exists
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM hexbet_verified_players WHERE LOWER(player_name) = LOWER(%s)",
            (name,)
        )
        existing = cursor.fetchone()
        cursor.close()
        db.return_connection(conn)
        
        if existing:
            logger.warning(f"⚠️ {name} already in database")
            return False
        
        # Use first account as primary
        primary_riot_id = scraped_accounts[0]['riot_id']
        
        # Insert player
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO hexbet_verified_players (riot_id, player_name, player_type)
               VALUES (%s, %s, %s)
               RETURNING id""",
            (primary_riot_id, name, player_type)
        )
        player_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        db.return_connection(conn)
        
        logger.info(f"✅ Added player {name} with ID {player_id}")
        
        # Fetch stats for each account
        accounts = []
        for idx, scraped in enumerate(scraped_accounts):
            try:
                if idx > 0:
                    await asyncio.sleep(1.5)  # Rate limit
                
                riot_id = scraped['riot_id']
                game_name, tag_line = riot_id.split('#', 1)
                
                # Get PUUID
                account_url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
                headers = {'X-Riot-Token': riot_api.api_key}
                
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(account_url, headers=headers) as response:
                        if response.status != 200:
                            logger.warning(f"Failed to fetch PUUID for {riot_id}")
                            continue
                        
                        account_data = await response.json()
                        puuid = account_data.get('puuid')
                
                # Get ranked stats
                stats = await riot_api.get_ranked_stats_by_puuid(puuid, 'euw')
                
                if not stats:
                    logger.warning(f"No ranked stats for {riot_id}")
                    continue
                
                # Pick rank
                def pick_rank_entry(stats_list):
                    if not stats_list:
                        return 'UNRANKED', '', 50.0
                    solo = [s for s in stats_list if s.get('queueType') == 'RANKED_SOLO_5x5']
                    entry = solo[0] if solo else stats_list[0]
                    wins = entry.get('wins', 0)
                    losses = entry.get('losses', 0)
                    games = wins + losses
                    wr = round((wins / games) * 100, 1) if games else 50.0
                    return entry.get('tier', 'UNRANKED').upper(), entry.get('rank', '').upper(), wr
                
                tier, division, wr = pick_rank_entry(stats)
                
                soloq_entry = next((s for s in stats if s.get('queueType') == 'RANKED_SOLO_5x5'), stats[0] if stats else {})
                lp = soloq_entry.get('leaguePoints', 0)
                wins = soloq_entry.get('wins', 0)
                losses = soloq_entry.get('losses', 0)
                
                accounts.append({
                    'riot_id': riot_id,
                    'rank': tier,
                    'lp': lp,
                    'wins': wins,
                    'losses': losses,
                    'wr': wr
                })
                logger.info(f"✅ Fetched {riot_id}: {tier} {lp} LP")
            except Exception as e:
                logger.warning(f"❌ Failed to fetch {scraped.get('riot_id')}: {e}")
                continue
        
        if accounts:
            count = db.add_pro_accounts(player_id, accounts)
            logger.info(f"✅ Added {count} accounts for {name}")
            return True
        else:
            logger.warning(f"⚠️ No accounts added for {name}")
            return False
            
    except Exception as e:
        logger.error(f"Error adding {name}: {e}", exc_info=True)
        return False

async def main():
    """Main batch add function"""
    from dotenv import load_dotenv
    import os
    
    load_dotenv()
    
    db = TrackerDatabase()
    riot_api = RiotAPI(api_key=os.getenv('RIOT_API_KEY'))
    
    print("\n" + "="*50)
    print("HEXBET BATCH PLAYER ADD")
    print("="*50)
    
    added = 0
    failed = 0
    
    # Add pros
    print("\n[PRO PLAYERS]")
    for name in PRO_PLAYERS:
        if await add_player(db, riot_api, name, 'pro'):
            added += 1
        else:
            failed += 1
        await asyncio.sleep(2)  # Delay between players
    
    # Add streamers
    print("\n[STREAMERS]")
    for name in STREAMER_PLAYERS:
        if await add_player(db, riot_api, name, 'streamer'):
            added += 1
        else:
            failed += 1
        await asyncio.sleep(2)
    
    print("\n" + "="*50)
    print(f"✅ Added: {added} | ❌ Failed: {failed}")
    print("="*50 + "\n")

if __name__ == '__main__':
    asyncio.run(main())
