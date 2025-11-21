"""
Fetch complete pro player database using public APIs
This will download all players with their accounts in one go
"""

import aiohttp
import asyncio
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('fetcher')

async def fetch_pandascore_players():
    """Fetch from PandaScore API (public esports data)"""
    logger.info("🔍 Trying PandaScore API...")
    
    # PandaScore has public endpoint for LoL players
    url = "https://api.pandascore.co/lol/players"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"✅ Got {len(data)} players from PandaScore!")
                    return data
        except Exception as e:
            logger.warning(f"❌ PandaScore failed: {e}")
    
    return []

async def fetch_liquipedia_dump():
    """Try to get Liquipedia data dump"""
    logger.info("🔍 Trying Liquipedia...")
    
    # Liquipedia sometimes has public dumps
    urls = [
        "https://liquipedia.net/leagueoflegends/api.php?action=query&list=categorymembers&cmtitle=Category:Players&cmlimit=500&format=json",
    ]
    
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"✅ Got Liquipedia data!")
                        return data
            except Exception as e:
                logger.debug(f"Failed: {e}")
    
    return {}

async def main():
    """Main function to fetch and save pro player database"""
    
    all_players = []
    
    # Try multiple sources
    pandascore_data = await fetch_pandascore_players()
    
    if pandascore_data:
        for player in pandascore_data:
            all_players.append({
                'player_name': player.get('name', ''),
                'first_name': player.get('first_name', ''),
                'last_name': player.get('last_name', ''),
                'team': player.get('current_team', {}).get('name', ''),
                'role': player.get('role', ''),
                'nationality': player.get('nationality', ''),
                'accounts': [],  # Will need to be fetched separately
                'source': 'pandascore'
            })
    
    # Save what we got
    output_file = Path(__file__).parent / 'pro_players_database.json'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_players, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n✅ Saved {len(all_players)} players to {output_file}")
    
    if all_players:
        # Print sample
        logger.info("\n📋 Sample players:")
        for player in all_players[:10]:
            logger.info(f"  - {player['player_name']} ({player.get('team', 'No team')})")

if __name__ == '__main__':
    asyncio.run(main())
