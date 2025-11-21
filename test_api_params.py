"""Test different API parameters"""
import asyncio
import aiohttp

async def test():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    tests = [
        ("Default", "https://runeforge.dev/api/mods"),
        ("Page 0", "https://runeforge.dev/api/mods?page=0"),
        ("Page 5", "https://runeforge.dev/api/mods?page=5"),
        ("Page 50", "https://runeforge.dev/api/mods?page=50"),
        ("Sort: newest", "https://runeforge.dev/api/mods?sort=newest"),
        ("Sort: popular", "https://runeforge.dev/api/mods?sort=popular"),
        ("Sort: trending", "https://runeforge.dev/api/mods?sort=trending"),
        ("Sort: random", "https://runeforge.dev/api/mods?sort=random"),
        ("Limit 200", "https://runeforge.dev/api/mods?limit=200"),
    ]
    
    async with aiohttp.ClientSession() as session:
        for name, url in tests:
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        mods = data.get('mods', []) if isinstance(data, dict) else data
                        total = data.get('total', '?') if isinstance(data, dict) else '?'
                        print(f"{name:20} -> {len(mods):3} mods (total: {total})")
                        
                        # Show first mod name to see if it changes
                        if mods:
                            print(f"                       First: {mods[0].get('name', 'N/A')[:40]}")
                    else:
                        print(f"{name:20} -> Status {response.status}")
            except Exception as e:
                print(f"{name:20} -> Error: {e}")

asyncio.run(test())
