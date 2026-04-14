"""
LOLPros.gg Scraper for Player Verification
Automatically checks players on lolpros.gg and verifies pro/streamer status
"""
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import Optional, Dict
import logging
import re

logger = logging.getLogger('hexbet.lolpros_scraper')

async def fetch_lolpros_player(riot_id: str) -> Optional[Dict]:
    """
    Fetch player data from lolpros.gg
    Args:
        riot_id: RiotID in format "gameName#tagLine"
    Returns:
        Dict with player info or None if not found
    """
    try:
        # Extract game name for URL
        game_name = riot_id.split('#')[0].lower().replace(' ', '-')
        url = f"https://lolpros.gg/player/{game_name}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    logger.debug(f"Player not found on lolpros.gg: {riot_id} (status {response.status})")
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Check if page exists (not 404)
                if 'Player not found' in html or 'Page not found' in html:
                    return None
                
                # Extract player info
                player_data = {
                    'riot_id': riot_id,
                    'player_name': None,
                    'player_type': None,  # 'pro' or 'streamer'
                    'team': None,
                    'platform': None,
                    'lolpros_url': url,
                    'leaguepedia_url': None
                }
                
                # Try to find player name from page title or h1
                title = soup.find('h1')
                if title:
                    player_data['player_name'] = title.get_text(strip=True)
                else:
                    # Fallback to game name
                    player_data['player_name'] = game_name.title()
                
                # Check for Leaguepedia link (indicates pro/notable player)
                leaguepedia_link = soup.find('a', href=re.compile(r'lol\.fandom\.com'))
                if leaguepedia_link:
                    player_data['leaguepedia_url'] = leaguepedia_link.get('href')
                
                # Check for team (indicates pro player)
                team_section = soup.find(text=re.compile(r'PREVIOUS TEAMS|Current Team', re.IGNORECASE))
                if team_section:
                    team_parent = team_section.find_parent()
                    if team_parent:
                        team_name = team_parent.find_next('img')
                        if team_name and team_name.get('alt'):
                            player_data['team'] = team_name.get('alt')
                            player_data['player_type'] = 'pro'
                
                # Check for streaming platform (Twitch/YouTube)
                social_links = soup.find_all('a', href=True)
                for link in social_links:
                    href = link.get('href', '')
                    if 'twitch.tv' in href:
                        player_data['platform'] = 'Twitch'
                        # If no team found but has Twitch = streamer
                        if not player_data['player_type']:
                            player_data['player_type'] = 'streamer'
                    elif 'youtube.com' in href:
                        if not player_data['platform']:
                            player_data['platform'] = 'YouTube'
                        if not player_data['player_type']:
                            player_data['player_type'] = 'streamer'
                
                # If has Leaguepedia but no team = likely content creator/streamer
                if player_data['leaguepedia_url'] and not player_data['player_type']:
                    player_data['player_type'] = 'streamer'
                
                # Only return if we determined pro or streamer status
                if player_data['player_type']:
                    logger.info(f"✅ Found {player_data['player_type']}: {player_data['player_name']} ({riot_id})")
                    return player_data
                
                logger.debug(f"Player found but not pro/streamer: {riot_id}")
                return None
                
    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Timeout checking lolpros.gg for {riot_id}")
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch lolpros.gg data for {riot_id}: {e}")
        return None

async def check_and_verify_player(riot_id: str, db) -> Optional[str]:
    """
    Check player on lolpros.gg and add to database if verified
    Args:
        riot_id: RiotID to check
        db: TrackerDatabase instance
    Returns:
        Badge emoji string or None
    """
    # First check database cache
    cached = db.get_verified_player(riot_id)
    if cached:
        # Update last_seen
        try:
            conn = db.get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE hexbet_verified_players 
                    SET last_seen = NOW() 
                    WHERE LOWER(riot_id) = LOWER(%s)
                """, (riot_id,))
                conn.commit()
            db.return_connection(conn)
        except:
            pass
        
        # Return appropriate badge
        if cached['player_type'] == 'pro':
            return "<:PRO:1457231609458851961>"
        elif cached['player_type'] == 'streamer':
            return "<:Streamer:1457699155689341044>"
    
    # Check if recently checked (avoid spam)
    if cached and cached.get('last_checked'):
        from datetime import datetime, timedelta
        if datetime.now() - cached['last_checked'] < timedelta(hours=24):
            return None
    
    # Fetch from lolpros.gg
    player_data = await fetch_lolpros_player(riot_id)
    
    if player_data and player_data['player_type']:
        # Add to database
        db.add_verified_player(
            riot_id=player_data['riot_id'],
            player_name=player_data['player_name'],
            player_type=player_data['player_type'],
            team=player_data.get('team'),
            platform=player_data.get('platform'),
            lolpros_url=player_data['lolpros_url'],
            leaguepedia_url=player_data.get('leaguepedia_url')
        )
        
        # Return badge
        if player_data['player_type'] == 'pro':
            return "<:PRO:1457231609458851961>"
        elif player_data['player_type'] == 'streamer':
            return "<:Streamer:1457699155689341044>"
    
    # Mark as checked (even if not found)
    if cached:
        db.update_player_last_checked(riot_id)
    
    return None
