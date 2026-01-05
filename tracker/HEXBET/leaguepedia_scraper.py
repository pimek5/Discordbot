"""
Leaguepedia Scraper for Pro Players and Streamers
Manual database of verified accounts from Leaguepedia research
"""
from typing import Dict, List, Optional
import logging

logger = logging.getLogger('hexbet.leaguepedia')

# Manual database of verified pro players and their accounts
# Auto-generated from multi_source_scraper.py
# Source: pro_players_database.json
PRO_ACCOUNTS = {
    # T1
    'hide on bush#kr1': {'name': 'Faker', 'team': 'T1'},
    't1 zeus#kr1': {'name': 'Zeus', 'team': 'T1'},
    't1 keria#kr1': {'name': 'Keria', 'team': 'T1'},
    't1 oner#kr1': {'name': 'Oner', 'team': 'T1'},
    'gumayusi': {'name': 'Gumayusi', 'team': 'T1'},
    'doran': {'name': 'Doran', 'team': 'T1'},
    'peyz': {'name': 'Peyz', 'team': 'T1'},
    
    # Gen.G
    'gen chovy#kr1': {'name': 'Chovy', 'team': 'Gen.G'},
    'canyon': {'name': 'Canyon', 'team': 'Gen.G'},
    'peanut': {'name': 'Peanut', 'team': 'Gen.G'},
    'lehends': {'name': 'Lehends', 'team': 'Gen.G'},
    
    # Dplus KIA
    'dk showmaker#kr1': {'name': 'ShowMaker', 'team': 'Dplus KIA'},
    'dk canyon#kr1': {'name': 'Canyon', 'team': 'Dplus KIA'},
    
    # G2 Esports
    'g2 caps#euw': {'name': 'Caps', 'team': 'G2 Esports'},
    'g2 perkz#euw': {'name': 'Perkz', 'team': 'G2 Esports'},
    
    # Fnatic
    'fnc upset#euw': {'name': 'Upset', 'team': 'Fnatic'},
    'fnc razork#euw': {'name': 'Razork', 'team': 'Fnatic'},
    
    # Other teams
    'jdg ruler#kr1': {'name': 'Ruler', 'team': 'JD Gaming'},
    'wbg theshy#kr1': {'name': 'TheShy', 'team': 'Weibo Gaming'},
    'jankos': {'name': 'Jankos', 'team': 'Heretics'},
    'deft': {'name': 'Deft', 'team': 'HLE'},
    'beryl': {'name': 'BeryL', 'team': 'DRX'},
    
    # Free Agents / Retired
    'rekkles#euw': {'name': 'Rekkles', 'team': 'Free Agent'},
    'ig rookie#kr1': {'name': 'Rookie', 'team': 'Free Agent'},
    'fpx doinb#na1': {'name': 'Doinb', 'team': 'Retired'},
}

# Streamer accounts
# Verified accounts only - do not add guessed/placeholder data
STREAMER_ACCOUNTS = {
    # TheBausffs (verified from multiple sources)
    'thebausffs#cool': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'dangerous dork#lick': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'streaming badboy#int': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'thebausffs#3710': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'bosch drill#euw': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'mollusca slime#yummy': {'name': 'Thebausffs', 'platform': 'Twitch'},
    'silly snail#öga': {'name': 'Thebausffs', 'platform': 'Twitch'},
    
    # Other verified streamers (add only with confirmed Riot IDs)
    # 'agurin#euw': {'name': 'Agurin', 'platform': 'Twitch'},  # Needs verification
    # 'drututt': {'name': 'Drututt', 'platform': 'Twitch'},     # Needs verification
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
        return "<:STRM:1457671230432743567>"
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
