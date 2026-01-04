"""
Advanced Pro Player & Streamer Scraper
Scrapes multiple League of Legends analytics sites to discover pro players and streamers

Supported Sources:
1. lolpros.gg - Player profiles with Leaguepedia links
2. op.gg - High elo leaderboards (Challenger/GM/Master)
3. u.gg - Pro builds and player data
4. leaguepedia.com - Official esports wiki
5. liquipedia.net - Esports database

Usage:
    python scrape_all_pros.py [--source all|lolpros|opgg|ugg|leaguepedia] [--region all|kr|euw|na]
"""

import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import json
import logging
from datetime import datetime
import argparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('pro_scraper')


class ProPlayerScraper:
    """Scraper for discovering pro players and streamers"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        self.results = {
            'pros': [],
            'streamers': [],
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def scrape_lolpros_gg(self, player_names: List[str]) -> List[Dict]:
        """
        Scrape lolpros.gg for specific players
        
        Args:
            player_names: List of player names to check
            
        Returns:
            List of player data dicts
        """
        logger.info(f"🔍 Scraping lolpros.gg for {len(player_names)} players...")
        players = []
        
        for name in player_names:
            try:
                url = f"https://lolpros.gg/player/{name.lower().replace(' ', '-')}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status != 200:
                            logger.debug(f"Player not found: {name} (status {response.status})")
                            continue
                        
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Extract player data
                        player_data = {
                            'name': name,
                            'source': 'lolpros.gg',
                            'url': url,
                            'type': None,
                            'team': None,
                            'leaguepedia': None,
                            'socials': {}
                        }
                        
                        # Check for Leaguepedia link
                        leaguepedia = soup.find('a', href=lambda x: x and 'lol.fandom.com' in x)
                        if leaguepedia:
                            player_data['leaguepedia'] = leaguepedia.get('href')
                            player_data['type'] = 'pro'  # Has Leaguepedia = notable player
                        
                        # Check for team
                        team_elem = soup.find(text=lambda x: x and 'Team' in x)
                        if team_elem and team_elem.find_parent():
                            team_name = team_elem.find_parent().find_next('img')
                            if team_name:
                                player_data['team'] = team_name.get('alt', '')
                                player_data['type'] = 'pro'
                        
                        # Check for streaming platforms
                        for link in soup.find_all('a', href=True):
                            href = link.get('href', '')
                            if 'twitch.tv' in href:
                                player_data['socials']['twitch'] = href
                                if not player_data['type']:
                                    player_data['type'] = 'streamer'
                            elif 'youtube.com' in href:
                                player_data['socials']['youtube'] = href
                                if not player_data['type']:
                                    player_data['type'] = 'streamer'
                        
                        if player_data['type']:
                            players.append(player_data)
                            logger.info(f"✅ Found {player_data['type']}: {name}")
                
                await asyncio.sleep(2)  # Rate limiting
                
            except Exception as e:
                logger.warning(f"Error scraping {name}: {e}")
                continue
        
        return players
    
    async def scrape_opgg_leaderboard(self, region: str = 'euw') -> List[Dict]:
        """
        Scrape OP.GG leaderboard for high elo players
        
        Args:
            region: Server region (euw, kr, na, etc.)
            
        Returns:
            List of high elo player names
        """
        logger.info(f"🔍 Scraping OP.GG {region.upper()} Challenger leaderboard...")
        players = []
        
        try:
            url = f"https://www.op.gg/leaderboards/tier?region={region}&tier=challenger"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch OP.GG leaderboard: {response.status}")
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find player entries (structure may vary)
                    # This is a simplified example - actual selectors may differ
                    player_elements = soup.find_all('td', class_='summoner-name')
                    
                    for elem in player_elements[:50]:  # Top 50 players
                        try:
                            name_tag = elem.find('a')
                            if name_tag:
                                player_name = name_tag.get_text(strip=True)
                                players.append({
                                    'name': player_name,
                                    'source': 'op.gg',
                                    'region': region,
                                    'tier': 'Challenger',
                                    'type': 'high_elo'
                                })
                        except:
                            continue
                    
                    logger.info(f"✅ Found {len(players)} Challenger players on OP.GG {region.upper()}")
        
        except Exception as e:
            logger.error(f"Error scraping OP.GG: {e}")
        
        return players
    
    async def scrape_leaguepedia_pros(self) -> List[Dict]:
        """
        Scrape Leaguepedia for current pro players
        
        Returns:
            List of pro player data
        """
        logger.info("🔍 Scraping Leaguepedia for active pro players...")
        players = []
        
        try:
            # Leaguepedia uses Cargo tables - need to query their API
            url = "https://lol.fandom.com/wiki/Special:CargoExport"
            params = {
                'tables': 'Players,CurrentLeagues',
                'fields': 'Players.Player,Players.Team,Players.Country,Players.Role',
                'where': 'Players.IsRetired=0',
                'limit': '500',
                'format': 'json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=self.headers, timeout=aiohttp.ClientTimeout(total=20)) as response:
                    if response.status != 200:
                        logger.warning(f"Leaguepedia API error: {response.status}")
                        return []
                    
                    data = await response.json()
                    
                    for player in data:
                        players.append({
                            'name': player.get('Player', 'Unknown'),
                            'team': player.get('Team', ''),
                            'role': player.get('Role', ''),
                            'country': player.get('Country', ''),
                            'source': 'leaguepedia',
                            'type': 'pro',
                            'url': f"https://lol.fandom.com/wiki/{player.get('Player', '').replace(' ', '_')}"
                        })
                    
                    logger.info(f"✅ Found {len(players)} active pro players on Leaguepedia")
        
        except Exception as e:
            logger.error(f"Error scraping Leaguepedia: {e}")
        
        return players
    
    async def scrape_ugg_pros(self) -> List[Dict]:
        """
        Scrape U.GG for pro builds and player data
        
        Returns:
            List of pro player names
        """
        logger.info("🔍 Scraping U.GG for pro player builds...")
        players = []
        
        try:
            url = "https://u.gg/lol/pro-play"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        logger.warning(f"U.GG error: {response.status}")
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find pro player sections
                    # Note: U.GG structure changes frequently, this is a template
                    player_links = soup.find_all('a', href=lambda x: x and '/lol/pro-player/' in x)
                    
                    for link in player_links:
                        player_name = link.get_text(strip=True)
                        if player_name:
                            players.append({
                                'name': player_name,
                                'source': 'u.gg',
                                'type': 'pro',
                                'url': f"https://u.gg{link.get('href')}"
                            })
                    
                    logger.info(f"✅ Found {len(players)} pro players on U.GG")
        
        except Exception as e:
            logger.error(f"Error scraping U.GG: {e}")
        
        return players
    
    async def scrape_all(self, regions: List[str] = ['euw', 'kr', 'na']) -> Dict:
        """
        Run all scrapers and aggregate results
        
        Args:
            regions: List of regions to scrape
            
        Returns:
            Dictionary with all discovered players
        """
        logger.info("🚀 Starting comprehensive pro/streamer scraping...")
        
        # Scrape Leaguepedia first (authoritative source for pros)
        leaguepedia_players = await self.scrape_leaguepedia_pros()
        
        # Get player names from Leaguepedia to check on lolpros.gg
        player_names = [p['name'] for p in leaguepedia_players]
        
        # Scrape lolpros.gg for these players (get accounts, socials)
        lolpros_players = await self.scrape_lolpros_gg(player_names[:20])  # Limit to avoid rate limits
        
        # Scrape OP.GG leaderboards
        opgg_tasks = [self.scrape_opgg_leaderboard(region) for region in regions]
        opgg_results = await asyncio.gather(*opgg_tasks)
        opgg_players = [p for result in opgg_results for p in result]
        
        # Scrape U.GG
        ugg_players = await self.scrape_ugg_pros()
        
        # Aggregate results
        all_pros = leaguepedia_players + lolpros_players + ugg_players
        all_high_elo = opgg_players
        
        # Deduplicate by name
        unique_pros = {}
        for player in all_pros:
            name = player.get('name', '').lower()
            if name and name not in unique_pros:
                unique_pros[name] = player
        
        self.results = {
            'pros': list(unique_pros.values()),
            'high_elo': all_high_elo,
            'total_pros': len(unique_pros),
            'total_high_elo': len(all_high_elo),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return self.results
    
    def save_results(self, filename: str = 'scraped_pros.json'):
        """Save results to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Results saved to {filename}")


