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
        
        # DPM.LOL uses Next.js - data is in __NEXT_DATA__ JSON
        import json
        next_data_pattern = r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>'
        match = re.search(next_data_pattern, text, re.DOTALL)
        
        if match:
            try:
                next_data = json.loads(match.group(1))
                logger.info(f"✅ Found __NEXT_DATA__ for {pro_name}")
                
                # Extract accounts from Next.js data structure
                accounts = []
                props = next_data.get('props', {}).get('pageProps', {})
                
                # Try to find accounts in various possible locations
                player_data = props.get('player', {}) or props.get('data', {}) or props
                accounts_data = player_data.get('accounts', []) or player_data.get('soloQueueAccounts', [])
                
                for acc in accounts_data:
                    try:
                        riot_id = f"{acc.get('gameName', 'Unknown')}#{acc.get('tagLine', 'NA1')}"
                        rank = acc.get('tier', 'UNRANKED').upper()
                        lp = acc.get('leaguePoints', 0)
                        wins = acc.get('wins', 0)
                        losses = acc.get('losses', 0)
                        total = wins + losses
                        wr = (wins / total * 100) if total > 0 else 0.0
                        
                        accounts.append({
                            'riot_id': riot_id,
                            'rank': rank,
                            'lp': lp,
                            'wins': wins,
                            'losses': losses,
                            'wr': wr
                        })
                    except Exception as e:
                        logger.warning(f"Failed to parse account: {e}")
                        continue
                
                logger.info(f"✅ Scraped {len(accounts)} accounts for {pro_name} from __NEXT_DATA__")
                return accounts
            
            except Exception as e:
                logger.error(f"Failed to parse __NEXT_DATA__: {e}")
        
        logger.warning(f"⚠️ No __NEXT_DATA__ found for {pro_name}, DPM.LOL may have changed structure")
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
