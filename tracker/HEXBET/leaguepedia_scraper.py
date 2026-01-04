"""
Leaguepedia Scraper for Pro Players and Streamers
Fetches player accounts from Leaguepedia wiki
"""
import aiohttp
import asyncio
import re
from typing import Dict, List, Set, Optional
import logging

logger = logging.getLogger('hexbet.leaguepedia')

# Cache of verified players
LEAGUEPEDIA_CACHE = {
    'pro': {},      # {riot_id: {'name': str, 'team': str, 'region': str}}
    'streamer': {}  # {riot_id: {'name': str, 'platform': str}}
}

async def fetch_leaguepedia_player(player_name: str) -> Optional[Dict]:
    """
    Fetch player data from Leaguepedia API
    Returns player info including their soloqueue accounts
    """
    try:
        url = f"https://lol.fandom.com/api.php"
        params = {
            'action': 'query',
            'format': 'json',
            'prop': 'revisions',
            'titles': player_name,
            'rvprop': 'content',
            'rvslots': 'main'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                pages = data.get('query', {}).get('pages', {})
                
                for page_id, page in pages.items():
                    if page_id == '-1':  # Page not found
                        continue
                    
                    revisions = page.get('revisions', [])
                    if not revisions:
                        continue
                    
                    content = revisions[0].get('slots', {}).get('main', {}).get('*', '')
                    
                    # Parse soloqueue IDs from content
                    accounts = parse_soloqueue_ids(content)
                    
                    # Parse team info
                    team = parse_team_info(content)
                    
                    # Check if player is pro or streamer
                    is_pro = 'Current Team' in content or 'Team History' in content
                    
                    return {
                        'name': player_name,
                        'accounts': accounts,
                        'team': team,
                        'is_pro': is_pro,
                        'is_streamer': 'Twitch' in content or 'YouTube' in content or 'stream' in content.lower()
                    }
        
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch Leaguepedia data for {player_name}: {e}")
        return None

def parse_soloqueue_ids(content: str) -> List[str]:
    """
    Parse Soloqueue IDs section from Leaguepedia page content
    Format: KR: Hide on bush#KR1
    """
    accounts = []
    
    # Look for Soloqueue IDs section
    sq_match = re.search(r'\|[\s]*soloqueue[\s]*=[\s]*([^\|]+)', content, re.IGNORECASE)
    if sq_match:
        sq_text = sq_match.group(1)
        
        # Extract region: account#tag patterns
        # Matches patterns like: KR: Hide on bush#KR1, EUW: Hide on bush#61151
        account_pattern = r'([A-Z]+):\s*([^,\n]+?)(?:#([^\s,]+))?(?=\s*[,\n]|$)'
        matches = re.findall(account_pattern, sq_text)
        
        for region, name, tag in matches:
            name = name.strip()
            if tag:
                accounts.append(f"{name}#{tag}")
            else:
                accounts.append(name)
    
    return accounts

def parse_team_info(content: str) -> Optional[str]:
    """Parse current team from page content"""
    # Look for team= parameter
    team_match = re.search(r'\|[\s]*team[\s]*=[\s]*([^\|]+)', content, re.IGNORECASE)
    if team_match:
        team = team_match.group(1).strip()
        # Remove wiki markup
        team = re.sub(r'\[\[([^\]]+)\]\]', r'\1', team)
        return team
    return None

async def load_major_pro_players():
    """
    Load accounts for major pro players from Leaguepedia
    Focuses on players from major leagues (LEC, LCK, LCS, LPL)
    """
    global LEAGUEPEDIA_CACHE
    
    # List of known high-profile pro players to fetch
    major_players = [
        # LCK Stars
        'Faker', 'Chovy', 'Keria', 'Zeus', 'Oner', 'Gumayusi', 'Doran', 
        'Peyz', 'ShowMaker', 'Canyon', 'Ruler', 'Deft', 'BeryL',
        # LEC Stars  
        'Caps', 'Upset', 'Jankos', 'Elyoya', 'Vetheo', 'Hans sama',
        # LCS/NA
        'Jojopyun', 'Berserker', 'Blaber', 'Impact', 'CoreJJ',
        # LPL (using English names)
        'TheShy', 'Rookie', 'JackeyLove', 'Knight', 'Bin',
        # Popular streamers/content creators
        'Agurin', 'Rekkles', 'Doublelift', 'Sneaky'
    ]
    
    loaded_count = 0
    for player_name in major_players[:30]:  # Limit to avoid rate limits
        try:
            player_data = await fetch_leaguepedia_player(player_name)
            if player_data and player_data.get('accounts'):
                # Store each account
                for account in player_data['accounts']:
                    account_lower = account.lower()
                    
                    if player_data.get('is_pro'):
                        LEAGUEPEDIA_CACHE['pro'][account_lower] = {
                            'name': player_data['name'],
                            'team': player_data.get('team', 'Unknown'),
                            'accounts': player_data['accounts']
                        }
                        loaded_count += 1
                    
                    if player_data.get('is_streamer'):
                        LEAGUEPEDIA_CACHE['streamer'][account_lower] = {
                            'name': player_data['name'],
                            'accounts': player_data['accounts']
                        }
            
            # Rate limiting
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"Failed to process {player_name}: {e}")
            continue
    
    pro_count = len(LEAGUEPEDIA_CACHE['pro'])
    streamer_count = len(LEAGUEPEDIA_CACHE['streamer'])
    logger.info(f"Loaded {pro_count} pro player accounts and {streamer_count} streamer accounts from Leaguepedia")

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
