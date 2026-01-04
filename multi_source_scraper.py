"""
Multi-source scraper for pro players and high elo players
Uses available sources: Leaguepedia, Riot API, manual known players
"""
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
from datetime import datetime
import os

# Riot API key from environment or config
RIOT_API_KEY = os.getenv('RIOT_API_KEY', '')

# Known pro players to seed the database
KNOWN_PROS = {
    'Faker': {'riot_id': 'Hide on bush#KR1', 'team': 'T1', 'role': 'Mid', 'region': 'kr'},
    'Chovy': {'riot_id': 'Gen Chovy#KR1', 'team': 'Gen.G', 'role': 'Mid', 'region': 'kr'},
    'Zeus': {'riot_id': 'T1 Zeus#KR1', 'team': 'T1', 'role': 'Top', 'region': 'kr'},
    'Keria': {'riot_id': 'T1 Keria#KR1', 'team': 'T1', 'role': 'Support', 'region': 'kr'},
    'Oner': {'riot_id': 'T1 Oner#KR1', 'team': 'T1', 'role': 'Jungle', 'region': 'kr'},
    'Caps': {'riot_id': 'G2 Caps#EUW', 'team': 'G2 Esports', 'role': 'Mid', 'region': 'euw'},
    'Upset': {'riot_id': 'FNC Upset#EUW', 'team': 'Fnatic', 'role': 'ADC', 'region': 'euw'},
    'Razork': {'riot_id': 'FNC Razork#EUW', 'team': 'Fnatic', 'role': 'Jungle', 'region': 'euw'},
    'Rekkles': {'riot_id': 'Rekkles#EUW', 'team': 'Free Agent', 'role': 'ADC', 'region': 'euw'},
    'Perkz': {'riot_id': 'G2 Perkz#EUW', 'team': 'G2 Esports', 'role': 'ADC', 'region': 'euw'},
    'ShowMaker': {'riot_id': 'DK ShowMaker#KR1', 'team': 'Dplus KIA', 'role': 'Mid', 'region': 'kr'},
    'Canyon': {'riot_id': 'DK Canyon#KR1', 'team': 'Dplus KIA', 'role': 'Jungle', 'region': 'kr'},
    'Ruler': {'riot_id': 'JDG Ruler#KR1', 'team': 'JD Gaming', 'role': 'ADC', 'region': 'kr'},
    'Doinb': {'riot_id': 'FPX Doinb#NA1', 'team': 'Retired', 'role': 'Mid', 'region': 'na'},
    'TheShy': {'riot_id': 'WBG TheShy#KR1', 'team': 'Weibo Gaming', 'role': 'Top', 'region': 'kr'},
    'Rookie': {'riot_id': 'IG Rookie#KR1', 'team': 'Free Agent', 'role': 'Mid', 'region': 'kr'},
}

KNOWN_STREAMERS = {
    'TheBausffs': {
        'accounts': [
            'Thebausffs#COOL',
            'Dangerous Dork#Lick',
            'Streaming Badboy#INT',
            'Thebausffs#3710',
            'Bosch Drill#EUW',
            'Mollusca Slime#Yummy',
            'Silly Snail#Öga',
        ],
        'region': 'euw',
        'main_role': 'Top'
    },
    'Agurin': {
        'accounts': ['Agurin#EUW', 'Agurin#9464'],
        'region': 'euw',
        'main_role': 'Jungle'
    },
    'Kamet0': {
        'accounts': ['Kamet0#EUW'],
        'region': 'euw',
        'main_role': 'Jungle'
    },
    'RatIRL': {
        'accounts': ['Rat IRL#EUNE', 'RAT IRL#EUW'],
        'region': 'eune',
        'main_role': 'ADC'
    },
    'Doublelift': {
        'accounts': ['Doublelift#NA1'],
        'region': 'na',
        'main_role': 'ADC'
    },
}

