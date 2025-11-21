"""
Test fetching RAT IRL from lolpros.gg/player/rat-irl
"""
import asyncio
import aiohttp
import re
import json

async def test_ratirl_lolpros():
    url = "https://lolpros.gg/player/rat-irl"
    print(f"🔍 Fetching: {url}\n")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            print(f"Status: {resp.status}")
            
            if resp.status != 200:
                print(f"❌ Failed with status {resp.status}")
                return
            
            html = await resp.text()
            print(f"✅ Got HTML: {len(html)} chars\n")
            
            # Look for Nuxt.js JSON
            json_patterns = [
                (r'window\.__NUXT__\s*=\s*({.+?})</script>', 'window.__NUXT__'),
                (r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.+?)</script>', '__NUXT_DATA__ script'),
                (r'<script[^>]*type="application/json"[^>]*>(.+?)</script>', 'application/json'),
            ]
            
            json_found = False
            
            for pattern, name in json_patterns:
                matches = re.findall(pattern, html, re.DOTALL)
                if matches:
                    print(f"✅ Found JSON pattern: {name} ({len(matches)} matches)")
                    
                    for i, json_str in enumerate(matches[:2], 1):  # Check first 2 matches
                        try:
                            data = json.loads(json_str)
                            json_found = True
                            
                            print(f"\n📦 Match {i} - Type: {type(data)}")
                            
                            if isinstance(data, dict):
                                print(f"Top-level keys: {list(data.keys())[:15]}")
                                
                                # Try to find player data
                                possible_paths = [
                                    ['data', 'player'],
                                    ['state', 'player'],
                                    ['fetch', 'player'],
                                    ['player'],
                                    ['data', 'data', 'player'],
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
                                        print(f"\n🌟 FOUND PLAYER at path: {' -> '.join(path)}")
                                        print(f"   Keys: {list(current.keys())}")
                                        
                                        # Extract player info
                                        print(f"\n📋 PLAYER INFO:")
                                        print(f"   Name: {current.get('name', 'N/A')}")
                                        print(f"   Team: {current.get('team', 'N/A')}")
                                        print(f"   Role: {current.get('role', 'N/A')}")
                                        print(f"   Country: {current.get('country', 'N/A')}")
                                        
                                        # Extract accounts
                                        accounts = current.get('accounts', current.get('summoners', []))
                                        print(f"\n📋 ACCOUNTS ({len(accounts)}):")
                                        
                                        for j, acc in enumerate(accounts[:10], 1):
                                            if isinstance(acc, dict):
                                                summoner = acc.get('name', acc.get('summonerName', acc.get('gameName', 'Unknown')))
                                                tag = acc.get('tag', acc.get('tagLine', ''))
                                                region = acc.get('region', acc.get('platformId', 'Unknown'))
                                                lp = acc.get('lp', acc.get('leaguePoints', 0))
                                                tier = acc.get('tier', acc.get('rank', ''))
                                                
                                                print(f"   {j}. {summoner}#{tag} ({region.upper()}) - {tier} {lp} LP")
                                            else:
                                                print(f"   {j}. {acc}")
                                        
                                        return  # Found what we need
                            
                        except json.JSONDecodeError as e:
                            print(f"⚠️ JSON parse error for match {i}: {e}")
                            continue
            
            if not json_found:
                print("❌ No JSON found, trying meta tags...")
                
                # Extract from meta description
                meta_match = re.search(r'data-hid="description"[^>]*content="([^"]+)"', html)
                if meta_match:
                    description = meta_match.group(1)
                    print(f"\n✅ Found meta description!")
                    print(f"Length: {len(description)} chars")
                    
                    # Parse player info and accounts
                    parts = description.split(' | ')
                    
                    if len(parts) > 2:
                        role = parts[0]  # "Bot"
                        country = parts[1]  # "Sweden"
                        
                        print(f"\n🌟 PLAYER INFO:")
                        print(f"   Name: RAT IRL")
                        print(f"   Role: {role}")
                        print(f"   Country: {country}")
                        
                        # Extract accounts (everything after country)
                        account_strings = parts[2:]
                        
                        print(f"\n📋 ACCOUNTS ({len(account_strings)}):")
                        
                        for i, acc_str in enumerate(account_strings[:15], 1):
                            # Parse: "Jennifer Holland#EUW11 [Grandmaster 1014LP]"
                            match = re.match(r'(.+?)#([^\s\[]+)\s*\[(.+?)\s*(\d+)?LP?\]', acc_str)
                            if match:
                                summoner = match.group(1).strip()
                                tag = match.group(2).strip()
                                rank = match.group(3).strip()
                                lp = match.group(4) if match.group(4) else "0"
                                
                                print(f"   {i}. {summoner}#{tag} - {rank} {lp} LP")
                            else:
                                # Try without LP
                                match2 = re.match(r'(.+?)#([^\s\[]+)\s*\[(.+?)\]', acc_str)
                                if match2:
                                    summoner = match2.group(1).strip()
                                    tag = match2.group(2).strip()
                                    rank = match2.group(3).strip()
                                    print(f"   {i}. {summoner}#{tag} - {rank}")
                        
                        return
                
                print("\n❌ No meta description found")
                print(f"\nHTML Preview (first 3000 chars):")
                print(html[:3000])
                
                # Try to find any data attributes
                print("\n\n🔍 Looking for data attributes...")
                data_attrs = re.findall(r'data-[a-z-]+=(["\'])(.*?)\1', html[:5000])
                if data_attrs:
                    print(f"Found {len(data_attrs)} data attributes:")
                    for attr, value in data_attrs[:10]:
                        print(f"  {value[:100]}")

if __name__ == '__main__':
    asyncio.run(test_ratirl_lolpros())
