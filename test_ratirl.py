"""
Quick test to fetch RAT IRL data from LoLPros/DeepLoL
"""
import asyncio
import aiohttp
import re
import json

async def test_ratirl():
    print("🔍 Searching for RAT IRL...")
    
    # Try DeepLoL Streamers with different variations
    urls_to_try = [
        "https://www.deeplol.gg/strm/ratirl",
        "https://www.deeplol.gg/strm/rat-irl",
        "https://www.deeplol.gg/strm/RAT%20IRL",
        "https://www.deeplol.gg/pro/ratirl",
    ]
    
    async with aiohttp.ClientSession() as session:
        for url in urls_to_try:
            print(f"\n📍 Trying: {url}")
            
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    print(f"Status: {resp.status}")
                    
                    if resp.status == 404:
                        continue
                    
                    if resp.status == 200:
                        html = await resp.text()
                        
                        # Check if it's actual player page (not default/error)
                        if 'RAT' in html.upper() or 'ratirl' in html.lower():
                            print(f"✅ Found player page! Length: {len(html)} chars")
                
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
                            print(f"\n✅ Found JSON with pattern!")
                            print(f"Top keys: {list(data.keys())[:10]}")
                            
                            # Try to extract player
                            if 'props' in data and 'pageProps' in data['props']:
                                page_props = data['props']['pageProps']
                                if 'player' in page_props:
                                    player = page_props['player']
                                    print(f"\n🌟 PLAYER DATA:")
                                    print(f"Name: {player.get('name', 'N/A')}")
                                    print(f"Team: {player.get('team', 'N/A')}")
                                    print(f"Role: {player.get('role', 'N/A')}")
                                    print(f"Region: {player.get('region', 'N/A')}")
                                    
                                    accounts = player.get('accounts', [])
                                    print(f"\n📋 ACCOUNTS ({len(accounts)}):")
                                    for i, acc in enumerate(accounts[:10], 1):
                                        game_name = acc.get('gameName', acc.get('name', 'Unknown'))
                                        tag = acc.get('tagLine', acc.get('tag', ''))
                                        region = acc.get('region', 'Unknown')
                                        lp = acc.get('leaguePoints', acc.get('lp', 0))
                                        tier = acc.get('tier', '')
                                        
                                        print(f"{i}. {game_name}#{tag} ({region}) - {tier} {lp} LP")
                                    
                                    return
                            
                            # Try direct player key
                            if 'player' in data:
                                player = data['player']
                                print(f"\n🌟 PLAYER DATA (direct):")
                                print(f"Name: {player.get('name', 'N/A')}")
                                
                                accounts = player.get('accounts', [])
                                print(f"\n📋 ACCOUNTS ({len(accounts)}):")
                                for i, acc in enumerate(accounts[:10], 1):
                                    print(f"{i}. {acc}")
                                return
                            
                        except Exception as e:
                            print(f"❌ JSON parse error: {e}")
                            continue
                
                print("\n⚠️ No JSON found, saving HTML preview...")
                print(f"HTML preview:\n{html[:2000]}")
        
        # Try LoLPros
        url2 = "https://lolpros.gg/player/ratirl"
        print(f"\n📍 Trying: {url2}")
        
        async with session.get(url2, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                html = await resp.text()
                print(f"✅ Got page! Length: {len(html)} chars")
                
                # Look for Nuxt JSON
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
                            print(f"\n✅ Found Nuxt JSON!")
                            print(f"Top keys: {list(data.keys())[:10] if isinstance(data, dict) else 'not dict'}")
                            
                            # Navigate common paths
                            paths = [
                                ['data', 'player'],
                                ['state', 'player'],
                                ['player'],
                            ]
                            
                            for path in paths:
                                current = data
                                for key in path:
                                    if isinstance(current, dict) and key in current:
                                        current = current[key]
                                    else:
                                        current = None
                                        break
                                
                                if current and isinstance(current, dict):
                                    print(f"\n🌟 PLAYER DATA (path: {' -> '.join(path)}):")
                                    print(f"Name: {current.get('name', 'N/A')}")
                                    print(f"Team: {current.get('team', 'N/A')}")
                                    
                                    accounts = current.get('accounts', current.get('summoners', []))
                                    print(f"\n📋 ACCOUNTS ({len(accounts)}):")
                                    for i, acc in enumerate(accounts[:10], 1):
                                        print(f"{i}. {acc}")
                                    return
                            
                        except Exception as e:
                            print(f"❌ JSON parse error: {e}")
                            continue

if __name__ == '__main__':
    asyncio.run(test_ratirl())
