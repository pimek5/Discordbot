import os
import asyncio
import logging
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
