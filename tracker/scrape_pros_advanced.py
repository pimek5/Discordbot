"""
Advanced Pro Account Scraper - Using Known APIs
Fetches from working endpoints discovered in testing
"""

import aiohttp
import asyncio
import json
import os
from dotenv import load_dotenv
import psycopg2
from datetime import datetime

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

# Known working sources
SOURCES = {
    'u.gg': 'https://stats2.u.gg/lol/1.5/pro_player_list/15_23',
    'probuildstats': 'https://probuildstats.com/data/pros.json',
    'lolpros_backup': 'https://raw.githubusercontent.com/lolpros/lolpros-data/main/pros.json',
}

# Streamers to add manually
# HOW TO GET CORRECT RIOT IDs:
# 1. Go to https://www.op.gg or https://u.gg
# 2. Search for streamer name
# 3. Copy EXACT Riot ID format: "Name#TAG" (example: "Agurin#4367")
# 4. Check their stream to see all accounts they use
# 
# OR use /trackpros command in Discord to add them with correct data
#
# Template:
# 'StreamerName': {
#     'accounts': ['RiotID#TAG', 'AltAccount#TAG'],
#     'region': 'euw1',  # euw1, na1, kr, etc.
#     'role': 'Top',      # Top, Jungle, Mid, ADC, Support
#     'source': 'manual'
# },

KNOWN_STREAMERS = {
    # Add your streamers here with CORRECT Riot IDs
    # Example (replace with real data):
    # 'Agurin': {
    #     'accounts': ['Agurin#4367'],  # Get from op.gg or their stream
    #     'region': 'euw1',
    #     'role': 'Jungle',
    #     'source': 'manual'
    # },
}


