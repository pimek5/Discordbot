"""
DPM.LOL Pro Player Account Scraper
Extracts SoloQ accounts, ranks, LP, and winrates for pro players
Uses cloudscraper from apis/dpm_api.py infrastructure
"""
import sys
import os
import re
import logging
import asyncio
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Import from our existing API
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../apis'))
try:
    from dpm_api_pro import get_pro_accounts_async
except ImportError:
    logger.warning("Could not import dpm_api_pro, using inline fallback")
    get_pro_accounts_async = None


async def scrape_dpm_pro_accounts(player_name: str) -> List[Dict[str, any]]:
    """
    Scrape DPM.LOL for pro player accounts
    Returns list of accounts with: riot_id, rank, lp, wins, losses, wr%
    
    Args:
        player_name: Pro player name (e.g., "Rekkles")
    
    Returns:
        List[Dict] with keys: riot_id, rank, lp, wins, losses, wr
    """
    try:
        if get_pro_accounts_async:
            # Use the API function with cloudscraper
            accounts = await get_pro_accounts_async(player_name)
            logger.info(f"✅ Fetched {len(accounts)} accounts for {player_name} from DPM.LOL")
            return accounts
        else:
            # Fallback if import fails
            logger.warning(f"⚠️ DPM API not available, trying inline method")
            return await _fallback_scrape(player_name)
    
    except Exception as e:
        logger.error(f"❌ Error scraping DPM.LOL for {player_name}: {e}", exc_info=True)
        return []


async def _fallback_scrape(player_name: str) -> List[Dict[str, any]]:
    """Fallback scraper using cloudscraper directly"""
    import cloudscraper
    
    url = f"https://dpm.lol/pro/{player_name}"
    accounts = []
    
    try:
        def fetch():
            scraper = cloudscraper.create_scraper()
            resp = scraper.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.text
            return None
        
        loop = asyncio.get_event_loop()
        html = await loop.run_in_executor(None, fetch)
        
        if not html:
            logger.warning(f"❌ DPM.LOL returned non-200 for {player_name}")
            return []
        
        # Debug: log sample
        logger.info(f"📄 DPM.LOL HTML sample for {player_name} (first 2000 chars):\n{html[:2000]}")
        
        # Parse accounts using regex
        # Pattern: "gameName#tag RANK LP Wins-Losses (WR%)"
        pattern = r'(\w+[\s\w]*#\w+)\s+(CHALLENGER|GRANDMASTER|MASTER|DIAMOND|PLATINUM|GOLD|SILVER|BRONZE|IRON)\s+(\d+)\s+LP\s+(\d+)W\s*-\s*(\d+)L\s*\((\d+(?:\.\d+)?)\%\)'
        
        matches = re.finditer(pattern, html)
        match_count = 0
        for match in matches:
            match_count += 1
            riot_id = match.group(1).strip()
            rank = match.group(2)
            lp = int(match.group(3))
            wins = int(match.group(4))
            losses = int(match.group(5))
            wr = float(match.group(6))
            
            accounts.append({
                'riot_id': riot_id,
                'rank': rank,
                'lp': lp,
                'wins': wins,
                'losses': losses,
                'wr': wr
            })
        
        if match_count == 0:
            logger.warning(f"⚠️ No regex matches found for {player_name}. Pattern may need update.")
        
        logger.info(f"✅ Scraped {len(accounts)} accounts for {player_name} from DPM.LOL")
        return accounts
    
    except Exception as e:
        logger.error(f"❌ Error in fallback scrape for {player_name}: {e}")
        return []


# For testing
if __name__ == "__main__":
    async def test():
        accounts = await scrape_dpm_pro_accounts("Rekkles")
        for acc in accounts:
            print(f"  {acc['riot_id']} - {acc['rank']} {acc['lp']} LP ({acc['wr']}% WR)")
    
    asyncio.run(test())

