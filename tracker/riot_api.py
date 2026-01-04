"""
Riot API Module for Kassalytics
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
DDRAGON_VERSION = "15.1.1"  # Updated to include Zaahen (patch 15.1)
DDRAGON_BASE = f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}"

# Champion ID to name mapping (loaded at startup)
CHAMPION_ID_TO_NAME = {}

async def load_champion_data():
    """Load champion data from DDragon"""
    global CHAMPION_ID_TO_NAME
    try:
        logger.info("Loading champion data from DDragon...")
        timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f"{DDRAGON_BASE}/data/en_US/champion.json"
            logger.info(f"Fetching: {url}")
            async with session.get(url) as response:
                logger.info(f"Response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    for champ_name, champ_data in data['data'].items():
                        champ_id = int(champ_data['key'])
                        CHAMPION_ID_TO_NAME[champ_id] = champ_name
                    logger.info(f"Loaded {len(CHAMPION_ID_TO_NAME)} champions from DDragon")
                    
                    # Add manual overrides for newest champions if not in DDragon yet
                    if 950 not in CHAMPION_ID_TO_NAME:
                        CHAMPION_ID_TO_NAME[950] = "Mel"
                        logger.info("Added Mel (950) manually")
                    if 999 not in CHAMPION_ID_TO_NAME:
                        CHAMPION_ID_TO_NAME[999] = "Zaahen"
                        logger.info("Added Zaahen (999) manually")
                else:
                    logger.warning(f"DDragon returned status {response.status}")
    except asyncio.TimeoutError:
        logger.error("Timeout loading champion data from DDragon")
    except Exception as e:
        logger.error(f"Error loading champion data: {e}")

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


def platform_to_region(platform: str) -> str:
    """Map platform route (euw1) to short region code (euw). Fallback to euw."""
    for k, v in PLATFORM_ROUTES.items():
        if v == platform:
            return k
    return 'euw'


class RiotAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            'X-Riot-Token': api_key
        }
        if api_key:
            logger.info(f"🔑 API Key loaded: {api_key[:10]}...{api_key[-4:]} (len={len(api_key)})")
            logger.info(f"🔑 FULL KEY FOR DEBUG: {api_key}")
        else:
            logger.error("❌ No API key provided!")

    async def get_featured_games(self, platform: str = 'euw1', retries: int = 3) -> Optional[Dict]:
        """Get featured games (public matches) from spectator/v5 featured-games"""
        if not self.api_key:
            logger.error("❌ No API key available for featured games!")
            return None
        url = f"https://{platform}.api.riotgames.com/lol/spectator/v5/featured-games"
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"✅ Found {len(data.get('gameList', []))} games on {platform}")
                            return data
                        if response.status == 429:
                            logger.warning(f"⚠️ Rate limited on {platform}")
                            await asyncio.sleep(2 + attempt)
                            continue
                        if response.status == 403:
                            text = await response.text()
                            logger.error(f"❌ 403 Forbidden on {platform}. Response: {text[:200]}")
                            return None
                        # Other errors
                        text = await response.text()
                        logger.error(f"❌ Error {response.status} on {platform}: {text[:100]}")
                        return None
            except asyncio.TimeoutError:
                logger.warning(f"⏰ Timeout on {platform} (attempt {attempt+1})")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
            except Exception as e:
                logger.error(f"❌ Exception on {platform}: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
        return None
    
    async def get_account_by_riot_id(self, game_name: str, tag_line: str, 
                                     region: Optional[str] = None, 
                                     retries: int = 5) -> Optional[Dict]:
        """Get account by Riot ID (Name#TAG)"""
        if not self.api_key:
            return None
        
        # Build routing list: if region specified, try its routing first then fallback to all others
        if region:
            primary_routing = RIOT_REGIONS.get(region.lower())
            all_routings = list(set(RIOT_REGIONS.values()))
            regions_to_try = [r for r in [primary_routing] + all_routings if r]
        else:
            regions_to_try = list(set(RIOT_REGIONS.values()))
        
        for routing in regions_to_try:
            url = f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
            
            for attempt in range(retries):
                try:
                    # Escalating timeout per attempt to handle transient latency
                    timeout = aiohttp.ClientTimeout(total=20 + attempt * 5, connect=10)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(url, headers=self.headers) as response:
                            if response.status == 200:
                                logger.info(f"✅ Found account in {routing}: {game_name}#{tag_line}")
                                return await response.json()
                            elif response.status == 404:
                                logger.debug(f"🔍 Not found in routing {routing} (404) – trying next routing if available")
                                break  # Try next routing
                            elif response.status == 429:
                                logger.warning(f"⏳ Rate limited on routing {routing} (attempt {attempt + 1}/{retries})")
                                await asyncio.sleep(2 + attempt)
                                continue
                            else:
                                text = await response.text()
                                logger.warning(f"⚠️ Unexpected status {response.status} from {routing}: {text[:120]}")
                                break
                except asyncio.TimeoutError:
                    logger.warning(f"⏱️ Timeout (routing {routing}) attempt {attempt + 1}/{retries} for {game_name}#{tag_line}")
                    if attempt < retries - 1:
                        await asyncio.sleep(2)
                    continue
                except aiohttp.ClientError as e:
                    logger.warning(f"🌐 Network error (routing {routing}) attempt {attempt + 1}/{retries}: {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(2)
                    continue
                except Exception as e:
                    logger.error(f"❌ Error getting account: {e}")
                    break
        
        logger.warning(f"⚠️ Account not found after trying routings: {game_name}#{tag_line}")
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
        """Get summoner data by PUUID - uses platform endpoint
        
        NOTE: This endpoint NO LONGER returns 'id' field (encrypted summoner_id)
        Use get_summoner_by_name() if you need the encrypted summoner_id
        """
        if not self.api_key:
            return None
        
        # Convert region to platform (e.g., 'eune' -> 'eun1')
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        url = f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
        
        logger.info(f"🔍 Fetching summoner from platform: {platform} with PUUID: {puuid[:10]}...")
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"✅ Got summoner data from {platform}: {data}")
                            return data
                        elif response.status == 404:
                            logger.warning(f"❌ Summoner not found on {platform} (404)")
                            return None
                        elif response.status == 429:
                            logger.warning(f"⏳ Rate limited on {platform}")
                            await asyncio.sleep(2)
                            continue
                        else:
                            error_text = await response.text()
                            logger.error(f"❌ Unexpected status {response.status} from {platform}: {error_text[:200]}")
                            return None
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout getting summoner from {platform} (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except aiohttp.ClientError as e:
                logger.error(f"🌐 Network error getting summoner from {platform} (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except Exception as e:
                logger.error(f"❌ Error getting summoner: {e}")
                return None
        
        logger.warning(f"⚠️ Failed to get summoner after {retries} attempts")
        return None
    
    async def get_summoner_by_name(self, summoner_name: str, region: str, 
                                   retries: int = 5) -> Optional[Dict]:
        """Get summoner data by name - uses platform endpoint
        
        This endpoint DOES return 'id' field (encrypted summoner_id) which is needed for Spectator API
        Returns: {'id': 'encrypted_summoner_id', 'accountId': '...', 'puuid': '...', 'name': '...', etc}
        """
        if not self.api_key:
            return None
        
        # Convert region to platform (e.g., 'eune' -> 'eun1')
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        # URL encode the summoner name to handle special characters
        import urllib.parse
        encoded_name = urllib.parse.quote(summoner_name)
        url = f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{encoded_name}"
        
        logger.info(f"🔍 Fetching summoner from platform: {platform} with name: {summoner_name}")
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"✅ Got summoner data with ID: {data.get('id', 'MISSING')[:20]}...")
                            return data
                        elif response.status == 404:
                            logger.warning(f"❌ Summoner '{summoner_name}' not found on {platform} (404)")
                            return None
                        elif response.status == 429:
                            logger.warning(f"⏳ Rate limited on {platform}")
                            await asyncio.sleep(2)
                            continue
                        else:
                            error_text = await response.text()
                            logger.error(f"❌ Unexpected status {response.status} from {platform}: {error_text[:200]}")
                            return None
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout getting summoner from {platform} (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except aiohttp.ClientError as e:
                logger.error(f"🌐 Network error getting summoner from {platform} (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except Exception as e:
                logger.error(f"❌ Error getting summoner: {e}")
                return None
        
        logger.warning(f"⚠️ Failed to get summoner after {retries} attempts")
        return None
    
    async def verify_third_party_code(self, puuid: str, region: str, 
                                     expected_code: str, retries: int = 3) -> bool:
        """Verify League client 3rd party code - uses platform endpoint with PUUID"""
        if not self.api_key:
            return False
        
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        # Use PUUID endpoint instead of summoner ID
        url = f"https://{platform}.api.riotgames.com/lol/platform/v4/third-party-code/by-puuid/{puuid}"
        
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
                            retry_after = int(response.headers.get('Retry-After', 2))
                            await asyncio.sleep(retry_after)
                            continue
            except Exception as e:
                logger.warning(f"Error verifying code (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
        
        return False
    
    async def get_ranked_stats_by_puuid(self, puuid: str, region: str, 
                                       retries: int = 5) -> Optional[List[Dict]]:
        """Get ranked statistics using PUUID directly - NEW METHOD"""
        if not self.api_key:
            return None
        
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        # Try new PUUID-based endpoint first
        url = f"https://{platform}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
        
        logger.info(f"🔍 Fetching ranked stats directly with PUUID from {platform}")
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            ranked_data = await response.json()
                            logger.info(f"✅ Got ranked stats via PUUID: {len(ranked_data)} entries")
                            return ranked_data
                        elif response.status == 404:
                            logger.info(f"📭 No ranked data found (404) - player may be unranked")
                            return []  # No ranked data found
                        elif response.status == 429:
                            logger.warning(f"⏳ Rate limited (attempt {attempt + 1}/{retries})")
                            await asyncio.sleep(2)
                            continue
                        else:
                            error_text = await response.text()
                            logger.error(f"❌ Unexpected status {response.status}: {error_text[:200]}")
                            return []
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
                return []
        
        logger.warning(f"⚠️ Failed to get ranked stats after {retries} attempts")
        return []
    
    async def get_ranked_stats(self, summoner_id: str, region: str, 
                              retries: int = 5) -> Optional[List[Dict]]:
        """Get ranked statistics using summoner ID - DEPRECATED, use get_ranked_stats_by_puuid instead"""
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
                            return []  # No ranked data found
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
    
    async def get_challenger_league(self, region: str, queue: str = 'RANKED_SOLO_5x5', retries: int = 3) -> Optional[Dict]:
        """Get Challenger league entries for a region"""
        if not self.api_key:
            return None
        
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        url = f"https://{platform}.api.riotgames.com/lol/league/v4/challengerleagues/by-queue/{queue}"
        
        logger.info(f"🔍 Fetching Challenger league from {platform}")
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"✅ Got {len(data.get('entries', []))} Challenger entries from {platform}")
                            return data
                        elif response.status == 429:
                            await asyncio.sleep(2)
                            continue
            except Exception as e:
                logger.error(f"Error getting Challenger league: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
        
        return None
    
    async def get_grandmaster_league(self, region: str, queue: str = 'RANKED_SOLO_5x5', retries: int = 3) -> Optional[Dict]:
        """Get Grandmaster league entries for a region"""
        if not self.api_key:
            return None
        
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        url = f"https://{platform}.api.riotgames.com/lol/league/v4/grandmasterleagues/by-queue/{queue}"
        
        logger.info(f"🔍 Fetching Grandmaster league from {platform}")
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"✅ Got {len(data.get('entries', []))} Grandmaster entries from {platform}")
                            return data
                        elif response.status == 429:
                            await asyncio.sleep(2)
                            continue
            except Exception as e:
                logger.error(f"Error getting Grandmaster league: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
        
        return None
    
    async def get_master_league(self, region: str, queue: str = 'RANKED_SOLO_5x5', retries: int = 3) -> Optional[Dict]:
        """Get Master league entries for a region"""
        if not self.api_key:
            return None
        
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        url = f"https://{platform}.api.riotgames.com/lol/league/v4/masterleagues/by-queue/{queue}"
        
        logger.info(f"🔍 Fetching Master league from {platform}")
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"✅ Got {len(data.get('entries', []))} Master entries from {platform}")
                            return data
                        elif response.status == 429:
                            await asyncio.sleep(2)
                            continue
            except Exception as e:
                logger.error(f"Error getting Master league: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
        
        return None
    
    async def get_summoner_by_id(self, summoner_id: str, region: str, retries: int = 3) -> Optional[Dict]:
        """Get summoner data by summoner ID"""
        if not self.api_key:
            return None
        
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        url = f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/{summoner_id}"
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 429:
                            await asyncio.sleep(2)
                            continue
            except Exception as e:
                logger.debug(f"Error getting summoner by ID: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
        
        return None
    
    async def get_account_by_puuid(self, puuid: str, region: str, retries: int = 3) -> Optional[Dict]:
        """Get account info (gameName, tagLine) by PUUID"""
        if not self.api_key:
            return None
        
        # Use regional routing for account API
        regional_route = RIOT_REGIONS.get(region.lower(), 'europe')
        url = f"https://{regional_route}.api.riotgames.com/riot/account/v1/accounts/by-puuid/{puuid}"
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 429:
                            await asyncio.sleep(2)
                            continue
            except Exception as e:
                logger.debug(f"Error getting account by PUUID: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
        
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
    
    async def get_match_history(self, puuid: str, region: str, 
                                count: int = 10, retries: int = 5) -> Optional[List[str]]:
        """Get match IDs for a player - uses routing endpoint"""
        if not self.api_key:
            return None
        
        routing = RIOT_REGIONS.get(region.lower(), 'europe')
        url = f"https://{routing}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?count={count}"
        
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
                logger.warning(f"⏱️ Timeout getting match history (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except aiohttp.ClientError as e:
                logger.warning(f"🌐 Network error getting match history (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except Exception as e:
                logger.error(f"❌ Error getting match history: {e}")
                return None
        
        logger.warning(f"⚠️ Failed to get match history after {retries} attempts")
        return None
    
    async def get_match_details(self, match_id: str, region: str, 
                               retries: int = 5) -> Optional[Dict]:
        """Get detailed match data - uses routing endpoint"""
        if not self.api_key:
            return None
        
        routing = RIOT_REGIONS.get(region.lower(), 'europe')
        url = f"https://{routing}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        
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
                logger.warning(f"⏱️ Timeout getting match details (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except aiohttp.ClientError as e:
                logger.warning(f"🌐 Network error getting match details (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                continue
            except Exception as e:
                logger.error(f"❌ Error getting match details: {e}")
                return None
        
        
        logger.warning(f"⚠️ Failed to get match details after {retries} attempts")
        return None
    
    async def get_active_game(self, puuid: str, region: str, 
                             summoner_id: Optional[str] = None,
                             retries: int = 3) -> Optional[Dict]:
        """Get current active game for a player - SPECTATOR-V5
        
        Uses PUUID (not summoner_id) for Spectator V5 endpoint
        """
        if not self.api_key:
            return None
        
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        url = f"https://{platform}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{puuid}"
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=15, connect=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"✅ Active game found: Game ID {data.get('gameId')}, Queue {data.get('gameQueueConfigId')}")
                            return data
                        elif response.status == 404:
                            # Player not in game
                            return None
                        elif response.status == 429:
                            logger.warning(f"⚠️ Rate limit hit, retrying...")
                            await asyncio.sleep(1)
                            continue
                        elif response.status in [400, 403]:
                            # 400/403 = Normal errors (bad request, invalid token, timeout) - silent return
                            return None
                        else:
                            text = await response.text()
                            logger.error(f"❌ Spectator API error {response.status}: {text[:200]}")
                            return None
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout getting active game (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
            except aiohttp.ClientError as e:
                logger.warning(f"🌐 Network error getting active game (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
            except Exception as e:
                logger.error(f"❌ Error getting active game: {e}")
                return None
        
        return None

    async def get_active_game_by_summoner_id(self, summoner_id: str, region: str, 
                             retries: int = 3) -> Optional[Dict]:
        """Get current active game for a player using summoner_id directly - SPECTATOR-V5"""
        if not self.api_key:
            return None
        
        platform = PLATFORM_ROUTES.get(region.lower(), 'euw1')
        url = f"https://{platform}.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{summoner_id}"
        
        logger.info(f"🔍 Calling Spectator API for summoner {summoner_id[:10]}... on {platform}")
        
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=15, connect=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        logger.info(f"📡 API Response: {response.status} for summoner {summoner_id[:10]}...")
                        if response.status == 200:
                            data = await response.json()
                            logger.info(f"✅ Active game found: Game ID {data.get('gameId')}, Queue {data.get('gameQueueConfigId')}")
                            return data
                        elif response.status == 404:
                            # Player not in game
                            logger.info(f"❌ 404 - Player not in game")
                            return None
                        elif response.status == 429:
                            # Rate limit hit - wait longer before retry
                            retry_after = int(response.headers.get('Retry-After', 2))
                            logger.warning(f"⚠️ Rate limit hit, waiting {retry_after}s before retry...")
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            logger.warning(f"⚠️ Unexpected status code: {response.status}")
                            text = await response.text()
                            logger.debug(f"Response body: {text[:200]}")
                            return None
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout getting active game (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
            except aiohttp.ClientError as e:
                logger.warning(f"🌐 Network error getting active game (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                continue
            except Exception as e:
                logger.error(f"❌ Error getting active game: {e}")
                return None
        
        return None


