"""
Web Scrapers for RuneForge and Divine Skins
Extracts profile and mod information
"""

import aiohttp
from bs4 import BeautifulSoup
import logging
from datetime import datetime
import re

logger = logging.getLogger('creator_scraper')


class RuneForgeScraper:
    """Scraper for RuneForge.dev"""
    
    BASE_URL = "https://runeforge.dev"
    
    async def get_profile_data(self, username: str) -> dict:
        """Get user profile data from RuneForge"""
        try:
            url = f"{self.BASE_URL}/users/{username}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"❌ Failed to fetch RuneForge profile: {url} (Status: {response.status})")
                        return None
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Extract profile information
                    profile_data = {
                        'username': username,
                        'platform': 'runeforge',
                        'profile_url': url
                    }
                    
                    # Parse stats (this is a template - adjust based on actual HTML structure)
                    # You'll need to inspect the actual page to find correct selectors
                    
                    # Example selectors (ADJUST THESE):
                    rank_elem = soup.find('div', class_='rank')
                    if rank_elem:
                        profile_data['rank'] = rank_elem.get_text(strip=True)
                    
                    mods_elem = soup.find('div', class_='mods-count')
                    if mods_elem:
                        mods_text = mods_elem.get_text(strip=True)
                        profile_data['total_mods'] = self._parse_number(mods_text)
                    
                    downloads_elem = soup.find('div', class_='downloads-count')
                    if downloads_elem:
                        downloads_text = downloads_elem.get_text(strip=True)
                        profile_data['total_downloads'] = self._parse_number(downloads_text)
                    
                    views_elem = soup.find('div', class_='views-count')
                    if views_elem:
                        views_text = views_elem.get_text(strip=True)
                        profile_data['total_views'] = self._parse_number(views_text)
                    
                    followers_elem = soup.find('div', class_='followers-count')
                    if followers_elem:
                        followers_text = followers_elem.get_text(strip=True)
                        profile_data['followers'] = self._parse_number(followers_text)
                    
                    following_elem = soup.find('div', class_='following-count')
                    if following_elem:
                        following_text = following_elem.get_text(strip=True)
                        profile_data['following'] = self._parse_number(following_text)
                    
                    joined_elem = soup.find('div', class_='join-date')
                    if joined_elem:
                        profile_data['joined_date'] = joined_elem.get_text(strip=True)
                    
                    logger.info(f"✅ RuneForge profile fetched: {username}")
                    return profile_data
                    
        except Exception as e:
            logger.error(f"❌ Error scraping RuneForge profile {username}: {e}")
            return None
    
    async def get_user_mods(self, username: str) -> list:
        """Get all mods by user"""
        try:
            url = f"{self.BASE_URL}/users/{username}/mods"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"❌ Failed to fetch mods: {url}")
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    mods = []
                    
                    # Find all mod cards (ADJUST SELECTORS BASED ON ACTUAL HTML)
                    mod_cards = soup.find_all('div', class_='mod-card')
                    
                    for card in mod_cards:
                        try:
                            mod_link = card.find('a', href=True)
                            if not mod_link:
                                continue
                            
                            mod_url = mod_link['href']
                            if not mod_url.startswith('http'):
                                mod_url = f"{self.BASE_URL}{mod_url}"
                            
                            # Extract mod ID from URL
                            mod_id = mod_url.split('/')[-1]
                            
                            mod_name = mod_link.get_text(strip=True)
                            
                            # Get updated date
                            updated_elem = card.find('time')
                            updated_at = updated_elem.get('datetime', '') if updated_elem else ''
                            
                            mods.append({
                                'id': mod_id,
                                'name': mod_name,
                                'url': mod_url,
                                'updated_at': updated_at
                            })
                            
                        except Exception as e:
                            logger.error(f"❌ Error parsing mod card: {e}")
                            continue
                    
                    logger.info(f"✅ Found {len(mods)} mods for {username} on RuneForge")
                    return mods
                    
        except Exception as e:
            logger.error(f"❌ Error getting user mods from RuneForge: {e}")
            return []
    
    async def get_latest_mods(self) -> list:
        """Get latest mods from the main page"""
        try:
            url = f"{self.BASE_URL}/mods"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"❌ Failed to fetch latest mods: {url}")
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    mods = []
                    mod_cards = soup.find_all('div', class_='mod-card')
                    
                    for card in mod_cards:
                        try:
                            mod_link = card.find('a', href=True)
                            if not mod_link:
                                continue
                            
                            author_elem = card.find('div', class_='author')
                            if author_elem:
                                author_link = author_elem.find('a', href=True)
                                if author_link:
                                    author = author_link.get_text(strip=True)
                                    author_url = author_link['href']
                                    
                                    mod_url = mod_link['href']
                                    if not mod_url.startswith('http'):
                                        mod_url = f"{self.BASE_URL}{mod_url}"
                                    
                                    mods.append({
                                        'author': author,
                                        'author_url': author_url,
                                        'mod_name': mod_link.get_text(strip=True),
                                        'mod_url': mod_url,
                                        'mod_id': mod_url.split('/')[-1]
                                    })
                                    
                        except Exception as e:
                            logger.error(f"❌ Error parsing latest mod: {e}")
                            continue
                    
                    return mods
                    
        except Exception as e:
            logger.error(f"❌ Error getting latest mods: {e}")
            return []
    
    def _parse_number(self, text: str) -> int:
        """Parse number from text (handles k, m suffixes)"""
        try:
            text = text.lower().strip()
            multiplier = 1
            
            if 'k' in text:
                multiplier = 1000
                text = text.replace('k', '')
            elif 'm' in text:
                multiplier = 1000000
                text = text.replace('m', '')
            
            # Remove any non-numeric characters except decimal point
            text = re.sub(r'[^\d.]', '', text)
            
            if text:
                return int(float(text) * multiplier)
            return 0
            
        except Exception as e:
            logger.error(f"❌ Error parsing number '{text}': {e}")
            return 0


