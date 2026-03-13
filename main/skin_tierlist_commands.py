"""
Skin Tierlist Commands Module
/skintierlist - Create a skin tierlist for a champion
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
import aiohttp
import re
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
import asyncio
from datetime import datetime, timedelta

logger = logging.getLogger('skin_tierlist_commands')

# Global session for better performance
_session: Optional[aiohttp.ClientSession] = None

async def get_session() -> aiohttp.ClientSession:
    """Get or create global aiohttp session"""
    global _session
    if _session is None:
        _session = aiohttp.ClientSession()
    return _session

# Tier colors for embeds
TIER_COLORS = {
    'S': discord.Color.red(),      # Red
    'A': discord.Color.orange(),   # Orange
    'B': discord.Color.gold(),     # Gold
    'C': discord.Color.yellow(),   # Yellow
    'D': discord.Color.green(),    # Green
    'E': discord.Color.blue(),     # Blue
    'F': discord.Color.purple(),   # Purple
}

TIER_EMOJIS = {
    'S': '🟥',
    'A': '🟧',
    'B': '🟨',
    'C': '🟩',
    'D': '🟦',
    'E': '🟪',
    'F': '⬛',
}


class SkinTierlistView(discord.ui.View):
    """Interactive view for skin tierlist with tier assignment buttons"""
    
    def __init__(self, user_id: int, skins: List[Dict], champion: str, timeout: int = 600):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.skins = skins
        self.champion = champion
        self.tierlist = {tier: [] for tier in ['S', 'A', 'B', 'C', 'D', 'E', 'F']}
        self.current_skin_index = 0
        self.original_message = None
        
        # Create buttons for each skin (up to 25 buttons, Discord limit)
        self._add_skin_buttons()
    
    def _add_skin_buttons(self):
        """Add numbered buttons for each skin (1-9, 10-19, etc.)"""
        for idx, skin in enumerate(self.skins[:25]):  # Discord has 25 button limit per message
            button = discord.ui.Button(
                label=str(idx + 1),
                style=discord.ButtonStyle.secondary,
                custom_id=f"skin_btn_{idx}"
            )
            button.callback = self._skin_button_callback(idx)
            self.add_item(button)
        
        # Add tier buttons
        for tier in ['S', 'A', 'B', 'C', 'D', 'E', 'F']:
            button = discord.ui.Button(
                label=f"Tier {tier}",
                style=discord.ButtonStyle.danger if tier == 'S' else discord.ButtonStyle.secondary,
                custom_id=f"tier_btn_{tier}"
            )
            button.callback = self._tier_button_callback(tier)
            self.add_item(button)
        
        # Add done button
        done_button = discord.ui.Button(
            label="✅ Done",
            style=discord.ButtonStyle.success,
            custom_id="done_btn"
        )
        done_button.callback = self._done_callback
        self.add_item(done_button)
    
    def _skin_button_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.defer()
                return
            
            self.current_skin_index = index
            embed = self._create_skin_selection_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        
        return callback
    
    def _tier_button_callback(self, tier: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.defer()
                return
            
            if self.current_skin_index < len(self.skins):
                skin = self.skins[self.current_skin_index]
                
                # Remove skin from other tiers
                for t in self.tierlist.values():
                    if skin['name'] in t:
                        t.remove(skin['name'])
                
                # Add to selected tier
                if skin['name'] not in self.tierlist[tier]:
                    self.tierlist[tier].append(skin['name'])
                
                # Move to next skin
                self.current_skin_index += 1
                if self.current_skin_index >= len(self.skins):
                    self.current_skin_index = len(self.skins) - 1
                
                embed = self._create_skin_selection_embed()
                await interaction.response.edit_message(embed=embed, view=self)
        
        return callback
    
    def _create_skin_selection_embed(self) -> discord.Embed:
        """Create embed showing current skin selection"""
        skin = self.skins[self.current_skin_index]
        
        embed = discord.Embed(
            title=f"{self.champion} Skin Tierlist",
            description=f"**Select tier for: {skin['name']}**\n({self.current_skin_index + 1}/{len(self.skins)})",
            color=discord.Color.blue()
        )
        
        if skin['image_url']:
            embed.set_thumbnail(url=skin['image_url'])
        
        # Show current tierlist progress
        embed.add_field(
            name="📊 Tierlist Progress",
            value=self._format_tierlist_progress(),
            inline=False
        )
        
        return embed
    
    def _format_tierlist_progress(self) -> str:
        """Format current tierlist for display"""
        result = []
        for tier in ['S', 'A', 'B', 'C', 'D', 'E', 'F']:
            skins_in_tier = self.tierlist[tier]
            if skins_in_tier:
                result.append(f"{TIER_EMOJIS[tier]} **Tier {tier}**: {', '.join(skins_in_tier)}")
        
        if not result:
            return "No skins ranked yet"
        
        return "\n".join(result)
    
    async def _done_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        
        embed = self._create_final_tierlist_embed()
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()
    
    def _create_final_tierlist_embed(self) -> discord.Embed:
        """Create final tierlist embed"""
        embed = discord.Embed(
            title=f"🏆 {self.champion} Skin Tierlist - Final",
            color=discord.Color.gold()
        )
        
        for tier in ['S', 'A', 'B', 'C', 'D', 'E', 'F']:
            skins_in_tier = self.tierlist[tier]
            if skins_in_tier:
                value = "\n".join([f"• {skin}" for skin in skins_in_tier])
            else:
                value = "*No skins*"
            
            embed.add_field(
                name=f"{TIER_EMOJIS[tier]} Tier {tier}",
                value=value,
                inline=True
            )
        
        total_skins = sum(len(skins) for skins in self.tierlist.values())
        embed.set_footer(text=f"Total skins ranked: {total_skins}/{len(self.skins)}")
        
        return embed


class SkinScraper:
    """Scrapes skin information from League of Legends wiki"""
    
    # Special champion name mappings (for champions with unusual wiki URLs)
    CHAMPION_URL_MAPPING = {
        "DrMundo": "Dr._Mundo",
        "JarvanIV": "Jarvan IV",
        "KSante": "K'Sante",
        "XinZhao": "Xin Zhao",
        "Khazix": "Kha'Zix",
        "LeeSin": "Lee Sin",
        "MasterYi": "Master Yi",
        "RekSai": "Rek'Sai",
        "AurelionSol": "Aurelion Sol",
        "Chogath": "Cho'Gath",
        "Leblanc": "LeBlanc",
        "Kaisa": "Kai'Sa",
        "KogMaw": "Kog'Maw",
        "MissFortune": "Miss Fortune",
        "TwistedFate": "Twisted Fate",
        "Renata": "Renata Glasc",
        "TahmKench": "Tahm Kench",
        "Velkoz": "Vel'Koz",
    }
    
    @staticmethod
    async def fetch_champion_skins(champion_name: str) -> List[Dict]:
        """Fetch skins for a champion from wiki sources"""
        try:
            # Normalize input: capitalize each word (e.g. "twitch" -> "Twitch", "twisted fate" -> "Twisted Fate")
            champion_name = champion_name.strip().title()
            # Use mapping if available, otherwise use provided name
            display_name = SkinScraper.CHAMPION_URL_MAPPING.get(champion_name, champion_name)
            
            # Normalize champion name for URL
            url_name = display_name.replace(" ", "_")
            url_name_encoded = url_name.replace("'", "%27")
            url_name_no_apostrophe = url_name.replace("'", "")
            
            # Try official wiki first with encoded apostrophe, then fallback variants
            urls_to_try = [
                f"https://wiki.leagueoflegends.com/en-us/{url_name_encoded}/Cosmetics",
                f"https://leagueoflegends.fandom.com/wiki/{url_name_encoded}/Skins",
                f"https://wiki.leagueoflegends.com/en-us/{url_name_no_apostrophe}/Cosmetics",
                f"https://leagueoflegends.fandom.com/wiki/{url_name_no_apostrophe}/Skins"
            ]
            
            # Use global session for better performance
            session = await get_session()
            for url in urls_to_try:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5, connect=2)) as response:
                        if response.status == 200:
                            html = await response.text()
                            skins = SkinScraper._parse_skins_from_html(html, champion_name)
                            
                            if skins:
                                logger.info(f"✅ Found {len(skins)} skins for {champion_name}")
                                return skins
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout fetching from {url}")
                    continue
                except Exception as e:
                    logger.warning(f"Error fetching from {url}: {e}")
                    continue
            
            logger.warning(f"No skins found for {champion_name} from any source")
            return []
        
        except Exception as e:
            logger.error(f"Error in fetch_champion_skins: {e}")
            return []
    
    @staticmethod
    def _extract_image_url(html: str, skin_name: str) -> Optional[str]:
        """Extract image URL for a specific skin from HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for links containing the skin image file
            # Pattern: wiki.leagueoflegends.com/en-us/File:Champion_SkinName.jpg
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                href = link.get('href', '')
                
                # Check if it's a splash art link
                if '/File:' in href and '.jpg' in href:
                    # Extract filename from href
                    if 'wiki.leagueoflegends.com' in href:
                        # Convert wiki link to direct image URL
                        match = re.search(r'/File:(.+?)(?:\.jpg|\.png)', href, re.IGNORECASE)
                        if match:
                            filename = match.group(1)
                            # Build direct image URL
                            image_url = f"https://wiki.leagueoflegends.com/en-us/images/{filename.replace('_', '_')}.jpg"
                            return image_url
            
            return None
        except Exception as e:
            logger.debug(f"Error extracting image URL for {skin_name}: {e}")
            return None
    
    @staticmethod
    def _build_image_map(soup: BeautifulSoup) -> Dict[str, str]:
        """Build a map of normalized skin names to their wiki image CDN URLs from skin-icon divs"""
        try:
            image_map = {}
            
            # Find all skin-icon divs which contain data-skin attribute and image
            # These are in the cosmetics pages and contain the CDN image URLs
            skin_icons = soup.find_all('div', {'class': re.compile(r'.*skin-icon.*')})
            
            for div in skin_icons:
                # Get the skin name from data-skin attribute
                data_skin = div.get('data-skin', '')
                if not data_skin:
                    continue
                
                # Find the image inside this div
                img = div.find('img')
                if not img:
                    continue
                
                src = img.get('src', '')
                if not src or '.jpg' not in src.lower():
                    continue
                
                # Build full CDN URL
                if src.startswith('/'):
                    cdn_url = f"https://wiki.leagueoflegends.com{src}"
                else:
                    cdn_url = src
                
                # Normalize skin name for matching
                skin_name_normalized = data_skin.replace(' ', '').replace('_', '').replace('/', '').replace('-', '').replace('.', '').lower()
                
                # Store in map
                image_map[skin_name_normalized] = cdn_url
            
            return image_map
        except Exception as e:
            logger.debug(f"Error building image map: {e}")
            return {}
    
    @staticmethod
    def _parse_skins_from_html(html: str, champion_name: str) -> List[Dict]:
        """Parse skin information from wiki HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            skins = []
            seen = set()
            
            # Build a map of skin names to image URLs (reuse soup)
            image_map = SkinScraper._build_image_map(soup)
            
            # Common patterns to skip (only chromatic variants, not full skin names)
            SKIP_PATTERNS = {
                'chromas', 'view in 3d', 'explore properties', 'eternals', 'chroma',
                'amethyst', 'aquamarine', 'citrine', 'emerald', 'obsidian', 'pearl',
                'rose quartz', 'ruby', 'sapphire', 'tanzanite', 'turquoise', 'cateye',
                'defray', 'inked', 'pariah', 'meteor', 'k.o.', 'nightwire', 'peridor',
                'jasper', 'edition', 'limited edition'
            }
            
            # Find all h2 headers (main sections)
            h2_headers = soup.find_all('h2')
            
            for header in h2_headers:
                header_text = header.get_text(strip=True).lower()
                
                # We're looking for skin sections (Available, Legacy Vault, etc.)
                if not any(keyword in header_text for keyword in ['available', 'vault', 'rare', 'legacy']):
                    continue
                
                # Get the content after this header until the next h2
                current = header.find_next_sibling()
                
                while current and current.name != 'h2':
                    if current.name == 'div':
                        # Get all text from this div
                        full_text = current.get_text(strip=True)
                        
                        # Look for "View in 3D" which appears after each skin name
                        # Split by this marker
                        parts = full_text.split('View in 3D')
                        
                        for part in parts:
                            # Clean up the part
                            part = part.strip()
                            
                            # Extract just the skin name (first line usually)
                            lines = part.split('\n')
                            if lines:
                                potential_skin = lines[0].strip()
                                
                                # Remove common markers and artifacts
                                potential_skin = re.sub(r'•View.*?Music', '', potential_skin).strip()  # Remove "•View Music" markers
                                potential_skin = re.sub(r'•.*', '', potential_skin).strip()  # Remove bullet points and after
                                potential_skin = re.sub(r'Chromas.*', '', potential_skin).strip()  # Remove "Chromas" section
                                
                                # Remove pricing info (before skin name) - remove pricing codes at start
                                potential_skin = re.sub(r'^\d+\s*/', '', potential_skin).strip()  # Remove "975/" or "1350/" at start
                                potential_skin = re.sub(r'^.*?pricing\s*/\s*', '', potential_skin).strip()  # "Special pricing / " at start
                                potential_skin = re.sub(r'^.*?pass\s*/\s*', '', potential_skin).strip()  # "Battle Pass / " at start
                                
                                # Remove dates (format: DD-Mmm-YYYY or YYYY-MM-DD or numbers/slash patterns)
                                potential_skin = re.sub(r'\d{1,2}-\w+-\d{4}', '', potential_skin).strip()
                                potential_skin = re.sub(r'\d{4}-\d{2}-\d{2}', '', potential_skin).strip()
                                potential_skin = re.sub(r'\d+\s*/', '', potential_skin).strip()
                                potential_skin = re.sub(r'/\s*\d+', '', potential_skin).strip()
                                potential_skin = re.sub(r'/$', '', potential_skin).strip()  # Remove trailing slash
                                
                                # If only "Battle Pass" or similar remains, skip it
                                if potential_skin.lower() in ['battle pass', 'special pricing', 'pricing']:
                                    continue
                                
                                # Remove URLs and links
                                potential_skin = re.sub(r'http\S+', '', potential_skin).strip()
                                
                                if not potential_skin or len(potential_skin) < 3:
                                    continue
                                
                                # Skip if it looks like a chroma or meta term
                                if any(skip in potential_skin.lower() for skip in SKIP_PATTERNS):
                                    continue
                                
                                if potential_skin not in seen:
                                    seen.add(potential_skin)
                                    # Try to find image URL for this skin
                                    # Normalize skin name for matching: remove special chars, spaces, lowercase
                                    skin_name_normalized = potential_skin.replace(' ', '').replace('_', '').replace('/', '').replace('-', '').replace('.', '').lower()
                                    
                                    # Try to find image by checking all image map keys
                                    image_url = None
                                    for map_key, map_url in image_map.items():
                                        # Check if the map key is contained in the normalized skin name
                                        if map_key in skin_name_normalized:
                                            image_url = map_url
                                            break
                                    
                                    skins.append({
                                        'name': potential_skin,
                                        'image_url': image_url,
                                        'tier': None
                                    })
                    
                    current = current.find_next_sibling()
            
            return skins[:25]  # Limit to 25 skins for button limit
        
        except Exception as e:
            logger.error(f"Error parsing skins HTML: {e}")
            return []


class SkinTierlistCommands(commands.Cog):
    """Skin Tierlist Commands Cog"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scraper = SkinScraper()
    
    @app_commands.command(
        name="skintierlist",
        description="Create an interactive skin tierlist for a League of Legends champion"
    )
    @app_commands.describe(
        champion="Champion name (e.g., Twitch, Ahri, Yasuo)"
    )
    async def skin_tierlist(
        self,
        interaction: discord.Interaction,
        champion: str
    ):
        """Create an interactive skin tierlist"""
        
        await interaction.response.defer(thinking=True)
        
        try:
            # Fetch skins for the champion
            logger.info(f"Fetching skins for {champion}...")
            skins = await self.scraper.fetch_champion_skins(champion)
            
            if not skins:
                embed = discord.Embed(
                    title="❌ No Skins Found",
                    description=f"Could not find skins for champion: **{champion}**\n\nMake sure the champion name is spelled correctly (e.g., Twitch, Ahri, Yasuo).",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Create tierlist view
            view = SkinTierlistView(
                user_id=interaction.user.id,
                skins=skins,
                champion=champion.title()
            )
            
            # Create initial embed
            embed = discord.Embed(
                title=f"🎨 {champion.title()} Skin Tierlist",
                description=f"Click skin numbers to select, then choose a tier.\n**Found {len(skins)} skins** to rank!",
                color=discord.Color.blue()
            )
            
            if skins[0]['image_url']:
                embed.set_thumbnail(url=skins[0]['image_url'])
            
            embed.add_field(
                name="📋 How to use",
                value="1. Click a skin number (1-25)\n2. Select a tier (S-F)\n3. Repeat until done\n4. Click ✅ Done when finished",
                inline=False
            )
            
            embed.add_field(
                name="🧾 Skins to rank",
                value="\n".join([f"{i+1}. {skin['name']}" for i, skin in enumerate(skins[:10])]) + 
                      ("\n..." if len(skins) > 10 else ""),
                inline=False
            )
            
            message = await interaction.followup.send(embed=embed, view=view)
            view.original_message = message
        
        except Exception as e:
            logger.error(f"Error in skin_tierlist command: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    """Setup function for Cog"""
    await bot.add_cog(SkinTierlistCommands(bot))
    logger.info("SkinTierlistCommands loaded")

