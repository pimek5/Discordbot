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
        player_name: Pro player name (e.g., "Agurin")
    
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
            
            rank = rank_img.get('alt', 'UNRANKED').upper()
            
            # Find LP text (e.g., "1167 LP")
            lp = 0
            lp_span = link.find('span', string=re.compile(r'\d+\s*LP'))
            if lp_span:
                lp_text = lp_span.get_text(strip=True)
                lp_match = re.search(r'(\d+)\s*LP', lp_text)
                if lp_match:
                    lp = int(lp_match.group(1))
            
            # Find W/L text (e.g., "363W - 295L (55%)")
            wins = 0
            losses = 0
            wr = 0.0
            
            wl_span = link.find('span', string=re.compile(r'\d+W\s*-\s*\d+L'))
            if wl_span:
                wl_text = wl_span.get_text(strip=True)
                wl_match = re.search(r'(\d+)W\s*-\s*(\d+)L\s*\((\d+)%\)', wl_text)
                if wl_match:
                    wins = int(wl_match.group(1))
                    losses = int(wl_match.group(2))
                    wr = float(wl_match.group(3))
            
            accounts.append({
                'riot_id': riot_id,
                'rank': rank,
                'lp': lp,
                'wins': wins,
                'losses': losses,
                'wr': wr
            })
        
        logger.info(f"✅ Scraped {len(accounts)} accounts for {player_name} from DPM.LOL HTML")
        return accounts
    
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
