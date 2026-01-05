"""
DPM.LOL Pro Player Accounts Fetcher
Uses DPM.LOL API to get pro player SoloQ accounts with ranks
"""
import cloudscraper
import asyncio
import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def get_pro_accounts_from_dpmlol(pro_name: str) -> List[Dict[str, any]]:
    """
    Fetch pro player SoloQ accounts from DPM.LOL profile page
    
    Args:
        pro_name: Pro player name (e.g., "Rekkles")
    
    Returns:
        List of accounts with: riot_id, rank, lp, wins, losses, wr
    """
    url = f"https://dpm.lol/pro/{pro_name}"
    accounts = []
    
    try:
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(url, timeout=10)
        
        if resp.status_code != 200:
            logger.warning(f"❌ DPM.LOL returned {resp.status_code} for {pro_name}")
            return []
        
        text = resp.text
        
        # Debug: log first 2000 chars to see what we're parsing
        logger.info(f"📄 DPM.LOL HTML sample for {pro_name} (first 2000 chars):\n{text[:2000]}")
        
        # Find all account entries with pattern: "gameName#tag RANK LP Wins-Losses (WR%)"
        # Example: "LR Rekkles #LRAT CHALLENGER 1658 LP 418W - 330L (56%)"
        
        # Pattern to match account lines
        pattern = r'(\w+[\s\w]*#\w+)\s+(CHALLENGER|GRANDMASTER|MASTER|DIAMOND|PLATINUM|GOLD|SILVER|BRONZE|IRON)\s+(\d+)\s+LP\s+(\d+)W\s*-\s*(\d+)L\s*\((\d+(?:\.\d+)?)\%\)'
        
        matches = re.finditer(pattern, text)
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
            logger.warning(f"⚠️ No regex matches found for {pro_name}. Pattern may need update.")
        
        logger.info(f"✅ Scraped {len(accounts)} accounts for {pro_name} from DPM.LOL")
        return accounts
    
    except Exception as e:
        logger.error(f"❌ Error scraping DPM.LOL for {pro_name}: {e}")
        return []


async def get_pro_accounts_async(pro_name: str) -> List[Dict[str, any]]:
    """Async wrapper for get_pro_accounts_from_dpmlol"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_pro_accounts_from_dpmlol, pro_name)


if __name__ == "__main__":
    # Test
    accounts = get_pro_accounts_from_dpmlol("Rekkles")
    for acc in accounts:
        print(f"  {acc['riot_id']} - {acc['rank']} {acc['lp']} LP ({acc['wr']}% WR)")
