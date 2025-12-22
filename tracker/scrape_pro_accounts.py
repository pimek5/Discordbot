"""
Pro Players & Streamers Account Scraper
Fetches data from multiple sources and adds to database
"""

import aiohttp
import asyncio
import json
import os
from dotenv import load_dotenv
import psycopg2
from bs4 import BeautifulSoup
import re

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

class ProAccountScraper:
    def __init__(self):
        self.session = None
        self.players_data = []
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def scrape_lolpros(self):
        """Scrape LoLPros.gg for pro player accounts"""
        print("\n🔍 Scraping LoLPros.gg...")
        
        try:
            # Try main page scraping
            url = "https://lolpros.gg/players"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find player cards/links
                    player_links = soup.find_all('a', href=re.compile(r'/player/'))
                    print(f"  Found {len(player_links)} player links")
                    
                    for link in player_links[:50]:  # Limit to first 50 for testing
                        player_url = link.get('href')
                        if not player_url.startswith('http'):
                            player_url = f"https://lolpros.gg{player_url}"
                        
                        player_name = link.get_text(strip=True)
                        if player_name:
                            await self.scrape_player_page(player_url, player_name, 'lolpros')
                            await asyncio.sleep(1)  # Rate limiting
                    
                    return True
        except Exception as e:
            print(f"  ❌ LoLPros error: {e}")
        
        return False
    
    async def scrape_player_page(self, url, player_name, source):
        """Scrape individual player page for accounts"""
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Look for account information
                    accounts = []
                    
                    # Common patterns for account names
                    account_elements = soup.find_all(['div', 'span', 'a'], class_=re.compile(r'account|summoner|riot[-_]?id', re.I))
                    
                    for elem in account_elements:
                        text = elem.get_text(strip=True)
                        # Look for Riot ID format (Name#TAG)
                        if '#' in text and len(text) < 50:
                            accounts.append(text)
                    
                    if accounts:
                        player_data = {
                            'name': player_name,
                            'accounts': list(set(accounts)),  # Remove duplicates
                            'source': source,
                            'url': url
                        }
                        self.players_data.append(player_data)
                        print(f"  ✅ {player_name}: {len(accounts)} accounts")
                    
        except Exception as e:
            print(f"  ⚠️ Error scraping {player_name}: {e}")
    
    async def scrape_deeplol(self):
        """Scrape DeepLoL for pro/streamer accounts"""
        print("\n🔍 Scraping DeepLoL.gg...")
        
        try:
            # Try pros page
            url = "https://www.deeplol.gg/pros"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find player cards
                    player_cards = soup.find_all(['div', 'a'], class_=re.compile(r'player|pro|card', re.I))
                    print(f"  Found {len(player_cards)} potential player elements")
                    
                    for card in player_cards[:30]:
                        # Extract player name and accounts
                        name_elem = card.find(['span', 'div', 'h2', 'h3'], class_=re.compile(r'name|player', re.I))
                        if name_elem:
                            player_name = name_elem.get_text(strip=True)
                            
                            # Look for accounts in this card
                            accounts = []
                            account_texts = card.find_all(text=re.compile(r'#[A-Z0-9]{3,5}'))
                            for text in account_texts:
                                if '#' in text:
                                    accounts.append(text.strip())
                            
                            if player_name and accounts:
                                player_data = {
                                    'name': player_name,
                                    'accounts': list(set(accounts)),
                                    'source': 'deeplol',
                                    'url': url
                                }
                                self.players_data.append(player_data)
                                print(f"  ✅ {player_name}: {len(accounts)} accounts")
                    
                    return True
        except Exception as e:
            print(f"  ❌ DeepLoL error: {e}")
        
        return False
    
    async def scrape_dpm(self):
        """Scrape DPM.lol for challenger players"""
        print("\n🔍 Scraping DPM.lol...")
        
        regions = ['euw1', 'kr', 'na1', 'eun1']
        
        for region in regions:
            try:
                url = f"https://dpm.lol/leaderboard/{region}"
                async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Find leaderboard entries
                        entries = soup.find_all(['tr', 'div'], class_=re.compile(r'leaderboard|player|rank', re.I))
                        print(f"  {region.upper()}: Found {len(entries)} entries")
                        
                        for entry in entries[:20]:  # Top 20 per region
                            # Look for Riot ID
                            riot_id = entry.find(text=re.compile(r'.+#[A-Z0-9]{3,5}'))
                            if riot_id:
                                riot_id = riot_id.strip()
                                if '#' in riot_id:
                                    player_data = {
                                        'name': riot_id.split('#')[0],
                                        'accounts': [riot_id],
                                        'source': 'dpm',
                                        'region': region,
                                        'url': url
                                    }
                                    self.players_data.append(player_data)
                
                await asyncio.sleep(2)  # Rate limiting between regions
                
            except Exception as e:
                print(f"  ⚠️ DPM {region} error: {e}")
    
    async def fetch_opgg_pros(self):
        """Try to fetch from OP.GG API"""
        print("\n🔍 Trying OP.GG API...")
        
        try:
            # OP.GG has some public endpoints
            url = "https://lol-web-api.op.gg/api/v1.0/internal/bypass/pro-players"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, dict) and 'data' in data:
                        pros = data['data']
                        print(f"  ✅ Found {len(pros)} pros from OP.GG")
                        
                        for pro in pros[:100]:
                            accounts = []
                            if 'summoner_name' in pro:
                                accounts.append(pro['summoner_name'])
                            if 'accounts' in pro:
                                accounts.extend(pro['accounts'])
                            
                            if pro.get('name') and accounts:
                                player_data = {
                                    'name': pro['name'],
                                    'accounts': accounts,
                                    'source': 'opgg',
                                    'team': pro.get('team_name'),
                                    'role': pro.get('position')
                                }
                                self.players_data.append(player_data)
                        
                        return True
        except Exception as e:
            print(f"  ❌ OP.GG error: {e}")
        
        return False
    
    def save_to_database(self):
        """Save scraped data to PostgreSQL database"""
        print(f"\n💾 Saving {len(self.players_data)} players to database...")
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        try:
            # Create table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tracked_pros (
                    id SERIAL PRIMARY KEY,
                    player_name TEXT NOT NULL,
                    accounts JSONB,
                    source TEXT,
                    team TEXT,
                    role TEXT,
                    region TEXT,
                    enabled BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(player_name)
                )
            """)
            conn.commit()
            print("  ✅ Table ready")
            
            added = 0
            updated = 0
            
            for player in self.players_data:
                try:
                    # Check if player exists
                    cur.execute("SELECT id, accounts FROM tracked_pros WHERE player_name = %s", 
                               (player['name'],))
                    existing = cur.fetchone()
                    
                    if existing:
                        # Update with new accounts (merge)
                        existing_accounts = existing[1] if existing[1] else []
                        all_accounts = list(set(existing_accounts + player['accounts']))
                        
                        cur.execute("""
                            UPDATE tracked_pros 
                            SET accounts = %s, source = %s
                            WHERE player_name = %s
                        """, (json.dumps(all_accounts), player['source'], player['name']))
                        updated += 1
                    else:
                        # Insert new player
                        cur.execute("""
                            INSERT INTO tracked_pros (player_name, accounts, source, team, role, region)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            player['name'],
                            json.dumps(player['accounts']),
                            player['source'],
                            player.get('team'),
                            player.get('role'),
                            player.get('region')
                        ))
                        added += 1
                    
                except Exception as e:
                    print(f"  ⚠️ Error saving {player['name']}: {e}")
                    conn.rollback()
                    continue
            
            conn.commit()
            print(f"\n✅ Database updated:")
            print(f"   • Added: {added} new players")
            print(f"   • Updated: {updated} existing players")
            
        except Exception as e:
            print(f"❌ Database error: {e}")
            conn.rollback()
        finally:
            cur.close()
            conn.close()
    
    def save_to_json(self, filename='scraped_pros.json'):
        """Save scraped data to JSON file for backup"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.players_data, f, indent=2, ensure_ascii=False)
        print(f"💾 Backup saved to {filename}")


async def main():
    print("=" * 60)
    print("PRO PLAYERS & STREAMERS ACCOUNT SCRAPER")
    print("=" * 60)
    
    async with ProAccountScraper() as scraper:
        # Try all sources
        await scraper.fetch_opgg_pros()
        await scraper.scrape_lolpros()
        await scraper.scrape_deeplol()
        await scraper.scrape_dpm()
        
        print(f"\n📊 Total players scraped: {len(scraper.players_data)}")
        
        if scraper.players_data:
            # Show sample
            print("\n📋 Sample data:")
            for player in scraper.players_data[:5]:
                print(f"  • {player['name']}: {player['accounts']}")
            
            # Save to JSON backup
            scraper.save_to_json()
            
            # Save to database
            scraper.save_to_database()
        else:
            print("\n⚠️ No data scraped. Check network or try different sources.")
    
    print("\n✅ Scraping complete!")


if __name__ == "__main__":
    asyncio.run(main())
