"""
Leaguepedia Scraper for Pro Players and Streamers
Manual database of verified accounts from Leaguepedia research
"""
from typing import Dict, List, Optional
import logging

logger = logging.getLogger('hexbet.leaguepedia')

# Manual database of verified pro players and their accounts
# Source: https://lol.fandom.com/wiki/{PlayerName}
PRO_ACCOUNTS = {
    # Faker (T1)
    'hide on bush': {'name': 'Faker', 'team': 'T1', 'accounts': ['Hide on bush#KR1', 'Hide on bush#61151', 'Hide on bush#canad']},
    'hide on bush#kr1': {'name': 'Faker', 'team': 'T1'},
    'hide on bush#61151': {'name': 'Faker', 'team': 'T1'},
    'hide on bush#canad': {'name': 'Faker', 'team': 'T1'},
    
    # Chovy (Gen.G)
    'chovy': {'name': 'Chovy', 'team': 'Gen.G'},
    
    # Zeus (T1)
    'zeus': {'name': 'Zeus', 'team': 'T1'},
    
    # Keria (T1)
    'keria': {'name': 'Keria', 'team': 'T1'},
    
    # Oner (T1)
    'oner': {'name': 'Oner', 'team': 'T1'},
    
    # Gumayusi (T1)
    'gumayusi': {'name': 'Gumayusi', 'team': 'T1'},
    
    # Doran (T1)
    'doran': {'name': 'Doran', 'team': 'T1'},
    
    # Caps (G2)
    'caps': {'name': 'Caps', 'team': 'G2'},
    
    # Upset (FNC)
    'upset': {'name': 'Upset', 'team': 'Fnatic'},
    
    # Jankos
    'jankos': {'name': 'Jankos', 'team': 'Heretics'},
    
    # ShowMaker (KT)
    'showmaker': {'name': 'ShowMaker', 'team': 'KT'},
    
    # Canyon (Gen.G)  
    'canyon': {'name': 'Canyon', 'team': 'Gen.G'},
    
    # Ruler (JDG)
    'ruler': {'name': 'Ruler', 'team': 'JDG'},
    
    # Deft (HLE)
    'deft': {'name': 'Deft', 'team': 'HLE'},
    
    # BeryL (DRX)
    'beryl': {'name': 'BeryL', 'team': 'DRX'},
    
    # Peanut (Gen.G)
    'peanut': {'name': 'Peanut', 'team': 'Gen.G'},
    
    # Peyz (T1)
    'peyz': {'name': 'Peyz', 'team': 'T1'},
    
    # Lehends (Gen.G)
    'lehends': {'name': 'Lehends', 'team': 'Gen.G'},
}

# Streamer accounts
STREAMER_ACCOUNTS = {
    # Agurin
    'agurin': {'name': 'Agurin', 'platform': 'Twitch'},
    
    # Thebausffs (Simon Hofverberg) - Source: lolpros.gg
    'thebausffs#cool': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'dangerous dork#lick': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'streaming badboy#int': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'thebausffs#3710': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'bosch drill#euw': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'mollusca slime#yummy': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'silly snail#öga': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'demon simon#0000': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'thebausffs#56243': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'thebausffs#euw': {'name': 'Thebausffs', 'platform': 'Twitch'},
    
    # Other streamers
    'drututt': {'name': 'Drututt', 'platform': 'Twitch'},
    'nemesis': {'name': 'Nemesis', 'platform': 'Twitch'},
}

# Cache structure
LEAGUEPEDIA_CACHE = {
    'pro': PRO_ACCOUNTS.copy(),
    'streamer': STREAMER_ACCOUNTS.copy()
}

async def load_major_pro_players():
    """
    Load verified pro player accounts
    Using manual database compiled from Leaguepedia
    """
    # Already loaded in module initialization
    logger.info(f"✅ Loaded {len(PRO_ACCOUNTS)} pro accounts and {len(STREAMER_ACCOUNTS)} streamer accounts")
    pass

def is_verified_pro(riot_id: str) -> bool:
    """Check if player is verified pro from Leaguepedia"""
    if not riot_id:
        return False
    riot_id_lower = riot_id.lower().strip()
    return riot_id_lower in LEAGUEPEDIA_CACHE['pro']

def is_verified_streamer(riot_id: str) -> bool:
    """Check if player is verified streamer from Leaguepedia"""
    if not riot_id:
        return False
    riot_id_lower = riot_id.lower().strip()
    return riot_id_lower in LEAGUEPEDIA_CACHE['streamer']

def get_player_badge(riot_id: str) -> Optional[str]:
    """
    Get badge for player (PRO or STRM)
    Returns emoji string or None
    """
    if is_verified_pro(riot_id):
        return "<:PRO:1457231609458851961>"
    elif is_verified_streamer(riot_id):
        return "<:STRM:1457328151095939138>"
    return None

def get_player_info(riot_id: str) -> Optional[Dict]:
    """Get full player info from cache"""
    riot_id_lower = riot_id.lower().strip()
    
    if riot_id_lower in LEAGUEPEDIA_CACHE['pro']:
        info = LEAGUEPEDIA_CACHE['pro'][riot_id_lower].copy()
        info['type'] = 'pro'
        return info
    
    if riot_id_lower in LEAGUEPEDIA_CACHE['streamer']:
        info = LEAGUEPEDIA_CACHE['streamer'][riot_id_lower].copy()
        info['type'] = 'streamer'
        return info
    
    return None