class AdvancedProScraper:
    def __init__(self):
        self.players = []
        
    async def fetch_from_api(self, name, url):
        """Fetch from a known API endpoint"""
        print(f"\n🔍 Fetching from {name}...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        # Parse based on source
                        if name == 'u.gg':
                            return self.parse_ugg(data)
                        elif name == 'probuildstats':
                            return self.parse_probuildstats(data)
                        elif 'lolpros' in name:
                            return self.parse_lolpros(data)
                    else:
                        print(f"  ⚠️ Status {resp.status}")
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        return []
    
    def parse_ugg(self, data):
        """Parse U.GG pro player data"""
        players = []
        
        try:
            if isinstance(data, list):
                for player in data:
                    accounts = []
                    
                    # U.GG format
                    if 'summoner_name' in player:
                        accounts.append(player['summoner_name'])
                    if 'accounts' in player:
                        accounts.extend(player['accounts'])
                    
                    if player.get('name') or player.get('player_name'):
                        player_data = {
                            'name': player.get('name') or player.get('player_name'),
                            'accounts': accounts,
                            'team': player.get('team'),
                            'role': player.get('position') or player.get('role'),
                            'region': player.get('region', 'unknown'),
                            'source': 'u.gg'
                        }
                        players.append(player_data)
            
            print(f"  ✅ Parsed {len(players)} players from U.GG")
        except Exception as e:
            print(f"  ⚠️ Parse error: {e}")
        
        return players
    
    def parse_probuildstats(self, data):
        """Parse ProBuildStats data"""
        players = []
        
        try:
            if isinstance(data, dict):
                if 'pros' in data:
                    data = data['pros']
                elif 'players' in data:
                    data = data['players']
            
            if isinstance(data, list):
                for player in data:
                    accounts = []
                    
                    # Different possible account fields
                    for field in ['summoner_name', 'summonerName', 'riotId', 'accounts']:
                        if field in player:
                            val = player[field]
                            if isinstance(val, str):
                                accounts.append(val)
                            elif isinstance(val, list):
                                accounts.extend(val)
                    
                    if player.get('name'):
                        player_data = {
                            'name': player['name'],
                            'accounts': accounts,
                            'team': player.get('team'),
                            'role': player.get('role') or player.get('position'),
                            'region': player.get('region', 'unknown'),
                            'source': 'probuildstats'
                        }
                        players.append(player_data)
            
            print(f"  ✅ Parsed {len(players)} players from ProBuildStats")
        except Exception as e:
            print(f"  ⚠️ Parse error: {e}")
        
        return players
    
    def parse_lolpros(self, data):
        """Parse LoLPros data"""
        players = []
        
        try:
            if isinstance(data, dict) and 'players' in data:
                data = data['players']
            
            if isinstance(data, list):
                for player in data:
                    accounts = []
                    
                    if 'accounts' in player:
                        for acc in player['accounts']:
                            if isinstance(acc, dict):
                                if 'summonerName' in acc:
                                    accounts.append(acc['summonerName'])
                                elif 'riotId' in acc:
                                    accounts.append(acc['riotId'])
                            elif isinstance(acc, str):
                                accounts.append(acc)
                    
                    if player.get('name'):
                        player_data = {
                            'name': player['name'],
                            'accounts': accounts,
                            'team': player.get('team'),
                            'role': player.get('role'),
                            'region': player.get('region', 'unknown'),
                            'source': 'lolpros'
                        }
                        players.append(player_data)
            
            print(f"  ✅ Parsed {len(players)} players from LoLPros")
        except Exception as e:
            print(f"  ⚠️ Parse error: {e}")
        
        return players
    
    def add_known_streamers(self):
        """Add known streamers/content creators"""
        print(f"\n📺 Adding {len(KNOWN_STREAMERS)} known streamers...")
        
        for name, data in KNOWN_STREAMERS.items():
            player_data = {
                'name': name,
                'accounts': data['accounts'],
                'role': data['role'],
                'region': data['region'],
                'source': data['source'],
                'team': 'Streamer'
            }
            self.players.append(player_data)
        
        print(f"  ✅ Added {len(KNOWN_STREAMERS)} streamers")
    
    async def fetch_all_sources(self):
        """Fetch from all known sources"""
        tasks = []
        for name, url in SOURCES.items():
            tasks.append(self.fetch_from_api(name, url))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                self.players.extend(result)
            elif isinstance(result, Exception):
                print(f"  ⚠️ Task failed: {result}")
    
    def save_to_database(self):
        """Save to PostgreSQL database"""
        print(f"\n💾 Saving {len(self.players)} players to database...")
        
        if not self.players:
            print("  ⚠️ No players to save")
            return
        
        if not DATABASE_URL:
            print("  ⚠️ DATABASE_URL not configured - skipping database save")
            print("  💡 Data saved to JSON file instead")
            return
        
        try:
            conn = psycopg2.connect(DATABASE_URL)
        except Exception as e:
            print(f"  ⚠️ Cannot connect to database: {e}")
            print("  💡 Data saved to JSON file instead")
            return
        cur = conn.cursor()
        
        try:
            # Create table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tracked_pros (
                    id SERIAL PRIMARY KEY,
                    player_name TEXT NOT NULL UNIQUE,
                    accounts JSONB DEFAULT '[]'::jsonb,
                    source TEXT,
                    team TEXT,
                    role TEXT,
                    region TEXT,
                    enabled BOOLEAN DEFAULT true,
                    last_updated TIMESTAMP DEFAULT NOW(),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Create index for faster lookups
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_tracked_pros_player_name 
                ON tracked_pros(player_name)
            """)
            
            conn.commit()
            print("  ✅ Table ready")
            
            added = 0
            updated = 0
            errors = 0
            
            for player in self.players:
                try:
                    # Clean accounts list
                    accounts = [acc.strip() for acc in player.get('accounts', []) if acc]
                    if not accounts:
                        continue
                    
                    # Check if exists
                    cur.execute(
                        "SELECT id, accounts FROM tracked_pros WHERE player_name = %s",
                        (player['name'],)
                    )
                    existing = cur.fetchone()
                    
                    if existing:
                        # Merge accounts
                        existing_accounts = existing[1] if existing[1] else []
                        all_accounts = list(set(existing_accounts + accounts))
                        
                        cur.execute("""
                            UPDATE tracked_pros 
                            SET accounts = %s, 
                                source = %s, 
                                team = COALESCE(%s, team),
                                role = COALESCE(%s, role),
                                region = COALESCE(%s, region),
                                last_updated = NOW()
                            WHERE player_name = %s
                        """, (
                            json.dumps(all_accounts),
                            player.get('source'),
                            player.get('team'),
                            player.get('role'),
                            player.get('region'),
                            player['name']
                        ))
                        updated += 1
                    else:
                        # Insert new
                        cur.execute("""
                            INSERT INTO tracked_pros 
                            (player_name, accounts, source, team, role, region)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            player['name'],
                            json.dumps(accounts),
                            player.get('source'),
                            player.get('team'),
                            player.get('role'),
                            player.get('region')
                        ))
                        added += 1
                    
                    # Commit every 10 players
                    if (added + updated) % 10 == 0:
                        conn.commit()
                    
                except Exception as e:
                    print(f"  ⚠️ Error saving {player.get('name', 'unknown')}: {e}")
                    errors += 1
                    conn.rollback()
            
            conn.commit()
            
            print(f"\n✅ Database updated:")
            print(f"   • Added: {added} new players")
            print(f"   • Updated: {updated} existing players")
            print(f"   • Errors: {errors}")
            
            # Show total in database
            cur.execute("SELECT COUNT(*) FROM tracked_pros WHERE enabled = true")
            total = cur.fetchone()[0]
            print(f"   • Total active pros: {total}")
            
        except Exception as e:
            print(f"❌ Database error: {e}")
            conn.rollback()
        finally:
            cur.close()
            conn.close()
    
    def save_to_json(self, filename='scraped_pros_advanced.json'):
        """Save to JSON backup"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'scraped_at': datetime.now().isoformat(),
                'total_players': len(self.players),
                'players': self.players
            }, f, indent=2, ensure_ascii=False)
        print(f"💾 Backup saved to {filename}")


async def main():
    print("=" * 70)
    print("ADVANCED PRO PLAYERS & STREAMERS SCRAPER")
    print("=" * 70)
    
    scraper = AdvancedProScraper()
    
    # Add known streamers first
    scraper.add_known_streamers()
    
    # Fetch from all sources
    await scraper.fetch_all_sources()
    
    print(f"\n📊 SUMMARY")
    print(f"   Total players collected: {len(scraper.players)}")
    
    if scraper.players:
        # Group by source
        by_source = {}
        for player in scraper.players:
            source = player.get('source', 'unknown')
            by_source[source] = by_source.get(source, 0) + 1
        
        print(f"\n   By source:")
        for source, count in sorted(by_source.items()):
            print(f"     • {source}: {count}")
        
        # Show samples
        print(f"\n📋 Sample players:")
        for player in scraper.players[:10]:
            accounts_str = ', '.join(player['accounts'][:3])
            if len(player['accounts']) > 3:
                accounts_str += f" (+{len(player['accounts'])-3} more)"
            print(f"  • {player['name']}: {accounts_str}")
        
        # Save
        scraper.save_to_json()
        scraper.save_to_database()
    else:
        print("\n⚠️ No data collected. Check network connection.")
    
    print("\n✅ Scraping complete!")


if __name__ == "__main__":
    asyncio.run(main())
