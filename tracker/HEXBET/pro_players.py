"""
Pro Players Database for HEXBET
Tracks professional League of Legends players
"""
import aiohttp
import asyncio
from typing import Set, Optional
import logging

logger = logging.getLogger('hexbet.pro_players')

# Cache of pro player game names (just the name part, not tag)
PRO_PLAYERS_CACHE: Set[str] = set()

# Static list of known pro players (fallback)
KNOWN_PRO_PLAYERS = {
    # LEC
    'Caps', 'Upset', 'Kaiser', 'Elyoya', 'Jankos', 'Targamas', 'Comp', 'Mikyx',
    'Irrelevant', 'Vetheo', 'Cabo', 'Inspired', 'Hans sama', 'Trymbi', 'Advienne',
    'Nisqy', 'BrokenBlade', 'Yike', 'Jackspektra', 'Labrov', 'Saken',
    # LCK  
    'Faker', 'Keria', 'Oner', 'Zeus', 'Gumayusi', 'Chovy', 'Doran', 'Delight',
    'Peyz', 'Zeka', 'Peanut', 'ShowMaker', 'Canyon', 'Ruler', 'Lehends',
    'Deft', 'BeryL', 'Canna', 'Kiin', 'Viper', 'Doran', 'Aiming', 'Life',
    # LPL
    'TheShy', 'Rookie', 'JackeyLove', 'Meiko', 'Knight', 'Bin', 'Elk', 'XUN',
    '369', 'Xiaohu', 'GALA', 'Missing', 'Light', 'Breathe', 'Hope', 'ON',
    # LCS/Academy
    'Jojopyun', 'Berserker', 'Vulcan', 'Blaber', 'Impact', 'Doublelift', 'CoreJJ',
    'Tactical', 'Ssumday', 'River', 'Tenacity', 'Busio', 'Dhokla', 'Massu',
    # Other notable
    'Rekkles', 'Perkz', 'Alphari', 'Jensen', 'PowerOfEvil', 'Svenskeren',
}

async def load_pro_players_from_api():
    """
    Load pro players from esports API or web scraping
    This is a placeholder - you can implement actual scraping here
    """
    global PRO_PLAYERS_CACHE
    try:
        # For now, use static list
        PRO_PLAYERS_CACHE = {name.lower() for name in KNOWN_PRO_PLAYERS}
        logger.info(f"Loaded {len(PRO_PLAYERS_CACHE)} pro players")
    except Exception as e:
        logger.error(f"Failed to load pro players: {e}")
        PRO_PLAYERS_CACHE = {name.lower() for name in KNOWN_PRO_PLAYERS}

def is_pro_player(riot_id: str) -> bool:
    """
    Check if a player is a pro player
    Args:
        riot_id: RiotID in format "gameName#tagLine" or just "gameName"
    Returns:
        True if player is in pro database
    """
    if not riot_id:
        return False
    
    # Extract game name (before #)
    game_name = riot_id.split('#')[0].lower().strip()
    
    # Check against cache
    return game_name in PRO_PLAYERS_CACHE

def get_pro_emoji() -> str:
    """Return pro player emoji"""
    return "🅿️"
