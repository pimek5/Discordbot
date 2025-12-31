"""
RL-Stats.pl Scraper
Scrapes professional League of Legends team and player data
"""

import aiohttp
from bs4 import BeautifulSoup
import logging
import re

logger = logging.getLogger('rlstats_scraper')


class RLStatsScraper:
    BASE_URL = "https://www.rl-stats.pl"
    
    async def get_team_rankings(self) -> list:
        """Scrape team rankings from main page"""
        try:
            url = f"{self.BASE_URL}/rankings"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.error("❌ Failed to fetch rankings: %s", response.status)
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    teams = []
                    # Find all table rows with team data
                    rows = soup.find_all('tr')
                    
                    for row in rows:
                        try:
                            cells = row.find_all('td')
                            if len(cells) < 4:
                                continue
                            
                            # Extract rank (first cell)
                            rank_text = cells[0].get_text(strip=True)
                            if not rank_text.isdigit():
                                continue
                            rank = int(rank_text)
                            
                            # Extract team name and tag
                            team_cell = cells[1]
                            team_name = team_cell.get_text(strip=True)
                            
                            # Try to find team link
                            team_link = team_cell.find('a', href=True)
                            team_url = ""
                            team_tag = ""
                            if team_link:
                                team_url = team_link['href']
                                if not team_url.startswith('http'):
                                    team_url = f"{self.BASE_URL}{team_url}"
                                # Extract tag from URL (e.g., /team/lr -> lr)
                                team_tag = team_url.rstrip('/').split('/')[-1].upper()
                            
                            # Parse team name to extract tag if embedded (e.g., "Los Ratones LR")
                            name_parts = team_name.split()
                            if len(name_parts) > 1:
                                potential_tag = name_parts[-1]
                                # If last part is short (2-5 chars) and uppercase-ish, it's likely a tag
                                if 2 <= len(potential_tag) <= 5 and potential_tag.isupper():
                                    team_tag = potential_tag
                                    team_name = ' '.join(name_parts[:-1])
                            
                            # Rating
                            rating_text = cells[2].get_text(strip=True)
                            rating_match = re.search(r'(\d+)', rating_text)
                            rating = int(rating_match.group(1)) if rating_match else 0
                            
                            # Rating change
                            change_text = cells[3].get_text(strip=True)
                            change_match = re.search(r'([+-]?\d+)', change_text)
                            rating_change = int(change_match.group(1)) if change_match else 0
                            
                            teams.append({
                                'rank': rank,
                                'name': team_name.strip(),
                                'tag': team_tag or 'UNK',
                                'rating': rating,
                                'rating_change': rating_change,
                                'url': team_url
                            })
                        except Exception as e:
                            logger.warning("⚠️ Error parsing team row: %s", e)
                            continue
                    
                    logger.info("✅ Scraped %s teams from rankings", len(teams))
                    return teams
        except Exception as e:
            logger.error("❌ Error scraping rankings: %s", e)
            return []
    
    async def get_team_roster(self, team_tag: str) -> dict:
        """Scrape team roster and details"""
        try:
            url = f"{self.BASE_URL}/team/{team_tag.lower()}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.error("❌ Failed to fetch team %s: %s", team_tag, response.status)
                        return None
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Extract team info
                    team_name = ""
                    h1 = soup.find('h1')
                    if h1:
                        team_name = h1.get_text(strip=True)
                    
                    # Parse roster table
                    roster = []
                    rows = soup.find_all('tr')
                    
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) < 3:
                            continue
                        
                        try:
                            # Player name (first cell with link)
                            player_cell = cells[0]
                            player_link = player_cell.find('a', href=True)
                            if not player_link:
                                continue
                            
                            player_name = player_link.get_text(strip=True)
                            player_url = player_link['href']
                            if not player_url.startswith('http'):
                                player_url = f"{self.BASE_URL}{player_url}"
                            
                            # Role (second cell)
                            role = cells[1].get_text(strip=True)
                            
                            # Stats (remaining cells: kills, deaths, assists, kda, rating)
                            stats = {}
                            if len(cells) >= 7:
                                try:
                                    stats['avg_kills'] = float(cells[2].get_text(strip=True))
                                    stats['avg_deaths'] = float(cells[3].get_text(strip=True))
                                    stats['avg_assists'] = float(cells[4].get_text(strip=True))
                                    stats['kda'] = float(cells[5].get_text(strip=True))
                                    stats['rating'] = float(cells[6].get_text(strip=True))
                                except ValueError:
                                    pass
                            
                            roster.append({
                                'name': player_name,
                                'role': role,
                                'url': player_url,
                                **stats
                            })
                        except Exception as e:
                            logger.warning("⚠️ Error parsing roster row: %s", e)
                            continue
                    
                    logger.info("✅ Scraped roster for %s: %s players", team_tag, len(roster))
                    return {
                        'name': team_name or team_tag,
                        'tag': team_tag.upper(),
                        'roster': roster
                    }
        except Exception as e:
            logger.error("❌ Error scraping team %s: %s", team_tag, e)
            return None
    
    async def get_player_stats(self, player_name: str) -> dict:
        """Scrape individual player statistics"""
        try:
            url = f"{self.BASE_URL}/player/{player_name}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.error("❌ Failed to fetch player %s: %s", player_name, response.status)
                        return None
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    data = {
                        'name': player_name,
                        'url': url
                    }
                    
                    # Extract role and team from header
                    page_text = soup.get_text()
                    
                    # Try to find role
                    role_match = re.search(r'(Top|Jungle|Mid|ADC|Support)', page_text)
                    if role_match:
                        data['role'] = role_match.group(1)
                    
                    # KDA ratio
                    kda_match = re.search(r'KDA Ratio\s+([\d.]+)', page_text)
                    if kda_match:
                        data['kda'] = float(kda_match.group(1))
                    
                    # Win rate
                    wr_match = re.search(r'([\d.]+)%\s+Win Rate', page_text)
                    if wr_match:
                        data['win_rate'] = float(wr_match.group(1))
                    
                    # Average stats
                    kills_match = re.search(r'([\d.]+)/[\d.]+/[\d.]+', page_text)
                    if kills_match:
                        kda_parts = kills_match.group(0).split('/')
                        if len(kda_parts) == 3:
                            data['avg_kills'] = float(kda_parts[0])
                            data['avg_deaths'] = float(kda_parts[1])
                            data['avg_assists'] = float(kda_parts[2])
                    
                    # CS/min
                    cs_match = re.search(r'CS/min\s+([\d.]+)', page_text)
                    if cs_match:
                        data['cs_per_min'] = float(cs_match.group(1))
                    
                    # Games played
                    games_match = re.search(r'Games\s+(\d+)', page_text)
                    if games_match:
                        data['games_played'] = int(games_match.group(1))
                    
                    # Parse champion stats
                    champions = []
                    # Look for champion images and associated data
                    for img in soup.find_all('img', src=lambda x: x and 'champion' in x):
                        try:
                            # Extract champion name from image URL
                            src = img.get('src', '')
                            champ_match = re.search(r'/champion/([^.]+)\.png', src)
                            if not champ_match:
                                continue
                            
                            champ_name = champ_match.group(1)
                            
                            # Try to find associated stats in parent or siblings
                            parent = img.find_parent()
                            if parent:
                                parent_text = parent.get_text()
                                # Look for pattern: "13 Cho'Gath 1.91 KDA • 85% WR"
                                stats_match = re.search(r'(\d+)\s+\w+\s+([\d.]+)\s+KDA\s+•\s+([\d.]+)%\s+WR', parent_text)
                                if stats_match:
                                    champions.append({
                                        'champion': champ_name,
                                        'games': int(stats_match.group(1)),
                                        'kda': float(stats_match.group(2)),
                                        'win_rate': float(stats_match.group(3))
                                    })
                        except Exception as e:
                            logger.warning("⚠️ Error parsing champion: %s", e)
                            continue
                    
                    data['champions'] = champions[:5]  # Top 5
                    
                    logger.info("✅ Scraped player stats for %s", player_name)
                    return data
        except Exception as e:
            logger.error("❌ Error scraping player %s: %s", player_name, e)
            return None
