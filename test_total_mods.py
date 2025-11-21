"""Check total mods available in RuneForge API"""
import asyncio
import aiohttp

async def test():
    # Check different page sizes
    print("=" * 60)
    print("Testing RuneForge API pagination")
    print("=" * 60)
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    async with aiohttp.ClientSession() as session:
        # Test page 0 with limit 50
        print("\n1️⃣ Current /randommod setup (page=0, limit=50):")
        async with session.get("https://runeforge.dev/api/mods?page=0&limit=50", headers=headers) as response:
            data = await response.json()
            mods = data if isinstance(data, list) else data.get('mods', [])
            print(f"   Found: {len(mods)} mods")
            print(f"   Response type: {type(data)}")
            if isinstance(data, dict):
                print(f"   Keys: {list(data.keys())}")
                if 'total' in data:
                    print(f"   Total available: {data['total']}")
                if 'totalPages' in data:
                    print(f"   Total pages: {data['totalPages']}")
        
        # Test larger limit
        print("\n2️⃣ Testing larger limit (page=0, limit=100):")
        async with session.get("https://runeforge.dev/api/mods?page=0&limit=100", headers=headers) as response:
            data = await response.json()
            mods = data if isinstance(data, list) else data.get('mods', [])
            print(f"   Found: {len(mods)} mods")
        
        # Test page 1
        print("\n3️⃣ Testing page 1 (page=1, limit=50):")
        async with session.get("https://runeforge.dev/api/mods?page=1&limit=50", headers=headers) as response:
            data = await response.json()
            mods = data if isinstance(data, list) else data.get('mods', [])
            print(f"   Found: {len(mods)} mods")
        
        # Test without pagination params
        print("\n4️⃣ Testing without params:")
        async with session.get("https://runeforge.dev/api/mods", headers=headers) as response:
            data = await response.json()
            mods = data if isinstance(data, list) else data.get('mods', [])
            print(f"   Found: {len(mods)} mods")
            if isinstance(data, dict) and 'total' in data:
                print(f"   Total in database: {data['total']}")
        
        print("\n" + "=" * 60)
        print("RECOMMENDATION:")
        print("=" * 60)
        print("Currently /randommod picks from only 50 mods (page 0)")
        print("To make it truly random across ALL mods:")
        print("1. Get total count from API")
        print("2. Pick random page number")
        print("3. Pick random mod from that page")
        print("OR")
        print("4. Increase limit to max (e.g., 200-500)")

asyncio.run(test())