async def main():
    parser = argparse.ArgumentParser(description='Scrape pro players and streamers from analytics sites')
    parser.add_argument('--regions', nargs='+', default=['euw', 'kr', 'na'], help='Regions to scrape')
    parser.add_argument('--output', default='scraped_pros.json', help='Output JSON file')
    args = parser.parse_args()
    
    scraper = ProPlayerScraper()
    
    print("\n" + "="*60)
    print("🎮 Advanced Pro Player & Streamer Scraper")
    print("="*60 + "\n")
    
    results = await scraper.scrape_all(regions=args.regions)
    
    print("\n" + "="*60)
    print("📊 RESULTS")
    print("="*60)
    print(f"✅ Total Pro Players: {results['total_pros']}")
    print(f"✅ Total High Elo Players: {results['total_high_elo']}")
    
    print(f"\n📝 Sample Pro Players:")
    for player in results['pros'][:10]:
        print(f"   • {player.get('name')} ({player.get('team', 'N/A')}) - {player.get('source')}")
    
    print(f"\n📝 Sample High Elo Players:")
    for player in results['high_elo'][:10]:
        print(f"   • {player.get('name')} ({player.get('region', 'N/A').upper()}) - {player.get('tier')}")
    
    scraper.save_results(args.output)
    
    print("\n" + "="*60)
    print(f"✅ Scraping complete! Results saved to {args.output}")
    print("="*60 + "\n")


if __name__ == '__main__':
    asyncio.run(main())
