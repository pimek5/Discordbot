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

async def add_player_simple(db: TrackerDatabase, name: str, player_type: str):
    """Add player with simple placeholder riot_id - will be updated by /hxpro command"""
    try:
        logger.info(f"Adding {player_type}: {name}")
        
        # Create placeholder riot_id
        placeholder_riot_id = f"{name}#0000"
        
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
        
        # Insert player with placeholder
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO hexbet_verified_players (riot_id, player_name, player_type)
               VALUES (%s, %s, %s)
               RETURNING id""",
            (placeholder_riot_id, name, player_type)
        )
        player_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        db.return_connection(conn)
        
        logger.info(f"✅ Added player {name} (ID: {player_id})")
        return True
            
    except Exception as e:
        logger.error(f"Error adding {name}: {e}", exc_info=True)
        return False

async def main():
    """Main batch add function"""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Override DATABASE_URL to Railway URL
    railway_url = "postgresql://postgres:VeNZZTCabRnROGyGHQbVSBcLlIIhYDuB@shinkansen.proxy.rlwy.net:23983/railway"
    os.environ['DATABASE_URL'] = railway_url
    
    db = TrackerDatabase()
    riot_api = RiotAPI(api_key=os.getenv('RIOT_API_KEY'))
    
    print("\n" + "="*50)
    print("HEXBET BATCH PLAYER ADD")
    print("="*50)
    print(f">> Connected to: {railway_url.split('@')[1].split('/')[0]}")
    
    added = 0
    failed = 0
    
    # Add pros
    print("\n[PRO PLAYERS]")
    for name in PRO_PLAYERS:
        if await add_player_simple(db, name, 'pro'):
            added += 1
        else:
            failed += 1
        await asyncio.sleep(0.5)  # Shorter delay
    
    # Add streamers
    print("\n[STREAMERS]")
    for name in STREAMER_PLAYERS:
        if await add_player_simple(db, name, 'streamer'):
            added += 1
        else:
            failed += 1
        await asyncio.sleep(0.5)
    
    print("\n" + "="*50)
    print(f">> Added: {added} | FAILED: {failed}")
    print("="*50 + "\n")

if __name__ == '__main__':
    asyncio.run(main())
