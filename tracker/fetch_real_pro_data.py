"""
Fetch REAL pro player data from working APIs
Gets actual Riot IDs, not fake ones
"""

import aiohttp
import asyncio
import json
from bs4 import BeautifulSoup

async def fetch_from_opgg():
    """Fetch from OP.GG - they have real Riot IDs"""
    print("\n🔍 Fetching from OP.GG API...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # OP.GG has a public endpoint for pros
            url = "https://lol-web-api.op.gg/api/v1.0/internal/bypass/pro-players/ranking"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    players = []
                    if 'data' in data:
                        for pro in data['data'][:50]:  # Top 50
                            if pro.get('summoner_name') and pro.get('player_name'):
                                player_data = {
                                    'name': pro['player_name'],
                                    'riot_id': pro['summoner_name'],  # This is the REAL Riot ID
                                    'region': pro.get('region', 'unknown'),
                                    'team': pro.get('team_name'),
                                    'role': pro.get('position'),
                                    'rank': pro.get('tier_info', {}).get('tier'),
                                    'lp': pro.get('tier_info', {}).get('lp'),
                                    'source': 'opgg'
                                }
                                players.append(player_data)
                    
                    print(f"  ✅ Found {len(players)} pros from OP.GG")
                    return players
                else:
                    print(f"  ⚠️ Status {resp.status}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    return []

async def fetch_from_ugg():
    """Fetch from U.GG"""
    print("\n🔍 Fetching from U.GG API...")
    
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://u.gg/api/leaderboard?region=euw1&queueType=ranked_solo_5x5"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    players = []
                    if isinstance(data, list):
                        for player in data[:50]:
                            if player.get('summonerName'):
                                player_data = {
                                    'name': player.get('summonerName'),
                                    'riot_id': player.get('summonerName'),
                                    'region': 'euw1',
                                    'rank': player.get('tier'),
                                    'lp': player.get('leaguePoints'),
                                    'source': 'ugg'
                                }
                                players.append(player_data)
                    
                    print(f"  ✅ Found {len(players)} high elo players from U.GG")
                    return players
                else:
                    print(f"  ⚠️ Status {resp.status}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    return []

async def scrape_deeplol():
    """Scrape DeepLoL for real pro accounts"""
    print("\n🔍 Scraping DeepLoL.gg...")
    
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://www.deeplol.gg/multi-search/pro"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    players = []
                    # DeepLoL shows real Riot IDs in their interface
                    # Look for data attributes or json in page
                    
                    scripts = soup.find_all('script')
                    for script in scripts:
                        if script.string and 'proPlayers' in script.string:
                            # Try to extract JSON data
                            try:
                                # DeepLoL embeds data in page
                                import re
                                json_match = re.search(r'proPlayers.*?(\[.*?\])', script.string)
                                if json_match:
                                    pro_data = json.loads(json_match.group(1))
                                    for pro in pro_data[:30]:
                                        if pro.get('name') and pro.get('accounts'):
                                            player_data = {
                                                'name': pro['name'],
                                                'accounts': pro['accounts'],
                                                'region': pro.get('region', 'unknown'),
                                                'team': pro.get('team'),
                                                'role': pro.get('role'),
                                                'source': 'deeplol'
                                            }
                                            players.append(player_data)
                            except:
                                pass
                    
                    if players:
                        print(f"  ✅ Found {len(players)} pros from DeepLoL")
                        return players
                    else:
                        print(f"  ⚠️ No data extracted from DeepLoL")
                else:
                    print(f"  ⚠️ Status {resp.status}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    return []

def save_results(all_players, filename='real_pro_data.json'):
    """Save to JSON"""
    print(f"\n💾 Saving {len(all_players)} players to {filename}...")
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            'total': len(all_players),
            'sources': list(set(p['source'] for p in all_players)),
            'players': all_players
        }, f, indent=2, ensure_ascii=False)
    
    print(f"  ✅ Saved!")

async def main():
    print("=" * 70)
    print("FETCH REAL PRO PLAYER DATA")
    print("=" * 70)
    
    all_players = []
    
    # Fetch from all sources
    opgg_data = await fetch_from_opgg()
    all_players.extend(opgg_data)
    
    ugg_data = await fetch_from_ugg()
    all_players.extend(ugg_data)
    
    deeplol_data = await scrape_deeplol()
    all_players.extend(deeplol_data)
    
    print(f"\n📊 SUMMARY")
    print(f"   Total players collected: {len(all_players)}")
    
    if all_players:
        # Group by source
        by_source = {}
        for p in all_players:
            source = p.get('source', 'unknown')
            by_source[source] = by_source.get(source, 0) + 1
        
        print(f"\n   By source:")
        for source, count in sorted(by_source.items()):
            print(f"     • {source}: {count}")
        
        # Show top 10 with REAL Riot IDs
        print(f"\n📋 Top 10 players with REAL Riot IDs:")
        for i, player in enumerate(all_players[:10], 1):
            riot_id = player.get('riot_id') or player.get('accounts', ['N/A'])[0]
            team = player.get('team', 'No team')
            rank = player.get('rank', 'Unranked')
            print(f"   {i}. {player['name']} - {riot_id} | {team} | {rank}")
        
        # Save
        save_results(all_players)
        
        print(f"\n💡 Use this data to populate KNOWN_STREAMERS in scrape_pros_advanced.py")
        print(f"   File saved: real_pro_data.json")
    else:
        print("\n⚠️ No data fetched. APIs might be down or changed.")
    
    print("\n✅ Done!")

if __name__ == "__main__":
    asyncio.run(main())
