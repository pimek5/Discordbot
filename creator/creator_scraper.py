"""
Web Scrapers for RuneForge and Divine Skins
Extracts profile and mod information
"""

import asyncio
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
             
             # HTML fallback with pagination
             all_mods = []
             seen_urls = set()
             page = 0
             max_pages = 50  # Safety limit
             error_500_count = 0  # Track server errors
             
             async with aiohttp.ClientSession() as session:
                 while page < max_pages:
                     url = f"{self.BASE_URL}/users/{username}/mods?page={page}"
                     logger.info("🔄 Fetching RuneForge mods page %s for %s", page, username)
                     
                     retry_count = 0
                     max_retries = 1
                     response_ok = False
                     
                     while retry_count <= max_retries and not response_ok:
                         try:
                             async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                                 if response.status == 200:
                                     response_ok = True
                                     error_500_count = 0  # Reset error counter on success
                                     html = await response.text()
                                     soup = BeautifulSoup(html, 'html.parser')
                                     
                                     # Find all links with /mods/ in href
                                     mod_links = soup.find_all('a', href=lambda x: x and '/mods/' in x and x != '/mods')
                                     
                                     page_mods = 0
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
                                             
                                             all_mods.append({
                                                 'id': mod_id, 
                                                 'name': mod_name, 
                                                 'url': mod_url, 
                                                 'updated_at': updated_at, 
                                                 'views': views, 
                                                 'downloads': downloads
                                             })
                                             page_mods += 1
                                         except Exception as e:
                                             logger.error("❌ Error parsing mod link: %s", e)
                                             continue
                                     
                                     # If no new mods found on this page, we're done
                                     if page_mods == 0:
                                         logger.info("📋 No more mods found at page %s, stopping pagination", page)
                                         return all_mods
                                     
                                     logger.info("✅ Page %s: found %s new mods", page, page_mods)
                                 else:
                                     # Check for 500 errors
                                     if response.status >= 500:
                                         error_500_count += 1
                                         logger.error("❌ Server error %s on page %s (count: %s)", response.status, page, error_500_count)
                                         if error_500_count > 2:
                                             logger.error("❌ Too many server errors (%s), stopping pagination", error_500_count)
                                             return all_mods
                                     
                                     if retry_count < max_retries:
                                         logger.warning("⚠️ Page %s returned %s, retrying...", page, response.status)
                                         retry_count += 1
                                         await asyncio.sleep(2)
                                     else:
                                         logger.warning("⚠️ Page %s failed with status %s, skipping...", page, response.status)
                                         response_ok = True  # Exit retry loop
                         except asyncio.TimeoutError:
                             if retry_count < max_retries:
                                 logger.warning("⚠️ Page %s timeout, retrying...", page)
                                 retry_count += 1
                                 await asyncio.sleep(2)
                             else:
                                 logger.warning("⚠️ Page %s timeout (no retries left), skipping...", page)
                                 response_ok = True  # Exit retry loop
                         except Exception as e:
                             if retry_count < max_retries:
                                 logger.warning("⚠️ Error fetching page %s: %s, retrying...", page, e)
                                 retry_count += 1
                                 await asyncio.sleep(2)
                             else:
                                 logger.warning("⚠️ Error fetching page %s: %s, skipping...", page, e)
                                 response_ok = True  # Exit retry loop
                     
                     # Delay between pages to avoid rate limiting
                     await asyncio.sleep(1)
                     page += 1
             
             logger.info("✅ Total: found %s mods for %s on RuneForge (scanned %s pages)", len(all_mods), username, page)
             return all_mods
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

    async def get_mod_details(self, mod_url: str) -> dict:
        """Fetch detailed information about a specific mod including description, tags, stats, and images."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(mod_url) as response:
                    if response.status != 200:
                        logger.warning("⚠️ Mod page returned status %s", response.status)
                        return {}
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    details = {
                        'name': '',
                        'description': '',
                        'author': '',
                        'views': 0,
                        'downloads': 0,
                        'likes': 0,
                        'version': '',
                        'updated_at': '',
                        'created_at': '',
                        'tags': [],
                        'image_url': None,
                        'author_avatar': None,
                        'category': ''
                    }
                    
                    # Try to extract from meta tags first
                    title_tag = soup.find('meta', property='og:title')
                    if title_tag:
                        details['name'] = title_tag.get('content', '')
                    
                    desc_tag = soup.find('meta', property='og:description') or soup.find('meta', attrs={'name': 'description'})
                    if desc_tag:
                        details['description'] = desc_tag.get('content', '')
                    
                    # Get image
                    og_image = soup.find('meta', property='og:image')
                    if og_image and og_image.get('content'):
                        img_url = og_image['content']
                        details['image_url'] = self._strip_cdn_proxy(img_url)
                    
                    # Parse page text for stats
                    page_text = soup.get_text()
                    
                    # Views - look for pattern before "views" text (may have [Image: Image] markers)
                    views_match = re.search(r'([\d,\.]+[kKmM]?)\s*\[?Image:\s*Image\]?\s*views?', page_text, re.I)
                    if not views_match:
                        views_match = re.search(r'([\d,\.]+[kKmM]?)\s*views?', page_text, re.I)
                    if views_match:
                        details['views'] = self._parse_number(views_match.group(1))
                        logger.info(f"[RuneForge] Views: {views_match.group(1)} -> {details['views']}")
                    
                    # Downloads
                    downloads_match = re.search(r'([\d,\.]+[kKmM]?)\s*\[?Image:\s*Image\]?\s*downloads?', page_text, re.I)
                    if not downloads_match:
                        downloads_match = re.search(r'([\d,\.]+[kKmM]?)\s*downloads?', page_text, re.I)
                    if downloads_match:
                        details['downloads'] = self._parse_number(downloads_match.group(1))
                        logger.info(f"[RuneForge] Downloads: {downloads_match.group(1)} -> {details['downloads']}")
                    
                    # Likes
                    likes_match = re.search(r'([\d,\.]+[kKmM]?)\s*\[?Image:\s*Image\]?\s*likes?', page_text, re.I)
                    if not likes_match:
                        likes_match = re.search(r'([\d,\.]+[kKmM]?)\s*likes?', page_text, re.I)
                    if likes_match:
                        details['likes'] = self._parse_number(likes_match.group(1))
                        logger.info(f"[RuneForge] Likes: {likes_match.group(1)} -> {details['likes']}")
                    
                    # Version
                    version_match = re.search(r'Version\s*[:)]?\s*([\d\.]+)', page_text, re.I)
                    if version_match:
                        details['version'] = version_match.group(1)
                    
                    # Updated date
                    updated_match = re.search(r'Updated\s*[:)]?\s*(.+?)(?:\n|$|Views|Downloads)', page_text, re.I)
                    if updated_match:
                        details['updated_at'] = updated_match.group(1).strip()
                    
                    # Author - find link to /users/username
                    author_link = soup.find('a', href=re.compile(r'^/users/[^/]+$'))
                    if author_link:
                        # Extract username from href like /users/p1mek
                        href = author_link.get('href', '')
                        username = href.split('/users/')[-1] if '/users/' in href else ''
                        if username:
                            details['author'] = username
                            logger.info(f"[RuneForge] Author: {username}")
                    
                    # Tags/Categories
                    tag_elements = soup.find_all('a', href=re.compile(r'/tags?/|/categories?/'))
                    details['tags'] = [tag.get_text(strip=True) for tag in tag_elements[:5]]
                    
                    logger.info("✅ Fetched mod details: %s", details.get('name', mod_url))
                    return details
        except Exception as e:
            logger.error(f"❌ Error fetching mod details from {mod_url}: {e}")
            return {}

    def _strip_cdn_proxy(self, url: str) -> str:
        """If url is a Cloudflare cdn-cgi/image proxy, extract the direct image link."""
        if url and '/cdn-cgi/image/' in url:
            # Find the last occurrence of 'https://' in the string (the real image link)
            idx = url.rfind('https://')
            if idx > 0:
                return url[idx:]
        return url


class DivineSkinsScraper:
    BASE_URL = "https://divineskins.gg"
    CATALOG_API = "https://api.divineskins.gg"
    CDN_URL = "https://lol-assets.divine-cdn.com"

    _API_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Origin': 'https://divineskins.gg',
        'Referer': 'https://divineskins.gg/',
    }

    async def get_user_skins(self, username: str) -> list:
        """Return list of skins for a user via the DivineSkins catalog API."""
        skins = []
        page = 0
        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    url = f"{self.CATALOG_API}/api/catalog/skins/search/{username}?page={page}&size=100"
                    async with session.get(url, headers=self._API_HEADERS) as resp:
                        if resp.status != 200:
                            logger.error("\u274c DivineSkins catalog API error %s: %s", resp.status, url)
                            break
                        data = await resp.json()
                        for item in data.get('content', []):
                            if item.get('artistUsername', '').lower() != username.lower():
                                continue
                            slug = item.get('slug', '')
                            artist = item.get('artistUsername', username)
                            image_path = item.get('imagePath', '')
                            skins.append({
                                'id': str(item.get('id', slug)),
                                'name': item.get('name', 'Untitled'),
                                'url': f"{self.BASE_URL}/{artist}/{slug}",
                                'updated_at': item.get('lastUpdatedDate', ''),
                                'downloads': item.get('downloadCount', 0),
                                'views': item.get('viewCount', 0),
                                'likes': item.get('likeCount', 0),
                                'image_url': f"{self.CDN_URL}/{image_path}" if image_path else None,
                            })
                        if data.get('last', True):
                            break
                        page += 1
            logger.info("\u2705 Found %s skins for %s on Divine Skins (API)", len(skins), username)
        except Exception as e:
            logger.error("\u274c Error getting user skins for %s: %s", username, e)
        return skins

    async def get_profile_data(self, username: str) -> dict | None:
        """Fetch Divine Skins profile by aggregating catalog API data."""
        try:
            skins = await self.get_user_skins(username)
            total_downloads = sum(s.get('downloads', 0) for s in skins)
            total_views = sum(s.get('views', 0) for s in skins)
            data = {
                'username': username,
                'platform': 'divineskins',
                'profile_url': f"{self.BASE_URL}/{username}",
                'total_mods': len(skins),
                'total_downloads': total_downloads,
                'total_views': total_views,
            }
            logger.info("\u2705 DivineSkins profile aggregated: %s \u2014 %d mods, %d dl, %d views",
                        username, len(skins), total_downloads, total_views)
            return data
        except Exception as e:
            logger.error("\u274c Error scraping DivineSkins profile %s: %s", username, e)
            return None

    async def get_mod_details(self, mod_url: str) -> dict:
        """Fetch skin details by extracting slug from URL and querying the catalog API."""
        details = {
            'name': '', 'description': '', 'author': '',
            'views': 0, 'downloads': 0, 'likes': 0,
            'version': '', 'updated_at': '', 'created_at': '',
            'tags': [], 'image_url': None, 'author_avatar': None, 'category': ''
        }
        try:
            parts = mod_url.rstrip('/').split('/')
            slug = parts[-1] if len(parts) >= 2 else ''
            artist = parts[-2] if len(parts) >= 4 else ''
            if artist and slug:
                # Search by artist username, then filter by slug
                url = f"{self.CATALOG_API}/api/catalog/skins/search/{artist}?size=100"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self._API_HEADERS) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for item in data.get('content', []):
                                if item.get('slug', '').lower() == slug.lower():
                                    details['name'] = item.get('name', '')
                                    details['author'] = item.get('artistUsername', artist)
                                    details['category'] = item.get('category', '')
                                    details['views'] = item.get('viewCount', 0)
                                    details['downloads'] = item.get('downloadCount', 0)
                                    details['likes'] = item.get('likeCount', 0)
                                    details['updated_at'] = item.get('lastUpdatedDate', '')
                                    details['created_at'] = item.get('contentUpdatedDate', '')
                                    ip = item.get('imagePath', '')
                                    if ip:
                                        details['image_url'] = f"{self.CDN_URL}/{ip}"
                                    logger.info("[DivineSkins] \u2705 Mod details from API: %s", details['name'])
                                    return details
            # Fallback: og: meta tags
            async with aiohttp.ClientSession() as session:
                async with session.get(mod_url, headers={'User-Agent': self._API_HEADERS['User-Agent']}) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        og_title = soup.find('meta', property='og:title')
                        if og_title:
                            details['name'] = og_title.get('content', '')
                        og_desc = soup.find('meta', property='og:description')
                        if og_desc:
                            details['description'] = og_desc.get('content', '')
                        og_image = soup.find('meta', property='og:image')
                        if og_image and og_image.get('content'):
                            details['image_url'] = og_image['content']
        except Exception as e:
            logger.error("\u274c Error fetching mod details from %s: %s", mod_url, e)
        return details

    async def get_mod_image(self, mod_url: str) -> str | None:
        """Return thumbnail image URL for a mod page."""
        try:
            parts = mod_url.rstrip('/').split('/')
            slug = parts[-1] if parts else ''
            artist = parts[-2] if len(parts) >= 4 else ''
            if artist and slug:
                # Search by artist username, then filter by slug
                url = f"{self.CATALOG_API}/api/catalog/skins/search/{artist}?size=100"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self._API_HEADERS) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for item in data.get('content', []):
                                if item.get('slug', '').lower() == slug.lower():
                                    ip = item.get('imagePath', '')
                                    if ip:
                                        return f"{self.CDN_URL}/{ip}"
            # Fallback og:image
            async with aiohttp.ClientSession() as session:
                async with session.get(mod_url, headers={'User-Agent': self._API_HEADERS['User-Agent']}) as resp:
                    if resp.status == 200:
                        soup = BeautifulSoup(await resp.text(), 'html.parser')
                        og = soup.find('meta', property='og:image')
                        if og:
                            return og.get('content')
        except Exception as e:
            logger.error("\u274c Error fetching mod image from %s: %s", mod_url, e)
        return None

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