class DivineSkinsScraper:
    """Scraper for DivineSkins.gg"""
    
    BASE_URL = "https://divineskins.gg"
    
    async def get_profile_data(self, username: str) -> dict:
        """Get user profile data from Divine Skins"""
        try:
            url = f"{self.BASE_URL}/{username}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"❌ Failed to fetch Divine Skins profile: {url} (Status: {response.status})")
                        return None
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    profile_data = {
                        'username': username,
                        'platform': 'divineskins',
                        'profile_url': url
                    }
                    
                    # Parse profile stats (ADJUST SELECTORS)
                    rank_elem = soup.find('div', class_='rank')
                    if rank_elem:
                        profile_data['rank'] = rank_elem.get_text(strip=True)
                    
                    skins_elem = soup.find('div', class_='skins-count')
                    if skins_elem:
                        skins_text = skins_elem.get_text(strip=True)
                        profile_data['total_mods'] = self._parse_number(skins_text)
                    
                    downloads_elem = soup.find('div', class_='downloads-count')
                    if downloads_elem:
                        downloads_text = downloads_elem.get_text(strip=True)
                        profile_data['total_downloads'] = self._parse_number(downloads_text)
                    
                    logger.info(f"✅ Divine Skins profile fetched: {username}")
                    return profile_data
                    
        except Exception as e:
            logger.error(f"❌ Error scraping Divine Skins profile {username}: {e}")
            return None
    
    async def get_user_skins(self, username: str) -> list:
        """Get all skins by user"""
        try:
            url = f"{self.BASE_URL}/{username}/skins"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"❌ Failed to fetch skins: {url}")
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    skins = []
                    skin_cards = soup.find_all('div', class_='skin-card')
                    
                    for card in skin_cards:
                        try:
                            skin_link = card.find('a', href=True)
                            if not skin_link:
                                continue
                            
                            skin_url = skin_link['href']
                            if not skin_url.startswith('http'):
                                skin_url = f"{self.BASE_URL}{skin_url}"
                            
                            skin_id = skin_url.split('/')[-1]
                            skin_name = skin_link.get_text(strip=True)
                            
                            updated_elem = card.find('time')
                            updated_at = updated_elem.get('datetime', '') if updated_elem else ''
                            
                            skins.append({
                                'id': skin_id,
                                'name': skin_name,
                                'url': skin_url,
                                'updated_at': updated_at
                            })
                            
                        except Exception as e:
                            logger.error(f"❌ Error parsing skin card: {e}")
                            continue
                    
                    logger.info(f"✅ Found {len(skins)} skins for {username} on Divine Skins")
                    return skins
                    
        except Exception as e:
            logger.error(f"❌ Error getting user skins: {e}")
            return []
    
    def _parse_number(self, text: str) -> int:
        """Parse number from text"""
        try:
            text = text.lower().strip()
            multiplier = 1
            
            if 'k' in text:
                multiplier = 1000
                text = text.replace('k', '')
            elif 'm' in text:
                multiplier = 1000000
                text = text.replace('m', '')
            
            text = re.sub(r'[^\d.]', '', text)
            
            if text:
                return int(float(text) * multiplier)
            return 0
            
        except Exception as e:
            logger.error(f"❌ Error parsing number '{text}': {e}")
            return 0
