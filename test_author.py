"""Test to check HTML structure for author"""
import asyncio
import aiohttp
from bs4 import BeautifulSoup

async def test_author_scraping():
    mod_url = "https://runeforge.dev/mods/c8e3e509-ff8f-496b-9bdc-c1e9fb656acf"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(mod_url) as response:
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            print("=" * 60)
            print("Searching for author in HTML...")
            print("=" * 60)
            
            # Check meta tags
            print("\n1️⃣ Meta tags:")
            for meta in soup.find_all('meta'):
                content = meta.get('content', '')
                if content and ('by' in content.lower() or 'author' in str(meta).lower()):
                    print(f"   {meta}")
            
            # Check links to /users/
            print("\n2️⃣ Links to /users/:")
            user_links = soup.find_all('a', href=lambda x: x and '/users/' in x)
            for link in user_links[:3]:
                print(f"   Text: {link.get_text(strip=True)}")
                print(f"   Href: {link.get('href')}")
                print()
            
            # Check for "By" text
            print("\n3️⃣ Text containing 'By':")
            page_text = soup.get_text()
            import re
            by_matches = re.findall(r'By\s+(\w+)', page_text, re.I)
            print(f"   Matches: {by_matches[:5]}")
            
            # Check all links
            print("\n4️⃣ First 10 links on page:")
            for i, link in enumerate(soup.find_all('a')[:10], 1):
                print(f"   {i}. {link.get_text(strip=True)[:40]:40} -> {link.get('href', '')[:60]}")

asyncio.run(test_author_scraping())
