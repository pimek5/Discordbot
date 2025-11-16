"""
HTML Selector Finder - Helper Script
Run this to test and find correct CSS selectors for RuneForge and Divine Skins

Usage:
    python test_selectors.py https://runeforge.dev/users/p1mek
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import sys


async def analyze_page(url: str):
    """Analyze page structure and suggest selectors"""
    print(f"\n🔍 Analyzing: {url}\n")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                print(f"❌ Failed to fetch page (Status: {response.status})")
                return
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            print("=" * 60)
            print("PAGE STRUCTURE ANALYSIS")
            print("=" * 60)
            
            # Find common profile elements
            print("\n📊 Looking for stats elements...")
            
            # Numbers (likely stats)
            numbers = soup.find_all(text=lambda t: t and any(char.isdigit() for char in str(t)))
            print(f"\n✓ Found {len(numbers)} elements with numbers")
            
            # Common stat keywords
            keywords = ['rank', 'mod', 'skin', 'download', 'view', 'follower', 'following', 'joined', 'creator']
            
            for keyword in keywords:
                elements = soup.find_all(text=lambda t: t and keyword.lower() in str(t).lower())
                if elements:
                    print(f"\n🎯 '{keyword.upper()}' found in {len(elements)} places:")
                    for elem in elements[:3]:  # Show first 3
                        parent = elem.parent
                        print(f"   Tag: <{parent.name}>")
                        if parent.get('class'):
                            print(f"   Class: {' '.join(parent['class'])}")
                        if parent.get('id'):
                            print(f"   ID: {parent['id']}")
            
            print("\n" + "=" * 60)
            print("COMMON SELECTORS TO TRY")
            print("=" * 60)
            
            # Suggest common patterns
            print("\n📝 Try these selector patterns:")
            
            # Classes with numbers
            print("\n1. Elements with class containing 'stat', 'count', or 'number':")
            stat_classes = soup.find_all(class_=lambda x: x and any(word in str(x).lower() for word in ['stat', 'count', 'number', 'metric']))
            for elem in stat_classes[:5]:
                classes = ' '.join(elem.get('class', []))
                print(f"   .{classes.replace(' ', '.')}")
            
            # Data attributes
            print("\n2. Elements with data attributes:")
            data_attrs = soup.find_all(lambda tag: any(attr.startswith('data-') for attr in tag.attrs))
            for elem in data_attrs[:5]:
                data_attr = [attr for attr in elem.attrs if attr.startswith('data-')]
                if data_attr:
                    print(f"   [{data_attr[0]}]")
            
            # Links (for mods/skins)
            print("\n3. Links (potential mod/skin cards):")
            links = soup.find_all('a', href=True)
            mod_links = [link for link in links if '/mod' in link['href'].lower() or '/skin' in link['href'].lower()]
            print(f"   Found {len(mod_links)} mod/skin links")
            if mod_links:
                print(f"   Example: {mod_links[0]['href']}")
                parent = mod_links[0].parent
                if parent.get('class'):
                    print(f"   Parent class: {' '.join(parent['class'])}")
            
            print("\n" + "=" * 60)
            print("FULL HTML SAMPLE (first 2000 chars)")
            print("=" * 60)
            print(html[:2000])
            print("\n... (truncated)")
            
            print("\n" + "=" * 60)
            print("NEXT STEPS")
            print("=" * 60)
            print("""
1. Open the URL in your browser
2. Right-click → Inspect Element
3. Find the stat you want (e.g., "24 mods")
4. Look at the HTML structure
5. Update creator_scraper.py with the correct selector

Example:
    If you see: <div class="stat-item"><span class="stat-value">24</span> mods</div>
    Use selector: soup.find('span', class_='stat-value')
            """)


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_selectors.py <url>")
        print("\nExamples:")
        print("  python test_selectors.py https://runeforge.dev/users/p1mek")
        print("  python test_selectors.py https://divineskins.gg/pimek")
        sys.exit(1)
    
    url = sys.argv[1]
    asyncio.run(analyze_page(url))


if __name__ == "__main__":
    main()