async def scrape_leaguepedia():
    """Scrape Leaguepedia for pro player list"""
    print("\n📚 Scraping Leaguepedia...")
    players = []
    
    url = "https://lol.fandom.com/wiki/List_of_Current_Professional_Players"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as resp:
                if resp.status != 200:
                    print(f"   ❌ Failed: {resp.status}")
                    return players
                
                html = await resp.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Find player tables
                tables = soup.find_all('table', class_='wikitable')
                
                for table in tables[:3]:  # First few tables usually have active players
                    rows = table.find_all('tr')[1:]  # Skip header
                    
                    for row in rows[:50]:  # Limit to avoid too much data
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 4:
                            try:
                                player_name = cells[0].get_text(strip=True)
                                team = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                                role = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                                
                                if player_name and len(player_name) < 30:
                                    players.append({
                                        'name': player_name,
                                        'team': team,
                                        'role': role,
                                        'type': 'pro',
                                        'source': 'leaguepedia'
                                    })
                            except Exception as e:
                                continue
                
                print(f"   ✅ Found {len(players)} players")
                return players
                
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return players

async def get_riot_challenger_players(region='euw1'):
    """Get Challenger players from Riot API"""
    print(f"\n🏆 Fetching Challenger ladder ({region})...")
    players = []
    
    if not RIOT_API_KEY:
        print("   ⚠️  No Riot API key - skipping")
        return players
    
    try:
        url = f"https://{region}.api.riotgames.com/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5"
        headers = {'X-Riot-Token': RIOT_API_KEY}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=30) as resp:
                if resp.status != 200:
                    print(f"   ❌ Failed: {resp.status}")
                    return players
                
                data = await resp.json()
                entries = data.get('entries', [])
                
                # Get top 100 players
                top_players = sorted(entries, key=lambda x: x.get('leaguePoints', 0), reverse=True)[:100]
                
                for entry in top_players:
                    players.append({
                        'summoner_name': entry.get('summonerName'),
                        'summoner_id': entry.get('summonerId'),
                        'lp': entry.get('leaguePoints'),
                        'wins': entry.get('wins'),
                        'losses': entry.get('losses'),
                        'type': 'high_elo',
                        'rank': 'Challenger',
                        'region': region,
                        'source': 'riot_api'
                    })
                
                print(f"   ✅ Found {len(players)} Challenger players")
                return players
                
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return players

async def get_riot_grandmaster_players(region='euw1'):
    """Get Grandmaster players from Riot API"""
    print(f"\n🎖️  Fetching Grandmaster ladder ({region})...")
    players = []
    
    if not RIOT_API_KEY:
        print("   ⚠️  No Riot API key - skipping")
        return players
    
    try:
        url = f"https://{region}.api.riotgames.com/lol/league/v4/grandmasterleagues/by-queue/RANKED_SOLO_5x5"
        headers = {'X-Riot-Token': RIOT_API_KEY}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=30) as resp:
                if resp.status != 200:
                    print(f"   ❌ Failed: {resp.status}")
                    return players
                
                data = await resp.json()
                entries = data.get('entries', [])
                
                # Get top 50 GM players
                top_players = sorted(entries, key=lambda x: x.get('leaguePoints', 0), reverse=True)[:50]
                
                for entry in top_players:
                    players.append({
                        'summoner_name': entry.get('summonerName'),
                        'summoner_id': entry.get('summonerId'),
                        'lp': entry.get('leaguePoints'),
                        'wins': entry.get('wins'),
                        'losses': entry.get('losses'),
                        'type': 'high_elo',
                        'rank': 'Grandmaster',
                        'region': region,
                        'source': 'riot_api'
                    })
                
                print(f"   ✅ Found {len(players)} Grandmaster players")
                return players
                
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return players

def load_known_players():
    """Load manually curated list of known pros and streamers"""
    print("\n📝 Loading known players...")
    
    pros = []
    for name, info in KNOWN_PROS.items():
        pros.append({
            'name': name,
            'riot_id': info['riot_id'],
            'team': info['team'],
            'role': info['role'],
            'region': info['region'],
            'type': 'pro',
            'source': 'manual'
        })
    
    streamers = []
    for name, info in KNOWN_STREAMERS.items():
        for account in info['accounts']:
            streamers.append({
                'name': name,
                'riot_id': account,
                'role': info['main_role'],
                'region': info['region'],
                'type': 'streamer',
                'source': 'manual'
            })
    
    print(f"   ✅ Loaded {len(pros)} pros, {len(streamers)} streamer accounts")
    return pros, streamers

