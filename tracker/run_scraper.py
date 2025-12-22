"""
Quick script to run the advanced pro account scraper
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrape_pros_advanced import main

if __name__ == "__main__":
    print("\n🚀 Starting Pro Account Scraper...\n")
    asyncio.run(main())
