"""
DPM.LOL Pro Player Account Scraper
Extracts SoloQ accounts, ranks, LP, and winrates for pro players
"""
import sys
import os
import re
import logging
import asyncio
from typing import List, Dict
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Import from our existing API
apis_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'apis'))
if apis_dir not in sys.path:
    sys.path.insert(0, apis_dir)
try:
    from dpm_api_pro import get_pro_accounts_async
except Exception as e:
    logger.info("dpm_api_pro import unavailable (%s), using inline fallback", e)
    get_pro_accounts_async = None


async def scrape_dpm_pro_accounts(player_name: str) -> List[Dict[str, any]]:
    """
    Scrape DPM.LOL for pro player accounts (RiotIDs only)
    Returns list of riot_ids - rank/LP/WR will be fetched from Riot API
    
    Args:
        player_name: Pro player name (e.g., "Agurin")
    
    Returns:
        List[Dict] with keys: riot_id (other fields will be fetched from API)
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
        
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        accounts = []
        
        # Find all account links (format: /GameName-TAG)
        account_links = soup.find_all('a', href=True)
        
        for link in account_links:
            href = link.get('href', '')
            
            # Skip non-account links
            if not href.startswith('/') or href.count('-') < 1:
                continue
                
            # Extract riot_id from href: /Bgurin-4000 -> Bgurin#4000
            riot_id_raw = href.strip('/')
            # Replace last dash with # (since gameName can have dashes)
            parts = riot_id_raw.rsplit('-', 1)
            if len(parts) != 2:
                continue
            riot_id = f"{parts[0]}#{parts[1]}"
            
            # Find rank image (has alt text like "CHALLENGER", "GRANDMASTER")
            rank_img = link.find('img', alt=lambda x: x and x.upper() in [
                'CHALLENGER', 'GRANDMASTER', 'MASTER', 'DIAMOND', 
                'PLATINUM', 'GOLD', 'SILVER', 'BRONZE', 'IRON'
            ])
            
            if not rank_img:
                continue
            
            # Only extract riot_id - rank/LP/WR will come from Riot API
            accounts.append({
                'riot_id': riot_id
            })
        
        # Deduplicate by riot_id
        seen = set()
        unique_accounts = []
        for acc in accounts:
            if acc['riot_id'] not in seen:
                seen.add(acc['riot_id'])
                unique_accounts.append(acc)
        
        logger.info(f"✅ Scraped {len(unique_accounts)} unique accounts for {player_name} from DPM.LOL")
        return unique_accounts
    
    except Exception as e:
        logger.error(f"❌ Error in fallback scrape for {player_name}: {e}")
        return []


# For testing
if __name__ == "__main__":
    async def test():
        accounts = await scrape_dpm_pro_accounts("Agurin")
        for acc in accounts:
            print(f"  {acc['riot_id']} - {acc['rank']} {acc['lp']} LP ({acc['wr']}% WR)")
    
    asyncio.run(test())
