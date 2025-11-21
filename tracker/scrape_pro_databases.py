"""
Scrape and cache pro player databases from LoLPros and DeepLoL
Run this script periodically to update the local database
"""

import aiohttp
import asyncio
import json
import re
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('scraper')

class ProPlayerScraper:
    def __init__(self):
        self.players = []
        
    async def scrape_lolpros(self):
        """Scrape all players from LoLPros.gg"""
        logger.info("🔍 Starting LoLPros scrape...")
        
        async with aiohttp.ClientSession() as session:
            # Try to get players list page
            urls_to_try = [
                "https://lolpros.gg/players",
                "https://lolpros.gg/api/players",
                "https://lolpros.gg/players.json",
            ]
            
            for url in urls_to_try:
                logger.info(f"  Trying: {url}")
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            content_type = resp.headers.get('content-type', '')
                            
                            if 'json' in content_type:
                                # Direct JSON response
                                data = await resp.json()
                                logger.info(f"  ✅ Got JSON! Type: {type(data)}")
                                
                                if isinstance(data, list):
                                    for player in data:
                                        await self._process_lolpros_player(player, session)
                                elif isinstance(data, dict):
                                    players_list = data.get('players', data.get('data', []))
                                    for player in players_list:
                                        await self._process_lolpros_player(player, session)
                                return
                            else:
                                # HTML response
                                html = await resp.text()
                                
                                # Look for embedded JSON
                                json_patterns = [
                                    r'window\.__NUXT__\s*=\s*({.+?})</script>',
                                    r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.+?)</script>',
                                    r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                                ]
                                
                                for pattern in json_patterns:
                                    match = re.search(pattern, html, re.DOTALL)
                                    if match:
                                        try:
                                            json_str = match.group(1)
                                            data = json.loads(json_str)
                                            logger.info(f"  ✅ Found embedded JSON!")
                                            
                                            # Navigate through common Nuxt.js structures
                                            players_list = self._extract_players_from_nuxt(data)
                                            
                                            if players_list:
                                                logger.info(f"  ✅ Found {len(players_list)} players in JSON")
                                                for player in players_list:
                                                    await self._process_lolpros_player(player, session)
                                                return
                                        except Exception as e:
                                            logger.warning(f"  ⚠️ JSON parse error: {e}")
                                            continue
                                
                                # Fallback: parse HTML links
                                logger.info("  ⚠️ No JSON found, parsing HTML links...")
                                soup = BeautifulSoup(html, 'html.parser')
                                
                                # Find all player links
                                player_links = []
                                for link in soup.find_all('a', href=True):
                                    href = link['href']
                                    if '/player/' in href:
                                        player_name = href.split('/player/')[-1].split('/')[0].split('?')[0]
                                        if player_name and player_name not in player_links:
                                            player_links.append(player_name)
                                
                                logger.info(f"  ✅ Found {len(player_links)} player links")
                                
                                # Fetch each player's page (limit to avoid rate limits)
                                for i, player_slug in enumerate(player_links[:200]):  # First 200 players
                                    if i % 10 == 0:
                                        logger.info(f"  Progress: {i}/{len(player_links[:200])}")
                                    
                                    await self._fetch_lolpros_player_page(player_slug, session)
                                    await asyncio.sleep(0.5)  # Rate limit protection
                                
                                return
                                
                except Exception as e:
                    logger.warning(f"  ❌ Error: {e}")
                    continue
            
            logger.warning("❌ Could not scrape LoLPros")
    
    def _extract_players_from_nuxt(self, data):
        """Extract players list from Nuxt.js data structure"""
        possible_paths = [
            ['players'],
            ['data', 'players'],
            ['state', 'players'],
            ['fetch', 'players'],
            ['data', 'data', 'players'],
        ]
        
        for path in possible_paths:
            current = data
            for key in path:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    current = None
                    break
            
            if current and isinstance(current, list):
                return current
        
        return []
    
    async def _fetch_lolpros_player_page(self, player_slug, session):
        """Fetch individual player page from LoLPros"""
        url = f"https://lolpros.gg/player/{player_slug}"
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return
                
                html = await resp.text()
                
                # Look for JSON in page
                json_patterns = [
                    r'window\.__NUXT__\s*=\s*({.+?})</script>',
                    r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.+?)</script>',
                ]
                
                for pattern in json_patterns:
                    match = re.search(pattern, html, re.DOTALL)
                    if match:
                        try:
                            json_str = match.group(1)
                            data = json.loads(json_str)
                            
                            # Try to extract player data
                            player_data = self._extract_player_from_json(data, player_slug)
                            if player_data:
                                self.players.append(player_data)
                                return
                        except:
                            continue
                
        except Exception as e:
            logger.debug(f"Error fetching {player_slug}: {e}")
    
    def _extract_player_from_json(self, data, player_slug):
        """Extract player info from JSON"""
        possible_paths = [
            ['data', 'player'],
            ['state', 'player'],
            ['fetch', 'player'],
            ['player'],
        ]
        
        for path in possible_paths:
            current = data
            for key in path:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    current = None
                    break
            
            if current and isinstance(current, dict):
                # Extract accounts
                accounts = []
                accounts_data = current.get('accounts', current.get('summoners', []))
                
                for acc in accounts_data:
                    if isinstance(acc, dict):
                        accounts.append({
                            'summoner_name': acc.get('name', acc.get('summonerName', acc.get('gameName', ''))),
                            'tag': acc.get('tag', acc.get('tagLine', '')),
                            'region': acc.get('region', acc.get('platformId', 'euw')).lower().replace('1', ''),
                            'lp': acc.get('lp', acc.get('leaguePoints', 0)),
                            'rank': acc.get('rank', acc.get('tier', ''))
                        })
                
                if accounts:
                    return {
                        'player_name': current.get('name', current.get('playerName', player_slug)),
                        'team': current.get('team', ''),
                        'role': current.get('role', current.get('position', '')),
                        'region': current.get('region', current.get('country', '')),
                        'accounts': accounts,
                        'source': 'lolpros'
                    }
        
        return None
    
    async def _process_lolpros_player(self, player_data, session):
        """Process a player entry from LoLPros"""
        if not isinstance(player_data, dict):
            return
        
        player_name = player_data.get('name', player_data.get('playerName', ''))
        if not player_name:
            return
        
        accounts = []
        accounts_data = player_data.get('accounts', player_data.get('summoners', []))
        
        for acc in accounts_data:
            if isinstance(acc, dict):
                accounts.append({
                    'summoner_name': acc.get('name', acc.get('summonerName', '')),
                    'tag': acc.get('tag', ''),
                    'region': acc.get('region', 'euw').lower(),
                    'lp': acc.get('lp', 0)
                })
        
        self.players.append({
            'player_name': player_name,
            'team': player_data.get('team', ''),
            'role': player_data.get('role', ''),
            'region': player_data.get('region', ''),
            'accounts': accounts,
            'source': 'lolpros'
        })
    
    async def scrape_deeplol(self, category='pro'):
        """Scrape all players from DeepLoL (pro or strm)"""
        logger.info(f"🔍 Starting DeepLoL {category.upper()} scrape...")
        
        async with aiohttp.ClientSession() as session:
            # Try to get players list
            urls_to_try = [
                f"https://www.deeplol.gg/api/{category}",
                f"https://www.deeplol.gg/{category}",
            ]
            
            for url in urls_to_try:
                logger.info(f"  Trying: {url}")
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            content_type = resp.headers.get('content-type', '')
                            
                            if 'json' in content_type:
                                data = await resp.json()
                                logger.info(f"  ✅ Got JSON!")
                                
                                if isinstance(data, list):
                                    for player in data:
                                        await self._process_deeplol_player(player, category, session)
                                elif isinstance(data, dict):
                                    players_list = data.get('players', data.get('data', []))
                                    for player in players_list:
                                        await self._process_deeplol_player(player, category, session)
                                return
                            else:
                                # HTML - parse for player links
                                html = await resp.text()
                                soup = BeautifulSoup(html, 'html.parser')
                                
                                player_links = []
                                for link in soup.find_all('a', href=True):
                                    href = link['href']
                                    if f'/{category}/' in href:
                                        player_name = href.split(f'/{category}/')[-1].split('/')[0].split('?')[0]
                                        if player_name and player_name not in player_links:
                                            player_links.append(player_name)
                                
                                logger.info(f"  ✅ Found {len(player_links)} player links")
                                
                                # Fetch each player (limit to first 200)
                                for i, player_slug in enumerate(player_links[:200]):
                                    if i % 10 == 0:
                                        logger.info(f"  Progress: {i}/{len(player_links[:200])}")
                                    
                                    await self._fetch_deeplol_player_page(player_slug, category, session)
                                    await asyncio.sleep(0.5)
                                
                                return
                                
                except Exception as e:
                    logger.warning(f"  ❌ Error: {e}")
                    continue
    
    async def _fetch_deeplol_player_page(self, player_slug, category, session):
        """Fetch individual player page from DeepLoL"""
        url = f"https://www.deeplol.gg/{category}/{player_slug}"
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return
                
                html = await resp.text()
                
                # Look for JSON
                json_patterns = [
                    r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                    r'window\.__NEXT_DATA__\s*=\s*({.+?})</script>',
                    r'<script id="__NEXT_DATA__"[^>]*>({.+?})</script>',
                ]
                
                for pattern in json_patterns:
                    match = re.search(pattern, html, re.DOTALL)
                    if match:
                        try:
                            json_str = match.group(1)
                            data = json.loads(json_str)
                            
                            player_data = self._extract_deeplol_player(data, player_slug, category)
                            if player_data:
                                self.players.append(player_data)
                                return
                        except:
                            continue
                
        except Exception as e:
            logger.debug(f"Error fetching {player_slug}: {e}")
    
    def _extract_deeplol_player(self, data, player_slug, category):
        """Extract player from DeepLoL JSON"""
        possible_paths = [
            ['player'],
            ['props', 'pageProps', 'player'],
            ['data', 'player'],
        ]
        
        for path in possible_paths:
            current = data
            for key in path:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    current = None
                    break
            
            if current and isinstance(current, dict):
                accounts = []
                accounts_data = current.get('accounts', [])
                
                for acc in accounts_data:
                    if isinstance(acc, dict):
                        accounts.append({
                            'summoner_name': acc.get('gameName', acc.get('name', '')),
                            'tag': acc.get('tagLine', acc.get('tag', '')),
                            'region': acc.get('region', 'euw').lower(),
                            'lp': acc.get('leaguePoints', acc.get('lp', 0)),
                            'rank': acc.get('tier', '')
                        })
                
                if accounts:
                    return {
                        'player_name': current.get('name', player_slug),
                        'team': current.get('team', ''),
                        'role': current.get('role', ''),
                        'region': current.get('region', ''),
                        'accounts': accounts,
                        'source': f'deeplol_{category}'
                    }
        
        return None
    
    async def _process_deeplol_player(self, player_data, category, session):
        """Process DeepLoL player"""
        if not isinstance(player_data, dict):
            return
        
        player_name = player_data.get('name', '')
        if not player_name:
            return
        
        accounts = []
        accounts_data = player_data.get('accounts', [])
        
        for acc in accounts_data:
            if isinstance(acc, dict):
                accounts.append({
                    'summoner_name': acc.get('gameName', acc.get('name', '')),
                    'tag': acc.get('tagLine', ''),
                    'region': acc.get('region', 'euw').lower(),
                    'lp': acc.get('leaguePoints', 0)
                })
        
        self.players.append({
            'player_name': player_name,
            'team': player_data.get('team', ''),
            'role': player_data.get('role', ''),
            'region': player_data.get('region', ''),
            'accounts': accounts,
            'source': f'deeplol_{category}'
        })
    
    def save_database(self, filename='pro_players_database.json'):
        """Save scraped data to JSON file"""
        logger.info(f"💾 Saving {len(self.players)} players to {filename}")
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.players, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ Saved!")
        
        # Print summary
        sources = {}
        total_accounts = 0
        for player in self.players:
            source = player['source']
            sources[source] = sources.get(source, 0) + 1
            total_accounts += len(player.get('accounts', []))
        
        logger.info(f"\n📊 Summary:")
        logger.info(f"  Total players: {len(self.players)}")
        logger.info(f"  Total accounts: {total_accounts}")
        for source, count in sources.items():
            logger.info(f"  {source}: {count} players")

async def main():
    scraper = ProPlayerScraper()
    
    # Scrape LoLPros
    await scraper.scrape_lolpros()
    
    # Scrape DeepLoL Pro
    await scraper.scrape_deeplol('pro')
    
    # Scrape DeepLoL Streamers
    await scraper.scrape_deeplol('strm')
    
    # Save to file
    scraper.save_database('tracker/pro_players_database.json')

if __name__ == '__main__':
    asyncio.run(main())
