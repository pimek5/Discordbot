"""Test improved random mod algorithm"""
import asyncio
import aiohttp
import random

async def test_random_selection():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    print("=" * 60)
    print("Testing TRUE RANDOM mod selection")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        # Step 1: Get total
        async with session.get("https://runeforge.dev/api/mods?page=0&limit=1", headers=headers) as response:
            data = await response.json()
            total_mods = data.get('total', 0)
            mods_per_page = 24
            total_pages = (total_mods + mods_per_page - 1) // mods_per_page
            
            print(f"\n📊 Database stats:")
            print(f"   Total mods: {total_mods}")
            print(f"   Mods per page: {mods_per_page}")
            print(f"   Total pages: {total_pages}")
        
        # Test 5 random selections
        print(f"\n🎲 Testing 5 random selections:")
        for i in range(5):
            random_page = random.randint(0, max(0, total_pages - 1))
            
            async with session.get(f"https://runeforge.dev/api/mods?page={random_page}", headers=headers) as response:
                data = await response.json()
                mods = data.get('mods', [])
                
                if mods:
                    mod = random.choice(mods)
                    print(f"\n   {i+1}. Page {random_page:3d} -> {mod.get('name')[:50]}")
                    print(f"      Author: {mod.get('publisher', {}).get('username', 'Unknown')}")

asyncio.run(test_random_selection())
