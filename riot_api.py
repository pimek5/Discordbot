"""
Riot API Module for Orianna Bot
Handles all Riot Games API interactions with retry logic
"""

import aiohttp
import asyncio
from typing import Optional, Dict, List
import logging

logger = logging.getLogger('riot_api')

# Regional routing values (for account-v1)
RIOT_REGIONS = {
    'br': 'americas',
    'eune': 'europe',
    'euw': 'europe',
    'jp': 'asia',
    'kr': 'asia',
    'lan': 'americas',
    'las': 'americas',
    'na': 'americas',
    'oce': 'sea',
    'tr': 'europe',
    'ru': 'europe'
}

# Platform routing values (for summoner/league/mastery endpoints)
PLATFORM_ROUTES = {
    'br': 'br1',
    'eune': 'eun1',
    'euw': 'euw1',
    'jp': 'jp1',
    'kr': 'kr',
    'lan': 'la1',
    'las': 'la2',
    'na': 'na1',
    'oce': 'oc1',
    'tr': 'tr1',
    'ru': 'ru',
    'ph': 'ph2',
    'sg': 'sg2',
    'th': 'th2',
    'tw': 'tw2',
    'vn': 'vn2'
}

# DDragon for champion data
DDRAGON_VERSION = "14.23.1"
DDRAGON_BASE = f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}"

# Champion ID to name mapping (loaded at startup)
CHAMPION_ID_TO_NAME = {}

async def load_champion_data():
    """Load champion data from DDragon"""
    global CHAMPION_ID_TO_NAME
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{DDRAGON_BASE}/data/en_US/champion.json"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    for champ_name, champ_data in data['data'].items():
                        champ_id = int(champ_data['key'])
                        CHAMPION_ID_TO_NAME[champ_id] = champ_name
                    logger.info(f"✅ Loaded {len(CHAMPION_ID_TO_NAME)} champions from DDragon")
    except Exception as e:
        logger.error(f"❌ Error loading champion data: {e}")

def get_champion_icon_url(champion_id: int) -> str:
    """Get champion splash art URL"""
    champ_name = CHAMPION_ID_TO_NAME.get(champion_id, "")
    if champ_name:
        return f"{DDRAGON_BASE}/img/champion/{champ_name}.png"
    return ""

def get_rank_icon_url(tier: str) -> str:
    """Get rank emblem URL from Community Dragon"""
    tier_lower = tier.lower()
    return f"https://raw.communitydragon.org/latest/plugins/rcp-fe-lol-static-assets/global/default/ranked-emblems/emblem-{tier_lower}.png"


class RiotAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            'X-Riot-Token': api_key
        }
    
    async def get_account_by_riot_id(self, game_name: str, tag_line: str, 
                                     region: Optional[str] = None, 
                                     retries: int = 5) -> Optional[Dict]:
        """Get account by Riot ID (Name#TAG)"""
        if not self.api_key:
            return None
        
        # If region specified, try that first
        regions_to_try = [region] if region else list(set(RIOT_REGIONS.values()))
        
        for routing in regions_to_try:
            url = f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
            
            for attempt in range(retries):
                try:
                    # Use longer timeout for Railway network
                    timeout = aiohttp.ClientTimeout(total=30, connect=10)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(url, headers=self.headers) as response:
                            if response.status == 200:
                                logger.info(f"✅ Found account in {routing}: {game_name}#{tag_line}")
                                return await response.json()
                            elif response.status == 404:
                                break  # Try next region
                            elif response.status == 429:
                                await asyncio.sleep(2)
                                continue
                except asyncio.TimeoutError:
                    logger.warning(f"⏱️ Timeout getting account (attempt {attempt + 1}/{retries})")
                    if attempt < retries - 1:
                        await asyncio.sleep(2)
                    continue
                except aiohttp.ClientError as e:
                    logger.warning(f"🌐 Network error (attempt {attempt + 1}/{retries}): {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(2)
                    continue
                except Exception as e:
                    logger.error(f"❌ Error getting account: {e}")
                    break
        
        logger.warning(f"⚠️ Account not found: {game_name}#{tag_line}")
        return None
    
    async def find_summoner_region(self, puuid: str, retries: int = 2) -> Optional[str]:
        """Auto-detect which region a summoner plays on - uses routing endpoints"""
        if not self.api_key:
            return None
        
        logger.info(f"🔍 Auto-detecting region for PUUID: {puuid[:8]}...")
        
        # Group regions by routing value for efficiency
        routing_groups = {}
        for region, routing in RIOT_REGIONS.items():
            if routing not in routing_groups:
                routing_groups[routing] = []
            routing_groups[routing].append(region)
        
        # Try each routing endpoint
        for routing, regions in routing_groups.items():
            url = f"https://{routing}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
            
            for attempt in range(retries):
                try:
                    timeout = aiohttp.ClientTimeout(total=10)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(url, headers=self.headers) as response:
                            if response.status == 200:
                                data = await response.json()
                                level = data.get('summonerLevel', 0)
                                if level > 1:
                                    # Return first region from this routing group
                                    region = regions[0]
                                    logger.info(f"✅ Found summoner via {routing} (Level {level}), using region: {region}")
                                    return region
                            elif response.status == 404:
                                break
                except:
                    if attempt < retries - 1:
                        await asyncio.sleep(0.3)
                    continue
        
        logger.warning(f"⚠️ Could not detect region for PUUID")
        return None
    
    async def get_summoner_by_puuid(self, puuid: str, region: str, 
                                   retries: int = 5) -> Optional[Dict]:
        """Get summoner data by PUUID - uses platform endpoint"""
        if not self.api_key:
            return None
        
        # Convert region to platform (e.g., 'eune' -> 'eun1')
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        url = f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 404:
                            return None
                        elif response.status == 429:
                            await asyncio.sleep(2)
                            continue
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout getting summoner (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except aiohttp.ClientError as e:
                logger.warning(f"🌐 Network error getting summoner (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except Exception as e:
                logger.error(f"❌ Error getting summoner: {e}")
                return None
        
        logger.warning(f"⚠️ Failed to get summoner after {retries} attempts")
        return None
    
    async def verify_third_party_code(self, summoner_id: str, region: str, 
                                     expected_code: str, retries: int = 3) -> bool:
        """Verify League client 3rd party code - uses platform endpoint"""
        if not self.api_key:
            return False
        
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        url = f"https://{platform}.api.riotgames.com/lol/platform/v4/third-party-code/by-summoner/{summoner_id}"
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            code = await response.text()
                            code = code.strip('"')
                            return code == expected_code
                        elif response.status == 404:
                            return False
                        elif response.status == 429:
                            await asyncio.sleep(1)
                            continue
            except Exception as e:
                logger.warning(f"Error verifying code (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
        
        return False
    
    async def get_ranked_stats(self, summoner_id: str, region: str, 
                              retries: int = 5) -> Optional[List[Dict]]:
        """Get ranked statistics - uses platform endpoint"""
        if not self.api_key:
            return None
        
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        url = f"https://{platform}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 404:
                            return None
                        elif response.status == 429:
                            await asyncio.sleep(2)
                            continue
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout getting ranked stats (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except aiohttp.ClientError as e:
                logger.warning(f"🌐 Network error getting ranked stats (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except Exception as e:
                logger.error(f"❌ Error getting ranked stats: {e}")
                return None
        
        logger.warning(f"⚠️ Failed to get ranked stats after {retries} attempts")
        return None
    
    async def get_champion_mastery(self, puuid: str, region: str, 
                                   count: int = 200, retries: int = 5) -> Optional[List[Dict]]:
        """Get top champion masteries - uses platform endpoint"""
        if not self.api_key:
            return None
        
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        url = f"https://{platform}.api.riotgames.com/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}/top?count={count}"
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 404:
                            return None
                        elif response.status == 429:
                            await asyncio.sleep(2)
                            continue
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout getting mastery (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except aiohttp.ClientError as e:
                logger.warning(f"🌐 Network error getting mastery (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except Exception as e:
                logger.error(f"❌ Error getting mastery: {e}")
                return None
        
        logger.warning(f"⚠️ Failed to get mastery after {retries} attempts")
        return None
