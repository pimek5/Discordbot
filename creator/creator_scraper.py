"""
Web Scrapers for RuneForge and Divine Skins
Extracts profile and mod information
"""

import aiohttp
from bs4 import BeautifulSoup
import logging
import re

logger = logging.getLogger('creator_scraper')


class RuneForgeScraper:
    BASE_URL = "https://runeforge.dev"
    API_URL = "https://runeforge.dev/api"
    
    async def get_profile_data(self, username: str) -> dict | None:
        try:
            # Try API first
            api_url = f"{self.API_URL}/users/{username}"
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        try:
                            json_data = await response.json()
                            return self._parse_api_profile(json_data, username)
                        except Exception as e:
                            logger.warning("⚠️ API response not JSON, trying HTML scraping: %s", e)
            
            # Fallback to HTML scraping
            url = f"{self.BASE_URL}/users/{username}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error("❌ Failed to fetch RuneForge profile: %s (Status: %s)", url, response.status)
                        return None
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    data = {
                        'username': username,
                        'platform': 'runeforge',
                        'profile_url': url
                    }
                    # TODO: Update selectors based on real structure
                    rank_elem = soup.find('div', class_='rank')
                    if rank_elem:
                        data['rank'] = rank_elem.get_text(strip=True)
                    mods_elem = soup.find('div', class_='mods-count')
                    if mods_elem:
                        data['total_mods'] = self._parse_number(mods_elem.get_text(strip=True))
                    downloads_elem = soup.find('div', class_='downloads-count')
                    if downloads_elem:
                        data['total_downloads'] = self._parse_number(downloads_elem.get_text(strip=True))
                    views_elem = soup.find('div', class_='views-count')
                    if views_elem:
                        data['total_views'] = self._parse_number(views_elem.get_text(strip=True))
                    followers_elem = soup.find('div', class_='followers-count')
                    if followers_elem:
                        data['followers'] = self._parse_number(followers_elem.get_text(strip=True))
                    following_elem = soup.find('div', class_='following-count')
                    if following_elem:
                        data['following'] = self._parse_number(following_elem.get_text(strip=True))
                    joined_elem = soup.find('div', class_='join-date')
                    if joined_elem:
                        data['joined_date'] = joined_elem.get_text(strip=True)
                    logger.info("✅ RuneForge profile fetched: %s", username)
                    return data
        except Exception as e:
            logger.error("❌ Error scraping RuneForge profile %s: %s", username, e)
            return None
    
    def _parse_api_profile(self, json_data: dict, username: str) -> dict:
        """Parse RuneForge API response."""
        data = {
            'username': username,
            'platform': 'runeforge',
            'profile_url': f"{self.BASE_URL}/users/{username}"
        }
        if 'rank' in json_data:
            data['rank'] = json_data['rank']
        if 'mods_count' in json_data or 'modsCount' in json_data:
            data['total_mods'] = json_data.get('mods_count', json_data.get('modsCount', 0))
        if 'downloads' in json_data or 'total_downloads' in json_data:
            data['total_downloads'] = json_data.get('downloads', json_data.get('total_downloads', 0))
        if 'views' in json_data or 'total_views' in json_data:
            data['total_views'] = json_data.get('views', json_data.get('total_views', 0))
        if 'followers' in json_data:
            data['followers'] = json_data['followers']
        if 'following' in json_data:
            data['following'] = json_data['following']
        if 'joined_at' in json_data or 'created_at' in json_data:
            data['joined_date'] = json_data.get('joined_at', json_data.get('created_at', ''))
        logger.info("✅ RuneForge API profile parsed: %s", username)
        return data
    
    async def get_user_mods(self, username: str) -> list:
        try:
            # Try API first
            api_url = f"{self.API_URL}/users/{username}/mods"
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        try:
                            json_data = await response.json()
                            if isinstance(json_data, list):
                                return self._parse_api_mods(json_data)
                            elif isinstance(json_data, dict) and 'mods' in json_data:
                                return self._parse_api_mods(json_data['mods'])
                        except Exception as e:
                            logger.warning("⚠️ API mods not JSON, trying HTML: %s", e)
            
            # Fallback to HTML
            url = f"{self.BASE_URL}/users/{username}/mods"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error("❌ Failed to fetch mods: %s", url)
                        return []
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    mods = []
                    # TODO: Adjust selectors to real structure
                    cards = soup.find_all('div', class_='mod-card')
                    for card in cards:
                        try:
                            link = card.find('a', href=True)
                            if not link:
                                continue
                            mod_url = link['href']
                            if not mod_url.startswith('http'):
                                mod_url = f"{self.BASE_URL}{mod_url}"
                            mod_id = mod_url.split('/')[-1]
                            mod_name = link.get_text(strip=True)
                            time_el = card.find('time')
                            updated_at = time_el.get('datetime', '') if time_el else ''
                            mods.append({'id': mod_id, 'name': mod_name, 'url': mod_url, 'updated_at': updated_at})
                        except Exception as e:
                            logger.error("❌ Error parsing mod card: %s", e)
                            continue
                    logger.info("✅ Found %s mods for %s on RuneForge", len(mods), username)
                    return mods
        except Exception as e:
            logger.error("❌ Error getting user mods: %s", e)
            return []
    
    def _parse_number(self, text: str) -> int:
        try:
            t = text.lower().strip()
            mult = 1
            if 'k' in t:
                mult = 1000
                t = t.replace('k', '')
            elif 'm' in t:
                mult = 1_000_000
                t = t.replace('m', '')
            t = re.sub(r'[^\d.]', '', t)
            return int(float(t) * mult) if t else 0
        except Exception:
            return 0


