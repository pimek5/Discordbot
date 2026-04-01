import os
import asyncio
import logging
import json
import random
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, quote
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, Any

HELPER_FORUM_ID = 1464368533088768124  # Support forum channel ID
SOLVED_TAG_ID = 1464379665333620746  # Tag applied when thread is solved
UNSOLVED_TAG_ID = 1464379721272787069  # Tag applied when thread is unsolved/created
STREAM_ROLE_ID = 1470171489096564736  # Role granted while streaming
STREAM_LIST_CHANNEL_ID = 1470173597157818559  # Channel for streaming roster embed
RANKDLE_POOL_FILE = os.path.join(os.path.dirname(__file__), "rankdle_pool.json")
RANKDLE_DAILY_STATE_FILE = os.path.join(os.path.dirname(__file__), "rankdle_daily_state.json")
RANKDLE_CHANNEL_ID = 1488821138841800814
AUTO_TRIAGE_KEYWORDS = {
    "bug": ["bug", "error", "crash", "exception", "failed", "traceback"],
    "install": ["install", "setup", "launcher", "open", "start", "cannot launch"],
    "performance": ["fps", "lag", "stutter", "freeze", "performance", "slow"],
}
GUILD_ID = os.getenv("HELPER_GUILD_ID")
TOKEN = os.getenv("HELPER_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("helper")

VALID_STREAM_HOSTS = {
    "twitch.tv",
}

ACCOUNT_ROUTINGS = ["europe", "americas", "asia", "sea"]

PLATFORM_ROUTES = {
    "br": "br1",
    "eune": "eun1",
    "euw": "euw1",
    "jp": "jp1",
    "kr": "kr",
    "lan": "la1",
    "las": "la2",
    "na": "na1",
    "oce": "oc1",
    "tr": "tr1",
    "ru": "ru",
    "ph": "ph2",
    "sg": "sg2",
    "th": "th2",
    "tw": "tw2",
    "vn": "vn2",
}

MATCH_ROUTING = {
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "na1": "americas",
    "oc1": "americas",
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "kr": "asia",
    "jp1": "asia",
    "sg2": "sea",
    "ph2": "sea",
    "th2": "sea",
    "tw2": "sea",
    "vn2": "sea",
}


def get_valid_stream_activity(member: discord.Member):
    for activity in member.activities:
        if not activity or activity.type != discord.ActivityType.streaming:
            continue

        stream_url = getattr(activity, "url", None)
        if not stream_url:
            continue

        try:
            hostname = urlparse(stream_url).netloc.lower()
        except Exception:
            continue

        if hostname.startswith("www."):
            hostname = hostname[4:]

        if any(hostname == valid_host or hostname.endswith(f".{valid_host}") for valid_host in VALID_STREAM_HOSTS):
            return activity

    return None


def extract_twitch_login(stream_url: str) -> str | None:
    try:
        parsed = urlparse(stream_url)
    except Exception:
        return None

    hostname = parsed.netloc.lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    if hostname != "twitch.tv" and not hostname.endswith(".twitch.tv"):
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return None

    login = path_parts[0].strip().lower()
    if login in {"directory", "downloads", "jobs", "settings", "subscriptions", "team", "videos"}:
        return None
    return login


def build_welcome_embed(bot_avatar_url: str = None) -> discord.Embed:
    embed = discord.Embed(
        title="👋 Welcome to the HEXRTBRXEN Help Forum",
        description=(
            "**🔧 Having issues with CSLOL/Mods?**\n\n"
            "We're here to help! Please follow the guidelines below to get the fastest support."
        ),
        color=discord.Color.from_rgb(88, 101, 242)
    )
    
    embed.add_field(
        name="❌ If you got an error message...",
        value=(
            "1. Click the **'Copy'** button on the **CSLOL** error screen\n"
            "2. Click the blue **'Click me if you got an error message!'** button below\n"
            "3. Paste your error in the box and press **'Submit'**\n"
            "4. Include additional context if needed"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📝 If the above doesn't apply / doesn't fix your issue...",
        value=(
            "Please provide **ALL** of the following information:\n"
            "• **Problem description** - What were you doing? What happened? What doesn't work?\n"
            "• **Mods list** - Which mods were you using when the issue occurred?\n"
            "• **Screenshots** - Include a screenshot if it would help explain your issue\n"
            "• **Version** - What version of CSLOL are you using?\n"
            "• **Steps to reproduce** - How can we reproduce your issue?"
        ),
        inline=False
    )
    
    embed.add_field(
        name="✅ Resolved your issue?",
        value=(
            "Click the **'Solved'** button below to mark this thread as resolved!\n"
            "This helps us keep the forum organized."
        ),
        inline=False
    )
    
    footer_text = "HEXRTBRXEN Support • Be patient, be descriptive, be helpful! 🤝"
    if bot_avatar_url:
        embed.set_footer(text=footer_text, icon_url=bot_avatar_url)
    else:
        embed.set_footer(text=footer_text)
    
    return embed


async def ensure_prefix(thread: discord.Thread, prefix: str):
    try:
        if thread.name.startswith(prefix):
            return
        # Remove existing [Solved] prefix if present
        clean_name = thread.name
        if clean_name.startswith("[Solved] "):
            clean_name = clean_name[len("[Solved] "):]
        await thread.edit(name=f"{prefix}{clean_name}")
    except Exception as e:
        logger.warning("Failed to edit thread name: %s", e)


def select_auto_triage_tag(forum: discord.ForumChannel, text: str) -> discord.ForumTag | None:
    lowered = (text or "").lower()
    if not lowered:
        return None

    for category, keywords in AUTO_TRIAGE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            for tag in forum.available_tags:
                tag_name = tag.name.lower()
                if category in tag_name:
                    return tag

    return None


class HelperView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Solved", emoji="✅", style=discord.ButtonStyle.success, custom_id="helper_solved")
    async def solved(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("This only works in a thread.", ephemeral=True)
            return
        await ensure_prefix(interaction.channel, "[Solved] ")
        try:
            # Apply solved tag
            forum = interaction.channel.parent
            solved_tag = discord.utils.get(forum.available_tags, id=SOLVED_TAG_ID)
            if solved_tag:
                # Remove unsolved tag if present
                new_tags = [tag for tag in interaction.channel.applied_tags if tag.id != UNSOLVED_TAG_ID]
                new_tags.append(solved_tag)
                await interaction.channel.edit(applied_tags=new_tags[:5])  # Max 5 tags
        except Exception as e:
            logger.warning("Failed to apply solved tag: %s", e)
        await interaction.response.send_message("Marked as solved. Thanks!", ephemeral=True)

    @discord.ui.button(label="Unsolved", emoji="❌", style=discord.ButtonStyle.danger, custom_id="helper_unsolved")
    async def unsolved(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("This only works in a thread.", ephemeral=True)
            return
        try:
            name = interaction.channel.name
            if name.startswith("[Solved] "):
                await interaction.channel.edit(name=name[len("[Solved] "):])
            # Apply unsolved tag
            forum = interaction.channel.parent
            unsolved_tag = discord.utils.get(forum.available_tags, id=UNSOLVED_TAG_ID)
            if unsolved_tag:
                # Remove solved tag if present
                new_tags = [tag for tag in interaction.channel.applied_tags if tag.id != SOLVED_TAG_ID]
                new_tags.append(unsolved_tag)
                await interaction.channel.edit(applied_tags=new_tags[:5])  # Max 5 tags
        except Exception as e:
            logger.warning("Failed to apply unsolved tag: %s", e)
        await interaction.response.send_message("Marked as unsolved.", ephemeral=True)

    @discord.ui.button(label="Click me if you got an error message!", style=discord.ButtonStyle.primary, custom_id="helper_error")
    async def error_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = (
            "Got an error? Please paste the copied error text here. Also include: what you were doing, "
            "mods in use, and a screenshot if possible."
        )
        await interaction.response.send_message(msg, ephemeral=True)


def create_bot():
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.presences = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.status_index = 0
    bot.streaming_embed_message_id = None
    bot.streaming_embed_signature = None
    bot.streaming_embed_last_update = None
    bot.streaming_embed_cleanup_done = False
    bot.twitch_access_token = None
    bot.twitch_access_token_expires_at = None
    bot.twitch_live_cache = {}
    bot.twitch_api_warning_logged = False
    bot.status_messages = [
        ("playing", "🧩 /help"),
        ("listening", "support requests"),
        ("playing", "✅ solved threads"),
        ("listening", "error reports"),
        ("playing", "📌 forum triage"),
    ]
    bot.rankdle_sessions = {}

    RANKDLE_RANKS = [
        "IRON",
        "BRONZE",
        "SILVER",
        "GOLD",
        "PLATINUM",
        "DIAMOND",
        "MASTER",
        "GRANDMASTER",
        "CHALLENGER",
    ]
    RANKDLE_INDEX = {rank: idx for idx, rank in enumerate(RANKDLE_RANKS)}
    RANKDLE_EMOJIS = {
        "IRON": "<:rank_Iron:1485677690974371932>",
        "BRONZE": "<:rank_Bronze:1485677682447351991>",
        "SILVER": "<:rank_Silver:1485677694971674826>",
        "GOLD": "<:rank_Gold:1485677688134963272>",
        "PLATINUM": "<:rank_Platinum:1485677693541417090>",
        "DIAMOND": "<:rank_Diamond:1485677685773566083>",
        "MASTER": "<:rank_Master:1485677692123746304>",
        "GRANDMASTER": "<:rank_Grandmaster:1485677689758023760>",
        "CHALLENGER": "<:rank_Challenger:1485677683496190145>",
        "EMERALD": "<:rank_Emerald:1485677686884925621>",
    }

    def load_rankdle_pool() -> list[dict]:
        if not os.path.exists(RANKDLE_POOL_FILE):
            return []
        try:
            with open(RANKDLE_POOL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [item for item in data if isinstance(item, dict)]
        except Exception as e:
            logger.warning("Failed to load rankdle pool: %s", e)
        return []

    def save_rankdle_pool(pool: list[dict]):
        try:
            with open(RANKDLE_POOL_FILE, "w", encoding="utf-8") as f:
                json.dump(pool, f, ensure_ascii=True, indent=2)
        except Exception as e:
            logger.error("Failed to save rankdle pool: %s", e)

    def rank_label(rank: str) -> str:
        upper = (rank or "").upper()
        return f"{RANKDLE_EMOJIS.get(upper, '🎯')} {upper}"

    def normalize_rankdle_rank(rank_name: str) -> str:
        value = (rank_name or "").strip().upper().replace(" ", "")
        if value == "GRANDMASTER":
            return "GRANDMASTER"
        if value in RANKDLE_INDEX:
            return value
        if value == "UNRANKED":
            return "IRON"
        return "IRON"

    def load_rankdle_daily_state() -> dict:
        if not os.path.exists(RANKDLE_DAILY_STATE_FILE):
            return {"date": None, "clips": [], "messages": [], "votes": {}, "winners": {}}
        try:
            with open(RANKDLE_DAILY_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("date", None)
                    data.setdefault("clips", [])
                    data.setdefault("messages", [])
                    data.setdefault("votes", {})
                    data.setdefault("winners", {})
                    return data
        except Exception as e:
            logger.warning("Failed to load rankdle daily state: %s", e)
        return {"date": None, "clips": [], "messages": [], "votes": {}, "winners": {}}

    def save_rankdle_daily_state(state: dict):
        try:
            with open(RANKDLE_DAILY_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=True, indent=2)
        except Exception as e:
            logger.error("Failed to save rankdle daily state: %s", e)

    def build_rankdle_daily_stats_text(state: dict, clip_index: int) -> str:
        key = str(clip_index)
        votes = (state.get("votes") or {}).get(key, {})
        winners = (state.get("winners") or {}).get(key, [])
        clips = state.get("clips") or []
        if clip_index >= len(clips):
            return "No stats available yet."
        winners_mentions = " ".join([f"<@{uid}>" for uid in winners]) if winners else "None yet"
        return (
            f"Total votes: **{len(votes)}**\n"
            f"Correct guesses: **{len(winners)}**\n"
            f"Winners: {winners_mentions}"
        )

    def build_rankdle_daily_clip_embed(state: dict, clip_index: int) -> discord.Embed:
        clips = state.get("clips") or []
        clip = clips[clip_index]
        clip_region = (clip.get("region") or "GLOBAL").upper()
        clip_date = state.get("date", "unknown")
        embed = discord.Embed(
            title=f"Rankdle Daily LoL - Clip {clip_index + 1}/3",
            description="Vote with buttons below. One vote per user for this clip.",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Date", value=clip_date, inline=True)
        embed.add_field(name="Clip", value=f"{clip_index + 1}/3", inline=True)
        embed.add_field(name="Region", value=clip_region, inline=True)
        embed.add_field(name="Stats", value=build_rankdle_daily_stats_text(state, clip_index), inline=False)
        embed.set_footer(text=f"Day: {clip_date}")
        return embed

    def extract_rankdle_region(clip_payload: dict) -> str:
        candidates = [
            clip_payload.get("region"),
            clip_payload.get("server"),
            clip_payload.get("platform"),
            clip_payload.get("locale"),
            clip_payload.get("shard"),
            clip_payload.get("cluster"),
        ]
        for value in candidates:
            if isinstance(value, str) and value.strip():
                normalized = value.strip().upper()
                aliases = {
                    "EUW1": "EUW",
                    "EUN1": "EUNE",
                    "NA1": "NA",
                    "KR": "KR",
                    "JP1": "JP",
                    "BR1": "BR",
                    "LA1": "LAN",
                    "LA2": "LAS",
                    "OC1": "OCE",
                    "TR1": "TR",
                    "RU": "RU",
                    "SG2": "SG",
                    "PH2": "PH",
                    "TH2": "TH",
                    "TW2": "TW",
                    "VN2": "VN",
                }
                return aliases.get(normalized, normalized)
        return "GLOBAL"

    async def scrape_rankdle_daily_lol_clips() -> list[dict]:
        base_url = "https://rankdle.com"
        session = await get_http_session()

        async with session.post(
            f"{base_url}/api/auth/createuser",
            json={},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"createuser failed ({resp.status})")
            create_data = await resp.json(content_type=None)
        user_token = create_data.get("token")
        if not user_token:
            raise RuntimeError("Rankdle token missing from createuser response")

        async with session.get(
            f"{base_url}/api/auth/getgamesdata",
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"getgamesdata failed ({resp.status})")
            games_data = await resp.json(content_type=None)
        daily_token = games_data.get("currDailyToken")
        if not daily_token:
            raise RuntimeError("Rankdle daily token missing")

        rank_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {user_token}",
        }
        async with session.get(
            f"{base_url}/api/auth/getgamesrankdata",
            headers=rank_headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"getgamesrankdata failed ({resp.status})")
            rank_data = await resp.json(content_type=None)

        iron_guess = (((rank_data.get("gamesRankData") or {}).get("lol") or {}).get("iron"))
        if not iron_guess:
            raise RuntimeError("Could not resolve LoL rank metadata")

        play_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {user_token}",
            "RankdleDaily": f"Bearer {daily_token}",
        }
        async with session.post(
            f"{base_url}/api/user/playgamereel",
            headers=play_headers,
            json={"game": "lol", "dailyId": None},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"playgamereel failed ({resp.status})")
            reel_data = await resp.json(content_type=None)

        reel_id = reel_data.get("id")
        clips = reel_data.get("clips") or []
        if not reel_id or not clips:
            raise RuntimeError("No clips returned by Rankdle playgamereel")

        reel_index = int(reel_data.get("reelIndex", 0) or 0)
        extracted = []

        for offset, clip in enumerate(clips):
            clip_id = clip.get("clipId")
            if not clip_id:
                continue

            guess_payload = {
                "clipId": clip_id,
                "reelId": reel_id,
                "reelIndex": reel_index + offset,
                "guess": iron_guess,
            }
            async with session.post(
                f"{base_url}/api/user/guesscliprank",
                headers=rank_headers,
                json=guess_payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ):
                pass

            async with session.get(
                f"{base_url}/api/user/getclipresult/{clip_id}",
                headers=rank_headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as result_resp:
                if result_resp.status != 200:
                    continue
                clip_result = await result_resp.json(content_type=None)

            if not clip_result.get("success"):
                continue

            resolved_url = (clip_result.get("url") or clip.get("clipLink") or "").strip()
            resolved_rank = normalize_rankdle_rank(clip_result.get("rankName") or "")
            if not resolved_url:
                continue

            merged_payload = {
                **(clip if isinstance(clip, dict) else {}),
                **(clip_result if isinstance(clip_result, dict) else {}),
            }

            extracted.append({
                "url": resolved_url,
                "rank": resolved_rank,
                "region": extract_rankdle_region(merged_payload),
                "source": "rankdle.com/lol",
            })

            async with session.post(
                f"{base_url}/api/user/getnextsection",
                headers=rank_headers,
                json={"clipId": clip_id, "reelId": reel_id},
                timeout=aiohttp.ClientTimeout(total=20),
            ):
                pass

        return extracted

    def build_rankdle_clip_embed(session: dict) -> discord.Embed:
        idx = session["current_index"]
        clip = session["clips"][idx]
        total = len(session["clips"])
        stars = session.get("stars", 0)

        embed = discord.Embed(
            title=f"🎮 Rank Guess • Clip {idx + 1}/{total}",
            description=(
                f"Watch clip: {clip.get('url')}\n"
                "Choose the rank you think this play belongs to."
            ),
            color=discord.Color.blurple(),
        )
        if clip.get("source"):
            embed.add_field(name="Source", value=clip["source"], inline=False)
        embed.set_footer(text=f"Stars: {stars} | Exact: ⭐⭐ | One rank off: ⭐")
        return embed

    def build_rankdle_result_embed(session: dict) -> discord.Embed:
        total_clips = len(session["clips"])
        max_stars = total_clips * 2
        stars = session.get("stars", 0)

        embed = discord.Embed(
            title="🏁 Rank Guess Result",
            description=f"Score: **{stars}/{max_stars}** stars",
            color=discord.Color.green() if stars >= max(2, total_clips) else discord.Color.orange(),
        )

        lines = []
        for i, row in enumerate(session.get("history", []), 1):
            line = (
                f"{i}. Guess: {rank_label(row['guess'])} | "
                f"Correct: {rank_label(row['correct'])} | +{row['stars']}⭐"
            )
            lines.append(line)

        embed.add_field(name="Rounds", value="\n".join(lines) if lines else "No rounds played", inline=False)
        return embed

    class RankdleSelect(discord.ui.Select):
        def __init__(self, owner_id: int):
            options = [discord.SelectOption(label=rank.title(), value=rank) for rank in RANKDLE_RANKS]
            super().__init__(
                placeholder="Choose rank...",
                min_values=1,
                max_values=1,
                options=options,
                custom_id="helper_rankdle_select",
            )
            self.owner_id = owner_id

        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("This game session is not yours.", ephemeral=True)
                return

            session = bot.rankdle_sessions.get(self.owner_id)
            if not session:
                await interaction.response.send_message("Session expired. Start a new one with /rankdle_play", ephemeral=True)
                return

            guess = self.values[0]
            idx = session["current_index"]
            clip = session["clips"][idx]
            correct = clip.get("rank", "IRON")

            diff = abs(RANKDLE_INDEX.get(guess, 0) - RANKDLE_INDEX.get(correct, 0))
            stars = 2 if diff == 0 else 1 if diff == 1 else 0
            session["stars"] += stars
            session.setdefault("history", []).append({"guess": guess, "correct": correct, "stars": stars})

            if idx + 1 >= len(session["clips"]):
                final_embed = build_rankdle_result_embed(session)
                bot.rankdle_sessions.pop(self.owner_id, None)
                await interaction.response.edit_message(embed=final_embed, view=None)
                return

            session["current_index"] += 1
            next_embed = build_rankdle_clip_embed(session)
            next_view = RankdleView(self.owner_id)
            await interaction.response.edit_message(embed=next_embed, view=next_view)

    class RankdleView(discord.ui.View):
        def __init__(self, owner_id: int):
            super().__init__(timeout=600)
            self.add_item(RankdleSelect(owner_id))

    class RankdleDailyVoteButton(discord.ui.Button):
        def __init__(self, clip_index: int, rank: str):
            super().__init__(
                label=rank.title(),
                style=discord.ButtonStyle.secondary,
                custom_id=f"helper_rankdle_daily_{clip_index}_{rank}",
                row=0 if RANKDLE_INDEX[rank] < 5 else 1,
                emoji=RANKDLE_EMOJIS.get(rank),
            )
            self.clip_index = clip_index
            self.rank = rank

        async def callback(self, interaction: discord.Interaction):
            state = load_rankdle_daily_state()
            today_key = datetime.now(timezone.utc).date().isoformat()

            if state.get("date") != today_key or self.clip_index >= len(state.get("clips") or []):
                await interaction.response.send_message("This daily vote is no longer active.", ephemeral=True)
                return

            key = str(self.clip_index)
            votes = state.setdefault("votes", {}).setdefault(key, {})
            user_key = str(interaction.user.id)
            if user_key in votes:
                await interaction.response.send_message(
                    f"You already voted on this clip: {rank_label(votes[user_key])}",
                    ephemeral=True,
                )
                return

            votes[user_key] = self.rank
            correct_rank = (state["clips"][self.clip_index].get("rank") or "IRON").upper()

            winners = state.setdefault("winners", {}).setdefault(key, [])
            guessed_correct = self.rank == correct_rank
            if guessed_correct and user_key not in winners:
                winners.append(user_key)

            save_rankdle_daily_state(state)

            try:
                if interaction.message and interaction.message.embeds:
                    updated = build_rankdle_daily_clip_embed(state, self.clip_index)
                    await interaction.message.edit(embed=updated)
            except Exception as e:
                logger.warning("Failed to refresh Rankdle daily stats embed: %s", e)

            if guessed_correct:
                await interaction.response.send_message(
                    f"Correct! {rank_label(correct_rank)}", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"Wrong guess. Correct rank: {rank_label(correct_rank)}", ephemeral=True
                )

    class RankdleDailyVoteView(discord.ui.View):
        def __init__(self, clip_index: int):
            super().__init__(timeout=None)
            for rank in RANKDLE_RANKS:
                self.add_item(RankdleDailyVoteButton(clip_index, rank))

    async def _download_rankdle_clip_to_file(url: str, target_path: Path) -> bool:
        """Download clip URL to target_path. Supports direct files and YouTube via yt-dlp."""
        if not url:
            return False

        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()

        # Direct media URLs can be downloaded with aiohttp.
        if parsed.scheme in {"http", "https"} and any(url.lower().split("?")[0].endswith(ext) for ext in (".mp4", ".webm", ".mov", ".m4v")):
            try:
                session = await get_http_session()
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status != 200:
                        return False
                    with open(target_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(1024 * 128):
                            if chunk:
                                f.write(chunk)
                return target_path.exists() and target_path.stat().st_size > 0
            except Exception as e:
                logger.warning("Direct clip download failed: %s", e)
                return False

        # Provider links (e.g., YouTube) via yt-dlp.
        try:
            import yt_dlp  # type: ignore
        except Exception:
            logger.warning("yt-dlp is not installed; cannot download provider clip from host=%s", host)
            return False

        def _download_with_ytdlp() -> bool:
            opts = {
                "format": "mp4/bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
                "outtmpl": str(target_path.with_suffix(".%(ext)s")),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "overwrites": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            if target_path.exists() and target_path.stat().st_size > 0:
                return True
            for candidate in target_path.parent.glob(f"{target_path.stem}.*"):
                if candidate.suffix.lower() in {".mp4", ".webm", ".mov", ".m4v"} and candidate.stat().st_size > 0:
                    candidate.replace(target_path)
                    return True
            return False

        try:
            return await asyncio.to_thread(_download_with_ytdlp)
        except Exception as e:
            logger.warning("yt-dlp clip download failed: %s", e)
            return False

    async def _send_rankdle_daily_clip_message(channel: discord.TextChannel, state: dict, clip_index: int) -> discord.Message:
        embed = build_rankdle_daily_clip_embed(state, clip_index)
        view = RankdleDailyVoteView(clip_index)
        clip_url = (state["clips"][clip_index].get("url") or "").strip()

        with tempfile.TemporaryDirectory(prefix="rankdle_clip_") as temp_dir:
            temp_path = Path(temp_dir) / f"rankdle_{state.get('date', 'today')}_{clip_index + 1}.mp4"
            downloaded = await _download_rankdle_clip_to_file(clip_url, temp_path)

            if downloaded:
                clip_file = discord.File(str(temp_path), filename=temp_path.name)
                return await channel.send(embed=embed, file=clip_file, view=view)

            logger.warning("Failed to download Rankdle clip for clip_index=%s url=%s", clip_index, clip_url)
            fallback_embed = embed.copy()
            fallback_embed.description = "Clip could not be downloaded for inline playback right now."
            return await channel.send(embed=fallback_embed, view=view)

    async def post_rankdle_daily_embeds(state: dict):
        channel = bot.get_channel(RANKDLE_CHANNEL_ID)
        if channel is None:
            try:
                channel = await bot.fetch_channel(RANKDLE_CHANNEL_ID)
            except Exception as e:
                raise RuntimeError(f"Could not fetch Rankdle channel {RANKDLE_CHANNEL_ID}: {e}")

        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError(f"Rankdle channel {RANKDLE_CHANNEL_ID} is not a text channel")

        message_ids = []
        for clip_index in range(min(3, len(state.get("clips") or []))):
            msg = await _send_rankdle_daily_clip_message(channel, state, clip_index)
            message_ids.append(msg.id)

        state["messages"] = message_ids
        save_rankdle_daily_state(state)

    async def restore_rankdle_daily_messages(state: dict) -> tuple[int, int]:
        """Restore missing Rankdle daily messages for current state.

        Returns: (restored_count, reused_count)
        """
        channel = bot.get_channel(RANKDLE_CHANNEL_ID)
        if channel is None:
            try:
                channel = await bot.fetch_channel(RANKDLE_CHANNEL_ID)
            except Exception as e:
                raise RuntimeError(f"Could not fetch Rankdle channel {RANKDLE_CHANNEL_ID}: {e}")

        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError(f"Rankdle channel {RANKDLE_CHANNEL_ID} is not a text channel")

        clips = state.get("clips") or []
        existing_ids = state.get("messages") or []
        new_ids: list[int] = []
        restored_count = 0
        reused_count = 0

        for clip_index in range(min(3, len(clips))):
            existing_message_id = existing_ids[clip_index] if clip_index < len(existing_ids) else None
            message_found = False

            if existing_message_id:
                try:
                    await channel.fetch_message(int(existing_message_id))
                    new_ids.append(int(existing_message_id))
                    reused_count += 1
                    message_found = True
                except Exception:
                    message_found = False

            if not message_found:
                posted = await _send_rankdle_daily_clip_message(channel, state, clip_index)
                new_ids.append(posted.id)
                restored_count += 1

        state["messages"] = new_ids
        save_rankdle_daily_state(state)
        return restored_count, reused_count

    async def ensure_rankdle_daily_content(force: bool = False) -> tuple[str, dict]:
        today_key = datetime.now(timezone.utc).date().isoformat()
        state = load_rankdle_daily_state()

        if not force and state.get("date") == today_key and len(state.get("clips") or []) >= 3:
            if len(state.get("messages") or []) >= 3:
                return "already_posted", state
            await post_rankdle_daily_embeds(state)
            return "posted_missing_messages", state

        extracted = await scrape_rankdle_daily_lol_clips()
        if not extracted:
            raise RuntimeError("Rankdle scrape returned 0 clips")

        clips_for_day = extracted[:3]
        if len(clips_for_day) < 3:
            raise RuntimeError(f"Expected 3 clips, got {len(clips_for_day)}")

        pool = load_rankdle_pool()
        existing_urls = {(entry.get("url") or "").strip() for entry in pool}
        added = 0
        for item in extracted:
            url = (item.get("url") or "").strip()
            if not url or url in existing_urls:
                continue
            pool.append(
                {
                    "url": url,
                    "rank": normalize_rankdle_rank(item.get("rank") or ""),
                    "region": (item.get("region") or "GLOBAL").upper(),
                    "source": item.get("source") or "rankdle.com/lol",
                    "added_by": 0,
                    "added_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            existing_urls.add(url)
            added += 1
        if added > 0:
            save_rankdle_pool(pool)

        state = {
            "date": today_key,
            "clips": clips_for_day,
            "messages": [],
            "votes": {},
            "winners": {},
        }
        save_rankdle_daily_state(state)
        await post_rankdle_daily_embeds(state)
        return "created_new_day", state

    rank_choices = [app_commands.Choice(name=rank.title(), value=rank) for rank in RANKDLE_RANKS]

    @bot.tree.command(name="rankdle_addclip", description="Add a clip to Helper rank guessing pool")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(url="Clip video URL", rank="Correct rank", source="Optional source/credit")
    @app_commands.choices(rank=rank_choices)
    async def rankdle_addclip(interaction: discord.Interaction, url: str, rank: app_commands.Choice[str], source: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            await interaction.followup.send("❌ Invalid URL. Use http/https link.", ephemeral=True)
            return

        pool = load_rankdle_pool()
        if any((entry.get("url") or "").strip() == url.strip() for entry in pool):
            await interaction.followup.send("ℹ️ Clip already exists in pool.", ephemeral=True)
            return

        pool.append(
            {
                "url": url.strip(),
                "rank": rank.value,
                "region": "GLOBAL",
                "source": (source or "").strip(),
                "added_by": interaction.user.id,
                "added_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        save_rankdle_pool(pool)
        await interaction.followup.send(
            f"✅ Added clip to pool. Rank: {rank_label(rank.value)}\nPool size: **{len(pool)}**",
            ephemeral=True,
        )

    @bot.tree.command(name="rankdle_pool", description="Show stats for Helper rank guessing pool")
    async def rankdle_pool(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        pool = load_rankdle_pool()

        embed = discord.Embed(title="🎬 Rank Guess Pool", color=discord.Color.blurple())
        embed.add_field(name="Total clips", value=str(len(pool)), inline=False)

        if pool:
            counts = {rank: 0 for rank in RANKDLE_RANKS}
            for entry in pool:
                rank = (entry.get("rank") or "").upper()
                if rank in counts:
                    counts[rank] += 1
            lines = [f"{rank_label(rank)}: {count}" for rank, count in counts.items() if count > 0]
            embed.add_field(name="By rank", value="\n".join(lines) if lines else "No rank metadata", inline=False)
            sample = pool[-1]
            embed.add_field(
                name="Last added",
                value=f"{rank_label(sample.get('rank', 'IRON'))}\n{sample.get('url', 'N/A')}",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @bot.tree.command(name="rankdle_play", description="Play rank guessing game from Helper clip pool")
    @app_commands.describe(rounds="Number of clips to guess (default 3)")
    async def rankdle_play(interaction: discord.Interaction, rounds: Optional[int] = 3):
        await interaction.response.defer(ephemeral=True)
        pool = load_rankdle_pool()
        if not pool:
            await interaction.followup.send(
                "❌ Pool is empty. Add clips first with /rankdle_addclip.",
                ephemeral=True,
            )
            return

        rounds = max(1, min(int(rounds or 3), 10))
        if len(pool) < rounds:
            await interaction.followup.send(
                f"❌ Not enough clips in pool ({len(pool)}). Need at least {rounds}.",
                ephemeral=True,
            )
            return

        clips = random.sample(pool, rounds)
        session = {
            "clips": clips,
            "current_index": 0,
            "stars": 0,
            "history": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        bot.rankdle_sessions[interaction.user.id] = session

        embed = build_rankdle_clip_embed(session)
        view = RankdleView(interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @bot.tree.command(name="rankdle_scrape", description="Scrape today's Rankdle LoL clips into local pool")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def rankdle_scrape(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            status, state = await ensure_rankdle_daily_content(force=False)
            if status == "already_posted":
                await interaction.followup.send(
                    f"ℹ️ Daily clips already scraped today ({state.get('date')}) and posted in <#{RANKDLE_CHANNEL_ID}>.",
                    ephemeral=True,
                )
                return

            await interaction.followup.send(
                (
                    f"✅ Rankdle daily ready for {state.get('date')}\n"
                    f"Clips: **{len(state.get('clips') or [])}**\n"
                    f"Posted in <#{RANKDLE_CHANNEL_ID}>"
                ),
                ephemeral=True,
            )
        except Exception as e:
            logger.error("rankdle_scrape failed: %s", e, exc_info=True)
            await interaction.followup.send(f"❌ rankdle_scrape failed: {e}", ephemeral=True)

    @bot.tree.command(name="rankdle_post", description="Restore today's Rankdle daily clips if messages were deleted")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def rankdle_post(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            today_key = datetime.now(timezone.utc).date().isoformat()
            state = load_rankdle_daily_state()

            # Ensure today's daily exists first.
            if state.get("date") != today_key or len(state.get("clips") or []) < 3:
                _, state = await ensure_rankdle_daily_content(force=False)

            restored_count, reused_count = await restore_rankdle_daily_messages(state)
            await interaction.followup.send(
                (
                    f"✅ Rankdle daily messages synced for **{state.get('date')}**\n"
                    f"Restored missing: **{restored_count}**\n"
                    f"Already present: **{reused_count}**\n"
                    f"Channel: <#{RANKDLE_CHANNEL_ID}>"
                ),
                ephemeral=True,
            )
        except Exception as e:
            logger.error("rankdle_post failed: %s", e, exc_info=True)
            await interaction.followup.send(f"❌ rankdle_post failed: {e}", ephemeral=True)

    @tasks.loop(hours=2)
    async def rankdle_auto_scrape_task():
        try:
            status, state = await ensure_rankdle_daily_content(force=False)
            logger.info(
                "Rankdle auto-scrape tick: status=%s date=%s clips=%s",
                status,
                state.get("date"),
                len(state.get("clips") or []),
            )
        except Exception as e:
            logger.warning("Rankdle auto-scrape failed: %s", e)

    @rankdle_auto_scrape_task.before_loop
    async def before_rankdle_auto_scrape_task():
        await bot.wait_until_ready()

    async def get_http_session() -> aiohttp.ClientSession:
        if not hasattr(bot, "http_session") or bot.http_session.closed:
            bot.http_session = aiohttp.ClientSession()
        return bot.http_session

    async def riot_get_json(url: str) -> tuple[Optional[dict], Optional[int], str]:
        if not RIOT_API_KEY:
            return None, None, "missing_key"

        session = await get_http_session()
        try:
            async with session.get(
                url,
                headers={"X-Riot-Token": RIOT_API_KEY},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                status = response.status
                if status == 200:
                    try:
                        data = await response.json(content_type=None)
                        return data, status, "ok"
                    except Exception:
                        return None, status, "invalid_json"
                if status == 404:
                    return None, status, "not_found"
                if status == 403:
                    return None, status, "forbidden"
                if status == 429:
                    return None, status, "rate_limited"
                return None, status, "error"
        except asyncio.TimeoutError:
            return None, None, "timeout"
        except aiohttp.ClientError:
            return None, None, "network_error"
        except Exception:
            return None, None, "error"

    async def riot_get_json_list(url: str) -> tuple[list[Any], Optional[int], str]:
        if not RIOT_API_KEY:
            return [], None, "missing_key"

        session = await get_http_session()
        try:
            async with session.get(
                url,
                headers={"X-Riot-Token": RIOT_API_KEY},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                status = response.status
                if status == 200:
                    try:
                        data = await response.json(content_type=None)
                        if isinstance(data, list):
                            return data, status, "ok"
                        return [], status, "invalid_json"
                    except Exception:
                        return [], status, "invalid_json"
                if status == 404:
                    return [], status, "not_found"
                if status == 403:
                    return [], status, "forbidden"
                if status == 429:
                    return [], status, "rate_limited"
                return [], status, "error"
        except asyncio.TimeoutError:
            return [], None, "timeout"
        except aiohttp.ClientError:
            return [], None, "network_error"
        except Exception:
            return [], None, "error"

    def build_account_routing_order(preferred_region: Optional[str]) -> list[str]:
        if not preferred_region:
            return ACCOUNT_ROUTINGS.copy()

        preferred_platform = PLATFORM_ROUTES.get(preferred_region.lower())
        preferred_routing = MATCH_ROUTING.get(preferred_platform, "europe") if preferred_platform else "europe"
        if preferred_routing in ACCOUNT_ROUTINGS:
            return [preferred_routing] + [r for r in ACCOUNT_ROUTINGS if r != preferred_routing]
        return ACCOUNT_ROUTINGS.copy()

    async def find_account_by_riot_id(game_name: str, tag_line: str, preferred_region: Optional[str]) -> tuple[Optional[dict], Optional[str], str]:
        for routing in build_account_routing_order(preferred_region):
            url = f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{quote(tag_line)}"
            data, _, reason = await riot_get_json(url)
            if data:
                return data, routing, "ok"
            if reason in {"forbidden", "missing_key", "rate_limited"}:
                return None, routing, reason
        return None, None, "not_found"

    async def find_account_by_puuid(puuid: str, preferred_region: Optional[str]) -> tuple[Optional[dict], Optional[str], str]:
        for routing in build_account_routing_order(preferred_region):
            url = f"https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-puuid/{quote(puuid)}"
            data, _, reason = await riot_get_json(url)
            if data:
                return data, routing, "ok"
            if reason in {"forbidden", "missing_key", "rate_limited"}:
                return None, routing, reason
        return None, None, "not_found"

    async def find_summoner_by_puuid_any_region(puuid: str, preferred_region: Optional[str]) -> tuple[Optional[dict], Optional[str], Optional[str], str]:
        region_order = list(PLATFORM_ROUTES.keys())
        if preferred_region and preferred_region.lower() in PLATFORM_ROUTES:
            pref = preferred_region.lower()
            region_order = [pref] + [r for r in region_order if r != pref]

        for region in region_order:
            platform = PLATFORM_ROUTES[region]
            url = f"https://{platform}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{quote(puuid)}"
            data, _, reason = await riot_get_json(url)
            if data:
                return data, region, platform, "ok"
            if reason in {"forbidden", "missing_key", "rate_limited"}:
                return None, None, None, reason
        return None, None, None, "not_found"

    def format_league_entry(entry: dict) -> str:
        tier = entry.get("tier", "UNRANKED")
        rank = entry.get("rank", "")
        lp = entry.get("leaguePoints", 0)
        wins = entry.get("wins", 0)
        losses = entry.get("losses", 0)
        total = wins + losses
        wr = (wins / total * 100) if total else 0
        return f"{tier} {rank} - {lp} LP ({wins}W/{losses}L, {wr:.1f}% WR)"

    @bot.tree.command(name="accountchecker", description="Check Riot account details by Riot ID or PUUID")
    @app_commands.describe(
        riot_id="Riot ID in format Name#TAG",
        puuid="Player PUUID",
        region="Preferred region (e.g. euw, eune, na, kr)",
    )
    async def accountchecker(
        interaction: discord.Interaction,
        riot_id: Optional[str] = None,
        puuid: Optional[str] = None,
        region: Optional[str] = None,
    ):
        await interaction.response.defer()

        if not RIOT_API_KEY:
            await interaction.followup.send("❌ `RIOT_API_KEY` is not configured on Helper service.")
            return

        if not riot_id and not puuid:
            await interaction.followup.send("❌ Provide at least one input: `riot_id` or `puuid`.")
            return

        preferred_region = region.lower().strip() if region else None
        if preferred_region and preferred_region not in PLATFORM_ROUTES:
            await interaction.followup.send(
                "❌ Invalid region. Use one of: br, eune, euw, jp, kr, lan, las, na, oce, tr, ru, ph, sg, th, tw, vn"
            )
            return

        account_data = None
        account_route = None
        lookup_reason = "ok"

        if riot_id:
            if "#" not in riot_id:
                await interaction.followup.send("❌ Invalid `riot_id` format. Use `Name#TAG`.")
                return
            game_name, tag_line = riot_id.split("#", 1)
            account_data, account_route, lookup_reason = await find_account_by_riot_id(
                game_name.strip(),
                tag_line.strip(),
                preferred_region,
            )
        else:
            account_data, account_route, lookup_reason = await find_account_by_puuid(
                puuid.strip(),
                preferred_region,
            )

        if not account_data:
            if lookup_reason == "forbidden":
                await interaction.followup.send("❌ Riot API rejected the request (403). Check API key permissions.")
            elif lookup_reason == "rate_limited":
                await interaction.followup.send("⏳ Riot API rate limit reached. Try again in a moment.")
            elif lookup_reason == "missing_key":
                await interaction.followup.send("❌ `RIOT_API_KEY` missing.")
            else:
                await interaction.followup.send("❌ Account not found by provided data.")
            return

        resolved_puuid = account_data.get("puuid")
        if not resolved_puuid:
            await interaction.followup.send("❌ Riot account found but missing PUUID.")
            return

        summoner_data, resolved_region, platform, summoner_reason = await find_summoner_by_puuid_any_region(
            resolved_puuid,
            preferred_region,
        )

        if not summoner_data:
            embed = discord.Embed(
                title="🧾 Account Checker",
                description="Riot account found, but League profile data could not be resolved.",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(
                name="Riot Account",
                value=f"**{account_data.get('gameName', 'Unknown')}#{account_data.get('tagLine', 'Unknown')}**",
                inline=False,
            )
            embed.add_field(name="PUUID", value=f"`{resolved_puuid}`", inline=False)
            embed.add_field(
                name="Reason",
                value=(
                    "Riot API doesn't expose a direct ban status endpoint.\n"
                    f"League profile lookup failed with: **{summoner_reason}**"
                ),
                inline=False,
            )
            await interaction.followup.send(embed=embed)
            return

        league_url = f"https://{platform}.api.riotgames.com/lol/league/v4/entries/by-puuid/{quote(resolved_puuid)}"
        league_entries, _, _ = await riot_get_json_list(league_url)

        mastery_url = (
            f"https://{platform}.api.riotgames.com/lol/champion-mastery/v4/champion-masteries/by-puuid/{quote(resolved_puuid)}/top?count=5"
        )
        mastery_entries, _, _ = await riot_get_json_list(mastery_url)

        match_route = MATCH_ROUTING.get(platform, "europe")
        match_ids_url = (
            f"https://{match_route}.api.riotgames.com/lol/match/v5/matches/by-puuid/{quote(resolved_puuid)}/ids?start=0&count=5"
        )
        match_ids, _, _ = await riot_get_json_list(match_ids_url)

        last_match_summary = "No recent match data"
        if match_ids:
            first_match = str(match_ids[0])
            match_detail_url = f"https://{match_route}.api.riotgames.com/lol/match/v5/matches/{quote(first_match)}"
            match_detail, _, _ = await riot_get_json(match_detail_url)
            if match_detail and isinstance(match_detail, dict):
                info = match_detail.get("info", {})
                participants = info.get("participants", [])
                participant = next((p for p in participants if p.get("puuid") == resolved_puuid), None)
                if participant:
                    champ = participant.get("championName", "Unknown")
                    kills = participant.get("kills", 0)
                    deaths = participant.get("deaths", 0)
                    assists = participant.get("assists", 0)
                    result = "Win" if participant.get("win") else "Loss"
                    mode = info.get("gameMode", "Unknown")
                    last_match_summary = f"{result} as **{champ}** ({kills}/{deaths}/{assists}) [{mode}]"

        embed = discord.Embed(
            title="🔎 Account Checker Result",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )

        riot_name = f"{account_data.get('gameName', 'Unknown')}#{account_data.get('tagLine', 'Unknown')}"
        embed.add_field(name="Riot Account", value=f"**{riot_name}**", inline=True)
        embed.add_field(name="Detected Region", value=f"**{resolved_region.upper()}**", inline=True)
        embed.add_field(name="Summoner Level", value=f"**{summoner_data.get('summonerLevel', 'Unknown')}**", inline=True)
        embed.add_field(name="PUUID", value=f"`{resolved_puuid}`", inline=False)

        solo_entry = next((e for e in league_entries if e.get("queueType") == "RANKED_SOLO_5x5"), None)
        flex_entry = next((e for e in league_entries if e.get("queueType") == "RANKED_FLEX_SR"), None)
        queue_lines = []
        queue_lines.append(f"SoloQ: {format_league_entry(solo_entry)}" if solo_entry else "SoloQ: UNRANKED")
        queue_lines.append(f"Flex: {format_league_entry(flex_entry)}" if flex_entry else "Flex: UNRANKED")
        embed.add_field(name="Current Ranks", value="\n".join(queue_lines), inline=False)

        if mastery_entries:
            mastery_lines = []
            for entry in mastery_entries[:5]:
                champ_id = entry.get("championId", "?")
                points = entry.get("championPoints", 0)
                level = entry.get("championLevel", 0)
                mastery_lines.append(f"• Champ ID {champ_id}: Lv{level}, {points:,} pts")
            embed.add_field(name="Top Mastery (Top 5)", value="\n".join(mastery_lines), inline=False)

        embed.add_field(name="Last Match", value=last_match_summary, inline=False)
        embed.add_field(
            name="Account Status / Bans",
            value=(
                "Riot public API does **not** expose a reliable banned/suspended flag.\n"
                "If account data is reachable, profile is currently queryable by API."
            ),
            inline=False,
        )
        embed.add_field(
            name="Rank History",
            value=(
                "Riot API provides current queue entries only.\n"
                "Historical season rank timeline requires your own snapshots database or external data source."
            ),
            inline=False,
        )
        embed.set_footer(text=f"Lookup route: {account_route or 'n/a'} | Platform: {platform}")

        icon_id = summoner_data.get("profileIconId")
        if isinstance(icon_id, int):
            embed.set_thumbnail(
                url=f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/profile-icons/{icon_id}.jpg"
            )

        await interaction.followup.send(embed=embed)

    async def get_twitch_access_token() -> str | None:
        if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
            if not bot.twitch_api_warning_logged:
                logger.warning("TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET not configured; streaming role verification is disabled")
                bot.twitch_api_warning_logged = True
            return None

        now = datetime.now(timezone.utc)
        if bot.twitch_access_token and bot.twitch_access_token_expires_at and now < bot.twitch_access_token_expires_at:
            return bot.twitch_access_token

        session = await get_http_session()
        try:
            async with session.post(
                "https://id.twitch.tv/oauth2/token",
                params={
                    "client_id": TWITCH_CLIENT_ID,
                    "client_secret": TWITCH_CLIENT_SECRET,
                    "grant_type": "client_credentials",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    body = await response.text()
                    logger.warning("Failed to fetch Twitch access token: %s %s", response.status, body[:200])
                    return None

                data = await response.json(content_type=None)
                expires_in = int(data.get("expires_in", 0))
                bot.twitch_access_token = data.get("access_token")
                bot.twitch_access_token_expires_at = now + timedelta(seconds=max(0, expires_in - 60))
                return bot.twitch_access_token
        except Exception as e:
            logger.warning("Error fetching Twitch access token: %s", e)
            return None

    async def is_twitch_channel_live(login: str) -> bool:
        cache_entry = bot.twitch_live_cache.get(login)
        now = datetime.now(timezone.utc)
        if cache_entry and cache_entry[1] > now:
            return cache_entry[0]

        access_token = await get_twitch_access_token()
        if not access_token:
            bot.twitch_live_cache[login] = (False, now + timedelta(seconds=60))
            return False

        session = await get_http_session()
        try:
            async with session.get(
                "https://api.twitch.tv/helix/streams",
                params={"user_login": login},
                headers={
                    "Client-ID": TWITCH_CLIENT_ID,
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 401:
                    bot.twitch_access_token = None
                    bot.twitch_access_token_expires_at = None
                    access_token = await get_twitch_access_token()
                    if not access_token:
                        bot.twitch_live_cache[login] = (False, now + timedelta(seconds=60))
                        return False
                    async with session.get(
                        "https://api.twitch.tv/helix/streams",
                        params={"user_login": login},
                        headers={
                            "Client-ID": TWITCH_CLIENT_ID,
                            "Authorization": f"Bearer {access_token}",
                        },
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as retry_response:
                        if retry_response.status != 200:
                            body = await retry_response.text()
                            logger.warning("Failed Twitch live check for %s: %s %s", login, retry_response.status, body[:200])
                            bot.twitch_live_cache[login] = (False, now + timedelta(seconds=60))
                            return False
                        data = await retry_response.json(content_type=None)
                elif response.status != 200:
                    body = await response.text()
                    logger.warning("Failed Twitch live check for %s: %s %s", login, response.status, body[:200])
                    bot.twitch_live_cache[login] = (False, now + timedelta(seconds=60))
                    return False
                else:
                    data = await response.json(content_type=None)

                is_live = bool(data.get("data"))
                bot.twitch_live_cache[login] = (is_live, now + timedelta(seconds=90))
                return is_live
        except Exception as e:
            logger.warning("Error checking Twitch live status for %s: %s", login, e)
            bot.twitch_live_cache[login] = (False, now + timedelta(seconds=60))
            return False

    async def get_verified_stream_activity(member: discord.Member):
        activity = get_valid_stream_activity(member)
        if not activity:
            return None

        stream_url = getattr(activity, "url", None)
        if not stream_url:
            return None

        twitch_login = extract_twitch_login(stream_url)
        if not twitch_login:
            return None

        if not await is_twitch_channel_live(twitch_login):
            return None

        return activity

    async def update_streaming_embed(guild: discord.Guild):
        channel = guild.get_channel(STREAM_LIST_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        role = guild.get_role(STREAM_ROLE_ID)
        if not role:
            return

        members = [m for m in role.members if not m.bot]
        members.sort(key=lambda m: m.display_name.lower())

        embeds = []
        signature_lines = []

        if members:
            lines = []
            for member in members:
                stream_activity = await get_verified_stream_activity(member)
                stream_url = getattr(stream_activity, "url", None) if stream_activity else None

                if stream_url:
                    entry = f"• {member.mention} [click]({stream_url})"
                    lines.append(entry)
                    signature_lines.append(f"{member.id}:{stream_url}")
                else:
                    entry = f"• {member.mention}"
                    lines.append(entry)
                    signature_lines.append(f"{member.id}:")

            chunk_size = 20
            chunks = [lines[i:i + chunk_size] for i in range(0, len(lines), chunk_size)]
            total_pages = len(chunks)
            max_pages = 10
            for idx, chunk in enumerate(chunks[:max_pages]):
                title = f"📺 Live Streams ({idx + 1}/{total_pages})"
                embed = discord.Embed(
                    title=title,
                    description="\n".join(chunk),
                    color=discord.Color.from_rgb(88, 101, 242)
                )
                embed.set_footer(text="Auto-updated by Helper")
                embeds.append(embed)

            if total_pages > max_pages:
                embeds[-1].set_footer(text="Auto-updated by Helper • List truncated")
        else:
            embed = discord.Embed(
                title="📺 Live Streams",
                description="*No one is streaming right now.*",
                color=discord.Color.from_rgb(88, 101, 242)
            )
            embed.set_footer(text="Auto-updated by Helper")
            embeds.append(embed)

        now = datetime.now(timezone.utc)
        signature = "\n".join(signature_lines) if members else "empty"
        message = None
        if bot.streaming_embed_message_id:
            try:
                message = await channel.fetch_message(bot.streaming_embed_message_id)
            except Exception:
                message = None

        if not message:
            try:
                async for msg in channel.history(limit=20):
                    if msg.author.id == bot.user.id and msg.embeds:
                        title = msg.embeds[0].title or ""
                        if title.startswith("📺 Live Streams"):
                            message = msg
                            bot.streaming_embed_message_id = msg.id
                            break
            except Exception as e:
                logger.warning("Failed to search streaming embed message: %s", e)

        if message and not bot.streaming_embed_cleanup_done:
            try:
                async for msg in channel.history(limit=50):
                    if msg.id == message.id:
                        continue
                    if msg.author.id != bot.user.id or not msg.embeds:
                        continue
                    title = msg.embeds[0].title or ""
                    if title.startswith("📺 Live Streams"):
                        try:
                            await msg.delete()
                        except Exception as e:
                            logger.warning("Failed to delete old streaming embed: %s", e)
            except Exception as e:
                logger.warning("Failed to cleanup streaming embeds: %s", e)
            bot.streaming_embed_cleanup_done = True

        if message and bot.streaming_embed_signature == signature:
            # Avoid editing when content did not change
            return
        if bot.streaming_embed_last_update and now - bot.streaming_embed_last_update < timedelta(seconds=60):
            # Debounce frequent updates triggered by presence changes
            return

        try:
            if message:
                await message.edit(embeds=embeds)
            else:
                sent = await channel.send(embeds=embeds)
                bot.streaming_embed_message_id = sent.id
            bot.streaming_embed_signature = signature
            bot.streaming_embed_last_update = now
        except discord.HTTPException as e:
            if e.code == 30046:
                try:
                    sent = await channel.send(embeds=embeds)
                    bot.streaming_embed_message_id = sent.id
                    bot.streaming_embed_signature = signature
                    bot.streaming_embed_last_update = now
                    if message:
                        try:
                            await message.delete()
                        except Exception as inner:
                            logger.warning("Failed to delete rotated streaming embed: %s", inner)
                    return
                except Exception as inner:
                    logger.warning("Failed to rotate streaming embed: %s", inner)
            logger.warning("Failed to update streaming embed: %s", e)

    async def sync_streaming_roles(guild: discord.Guild):
        role = guild.get_role(STREAM_ROLE_ID)
        if not role:
            return

        try:
            await guild.chunk(cache=True)
        except Exception as e:
            logger.warning("Failed to chunk guild members: %s", e)

        for member in list(guild.members):
            if member.bot:
                continue

            is_streaming = await get_verified_stream_activity(member) is not None

            try:
                if is_streaming and role not in member.roles:
                    await member.add_roles(role, reason="Streaming status detected (startup sync)")
                    logger.info(
                        "[STREAM_ROLE][SYNC] ADD user=%s (%s) role=%s",
                        member.id,
                        member.display_name,
                        role.id,
                    )
                elif not is_streaming and role in member.roles:
                    await member.remove_roles(role, reason="Streaming status ended (startup sync)")
                    logger.info(
                        "[STREAM_ROLE][SYNC] REMOVE user=%s (%s) role=%s",
                        member.id,
                        member.display_name,
                        role.id,
                    )
            except Exception as e:
                logger.warning("Failed to sync streaming role for %s: %s", member.id, e)

        await update_streaming_embed(guild)

    @tasks.loop(minutes=5)
    async def sync_streaming_roles_loop():
        if not GUILD_ID:
            return
        guild = bot.get_guild(int(GUILD_ID))
        if not guild:
            return
        await sync_streaming_roles(guild)

    @sync_streaming_roles_loop.before_loop
    async def before_sync_streaming_roles_loop():
        await bot.wait_until_ready()

    @bot.event
    async def on_ready():
        logger.info("Helper bot ready as %s", bot.user)
        if not change_status.is_running():
            change_status.start()
        if not sync_streaming_roles_loop.is_running():
            sync_streaming_roles_loop.start()
        if not rankdle_auto_scrape_task.is_running():
            rankdle_auto_scrape_task.start()
        if GUILD_ID:
            guild = bot.get_guild(int(GUILD_ID))
            if guild:
                await sync_streaming_roles(guild)

    @tasks.loop(minutes=5)
    async def change_status():
        """Rotate bot status every 5 minutes"""
        try:
            status_type, status_text = bot.status_messages[bot.status_index]
            if "{guilds}" in status_text:
                status_text = status_text.replace("{guilds}", str(len(bot.guilds)))
            if status_type == "listening":
                activity = discord.Activity(type=discord.ActivityType.listening, name=status_text)
            else:
                activity = discord.Game(name=status_text)
            await bot.change_presence(activity=activity, status=discord.Status.online)
            bot.status_index = (bot.status_index + 1) % len(bot.status_messages)
        except Exception as e:
            logger.warning("Failed to update status: %s", e)

    @change_status.before_loop
    async def before_change_status():
        await bot.wait_until_ready()

    @bot.event
    async def on_thread_create(thread: discord.Thread):
        if thread.parent_id != HELPER_FORUM_ID:
            return
        try:
            # Apply unsolved tag to new threads
            forum = thread.parent
            unsolved_tag = discord.utils.get(forum.available_tags, id=UNSOLVED_TAG_ID)

            starter_message = None
            try:
                starter_message = await thread.fetch_message(thread.id)
            except Exception:
                messages = [msg async for msg in thread.history(limit=1, oldest_first=True)]
                starter_message = messages[0] if messages else None

            triage_source = f"{thread.name}\n{starter_message.content if starter_message else ''}"
            triage_tag = select_auto_triage_tag(forum, triage_source)

            new_tags = list(thread.applied_tags)
            if unsolved_tag and unsolved_tag not in new_tags:
                new_tags.append(unsolved_tag)
            if triage_tag and triage_tag not in new_tags:
                new_tags.append(triage_tag)

            if len(new_tags) != len(thread.applied_tags):
                await thread.edit(applied_tags=new_tags[:5])  # Max 5 tags
            
            helper_view = HelperView()
            bot_avatar = bot.user.display_avatar.url if bot.user else None
            await thread.send(embed=build_welcome_embed(bot_avatar), view=helper_view)
            logger.info(
                "Posted helper embed in thread %s (triage tag: %s)",
                thread.id,
                triage_tag.name if triage_tag else "none"
            )
        except Exception as e:
            logger.error("Failed to post helper embed: %s", e)

    @bot.event
    async def on_presence_update(before: discord.Member, after: discord.Member):
        if after.bot:
            return

        if GUILD_ID and str(after.guild.id) != str(GUILD_ID):
            return

        role = after.guild.get_role(STREAM_ROLE_ID)
        if not role:
            return

        is_streaming = await get_verified_stream_activity(after) is not None

        try:
            if is_streaming and role not in after.roles:
                await after.add_roles(role, reason="Streaming status detected")
                logger.info(
                    "[STREAM_ROLE][PRESENCE] ADD user=%s (%s) role=%s",
                    after.id,
                    after.display_name,
                    role.id,
                )
            elif not is_streaming and role in after.roles:
                await after.remove_roles(role, reason="Streaming status ended")
                logger.info(
                    "[STREAM_ROLE][PRESENCE] REMOVE user=%s (%s) role=%s",
                    after.id,
                    after.display_name,
                    role.id,
                )
        except Exception as e:
            logger.warning("Failed to update streaming role: %s", e)

        await update_streaming_embed(after.guild)

    @bot.event
    async def setup_hook():
        bot.add_view(HelperView())
        state = load_rankdle_daily_state()
        for clip_index in range(min(3, len(state.get("clips") or []))):
            bot.add_view(RankdleDailyVoteView(clip_index))

        # Always sync globally so commands are available even without HELPER_GUILD_ID.
        try:
            synced_global = await bot.tree.sync()
            logger.info("Synced %s helper commands globally", len(synced_global))
        except Exception as e:
            logger.warning("Global command sync failed: %s", e)

        # If guild is configured, also sync guild-scoped for faster propagation.
        if GUILD_ID:
            try:
                guild_obj = discord.Object(id=int(GUILD_ID))
                bot.tree.copy_global_to(guild=guild_obj)
                synced_guild = await bot.tree.sync(guild=guild_obj)
                logger.info("Synced %s helper commands to guild %s", len(synced_guild), GUILD_ID)
            except Exception as e:
                logger.warning("Guild command sync failed for %s: %s", GUILD_ID, e)
        else:
            logger.warning("HELPER_GUILD_ID is not set; only global sync is active")

    async def close_http_session():
        if hasattr(bot, "http_session") and bot.http_session and not bot.http_session.closed:
            await bot.http_session.close()

    original_close = bot.close

    async def wrapped_close(*args, **kwargs):
        await close_http_session()
        await original_close(*args, **kwargs)

    bot.close = wrapped_close

    return bot


def main():
    if not TOKEN:
        raise RuntimeError("HELPER_TOKEN is not set")
    bot = create_bot()
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
