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
            print(f"Title: {soup.title.get_text(strip=True) if soup.title else 'N/A'}")
            print("\nFirst 2000 chars of HTML:\n")
            print(html[:2000])


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_selectors.py <url>")
        sys.exit(1)
    url = sys.argv[1]
    asyncio.run(analyze_page(url))


if __name__ == "__main__":
    main()
