"""
Simple scraper to fetch pro players directly from their profiles
"""
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
from datetime import datetime

# Known pro players and streamers
KNOWN_PLAYERS = [
    "Faker", "Chovy", "Zeus", "Keria", "Oner",  # T1
    "Caps", "Upset", "Razork", "Elyoya", "Perkz",  # EU
    "TheBausffs", "Agurin", "Thebaus", "Kamet0",  # Streamers
    "Rekkles", "Doublelift", "Bjergsen", "Jensen",  # NA
    "Doinb", "TheShy", "Rookie", "JackeyLove",  # CN
    "ShowMaker", "Canyon", "Ruler", "Lehends",  # KR
]

async def scrape_single_player(session, player_name, retry_count=0):
    """Scrape a single player from lolpros.gg with exponential backoff"""
    max_retries = 3
    try:
        url_name = player_name.lower().replace(' ', '-')
        url = f"https://lolpros.gg/player/{url_name}"
        
        print(f"🔎 Checking {player_name}... ", end='', flush=True)
        
        async with session.get(url) as resp:
            if resp.status == 429:
                if retry_count < max_retries:
                    wait_time = (2 ** retry_count) * 10  # 10s, 20s, 40s
                    print(f"⚠️ Rate limited! Waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    return await scrape_single_player(session, player_name, retry_count + 1)
                else:
                    print(f"⚠️ Rate limited! Max retries reached")
                    return None
            
            if resp.status != 200:
                print(f"❌ Not found (status {resp.status})")
                return None
            
            html = await resp.text()
            
            # Basic validation
            if len(html) < 1000 or "404" in html or "not found" in html.lower():
                print(f"❌ No data")
                return None
            
            soup = BeautifulSoup(html, 'html.parser')
            
            player_data = {
                'name': player_name,
                'riot_id': None,
                'team': None,
                'role': None,
                'type': 'pro',
                'source': 'lolpros.gg',
                'profile_url': url,
                'leaguepedia': None
            }
            
            # Find all possible Riot ID elements
            # Check meta tags first
            riot_id_meta = soup.find('meta', property='og:title')
            if riot_id_meta:
                content = riot_id_meta.get('content', '')
                if '#' in content:
                    player_data['riot_id'] = content.split('-')[0].strip()
            
            # Check for Riot ID in various places
            for elem in soup.find_all(['span', 'div', 'p', 'h1', 'h2']):
                text = elem.get_text(strip=True)
                if '#' in text and len(text) < 50:  # Likely a Riot ID
                    player_data['riot_id'] = text
                    break
            
            # Find team name
            team_link = soup.find('a', href=lambda x: x and '/team/' in x)
            if team_link:
                player_data['team'] = team_link.get_text(strip=True)
            
            # Find role
            for elem in soup.find_all(['span', 'div']):
                text = elem.get_text(strip=True).lower()
                if text in ['top', 'jungle', 'mid', 'adc', 'support']:
                    player_data['role'] = text.capitalize()
                    break
            
            # Check for Leaguepedia link
            lp_link = soup.find('a', href=lambda x: x and 'lol.fandom.com' in x)
            if lp_link:
                player_data['leaguepedia'] = lp_link.get('href')
            
            # Check for Twitch to identify streamers
            twitch_link = soup.find('a', href=lambda x: x and 'twitch.tv' in x)
            if twitch_link and not player_data['team']:
                player_data['type'] = 'streamer'
            
            print(f"✅ Found! ID: {player_data['riot_id']}, Team: {player_data['team']}, Role: {player_data['role']}")
            return player_data
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

async def main():
    print("=" * 60)
    print("🚀 Simple Pro Player Scraper")
    print("=" * 60)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    players_found = []
    
    connector = aiohttp.TCPConnector(limit=1)
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(headers=headers, connector=connector, timeout=timeout) as session:
        for i, player_name in enumerate(KNOWN_PLAYERS, 1):
            print(f"[{i}/{len(KNOWN_PLAYERS)}] ", end='', flush=True)
            player = await scrape_single_player(session, player_name)
            if player:
                players_found.append(player)
            
            # Progressive delay - longer as we go to avoid cumulative rate limits
            base_delay = 8
            extra_delay = min(i // 5, 10)  # Add 1s every 5 requests, max +10s
            total_delay = base_delay + extra_delay
            
            if i < len(KNOWN_PLAYERS):
                print(f"⏱️ Waiting {total_delay}s...")
                await asyncio.sleep(total_delay)
    
    print("\n" + "=" * 60)
    print(f"✅ Found {len(players_found)} players out of {len(KNOWN_PLAYERS)}")
    print("=" * 60)
    
    # Group by type
    pros = [p for p in players_found if p['type'] == 'pro']
    streamers = [p for p in players_found if p['type'] == 'streamer']
    
    print(f"\n📊 Results:")
    print(f"  - Pro Players: {len(pros)}")
    print(f"  - Streamers: {len(streamers)}")
    
    # Save results
    results = {
        'pros': pros,
        'streamers': streamers,
        'total_pros': len(pros),
        'total_streamers': len(streamers),
        'timestamp': datetime.now().isoformat()
    }
    
    with open('scraped_players.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved to scraped_players.json")
    
    # Show some examples
    if players_found:
        print(f"\n📋 Sample players:")
        for player in players_found[:5]:
            print(f"  - {player['name']}: {player['riot_id']} ({player['team']} - {player['role']})")

if __name__ == "__main__":
    asyncio.run(main())
