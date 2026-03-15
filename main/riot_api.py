"""
Riot API Module for Kassalytics
Handles all Riot Games API interactions with retry logic
"""

import aiohttp
import asyncio
import json
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

# Match routing for match-v5
MATCH_ROUTING = {
    'br1': 'americas', 'la1': 'americas', 'la2': 'americas', 'na1': 'americas', 'oc1': 'americas',
    'euw1': 'europe', 'eun1': 'europe', 'tr1': 'europe', 'ru': 'europe',
    'kr': 'asia', 'jp1': 'asia',
    'sg2': 'sea', 'ph2': 'sea', 'th2': 'sea', 'tw2': 'sea', 'vn2': 'sea'
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
        print("🔄 Loading champion data from DDragon...")
        timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f"{DDRAGON_BASE}/data/en_US/champion.json"
            print(f"📡 Fetching: {url}")
            async with session.get(url) as response:
                print(f"📡 Response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    for champ_name, champ_data in data['data'].items():
                        champ_id = int(champ_data['key'])
                        CHAMPION_ID_TO_NAME[champ_id] = champ_name
                    print(f"✅ Loaded {len(CHAMPION_ID_TO_NAME)} champions from DDragon")
                    logger.info(f"✅ Loaded {len(CHAMPION_ID_TO_NAME)} champions from DDragon")
                else:
                    print(f"⚠️ DDragon returned status {response.status}")
    except asyncio.TimeoutError:
        print("❌ Timeout loading champion data from DDragon")
        logger.error("❌ Timeout loading champion data from DDragon")
    except Exception as e:
        print(f"❌ Error loading champion data: {e}")
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
        if api_key:
            logger.info(f"🔑 Main Bot API Key: {api_key[:10]}...{api_key[-4:]} (len={len(api_key)})")
        else:
            logger.error("❌ No API key provided!")
    
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
    
    async def get_riot_id_from_puuid(self, puuid: str) -> Optional[Dict]:
        """Get current Riot ID (Name#TAG) from PUUID"""
        if not self.api_key:
            return None
        
        # Try all routing regions
        for routing in set(RIOT_REGIONS.values()):
            url = f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-puuid/{puuid}"
            
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            return {
                                'gameName': data.get('gameName'),
                                'tagLine': data.get('tagLine')
                            }
                        elif response.status == 404:
                            continue
            except:
                continue
        
        logger.warning(f"⚠️ Could not get Riot ID for PUUID {puuid[:8]}")
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
                            await asyncio.sleep(1)
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
                             retries: int = 3) -> Optional[Dict]:
        """Get current active game for a player - SPECTATOR-V5"""
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
                            return await response.json()
                        elif response.status == 404:
                            # Player not in game
                            return None
                        elif response.status == 429:
                            await asyncio.sleep(1)
                            continue
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
    
    async def check_decay_status(self, puuid: str, region: str) -> Dict:
        """Check if account is at risk of LP decay with accurate banking system
        
        Decay rules:
        - Diamond: max 30 days bank, decay starts after 30 days inactivity
        - Master/GM/Chall: max 14 days bank, decay starts after 14 days inactivity
        
        Returns dict with:
        - at_risk: bool
        - days_remaining: int
        - days_in_bank: int
        - max_bank: int
        - last_ranked_game: str
        - tier: str
        - lp: int
        - message: str
        """
        from datetime import datetime, timezone, timedelta
        
        # Pobierz ranked stats
        ranked_stats = await self.get_ranked_stats_by_puuid(puuid, region)
        if not ranked_stats:
            return {
                'at_risk': False,
                'days_remaining': None,
                'days_in_bank': 0,
                'max_bank': 0,
                'lp_loss_per_day': None,
                'days_until_demote': None,
                'last_ranked_game': None,
                'tier': 'UNRANKED',
                'lp': 0,
                'message': '❌ Brak danych rankingowych'
            }
        
        # Znajdź solo queue i sprawdź co dokładnie zawiera
        solo_queue = None
        for queue in ranked_stats:
            if queue.get('queueType') == 'RANKED_SOLO_5x5':
                solo_queue = queue
                logger.debug(f"🔍 Solo queue data: {queue}")  # Log all fields
                break
        
        if not solo_queue:
            return {
                'at_risk': False,
                'days_remaining': None,
                'days_in_bank': 0,
                'max_bank': 0,
                'lp_loss_per_day': None,
                'days_until_demote': None,
                'last_ranked_game': None,
                'tier': 'UNRANKED',
                'lp': 0,
                'message': '❌ Brak danych Solo Queue'
            }
        
        tier = solo_queue.get('tier', 'UNRANKED')
        rank = solo_queue.get('rank', '')
        lp = solo_queue.get('leaguePoints', 0)
        wins = solo_queue.get('wins', 0)
        losses = solo_queue.get('losses', 0)
        
        # Check if there's inactiveStartTime field from API
        inactive = solo_queue.get('inactive', False)
        inactive_start_time = solo_queue.get('inactiveStartTime')
        
        logger.debug(f"📊 Decay data: tier={tier} {rank} lp={lp} inactive={inactive}, inactiveStartTime={inactive_start_time}")
        
        # Decay działa tylko dla Diamond+
        decay_tiers = ['DIAMOND', 'MASTER', 'GRANDMASTER', 'CHALLENGER']
        if tier not in decay_tiers:
            return {
                'at_risk': False,
                'days_remaining': None,
                'days_in_bank': 0,
                'max_bank': 0,
                'lp_loss_per_day': None,
                'days_until_demote': None,
                'last_ranked_game': None,
                'tier': f'{tier} {rank}',
                'lp': lp,
                'message': f'✅ {tier} {rank} ({lp} LP) - no decay below Diamond'
            }
        
        # Ustaw parametry decay wg rankingu
        if tier == 'DIAMOND':
            decay_starts_after = 28
            lp_loss_per_day = 50
        else:  # Master+
            decay_starts_after = 14
            lp_loss_per_day = 75
        
        # Najlepsze źródło: jeśli API ma inactiveStartTime, użyj tego
        if inactive and inactive_start_time:
            try:
                # inactiveStartTime może być timestamp w ms
                if isinstance(inactive_start_time, (int, float)):
                    inactive_date = datetime.fromtimestamp(inactive_start_time / 1000, tz=timezone.utc)
                else:
                    # Lub może być string ISO format
                    inactive_date = datetime.fromisoformat(str(inactive_start_time).replace('Z', '+00:00'))
                
                now = datetime.now(timezone.utc)
                days_since_inactive = (now - inactive_date).days
                
                logger.info(f"✅ Using API inactiveStartTime: {days_since_inactive} days inactive")
                
                max_bank = decay_starts_after
                days_in_bank = max_bank
                days_remaining = max(0, max_bank - days_since_inactive)
                days_until_demote = max(0, lp // lp_loss_per_day) if days_remaining <= 0 else None
                
                if days_remaining <= 0:
                    return {
                        'at_risk': True,
                        'days_remaining': 0,
                        'days_in_bank': 0,
                        'max_bank': max_bank,
                        'lp_loss_per_day': lp_loss_per_day,
                        'days_until_demote': days_until_demote,
                        'last_ranked_game': inactive_date.strftime('%Y-%m-%d %H:%M UTC'),
                        'tier': f'{tier} {rank}',
                        'lp': lp,
                        'message': f'🚨 **DECAY ACTIVE!** {tier} {rank} ({lp} LP)\nInactive since: {days_since_inactive} days ago'
                    }
                elif days_remaining <= 3:
                    return {
                        'at_risk': True,
                        'days_remaining': days_remaining,
                        'days_in_bank': max(0, days_remaining),
                        'max_bank': max_bank,
                        'lp_loss_per_day': lp_loss_per_day,
                        'days_until_demote': None,
                        'last_ranked_game': inactive_date.strftime('%Y-%m-%d %H:%M UTC'),
                        'tier': f'{tier} {rank}',
                        'lp': lp,
                        'message': f'⚠️ **DECAY WARNING!** {tier} {rank} ({lp} LP)\n{days_remaining} days left in bank'
                    }
                else:
                    return {
                        'at_risk': False,
                        'days_remaining': days_remaining,
                        'days_in_bank': days_remaining,
                        'max_bank': max_bank,
                        'lp_loss_per_day': lp_loss_per_day,
                        'days_until_demote': None,
                        'last_ranked_game': inactive_date.strftime('%Y-%m-%d %H:%M UTC'),
                        'tier': f'{tier} {rank}',
                        'lp': lp,
                        'message': f'✅ {tier} {rank} ({lp} LP) - Safe for {days_remaining} days'
                    }
            except Exception as e:
                logger.warning(f"⚠️ Could not parse inactiveStartTime: {e}, falling back to match history")
        
        # Fallback: użyj match history jeśli API nie ma inactiveStartTime
        logger.info(f"📊 Falling back to match history for decay calculation")
        
        # Pobierz match history (ostatnie 100 gier aby mieć pełny obraz)
        match_ids = await self.get_match_history(puuid, region, count=100)
        if not match_ids:
            return {
                'at_risk': True,
                'days_remaining': 0,
                'days_in_bank': 0,
                'max_bank': decay_starts_after,
                'lp_loss_per_day': lp_loss_per_day,
                'days_until_demote': max(0, lp // lp_loss_per_day),
                'last_ranked_game': None,
                'tier': f'{tier} {rank}',
                'lp': lp,
                'message': f'⚠️ {tier} {rank} ({lp} LP) - no match history found'
            }
        
        # Zbierz daty wszystkich ranked solo queue gier
        ranked_game_dates = []
        for match_id in match_ids:
            match_data = await self.get_match_details(match_id, region)
            if not match_data:
                continue
            
            info = match_data.get('info', {})
            if info.get('queueId') == 420:  # Ranked Solo/Duo
                timestamp = info.get('gameCreation')
                if timestamp:
                    game_date = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                    ranked_game_dates.append(game_date)
        
        if not ranked_game_dates:
            return {
                'at_risk': True,
                'days_remaining': 0,
                'days_in_bank': 0,
                'max_bank': decay_starts_after,
                'lp_loss_per_day': lp_loss_per_day,
                'days_until_demote': max(0, lp // lp_loss_per_day),
                'last_ranked_game': None,
                'tier': f'{tier} {rank}',
                'lp': lp,
                'message': f'⚠️ {tier} {rank} ({lp} LP) - no ranked games in history'
            }
        
        # Sortuj daty od najstarszej do najnowszej
        ranked_game_dates.sort()
        
        now = datetime.now(timezone.utc)
        last_game_date = ranked_game_dates[-1]
        
        # Parametry banku wg ranku
        max_bank = decay_starts_after
        bank_per_game = 7 if tier == 'DIAMOND' else 1  # Diamond +7 dni/grę, Master+ +1 dzień/grę
        
        # Symuluj bank od ostatnich 60 dni (lub od najstarszej gry)
        simulation_start = max(ranked_game_dates[0], now - timedelta(days=60))
        
        # Grupuj gry po dniach (bez godzin)
        games_by_day = {}
        for game_date in ranked_game_dates:
            if game_date >= simulation_start:
                day_key = game_date.date()
                games_by_day[day_key] = games_by_day.get(day_key, 0) + 1
        
        # Symuluj bank dzień po dniu
        current_bank = max_bank  # Startujemy z pełnym bankiem
        current_date = simulation_start.date()
        today = now.date()
        
        while current_date <= today:
            if current_date in games_by_day:
                # Była gra tego dnia - dodaj dni do banku za każdą grę
                games_played = games_by_day[current_date]
                current_bank += games_played * bank_per_game
                current_bank = min(current_bank, max_bank)  # Cap na max
            else:
                # Nie było gry - bank maleje o 1
                current_bank -= 1
            
            current_date += timedelta(days=1)
        
        days_remaining = max(0, current_bank)
        days_in_bank = days_remaining
        days_until_demote = max(0, lp // lp_loss_per_day) if days_remaining <= 0 else None
        
        # Oblicz dni od ostatniej gry dla wyświetlenia
        days_since = (now - last_game_date).days
        
        logger.info(f"✅ Simulated bank for {tier} {rank}: {days_remaining}/{max_bank} days (last game: {last_game_date.strftime('%Y-%m-%d')})")
        
        # Jeśli days_remaining <= 0, decay aktywny
        if days_remaining <= 0:
            return {
                'at_risk': True,
                'days_remaining': 0,
                'days_in_bank': 0,
                'max_bank': max_bank,
                'lp_loss_per_day': lp_loss_per_day,
                'days_until_demote': days_until_demote,
                'last_ranked_game': last_game_date.strftime('%Y-%m-%d %H:%M UTC'),
                'tier': f'{tier} {rank}',
                'lp': lp,
                'message': f'🚨 **DECAY ACTIVE!** {tier} {rank} ({lp} LP)\n'
                          f'Last game: {days_since} days ago\n'
                          f'Bank empty — play immediately!'
            }
        elif days_remaining <= 3:
            return {
                'at_risk': True,
                'days_remaining': days_remaining,
                'days_in_bank': max(0, days_remaining),
                'max_bank': max_bank,
                'lp_loss_per_day': lp_loss_per_day,
                'days_until_demote': None,
                'last_ranked_game': last_game_date.strftime('%Y-%m-%d %H:%M UTC'),
                'tier': f'{tier} {rank}',
                'lp': lp,
                'message': f'⚠️ **DECAY WARNING!** {tier} {rank} ({lp} LP)\n'
                          f'Last game: {days_since} days ago\n'
                          f'Bank: {days_remaining}/{max_bank} days\n'
                          f'**{days_remaining} days left!**'
            }
        elif days_remaining <= 7:
            return {
                'at_risk': True,
                'days_remaining': days_remaining,
                'days_in_bank': days_remaining,
                'max_bank': max_bank,
                'lp_loss_per_day': lp_loss_per_day,
                'days_until_demote': None,
                'last_ranked_game': last_game_date.strftime('%Y-%m-%d %H:%M UTC'),
                'tier': f'{tier} {rank}',
                'lp': lp,
                'message': f'⚡ {tier} {rank} ({lp} LP)\n'
                          f'Last game: {days_since} days ago\n'
                          f'Bank: {days_remaining}/{max_bank} days\n'
                          f'{days_remaining} days remaining'
            }
        else:
            return {
                'at_risk': False,
                'days_remaining': days_remaining,
                'days_in_bank': days_remaining,
                'max_bank': max_bank,
                'lp_loss_per_day': lp_loss_per_day,
                'days_until_demote': None,
                'last_ranked_game': last_game_date.strftime('%Y-%m-%d %H:%M UTC'),
                'tier': f'{tier} {rank}',
                'lp': lp,
                'message': f'✅ {tier} {rank} ({lp} LP)\n'
                          f'Last game: {days_since} days ago\n'
                          f'Bank: {days_remaining}/{max_bank} days\n'
                          f'Safe for {days_remaining} more days'
            }
