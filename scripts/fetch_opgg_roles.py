import aiohttp
import asyncio
import json
from collections import defaultdict

async def fetch_opgg_champion_roles():
    """Fetch champion roles from OP.GG API"""
    
    # OP.GG has an API endpoint for champion stats
    url = "https://op.gg/api/v1.0/internal/bypass/champions/global"
    
    champion_roles = defaultdict(list)
    
    async with aiohttp.ClientSession() as session:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json',
                'Referer': 'https://www.op.gg/'
            }
            
            async with session.get(url, headers=headers) as resp:
                print(f"Status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ Fetched data from OP.GG")
                    
                    # Save raw response to inspect structure
                    with open('opgg_raw.json', 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    print("📝 Saved raw data to opgg_raw.json")
                    
                    # Try to parse champion role data
                    if isinstance(data, dict):
                        print(f"Keys: {list(data.keys())}")
                        
                        # Look for champion data
                        if 'data' in data:
                            champs = data['data']
                            print(f"Found {len(champs)} champions")
                            
                            for champ in champs[:10]:  # Show first 10
                                champ_id = champ.get('id')
                                name = champ.get('name')
                                positions = champ.get('positions', [])
                                print(f"{champ_id}: {name} -> {positions}")
                    
                else:
                    print(f"❌ Failed: {resp.status}")
                    text = await resp.text()
                    print(f"Response: {text[:500]}")
                    
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    return champion_roles

if __name__ == "__main__":
    asyncio.run(fetch_opgg_champion_roles())
