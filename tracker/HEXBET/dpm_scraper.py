"""
DPM.LOL Pro Player Account Scraper
Extracts SoloQ accounts, ranks, LP, and winrates for pro players
"""
import aiohttp
import asyncio
import re
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


async def scrape_dpm_pro_accounts(player_name: str) -> List[Dict[str, any]]:
    """
    Scrape DPM.LOL for pro player accounts
    Returns list of accounts with: riot_id, rank, lp, wins, losses, wr%
    
    Args:
        player_name: Pro player name (e.g., "Rekkles")
    
    Returns:
        List[Dict] with keys: riot_id, rank, lp, wins, losses, wr
    """
    url = f"https://dpm.lol/pro/{player_name}"
    accounts = []
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    logger.warning(f"❌ DPM.LOL returned {response.status} for {player_name}")
                    return []
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Find all SoloQ account entries
                # Pattern: "Profile Icon LR Rekkles #LRAT CHALLENGER 1658 LP 418W - 330L (56%)"
                soloq_section = soup.find('h3', string=lambda x: x and 'SOLO Q' in x.upper() if x else False)
                
                if not soloq_section:
                    logger.warning(f"⚠️ No SOLO Q section found for {player_name}")
                    return []
                
                # Find all account links after SOLO Q heading
                parent = soloq_section.parent
                if not parent:
                    return []
                
                # Look for account entries in the section
                for item in parent.find_all('a', href=True):
                    href = item.get('href', '')
                    text = item.get_text(strip=True)
                    
                    # Skip premium prompts and non-account links
                    if 'premium' in text.lower() or not href.startswith('/'):
                        continue
                    
                    # Parse account text: "Profile Icon LR Rekkles #LRAT CHALLENGER 1658 LP 418W - 330L (56%)"
                    # Or: "LR Rekkles #LRAT CHALLENGER 1658 LP 418W - 330L (56%)"
                    account_data = _parse_account_line(text)
                    if account_data:
                        accounts.append(account_data)
                
                logger.info(f"✅ Scraped {len(accounts)} accounts for {player_name} from DPM.LOL")
                return accounts
    
    except asyncio.TimeoutError:
        logger.error(f"⏱️ DPM.LOL request timeout for {player_name}")
        return []
    except Exception as e:
        logger.error(f"❌ Error scraping DPM.LOL for {player_name}: {e}")
        return []


def _parse_account_line(text: str) -> Optional[Dict[str, any]]:
    """
    Parse account line text
    Format: "LR Rekkles #LRAT CHALLENGER 1658 LP 418W - 330L (56%)"
    """
    try:
        # Remove "Profile Icon" prefix if present
        text = text.replace("Profile Icon", "").strip()
        
        # Pattern: gameName#tag RANK LP winW - lossL (winrate%)
        # Example: "LR Rekkles #LRAT CHALLENGER 1658 LP 418W - 330L (56%)"
        
        # Extract riot_id (gameName#tag)
        riot_id_match = re.search(r'^(.+?#\w+)\s+', text)
        if not riot_id_match:
            return None
        riot_id = riot_id_match.group(1).strip()
        
        # Extract rank (CHALLENGER, GRANDMASTER, MASTER, DIAMOND, etc)
        rank_match = re.search(r'(CHALLENGER|GRANDMASTER|MASTER|DIAMOND|PLATINUM|GOLD|SILVER|BRONZE|IRON)\s+(\d+)', text)
        if not rank_match:
            return None
        rank = rank_match.group(1)
        lp = int(rank_match.group(2))
        
        # Extract W-L record and winrate
        # Pattern: "418W - 330L (56%)"
        record_match = re.search(r'(\d+)W\s*-\s*(\d+)L\s*\((\d+(?:\.\d+)?)\%\)', text)
        if not record_match:
            return None
        
        wins = int(record_match.group(1))
        losses = int(record_match.group(2))
        wr = float(record_match.group(3))
        
        return {
            'riot_id': riot_id,
            'rank': rank,
            'lp': lp,
            'wins': wins,
            'losses': losses,
            'wr': wr
        }
    
    except Exception as e:
        logger.warning(f"Failed to parse account line: {text} - {e}")
        return None


# For testing
if __name__ == "__main__":
    import asyncio
    
    async def test():
        accounts = await scrape_dpm_pro_accounts("Rekkles")
        for acc in accounts:
            print(f"  {acc['riot_id']} - {acc['rank']} {acc['lp']} LP ({acc['wr']}% WR)")
    
    asyncio.run(test())
