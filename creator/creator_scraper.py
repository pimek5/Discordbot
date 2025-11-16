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
                    # Avatar / banner heuristics
                    avatar = soup.find('img', class_=re.compile('avatar|profile', re.I)) or soup.find('img', attrs={'alt': re.compile(username, re.I)})
                    if avatar and avatar.get('src'):
                        data['avatar_url'] = avatar['src']
                    banner_div = soup.find('div', class_=re.compile('banner|header', re.I))
                    if banner_div and banner_div.get('style') and 'url(' in banner_div['style']:
                        m = re.search(r'url\(([^)]+)\)', banner_div['style'])
                        if m:
                            data['banner_url'] = m.group(1).strip('"\'')
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
        if 'avatar' in json_data:
            data['avatar_url'] = json_data.get('avatar')
        if 'banner' in json_data or 'background' in json_data:
            data['banner_url'] = json_data.get('banner', json_data.get('background'))
        logger.info("✅ RuneForge API profile parsed: %s", username)
        return data
    
    async def get_user_mods(self, username: str) -> list:
         try:
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
             url = f"{self.BASE_URL}/users/{username}/mods?page=0"
             async with aiohttp.ClientSession() as session:
                 async with session.get(url) as response:
                     if response.status != 200:
                         logger.error("❌ Failed to fetch mods: %s", url)
                         return []
                     html = await response.text()
                     soup = BeautifulSoup(html, 'html.parser')
                     mods = []
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
                             views_el = card.find(string=re.compile('views', re.I))
                             downloads_el = card.find(string=re.compile('downloads', re.I))
                             views = self._parse_number(views_el) if views_el else 0
                             downloads = self._parse_number(downloads_el) if downloads_el else 0
                             mods.append({'id': mod_id, 'name': mod_name, 'url': mod_url, 'updated_at': updated_at, 'views': views, 'downloads': downloads})
                         except Exception as e:
                             logger.error("❌ Error parsing mod card: %s", e)
                             continue
                     logger.info("✅ Found %s mods for %s on RuneForge", len(mods), username)
                     return mods
         except Exception as e:
             logger.error("❌ Error getting user mods: %s", e)
             return []
 
    def _parse_api_mods(self, mods_list: list) -> list:
        """Parse RuneForge API mods list (with views/downloads if present)."""
        parsed = []
        for mod in mods_list:
            try:
                mod_id = mod.get('id', mod.get('slug', ''))
                mod_name = mod.get('name', mod.get('title', ''))
                mod_url = mod.get('url', f"{self.BASE_URL}/mods/{mod_id}")
                updated_at = mod.get('updated_at', mod.get('updatedAt', ''))
                views = mod.get('views', mod.get('view_count', 0))
                downloads = mod.get('downloads', mod.get('download_count', 0))
                parsed.append({
                    'id': str(mod_id),
                    'name': mod_name,
                    'url': mod_url,
                    'updated_at': updated_at,
                    'views': views,
                    'downloads': downloads
                })
            except Exception as e:
                logger.warning("⚠️ RuneForge mod parse failed: %s", e)
                continue
        logger.info("✅ API mods parsed: %s", len(parsed))
        return parsed

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
                    data = {'username': username, 'platform': 'divineskins', 'profile_url': url}
                    # Parse embedded __NEXT_DATA__ if present
                    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
                    if m:
                        try:
                            import json
                            next_json = json.loads(m.group(1))
                            props = next_json.get('props', {}).get('pageProps', {})
                            user = props.get('user') or props.get('creator') or {}
                            if user:
                                data['rank'] = user.get('rank')
                                data['total_mods'] = user.get('worksCount') or user.get('skinsCount') or user.get('modsCount')
                                data['total_downloads'] = user.get('downloads') or user.get('downloadCount')
                                data['total_views'] = user.get('views') or user.get('viewCount')
                                data['followers'] = user.get('followers') or user.get('followersCount')
                                data['following'] = user.get('following') or user.get('followingCount')
                                data['joined_date'] = user.get('joinedAt') or user.get('createdAt')
                                data['avatar_url'] = user.get('avatar') or user.get('image')
                                data['banner_url'] = user.get('banner') or user.get('background')
                                logger.info("✅ Divine Skins profile fetched via __NEXT_DATA__: %s", username)
                                return data
                        except Exception as e:
                            logger.warning("⚠️ Failed parsing __NEXT_DATA__ for Divine Skins: %s", e)
                    # Minimal fallback
                    soup = BeautifulSoup(html, 'html.parser')
                    avatar = soup.find('img', class_=re.compile('avatar|profile', re.I))
                    if avatar and avatar.get('src'):
                        data['avatar_url'] = avatar['src']
                    banner_div = soup.find('div', class_=re.compile('banner|header', re.I))
                    if banner_div and banner_div.get('style') and 'url(' in banner_div['style']:
                        m2 = re.search(r'url\(([^)]+)\)', banner_div['style'])
                        if m2:
                            data['banner_url'] = m2.group(1).strip('"\'')
                    logger.info("✅ Divine Skins profile fetched (fallback minimal): %s", username)
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
        if 'views' in json_data or 'viewCount' in json_data:
            data['total_views'] = json_data.get('views', json_data.get('viewCount', 0))
        if 'followers' in json_data or 'followersCount' in json_data:
            data['followers'] = json_data.get('followers', json_data.get('followersCount', 0))
        if 'following' in json_data or 'followingCount' in json_data:
            data['following'] = json_data.get('following', json_data.get('followingCount', 0))
        if 'joinedAt' in json_data or 'createdAt' in json_data:
            data['joined_date'] = json_data.get('joinedAt', json_data.get('createdAt', ''))
        if 'avatar' in json_data:
            data['avatar_url'] = json_data.get('avatar')
        if 'banner' in json_data or 'background' in json_data:
            data['banner_url'] = json_data.get('banner', json_data.get('background'))
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
