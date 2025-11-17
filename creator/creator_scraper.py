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
                    
                    # Avatar - find first image with profile/avatar in src
                    for img in soup.find_all('img'):
                        src = img.get('src', '')
                        alt = img.get('alt', '').lower()
                        if 'avatar' in alt or 'profile' in alt or 'avatar' in src or username in alt:
                            if src.startswith('http'):
                                data['avatar_url'] = src
                            elif src.startswith('/'):
                                data['avatar_url'] = f"https://runeforge.dev{src}"
                            break
                    
                    # Parse text for stats using regex patterns
                    page_text = soup.get_text()
                    
                    # Mods count - look for pattern like "24mods"
                    mods_match = re.search(r'(\d+)\s*mods?', page_text, re.I)
                    if mods_match:
                        data['total_mods'] = int(mods_match.group(1))
                    
                    # Downloads - look for "55.2k downloads"
                    downloads_match = re.search(r'([\d,\.]+[kKmM]?)\s*downloads?', page_text, re.I)
                    if downloads_match:
                        data['total_downloads'] = self._parse_number(downloads_match.group(1))
                    
                    # Views - look for "185.4k views"
                    views_match = re.search(r'([\d,\.]+[kKmM]?)\s*views?', page_text, re.I)
                    if views_match:
                        data['total_views'] = self._parse_number(views_match.group(1))
                    
                    # Followers
                    followers_match = re.search(r'(\d+)\s*followers?', page_text, re.I)
                    if followers_match:
                        data['followers'] = int(followers_match.group(1))
                    
                    # Following
                    following_match = re.search(r'(\d+)\s*following', page_text, re.I)
                    if following_match:
                        data['following'] = int(following_match.group(1))
                    
                    # Joined date - "Joined X months ago"
                    joined_match = re.search(r'Joined\s+(.+?)(?:\n|$|Overview|Mods)', page_text, re.I)
                    if joined_match:
                        data['joined_date'] = joined_match.group(1).strip()
                    
                    # Rank - look for "Creator" or similar badge
                    rank_match = re.search(r'@\w+\s*(\w+)\s*\d+\s*mods', page_text, re.I)
                    if rank_match:
                        potential_rank = rank_match.group(1)
                        if potential_rank.lower() in ['creator', 'contributor', 'developer', 'admin', 'moderator']:
                            data['rank'] = potential_rank
                    
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
                     seen_urls = set()
                     # Find all links with /mods/ in href
                     mod_links = soup.find_all('a', href=lambda x: x and '/mods/' in x and x != '/mods')
                     for link in mod_links:
                         try:
                             mod_url = link.get('href', '')
                             if not mod_url or mod_url in seen_urls:
                                 continue
                             if not mod_url.startswith('http'):
                                 mod_url = f"{self.BASE_URL}{mod_url}"
                             seen_urls.add(mod_url)
                             mod_id = mod_url.rstrip('/').split('/')[-1]
                             mod_name = link.get_text(strip=True)
                             if not mod_name:
                                 continue
                             # Try to find stats in parent or sibling elements
                             parent = link.find_parent()
                             views = 0
                             downloads = 0
                             updated_at = ''
                             if parent:
                                 # Look for time element
                                 time_el = parent.find('time')
                                 if time_el:
                                     updated_at = time_el.get('datetime', '')
                                 # Look for stats text
                                 stats_text = parent.get_text()
                                 views_match = re.search(r'([\d,\.]+)\s*k?\s*views?', stats_text, re.I)
                                 downloads_match = re.search(r'([\d,\.]+)\s*k?\s*downloads?', stats_text, re.I)
                                 if views_match:
                                     views = self._parse_number(views_match.group(1))
                                 if downloads_match:
                                     downloads = self._parse_number(downloads_match.group(1))
                             mods.append({
                                 'id': mod_id, 
                                 'name': mod_name, 
                                 'url': mod_url, 
                                 'updated_at': updated_at, 
                                 'views': views, 
                                 'downloads': downloads
                             })
                         except Exception as e:
                             logger.error("❌ Error parsing mod link: %s", e)
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
    
    async def get_mod_image(self, mod_url: str) -> str | None:
        """Fetch the main/thumbnail image from a mod page. Strips cdn-cgi/image proxy for Discord compatibility."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(mod_url) as response:
                    if response.status != 200:
                        logger.warning("⚠️ Mod page returned status %s", response.status)
                        return None
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    # Try og:image meta tag
                    og_image = soup.find('meta', property='og:image')
                    if og_image and og_image.get('content'):
                        img_url = og_image['content']
                        # Remove cdn-cgi/image proxy if present
                        img_url = self._strip_cdn_proxy(img_url)
                        if any(img_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                            logger.info(f"[get_mod_image] og:image: {img_url}")
                            return img_url
                    # Try twitter:image
                    twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
                    if twitter_image and twitter_image.get('content'):
                        img_url = twitter_image['content']
                        img_url = self._strip_cdn_proxy(img_url)
                        if any(img_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                            logger.info(f"[get_mod_image] twitter:image: {img_url}")
                            return img_url
                    # Try first <img> with direct image extension
                    for img in soup.find_all('img'):
                        src = img.get('src', '')
                        src = self._strip_cdn_proxy(src)
                        if any(src.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                            logger.info(f"[get_mod_image] <img>: {src}")
                            return src if src.startswith('http') else f"{self.BASE_URL}{src}"
                    logger.warning("[get_mod_image] No suitable image found on page")
                    return None
        except Exception as e:
            logger.error(f"❌ Error fetching mod image from {mod_url}: {e}")
            return None

    def _strip_cdn_proxy(self, url: str) -> str:
        """If url is a Cloudflare cdn-cgi/image proxy, extract the direct image link."""
        if url and '/cdn-cgi/image/' in url:
            # Find the last occurrence of 'https://' in the string (the real image link)
            idx = url.rfind('https://')
            if idx > 0:
                return url[idx:]
        return url
    
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
