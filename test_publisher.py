"""Check publisher field in API"""
import asyncio
import aiohttp

async def test():
    api_url = "https://runeforge.dev/api/mods?page=0&limit=3"
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as response:
            data = await response.json()
            mods = data if isinstance(data, list) else data.get('mods', [])
            
            print("Checking 'publisher' field in API:")
            for i, mod in enumerate(mods, 1):
                print(f"\n{i}. {mod.get('name')}")
                print(f"   Publisher: {mod.get('publisher')}")
                if isinstance(mod.get('publisher'), dict):
                    print(f"   Publisher keys: {list(mod['publisher'].keys())}")
                    print(f"   Username: {mod['publisher'].get('username')}")
                    print(f"   ID: {mod['publisher'].get('id')}")

asyncio.run(test())
