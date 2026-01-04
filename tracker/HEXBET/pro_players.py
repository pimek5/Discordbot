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
    Load pro players from Riot Esports API
    Uses esports-api.lolesports.com to get current pro players
    """
    global PRO_PLAYERS_CACHE
    
    # Start with static list
    PRO_PLAYERS_CACHE = {name.lower() for name in KNOWN_PRO_PLAYERS}
    initial_count = len(PRO_PLAYERS_CACHE)
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'x-api-key': '0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z'  # Public API key from Riot
            }
            
            # Get leagues
            leagues_url = "https://esports-api.lolesports.com/persisted/gw/getLeagues?hl=en-US"
            
            async with session.get(leagues_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    raise Exception(f"Failed to fetch leagues: {response.status}")
                
                leagues_data = await response.json()
                
                # Target major leagues
                major_leagues = ['LEC', 'LCK', 'LCS', 'LPL', 'CBLOL', 'LJL', 'LLA', 'PCS', 'VCS']
                league_ids = []
                
                for league in leagues_data.get('data', {}).get('leagues', []):
                    slug = league.get('slug', '').upper()
                    if any(major in slug for major in major_leagues):
                        league_ids.append(league.get('id'))
                
                # Get teams for each major league
                teams_processed = 0
                for league_id in league_ids[:8]:  # Process up to 8 leagues
                    try:
                        teams_url = f"https://esports-api.lolesports.com/persisted/gw/getTeams?hl=en-US&leagueId={league_id}"
                        async with session.get(teams_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as team_response:
                            if team_response.status == 200:
                                teams_data = await team_response.json()
                                
                                # Process all teams (API returns all historical teams)
                                for team in teams_data.get('data', {}).get('teams', []):
                                    players = team.get('players', [])
                                    if players:  # Only teams with players
                                        for player in players:
                                            summoner_name = player.get('summonerName', '')
                                            if summoner_name:
                                                PRO_PLAYERS_CACHE.add(summoner_name.lower())
                                        teams_processed += 1
                                        
                                        # Limit to first 100 teams per league to avoid too much data
                                        if teams_processed >= 100:
                                            break
                    except Exception as e:
                        logger.debug(f"Could not fetch team data for league {league_id}: {e}")
                        continue
                    
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.3)
        
        new_count = len(PRO_PLAYERS_CACHE)
        logger.info(f"Loaded {new_count} pro players ({new_count - initial_count} from API, {initial_count} static)")
    except Exception as e:
        logger.warning(f"Failed to load pro players from API: {e}")
        PRO_PLAYERS_CACHE = {name.lower() for name in KNOWN_PRO_PLAYERS}
        logger.info(f"Using static list: {len(PRO_PLAYERS_CACHE)} pro players")

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
    return "<:PRO:1457231609458851961>"
