"""
Pro Players & Streamers Database Sources
Testing various APIs and endpoints
"""

import aiohttp
import asyncio
import json

async def test_lolpros_api():
    """Test LoLPros.gg API endpoints"""
    print("\n=== Testing LoLPros.gg ===")
    
    urls = [
        "https://lolpros.gg/api/players",
        "https://api.lolpros.gg/players",
        "https://lolpros.gg/data/players.json",
        "https://lolpros.gg/players.json",
    ]
    
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                print(f"\nTrying: {url}")
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    print(f"Status: {resp.status}")
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"Success! Type: {type(data)}")
                        if isinstance(data, list):
                            print(f"Found {len(data)} items")
                            if data:
                                print(f"Sample: {json.dumps(data[0], indent=2)[:500]}")
                        elif isinstance(data, dict):
                            print(f"Keys: {list(data.keys())}")
                            if 'players' in data:
                                print(f"Found {len(data['players'])} players")
            except Exception as e:
                print(f"Error: {e}")

async def test_deeplol_api():
    """Test DeepLoL API endpoints"""
    print("\n\n=== Testing DeepLoL ===")
    
    urls = [
        "https://www.deeplol.gg/api/pros",
        "https://www.deeplol.gg/api/streamers",
        "https://api.deeplol.gg/pros",
        "https://api.deeplol.gg/players",
    ]
    
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                print(f"\nTrying: {url}")
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    print(f"Status: {resp.status}")
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"Success! Type: {type(data)}")
                        if isinstance(data, list) and data:
                            print(f"Found {len(data)} items")
                            print(f"Sample: {json.dumps(data[0], indent=2)[:500]}")
                        elif isinstance(data, dict):
                            print(f"Keys: {list(data.keys())}")
            except Exception as e:
                print(f"Error: {e}")

async def test_probuildstats():
    """Test ProBuildStats API"""
    print("\n\n=== Testing ProBuildStats ===")
    
    urls = [
        "https://probuildstats.com/api/pros",
        "https://probuildstats.com/api/players",
        "https://api.probuildstats.com/pros",
    ]
    
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                print(f"\nTrying: {url}")
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    print(f"Status: {resp.status}")
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"Success! Type: {type(data)}")
                        if isinstance(data, list) and data:
                            print(f"Found {len(data)} items")
                            print(f"Sample: {json.dumps(data[0], indent=2)[:500]}")
                        elif isinstance(data, dict):
                            print(f"Keys: {list(data.keys())}")
            except Exception as e:
                print(f"Error: {e}")

async def test_ugg():
    """Test U.GG API"""
    print("\n\n=== Testing U.GG ===")
    
    urls = [
        "https://u.gg/api/pros",
        "https://stats2.u.gg/lol/1.5/pro_player_list/15_23",
        "https://u.gg/lol/pro-players",
    ]
    
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                print(f"\nTrying: {url}")
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    print(f"Status: {resp.status}")
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            print(f"Success! Type: {type(data)}")
                            if isinstance(data, list) and data:
                                print(f"Found {len(data)} items")
                                print(f"Sample: {json.dumps(data[0], indent=2)[:500]}")
                            elif isinstance(data, dict):
                                print(f"Keys: {list(data.keys())}")
                        except:
                            text = await resp.text()
                            print(f"Got HTML/text ({len(text)} chars)")
            except Exception as e:
                print(f"Error: {e}")

async def main():
    print("=== PRO PLAYERS & STREAMERS DATABASE SEARCH ===")
    
    await test_lolpros_api()
    await test_deeplol_api()
    await test_probuildstats()
    await test_ugg()
    
    print("\n\n=== SUMMARY ===")
    print("Tested multiple API endpoints for pro players database")
    print("Check results above to see which APIs are accessible")

if __name__ == "__main__":
    asyncio.run(main())