async def main():
    print("=" * 70)
    print("🚀 Multi-Source Pro Player Scraper")
    print("=" * 70)
    
    all_pros = []
    all_streamers = []
    all_high_elo = []
    
    # 1. Load known players (always available)
    known_pros, known_streamers = load_known_players()
    all_pros.extend(known_pros)
    all_streamers.extend(known_streamers)
    
    # 2. Try Leaguepedia
    try:
        leaguepedia_players = await scrape_leaguepedia()
        all_pros.extend(leaguepedia_players)
    except Exception as e:
        print(f"❌ Leaguepedia failed: {e}")
    
    # 3. Try Riot API for multiple regions
    if RIOT_API_KEY:
        for region in ['euw1', 'kr', 'na1']:
            try:
                challenger = await get_riot_challenger_players(region)
                all_high_elo.extend(challenger)
                await asyncio.sleep(1)  # Rate limit
                
                grandmaster = await get_riot_grandmaster_players(region)
                all_high_elo.extend(grandmaster)
                await asyncio.sleep(1)  # Rate limit
            except Exception as e:
                print(f"❌ Riot API {region} failed: {e}")
    
    # Deduplication
    print("\n🔄 Deduplicating...")
    
    # Dedupe pros by name
    pros_dict = {}
    for pro in all_pros:
        name = pro.get('name', pro.get('riot_id', ''))
        if name and name not in pros_dict:
            pros_dict[name] = pro
    
    # Dedupe high elo by summoner ID
    high_elo_dict = {}
    for player in all_high_elo:
        sid = player.get('summoner_id', '')
        if sid and sid not in high_elo_dict:
            high_elo_dict[sid] = player
    
    final_pros = list(pros_dict.values())
    final_streamers = all_streamers  # Already unique
    final_high_elo = list(high_elo_dict.values())
    
    # Results
    print("\n" + "=" * 70)
    print("📊 RESULTS")
    print("=" * 70)
    print(f"✅ Pro Players: {len(final_pros)}")
    print(f"✅ Streamer Accounts: {len(final_streamers)}")
    print(f"✅ High Elo Players: {len(final_high_elo)}")
    print(f"✅ Total: {len(final_pros) + len(final_streamers) + len(final_high_elo)}")
    
    # Save to JSON
    results = {
        'pros': final_pros,
        'streamers': final_streamers,
        'high_elo': final_high_elo,
        'total_pros': len(final_pros),
        'total_streamers': len(final_streamers),
        'total_high_elo': len(final_high_elo),
        'timestamp': datetime.now().isoformat(),
        'sources': ['manual', 'leaguepedia', 'riot_api']
    }
    
    with open('pro_players_database.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("\n💾 Saved to pro_players_database.json")
    
    # Show samples
    print("\n📋 Sample Pro Players:")
    for pro in final_pros[:10]:
        print(f"   • {pro.get('name', 'N/A')} - {pro.get('team', 'N/A')} ({pro.get('role', 'N/A')})")
    
    if final_streamers:
        print("\n📋 Sample Streamers:")
        for streamer in final_streamers[:5]:
            print(f"   • {streamer.get('name', 'N/A')}: {streamer.get('riot_id', 'N/A')}")
    
    if final_high_elo:
        print("\n📋 Top 5 Challenger Players:")
        sorted_high_elo = sorted(final_high_elo, key=lambda x: x.get('lp', 0), reverse=True)
        for player in sorted_high_elo[:5]:
            print(f"   • {player.get('summoner_name', 'N/A')} - {player.get('lp', 0)} LP ({player.get('region', 'N/A')})")

if __name__ == "__main__":
    asyncio.run(main())
