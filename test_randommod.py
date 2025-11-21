"""Test script to check /randommod data fetching"""
import asyncio
import aiohttp
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'creator'))
from creator_scraper import RuneForgeScraper

async def test_random_mod():
    print("=" * 60)
    print("Testing /randommod data fetching")
    print("=" * 60)
    
    # Step 1: Test API response
    print("\n1️⃣ Testing RuneForge API...")
    api_url = "https://runeforge.dev/api/mods?page=0&limit=5"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url, headers=headers) as response:
            print(f"   Status: {response.status}")
            data = await response.json()
            mods = data if isinstance(data, list) else data.get('mods', [])
            print(f"   Found {len(mods)} mods")
            
            if mods:
                # Check first mod structure
                mod = mods[0]
                print(f"\n2️⃣ First mod from API:")
                print(f"   ID: {mod.get('id')}")
                print(f"   Name: {mod.get('name')}")
                print(f"   URL: {mod.get('url')}")
                print(f"   Author field: {mod.get('author')}")
                print(f"   Creator field: {mod.get('creator')}")
                print(f"   Image field: {mod.get('image')}")
                print(f"   Thumbnail field: {mod.get('thumbnail')}")
                print(f"   Cover field: {mod.get('cover')}")
                print(f"   Full mod keys:", list(mod.keys()))
                
                # Extract author - FIXED VERSION (uses publisher)
                publisher = mod.get('publisher', {})
                if isinstance(publisher, dict):
                    author_name = publisher.get('username', 'Unknown')
                    print(f"   ✅ Extracted author from publisher: {author_name}")
                else:
                    author_name = str(publisher) if publisher else 'Unknown'
                    print(f"   ⚠️ Publisher is not dict: {author_name}")
                
                # Step 3: Test scraper
                print(f"\n3️⃣ Testing scraper on first mod...")
                scraper = RuneForgeScraper()
                mod_url = mod.get('url', f"https://runeforge.dev/mods/{mod.get('id')}")
                print(f"   URL: {mod_url}")
                
                details = await scraper.get_mod_details(mod_url)
                print(f"\n   Scraper results:")
                print(f"   Name: {details.get('name')}")
                print(f"   Author: {details.get('author')}")
                print(f"   Image URL: {details.get('image_url')}")
                print(f"   Views: {details.get('views')}")
                print(f"   Likes: {details.get('likes')}")
                print(f"   Tags: {details.get('tags')}")
                
                # Summary
                print(f"\n" + "=" * 60)
                print("SUMMARY:")
                print("=" * 60)
                print(f"✅ API returns data: YES")
                print(f"{'✅' if author_name != 'Unknown' else '❌'} Author from API: {author_name}")
                print(f"{'✅' if details.get('author') else '❌'} Author from scraper: {details.get('author')}")
                print(f"{'✅' if details.get('image_url') else '❌'} Thumbnail from scraper: {details.get('image_url')}")
                
                if not details.get('author'):
                    print("\n⚠️ PROBLEM: Scraper nie wyciąga autora!")
                    print("   Trzeba dodać parsowanie autora w get_mod_details()")
                
                if not details.get('image_url'):
                    print("\n⚠️ PROBLEM: Scraper nie wyciąga obrazka!")
                    print("   Trzeba sprawdzić czy og:image jest dostępne")

if __name__ == "__main__":
    asyncio.run(test_random_mod())
