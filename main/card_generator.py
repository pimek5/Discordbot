"""
Dynamic Profile Card Generator for HEXRTBRXEN (Kassalytics)
Generates high-quality PNG profile cards using Pillow (PIL)
"""

import io
import os
import math
import logging
import aiohttp
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

logger = logging.getLogger('card_generator')

# Base paths
ROOT_DIR = Path(__file__).resolve().parent.parent
EMOJIS_DIR = ROOT_DIR / "emojis"
CHAMPS_DIR = EMOJIS_DIR / "champions"
RANKS_DIR = EMOJIS_DIR / "ranks"


def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Get best available TrueType font with fallback to default."""
    font_candidates = []
    if os.name == 'nt':  # Windows
        if bold:
            font_candidates.extend([
                "C:/Windows/Fonts/segoeuib.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/calibrib.ttf",
            ])
        else:
            font_candidates.extend([
                "C:/Windows/Fonts/segoeui.ttf",
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/calibri.ttf",
            ])
    else:  # Linux / Docker
        if bold:
            font_candidates.extend([
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            ])
        else:
            font_candidates.extend([
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            ])
    
    # Generic fallbacks
    if bold:
        font_candidates.extend(["DejaVuSans-Bold.ttf", "arialbd.ttf"])
    else:
        font_candidates.extend(["DejaVuSans.ttf", "arial.ttf"])

    for candidate in font_candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue

    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def _format_number(num: int) -> str:
    """Format large numbers with k/M suffixes."""
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}k"
    return str(num)


def _get_rank_color(tier: str) -> Tuple[int, int, int]:
    """Return primary theme color for a ranked tier."""
    tier_upper = (tier or "").upper()
    colors = {
        'CHALLENGER': (244, 197, 66),
        'GRANDMASTER': (231, 76, 60),
        'MASTER': (155, 89, 182),
        'DIAMOND': (52, 152, 219),
        'EMERALD': (46, 204, 113),
        'PLATINUM': (26, 188, 156),
        'GOLD': (241, 196, 15),
        'SILVER': (189, 195, 199),
        'BRONZE': (184, 115, 51),
        'IRON': (127, 140, 141),
        'UNRANKED': (149, 165, 166),
    }
    return colors.get(tier_upper, (0, 209, 255))


def _find_champion_icon_path(champion_name: str) -> Optional[Path]:
    """Find local PNG champion icon from emojis/champions/."""
    if not champion_name:
        return None
    
    clean_name = champion_name.replace(" ", "").replace("'", "").replace(".", "").lower()
    
    # Try exact match first
    for f in CHAMPS_DIR.glob("champ_*.png"):
        f_clean = f.stem.replace("champ_", "").replace(" ", "").replace("'", "").replace(".", "").lower()
        if f_clean == clean_name:
            return f
    
    # Prefix match
    for f in CHAMPS_DIR.glob("champ_*.png"):
        f_clean = f.stem.replace("champ_", "").replace(" ", "").replace("'", "").replace(".", "").lower()
        if f_clean.startswith(clean_name) or clean_name.startswith(f_clean):
            return f

    return None


def _find_rank_icon_path(tier: str) -> Optional[Path]:
    """Find local PNG rank icon from emojis/ranks/."""
    if not tier:
        return None
    tier_clean = tier.strip().capitalize()
    path = RANKS_DIR / f"rank_{tier_clean}.png"
    if path.exists():
        return path
    return None


async def _fetch_image_from_url(url: str) -> Optional[Image.Image]:
    """Fetch an image from HTTP/HTTPS URL asynchronously."""
    if not url:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        logger.warning("Failed to fetch image from %s: %s", url, e)
    return None


class ProfileCardGenerator:
    """Generates visual profile summary cards."""

    WIDTH = 960
    HEIGHT = 540

    @classmethod
    async def generate_card(
        cls,
        summoner_name: str,
        tagline: str,
        region: str,
        level: int,
        solo_rank: Optional[Dict],
        flex_rank: Optional[Dict],
        top_champions: List[Dict],
        stats_summary: Optional[Dict] = None,
        avatar_url: Optional[str] = None,
        background_champ: Optional[str] = None
    ) -> io.BytesIO:
        """
        Build and render a complete PNG profile card.
        Returns BytesIO stream ready to send as discord.File.
        """
        # Create base RGBA canvas
        card = Image.new("RGBA", (cls.WIDTH, cls.HEIGHT), (15, 18, 26, 255))
        draw = ImageDraw.Draw(card)

        # Primary tier for theme accents
        primary_tier = (solo_rank.get('tier') if solo_rank else None) or (flex_rank.get('tier') if flex_rank else 'UNRANKED')
        theme_color = _get_rank_color(primary_tier)

        # 1. Background gradient & subtle tech grid
        cls._draw_background(card, draw, theme_color)

        # 2. Header / Identity Block (Avatar, Name, Tag, Level, Region)
        avatar_img = None
        if avatar_url:
            avatar_img = await _fetch_image_from_url(avatar_url)
        cls._draw_identity_section(card, draw, summoner_name, tagline, region, level, avatar_img, theme_color)

        # 3. Solo/Duo & Flex Ranked Section
        cls._draw_ranked_section(card, draw, solo_rank, flex_rank, theme_color)

        # 4. Top Mastery Champions
        cls._draw_mastery_section(card, draw, top_champions)

        # 5. Performance / Match Stats Summary
        if stats_summary:
            cls._draw_stats_section(card, draw, stats_summary, theme_color)

        # 6. Card Border & Footer branding
        cls._draw_frame_and_branding(card, draw, theme_color)

        # Export to PNG buffer
        buffer = io.BytesIO()
        card.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)
        return buffer

    @classmethod
    def _draw_background(cls, card: Image.Image, draw: ImageDraw.Draw, theme_color: Tuple[int, int, int]):
        """Render multi-layer gradient background with subtle glowing accents."""
        w, h = cls.WIDTH, cls.HEIGHT

        # Base subtle vertical gradient
        for y in range(h):
            ratio = y / h
            r = int(14 + 10 * (1 - ratio))
            g = int(18 + 8 * (1 - ratio))
            b = int(28 + 14 * (1 - ratio))
            draw.line([(0, y), (w, y)], fill=(r, g, b, 255))

        # Top-left and bottom-right glow overlays
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        
        # Glow 1 (Top Left Accent)
        glow_color = (*theme_color, 35)
        glow_draw.ellipse((-100, -100, 450, 350), fill=glow_color)
        
        # Glow 2 (Bottom Right Hextech Accent)
        glow_draw.ellipse((w - 350, h - 250, w + 100, h + 100), fill=(0, 209, 255, 25))

        glow = glow.filter(ImageFilter.GaussianBlur(radius=60))
        card.alpha_composite(glow)

    @classmethod
    def _draw_identity_section(
        cls,
        card: Image.Image,
        draw: ImageDraw.Draw,
        summoner_name: str,
        tagline: str,
        region: str,
        level: int,
        avatar_img: Optional[Image.Image],
        theme_color: Tuple[int, int, int]
    ):
        """Draw player avatar with circular border, name, tag, level and region pill."""
        ax, ay, size = 40, 40, 100

        # Avatar rendering
        if avatar_img:
            avatar_resized = avatar_img.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
            mask = Image.new("L", (size, size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, size, size), fill=255)
            
            output_avatar = ImageOps.fit(avatar_resized, (size, size), centering=(0.5, 0.5))
            card.paste(output_avatar, (ax, ay), mask=mask)
        else:
            # Fallback circle placeholder
            draw.ellipse((ax, ay, ax + size, ay + size), fill=(30, 36, 52, 255))
            draw.text((ax + 32, ay + 32), "🎮", font=_get_font(36))

        # Avatar border (gold/tier themed)
        draw.ellipse((ax - 3, ay - 3, ax + size + 3, ay + size + 3), outline=(*theme_color, 220), width=3)

        # Level badge at bottom of avatar
        level_text = f"Lv. {level}"
        lvl_font = _get_font(13, bold=True)
        bbox = lvl_font.getbbox(level_text)
        bw = (bbox[2] - bbox[0]) + 16
        bx = ax + (size - bw) // 2
        by = ay + size - 10
        draw.rounded_rectangle((bx, by, bx + bw, by + 20), radius=6, fill=(18, 22, 34, 255), outline=(*theme_color, 180), width=1)
        draw.text((bx + 8, by + 3), level_text, fill=(255, 255, 255), font=lvl_font)

        # Name and Tagline
        tx = ax + size + 24
        name_font = _get_font(32, bold=True)
        tag_font = _get_font(20, bold=False)
        
        # Clamp name length if too long
        display_name = summoner_name[:16] + "..." if len(summoner_name) > 16 else summoner_name
        draw.text((tx, ay + 10), display_name, fill=(255, 255, 255), font=name_font)
        
        name_bbox = name_font.getbbox(display_name)
        name_w = name_bbox[2] - name_bbox[0]
        
        if tagline:
            draw.text((tx + name_w + 10, ay + 20), f"#{tagline}", fill=(140, 155, 180), font=tag_font)

        # Region Pill Badge
        region_font = _get_font(13, bold=True)
        reg_text = (region or "GLOBAL").upper()
        reg_bbox = region_font.getbbox(reg_text)
        rw = (reg_bbox[2] - reg_bbox[0]) + 16
        rx = tx
        ry = ay + 56
        draw.rounded_rectangle((rx, ry, rx + rw, ry + 22), radius=5, fill=(*theme_color, 45), outline=(*theme_color, 160), width=1)
        draw.text((rx + 8, ry + 4), reg_text, fill=(230, 240, 255), font=region_font)

        # Platform / System Subtitle
        sub_font = _get_font(13)
        draw.text((rx + rw + 12, ry + 4), "Verified Summoner • Season 2026", fill=(120, 135, 160), font=sub_font)

    @classmethod
    def _draw_ranked_section(
        cls,
        card: Image.Image,
        draw: ImageDraw.Draw,
        solo_rank: Optional[Dict],
        flex_rank: Optional[Dict],
        theme_color: Tuple[int, int, int]
    ):
        """Draw Ranked Solo/Duo and Flex cards with winrate bars and badges."""
        rx, ry, rw, rh = 40, 175, 420, 165
        
        # Glassmorphic container
        draw.rounded_rectangle((rx, ry, rx + rw, ry + rh), radius=12, fill=(22, 27, 40, 220), outline=(50, 60, 85, 200), width=1)
        
        # Header line inside container
        sec_font = _get_font(14, bold=True)
        draw.text((rx + 16, ry + 12), "RANKED SOLO / DUO", fill=(160, 180, 210), font=sec_font)

        if solo_rank:
            tier = solo_rank.get('tier', 'UNRANKED').title()
            rank = solo_rank.get('rank', '')
            lp = solo_rank.get('leaguePoints', 0)
            wins = solo_rank.get('wins', 0)
            losses = solo_rank.get('losses', 0)
            total = wins + losses
            wr = (wins / total * 100) if total > 0 else 0

            # Rank Icon
            icon_path = _find_rank_icon_path(tier)
            if icon_path:
                try:
                    r_img = Image.open(icon_path).convert("RGBA").resize((70, 70), Image.Resampling.LANCZOS)
                    card.paste(r_img, (rx + 16, ry + 40), mask=r_img)
                except Exception:
                    pass

            # Rank Title & LP
            rank_title_font = _get_font(22, bold=True)
            lp_font = _get_font(16, bold=False)
            tier_display = f"{tier} {rank}".strip()
            draw.text((rx + 98, ry + 44), tier_display, fill=(*theme_color, 255), font=rank_title_font)
            draw.text((rx + 98, ry + 72), f"{lp} LP", fill=(210, 225, 245), font=lp_font)

            # Winrate bar & stats
            wr_font = _get_font(13, bold=True)
            wr_text = f"{wins}W {losses}L ({wr:.1f}% WR)"
            draw.text((rx + 16, ry + 118), wr_text, fill=(170, 190, 215), font=wr_font)

            # Progress Bar
            bar_x, bar_y, bar_w, bar_h = rx + 16, ry + 140, rw - 32, 10
            draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=4, fill=(35, 42, 60, 255))
            fill_w = max(4, int(bar_w * (wr / 100.0)))
            draw.rounded_rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), radius=4, fill=(46, 204, 113, 255))
        else:
            draw.text((rx + 20, ry + 65), "Unranked", fill=(140, 150, 170), font=_get_font(24, bold=True))
            draw.text((rx + 20, ry + 105), "No ranked solo games recorded this season.", fill=(100, 115, 140), font=_get_font(13))

        # Flex Rank mini badge in bottom/side
        if flex_rank:
            ftier = flex_rank.get('tier', 'UNRANKED').title()
            frank = flex_rank.get('rank', '')
            flp = flex_rank.get('leaguePoints', 0)
            flex_text = f"Flex: {ftier} {frank} • {flp} LP".strip()
            draw.text((rx + rw - 180, ry + 12), flex_text, fill=(120, 140, 170), font=_get_font(12))

    @classmethod
    def _draw_mastery_section(cls, card: Image.Image, draw: ImageDraw.Draw, top_champions: List[Dict]):
        """Draw Top 3 Champions Mastery cards on the right side."""
        mx, my, mw, mh = 500, 40, 420, 300
        
        # Container
        draw.rounded_rectangle((mx, my, mx + mw, my + mh), radius=12, fill=(22, 27, 40, 220), outline=(50, 60, 85, 200), width=1)
        
        # Title
        sec_font = _get_font(14, bold=True)
        draw.text((mx + 16, my + 14), "TOP CHAMPIONS MASTERY", fill=(160, 180, 210), font=sec_font)

        if not top_champions:
            draw.text((mx + 20, my + 100), "No champion mastery data found.", fill=(120, 135, 160), font=_get_font(14))
            return

        item_y = my + 44
        item_h = 76
        
        for i, champ in enumerate(top_champions[:3]):
            cy = item_y + i * (item_h + 6)
            
            # Row background highlight
            draw.rounded_rectangle((mx + 12, cy, mx + mw - 12, cy + item_h), radius=8, fill=(30, 37, 54, 180))

            champ_name = champ.get('name', f"Champion {champ.get('champion_id', '')}")
            level = champ.get('level', 1)
            points = champ.get('score', 0)

            # Champion Icon
            icon_path = _find_champion_icon_path(champ_name)
            if icon_path:
                try:
                    c_img = Image.open(icon_path).convert("RGBA").resize((52, 52), Image.Resampling.LANCZOS)
                    # Round mask
                    c_mask = Image.new("L", (52, 52), 0)
                    ImageDraw.Draw(c_mask).rounded_rectangle((0, 0, 52, 52), radius=10, fill=255)
                    card.paste(c_img, (mx + 22, cy + 12), mask=c_mask)
                    draw.rounded_rectangle((mx + 22, cy + 12, mx + 74, cy + 64), radius=10, outline=(0, 209, 255, 140), width=1)
                except Exception:
                    pass

            # Champion Name & Level Badge
            name_f = _get_font(18, bold=True)
            draw.text((mx + 86, cy + 16), champ_name, fill=(240, 245, 255), font=name_f)
            
            # Mastery Points & Level
            pts_text = f"{points:,} pts"
            pts_f = _get_font(13)
            draw.text((mx + 86, cy + 42), pts_text, fill=(140, 160, 190), font=pts_f)

            # Level Pill Badge
            lvl_text = f"M{level}" if level < 10 else f"Lv.{level}"
            lvl_f = _get_font(13, bold=True)
            l_bbox = lvl_f.getbbox(lvl_text)
            lw = (l_bbox[2] - l_bbox[0]) + 14
            lx = mx + mw - 24 - lw
            ly = cy + 24
            draw.rounded_rectangle((lx, ly, lx + lw, ly + 24), radius=6, fill=(241, 196, 15, 40), outline=(241, 196, 15, 200), width=1)
            draw.text((lx + 7, ly + 4), lvl_text, fill=(241, 196, 15), font=lvl_f)

    @classmethod
    def _draw_stats_section(
        cls,
        card: Image.Image,
        draw: ImageDraw.Draw,
        stats: Dict,
        theme_color: Tuple[int, int, int]
    ):
        """Draw bottom performance bar with KDA, CS/min, Winrate and Games."""
        sx, sy, sw, sh = 40, 360, 880, 125
        
        # Container
        draw.rounded_rectangle((sx, sy, sx + sw, sy + sh), radius=12, fill=(22, 27, 40, 220), outline=(50, 60, 85, 200), width=1)
        
        # Grid of 4 key performance metrics
        metrics = [
            ("RECENT WINRATE", f"{stats.get('winrate', 0):.1f}%", f"{stats.get('wins', 0)}W - {stats.get('losses', 0)}L"),
            ("AVERAGE KDA", f"{stats.get('kda', 0.0):.2f}", f"{stats.get('avg_kills', 0):.1f} / {stats.get('avg_deaths', 0):.1f} / {stats.get('avg_assists', 0):.1f}"),
            ("CREEP SCORE", f"{stats.get('avg_cs', 0):.1f}", f"{stats.get('cs_per_min', 0.0):.1f} CS/min"),
            ("DAMAGE SHARE", f"{stats.get('avg_damage', 0):,}", f"{stats.get('games_played', 0)} Games Sampled"),
        ]

        col_w = sw // 4
        for idx, (title, main_val, sub_val) in enumerate(metrics):
            cx = sx + idx * col_w
            
            # Divider
            if idx > 0:
                draw.line([(cx, sy + 18), (cx, sy + sh - 18)], fill=(45, 54, 76, 200), width=1)

            # Label
            draw.text((cx + 20, sy + 16), title, fill=(130, 145, 175), font=_get_font(12, bold=True))
            
            # Value
            val_color = (*theme_color, 255) if idx == 0 else (240, 245, 255, 255)
            draw.text((cx + 20, sy + 40), str(main_val), fill=val_color, font=_get_font(26, bold=True))
            
            # Sub-caption
            draw.text((cx + 20, sy + 82), str(sub_val), fill=(140, 155, 180), font=_get_font(13))

    @classmethod
    def _draw_frame_and_branding(cls, card: Image.Image, draw: ImageDraw.Draw, theme_color: Tuple[int, int, int]):
        """Add sleek card border, corners, and footer branding text."""
        w, h = cls.WIDTH, cls.HEIGHT

        # Outer border
        draw.rounded_rectangle((4, 4, w - 5, h - 5), radius=16, outline=(40, 48, 68, 255), width=2)
        
        # Hextech corner accents (top-left & bottom-right)
        draw.line([(6, 24), (6, 6), (24, 6)], fill=(*theme_color, 255), width=2)
        draw.line([(w - 25, h - 7), (w - 7, h - 7), (w - 7, h - 25)], fill=(0, 209, 255, 255), width=2)

        # Bottom branding footer
        brand_font = _get_font(11, bold=True)
        draw.text((44, h - 26), "HEXRTBRXEN", fill=(0, 209, 255, 200), font=brand_font)
        draw.text((125, h - 26), "• KASSALYTICS DYNAMIC PROFILE CARD", fill=(110, 125, 150), font=_get_font(11))