class DivineSkinsScraper:
    BASE_URL = "https://divineskins.gg"
    API_URL = "https://divineskins.gg/api"
    
    async def get_profile_data(self, username: str) -> dict | None:
        try:
            # Try API first
            api_url = f"{self.API_URL}/users/{username}"
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        try:
                            json_data = await response.json()
                            return self._parse_api_profile(json_data, username)
                        except Exception as e:
                            logger.warning("⚠️ Divine Skins API not JSON, trying HTML: %s", e)
            
            # Fallback to HTML
            url = f"{self.BASE_URL}/{username}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error("❌ Failed to fetch Divine Skins profile: %s (Status: %s)", url, response.status)
                        return None
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    data = {'username': username, 'platform': 'divineskins', 'profile_url': url}
                    # TODO: Update selectors
                    rank = soup.find('div', class_='rank')
                    if rank:
                        data['rank'] = rank.get_text(strip=True)
                    skins = soup.find('div', class_='skins-count')
                    if skins:
                        data['total_mods'] = self._parse_number(skins.get_text(strip=True))
                    dls = soup.find('div', class_='downloads-count')
                    if dls:
                        data['total_downloads'] = self._parse_number(dls.get_text(strip=True))
                    logger.info("✅ Divine Skins profile fetched: %s", username)
                    return data
        except Exception as e:
            logger.error("❌ Error scraping Divine Skins profile %s: %s", username, e)
            return None
    
    def _parse_api_profile(self, json_data: dict, username: str) -> dict:
        """Parse Divine Skins API response."""
        data = {
            'username': username,
            'platform': 'divineskins',
            'profile_url': f"{self.BASE_URL}/{username}"
        }
        if 'rank' in json_data:
            data['rank'] = json_data['rank']
        if 'skins_count' in json_data or 'skinsCount' in json_data:
            data['total_mods'] = json_data.get('skins_count', json_data.get('skinsCount', 0))
        if 'downloads' in json_data or 'total_downloads' in json_data:
            data['total_downloads'] = json_data.get('downloads', json_data.get('total_downloads', 0))
        logger.info("✅ Divine Skins API profile parsed: %s", username)
        return data
    
    async def get_user_skins(self, username: str) -> list:
        try:
            # Try API first
            api_url = f"{self.API_URL}/users/{username}/skins"
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        try:
                            json_data = await response.json()
                            if isinstance(json_data, list):
                                return self._parse_api_skins(json_data)
                            elif isinstance(json_data, dict) and 'skins' in json_data:
                                return self._parse_api_skins(json_data['skins'])
                        except Exception as e:
                            logger.warning("⚠️ Divine Skins API skins not JSON, trying HTML: %s", e)
            
            # Fallback to HTML
            url = f"{self.BASE_URL}/{username}/skins"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error("❌ Failed to fetch skins: %s", url)
                        return []
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    skins = []
                    cards = soup.find_all('div', class_='skin-card')
                    for card in cards:
                        try:
                            link = card.find('a', href=True)
                            if not link:
                                continue
                            skin_url = link['href']
                            if not skin_url.startswith('http'):
                                skin_url = f"{self.BASE_URL}{skin_url}"
                            skin_id = skin_url.split('/')[-1]
                            skin_name = link.get_text(strip=True)
                            time_el = card.find('time')
                            updated_at = time_el.get('datetime', '') if time_el else ''
                            skins.append({'id': skin_id, 'name': skin_name, 'url': skin_url, 'updated_at': updated_at})
                        except Exception as e:
                            logger.error("❌ Error parsing skin card: %s", e)
                            continue
                    logger.info("✅ Found %s skins for %s on Divine Skins", len(skins), username)
                    return skins
        except Exception as e:
            logger.error("❌ Error getting user skins: %s", e)
            return []
    
    def _parse_number(self, text: str) -> int:
        try:
            t = text.lower().strip()
            mult = 1
            if 'k' in t:
                mult = 1000
                t = t.replace('k', '')
            elif 'm' in t:
                mult = 1_000_000
                t = t.replace('m', '')
            t = re.sub(r'[^\d.]', '', t)
            return int(float(t) * mult) if t else 0
        except Exception:
            return 0
