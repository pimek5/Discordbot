#!/usr/bin/env python3
"""
Test DPM.LOL scraper
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from HEXBET.dpm_scraper import scrape_dpm_pro_accounts

async def test():
    test_players = ['Agurin', 'Rekkles', 'Nemesis', 'Hans Sama']
    
    for player in test_players:
        print(f"\n[TEST] Scraping: {player}")
        result = await scrape_dpm_pro_accounts(player)
        if result:
            print(f"  SUCCESS - Found {len(result)} account(s):")
            for acc in result:
                print(f"    - {acc}")
        else:
            print(f"  FAIL - No accounts found")

if __name__ == '__main__':
    asyncio.run(test())
