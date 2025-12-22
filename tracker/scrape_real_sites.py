"""
Web scraper for REAL pro player data from actual websites
Gets real Riot IDs from HTML pages
"""

import aiohttp
import asyncio
import json
import re
from bs4 import BeautifulSoup
from datetime import datetime

class RealProScraper:
    def __init__(self):
        self.players = []
        self.seen_riot_ids = set()
    
    async def scrape_lolpros(self):
        """Scrape lolpros.gg for real pro accounts"""
        print("\n🔍 Scraping lolpros.gg...")
        
        try:
            async with aiohttp.ClientSession() as session:
                # Main pros page
                url = "https://lolpros.gg/pros"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Find Riot IDs in format Name#TAG
                        riot_id_pattern = re.compile(r'([A-Za-z0-9\s]+)#([A-Z0-9]{3,5})')
                        
                        # Look in all text
                        all_text = soup.get_text()
                        matches = riot_id_pattern.findall(all_text)
                        
                        for name, tag in matches:
                            riot_id = f"{name.strip()}#{tag}"
                            if riot_id not in self.seen_riot_ids:
                                self.seen_riot_ids.add(riot_id)
                                player = {
                                    'riot_id': riot_id,
                                    'name': name.strip(),
                                    'tag': tag,
                                    'source': 'lolpros.gg'
                                }
                                self.players.append(player)
                        
                        # Also look for JSON data in scripts
                        scripts = soup.find_all('script')
                        for script in scripts:
                            if script.string:
                                # Look for embedded JSON with player data
                                try:
                                    if 'players' in script.string or 'pros' in script.string:
                                        # Try to extract JSON
                                        json_match = re.search(r'\{.*"players".*\}|\[.*\]', script.string, re.DOTALL)
                                        if json_match:
                                            data = json.loads(json_match.group(0))
                                            # Parse the data
                                            self.parse_json_players(data, 'lolpros.gg')
                                except:
                                    pass
                        
                        print(f"  ✅ Found {len([p for p in self.players if p['source'] == 'lolpros.gg'])} players from LoLPros")
                        return True
                    else:
                        print(f"  ⚠️ Status {resp.status}")
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        return False
    
    async def scrape_dpm(self):
        """Scrape dpm.lol leaderboards"""
        print("\n🔍 Scraping dpm.lol...")
        
        regions = ['euw1', 'kr', 'na1']
        
        for region in regions:
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"https://dpm.lol/leaderboard/{region}"
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            # DPM shows Riot IDs in leaderboard
                            riot_id_pattern = re.compile(r'([A-Za-z0-9\s]+)#([A-Z0-9]{3,5})')
                            
                            # Find all riot IDs
                            all_text = soup.get_text()
                            matches = riot_id_pattern.findall(all_text)
                            
                            region_count = 0
                            for name, tag in matches[:50]:  # Top 50 per region
                                riot_id = f"{name.strip()}#{tag}"
                                if riot_id not in self.seen_riot_ids:
                                    self.seen_riot_ids.add(riot_id)
                                    player = {
                                        'riot_id': riot_id,
                                        'name': name.strip(),
                                        'tag': tag,
                                        'region': region,
                                        'source': 'dpm.lol'
                                    }
                                    self.players.append(player)
                                    region_count += 1
                            
                            print(f"  ✅ {region.upper()}: Found {region_count} players")
                        else:
                            print(f"  ⚠️ {region.upper()}: Status {resp.status}")
                
                await asyncio.sleep(2)  # Rate limiting
                
            except Exception as e:
                print(f"  ❌ {region.upper()}: Error {e}")
        
        return len([p for p in self.players if p['source'] == 'dpm.lol']) > 0
    
    async def scrape_deeplol(self):
        """Scrape deeplol.gg"""
        print("\n🔍 Scraping deeplol.gg...")
        
        try:
            async with aiohttp.ClientSession() as session:
                # Try multiple pages
                pages = [
                    "https://www.deeplol.gg/pros",
                    "https://www.deeplol.gg/multi-search/pro"
                ]
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                for url in pages:
                    try:
                        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                            if resp.status == 200:
                                html = await resp.text()
                                soup = BeautifulSoup(html, 'html.parser')
                                
                                # Find Riot IDs
                                riot_id_pattern = re.compile(r'([A-Za-z0-9\s]+)#([A-Z0-9]{3,5})')
                                
                                # Search in text
                                all_text = soup.get_text()
                                matches = riot_id_pattern.findall(all_text)
                                
                                for name, tag in matches:
                                    riot_id = f"{name.strip()}#{tag}"
                                    if riot_id not in self.seen_riot_ids:
                                        self.seen_riot_ids.add(riot_id)
                                        player = {
                                            'riot_id': riot_id,
                                            'name': name.strip(),
                                            'tag': tag,
                                            'source': 'deeplol.gg'
                                        }
                                        self.players.append(player)
                                
                                # Also search in data attributes and JSON
                                for elem in soup.find_all(attrs={'data-riot-id': True}):
                                    riot_id = elem['data-riot-id']
                                    if riot_id and '#' in riot_id and riot_id not in self.seen_riot_ids:
                                        self.seen_riot_ids.add(riot_id)
                                        name, tag = riot_id.split('#')
                                        player = {
                                            'riot_id': riot_id,
                                            'name': name,
                                            'tag': tag,
                                            'source': 'deeplol.gg'
                                        }
                                        self.players.append(player)
                    except Exception as e:
                        print(f"  ⚠️ {url}: {e}")
                
                deeplol_count = len([p for p in self.players if p['source'] == 'deeplol.gg'])
                if deeplol_count > 0:
                    print(f"  ✅ Found {deeplol_count} players from DeepLoL")
                    return True
                else:
                    print(f"  ⚠️ No players found")
        
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        return False
    
    def parse_json_players(self, data, source):
        """Parse JSON data for players"""
        try:
            if isinstance(data, dict):
                if 'players' in data:
                    data = data['players']
                elif 'pros' in data:
                    data = data['pros']
            
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        # Look for riot ID fields
                        riot_id = None
                        for key in ['riotId', 'riot_id', 'summonerName', 'summoner_name', 'gameName']:
                            if key in item and item[key] and '#' in str(item[key]):
                                riot_id = item[key]
                                break
                        
                        if riot_id and riot_id not in self.seen_riot_ids:
                            self.seen_riot_ids.add(riot_id)
                            name, tag = riot_id.split('#')
                            player = {
                                'riot_id': riot_id,
                                'name': name,
                                'tag': tag,
                                'source': source,
                                'team': item.get('team') or item.get('teamName'),
                                'role': item.get('role') or item.get('position'),
                                'region': item.get('region')
                            }
                            self.players.append(player)
        except:
            pass
    
    def save_to_json(self, filename='real_scraped_pros.json'):
        """Save to JSON"""
        print(f"\n💾 Saving to {filename}...")
        
        # Group by source
        by_source = {}
        for p in self.players:
            source = p['source']
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(p)
        
        data = {
            'scraped_at': datetime.now().isoformat(),
            'total_players': len(self.players),
            'total_unique_riot_ids': len(self.seen_riot_ids),
            'by_source': {source: len(players) for source, players in by_source.items()},
            'players': self.players
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"  ✅ Saved {len(self.players)} players!")
    
    def display_summary(self):
        """Display summary"""
        print(f"\n📊 SCRAPING SUMMARY")
        print(f"{'='*60}")
        print(f"Total unique Riot IDs: {len(self.seen_riot_ids)}")
        print(f"Total player entries: {len(self.players)}")
        
        # By source
        by_source = {}
        for p in self.players:
            source = p['source']
            by_source[source] = by_source.get(source, 0) + 1
        
        print(f"\nBy source:")
        for source, count in sorted(by_source.items()):
            print(f"  • {source}: {count}")
        
        # Show top 20
        print(f"\n📋 First 20 players with REAL Riot IDs:")
        for i, player in enumerate(self.players[:20], 1):
            info = f"{player['riot_id']}"
            if player.get('region'):
                info += f" | {player['region'].upper()}"
            if player.get('team'):
                info += f" | {player['team']}"
            print(f"  {i:2d}. {info}")


async def main():
    print("=" * 70)
    print("WEB SCRAPER FOR REAL PRO DATA")
    print("Scraping: lolpros.gg, dpm.lol, deeplol.gg")
    print("=" * 70)
    
    scraper = RealProScraper()
    
    # Scrape all sources
    await scraper.scrape_lolpros()
    await scraper.scrape_dpm()
    await scraper.scrape_deeplol()
    
    if scraper.players:
        scraper.display_summary()
        scraper.save_to_json()
        
        print(f"\n💡 File saved: real_scraped_pros.json")
        print(f"   Use this data to populate your database!")
    else:
        print(f"\n⚠️ No players found. Sites might have changed or require JS rendering.")
        print(f"💡 Alternative: Use browser DevTools to inspect pages and find API endpoints")
    
    print(f"\n✅ Scraping complete!")


if __name__ == "__main__":
    asyncio.run(main())
