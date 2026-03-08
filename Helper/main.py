import os
import logging
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp

HELPER_FORUM_ID = 1464368533088768124  # Support forum channel ID
SOLVED_TAG_ID = 1464379665333620746  # Tag applied when thread is solved
UNSOLVED_TAG_ID = 1464379721272787069  # Tag applied when thread is unsolved/created
STREAM_ROLE_ID = 1470171489096564736  # Role granted while streaming
STREAM_LIST_CHANNEL_ID = 1470173597157818559  # Channel for streaming roster embed
GUILD_ID = os.getenv("HELPER_GUILD_ID")
TOKEN = os.getenv("HELPER_TOKEN")
TIKTOK_USERNAME = (os.getenv("TIKTOK_USERNAME") or "").strip().lstrip("@")
TIKTOK_CHANNEL_ID = os.getenv("TIKTOK_CHANNEL_ID")
NOTIFY_ROLE_ID = int(os.getenv("HELPER_NOTIFY_ROLE_ID", "1173564965152637018"))
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN")
TIKTOK_STATE_FILE = os.getenv(
    "TIKTOK_STATE_FILE",
    str(Path(__file__).with_name("tiktok_state.json")),
)

try:
    TIKTOK_CHECK_MINUTES = max(1, int(os.getenv("TIKTOK_CHECK_MINUTES", "10")))
except ValueError:
    TIKTOK_CHECK_MINUTES = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("helper")


def load_tiktok_state() -> dict:
    """Load persisted TikTok posting state from disk."""
    try:
        state_path = Path(TIKTOK_STATE_FILE)
        if not state_path.exists():
            return {}
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to load TikTok state: %s", e)
        return {}


def save_tiktok_state(state: dict):
    """Persist TikTok posting state to disk."""
    try:
        state_path = Path(TIKTOK_STATE_FILE)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to save TikTok state: %s", e)


def build_tiktok_embed(video: dict, username: str) -> discord.Embed:
    """Build a rich embed for a TikTok video."""
    title = video.get("title") or f"New TikTok from @{username}"
    title = title[:256]
    url = video.get("url") or f"https://www.tiktok.com/@{username}"
    description = (video.get("description") or "").strip()
    if len(description) > 300:
        description = description[:297] + "..."

    embed = discord.Embed(
        title=title,
        url=url,
        description=description or "Tap the button below to watch.",
        color=discord.Color.from_rgb(18, 18, 18),
        timestamp=datetime.now(timezone.utc),
    )

    embed.set_author(name=f"@{username} on TikTok", icon_url=video.get("author_avatar") or discord.Embed.Empty)

    cover_url = video.get("cover")
    if cover_url:
        embed.set_image(url=cover_url)

    custom_stats = video.get("custom_stats")
    if custom_stats:
        stats_line = custom_stats
    else:
        stats_line = (
            f"▶️ {video.get('play_count', 0):,}  "
            f"❤️ {video.get('digg_count', 0):,}  "
            f"💬 {video.get('comment_count', 0):,}  "
            f"🔁 {video.get('share_count', 0):,}"
        )
    embed.add_field(name="Stats", value=stats_line, inline=False)

    created_ts = video.get("create_time")
    if created_ts:
        embed.add_field(name="Posted", value=f"<t:{int(created_ts)}:R>", inline=True)

    embed.set_footer(text="Auto-posted by Helper • TikTok tracker")
    return embed


async def fetch_latest_tiktok_video(username: str) -> dict | None:
    """Fetch latest TikTok post.

    Priority:
    1) Official TikTok API (if TIKTOK_ACCESS_TOKEN is configured)
    2) Public fallback endpoint (TikWM)
    """
    async def _official_fetch() -> dict | None:
        if not TIKTOK_ACCESS_TOKEN:
            return None

        api_url = (
            "https://open.tiktokapis.com/v2/video/list/"
            "?fields=id,title,video_description,create_time,cover_image_url,share_url,"
            "like_count,comment_count,share_count,view_count"
        )
        timeout = aiohttp.ClientTimeout(total=20)
        headers = {
            "Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {"max_count": 20}

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.post(api_url, json=payload) as resp:
                    if resp.status != 200:
                        logger.warning("Official TikTok API returned status %s", resp.status)
                        return None
                    raw = await resp.json(content_type=None)
        except Exception as e:
            logger.warning("Official TikTok API request failed: %s", e)
            return None

        data = raw.get("data") if isinstance(raw, dict) else None
        videos = []
        if isinstance(data, dict):
            videos = data.get("videos") or []

        if not videos:
            return None

        def _timestamp(v: dict) -> int:
            try:
                return int(v.get("create_time") or 0)
            except Exception:
                return 0

        latest = max(videos, key=_timestamp)
        video_id = str(latest.get("id") or "")
        return {
            "id": video_id,
            "url": latest.get("share_url") or (f"https://www.tiktok.com/@{username}/video/{video_id}" if video_id else None),
            "title": latest.get("title") or latest.get("video_description") or "New TikTok post",
            "description": latest.get("video_description") or latest.get("title") or "",
            "cover": latest.get("cover_image_url"),
            "author_avatar": None,
            "create_time": _timestamp(latest),
            "play_count": int(latest.get("view_count") or 0),
            "digg_count": int(latest.get("like_count") or 0),
            "comment_count": int(latest.get("comment_count") or 0),
            "share_count": int(latest.get("share_count") or 0),
        }

    async def _tikwm_profile_fallback() -> dict | None:
        """Fallback when TikWM post listing is blocked: use profile stats + video count signal."""
        info_url = f"https://www.tikwm.com/api/user/info?unique_id={username}"
        timeout = aiohttp.ClientTimeout(total=20)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.tikwm.com/",
        }

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(info_url) as resp:
                    if resp.status != 200:
                        logger.warning("TikTok profile fallback failed with status %s", resp.status)
                        return None
                    payload = await resp.json(content_type=None)
        except Exception as e:
            logger.warning("TikTok profile fallback error: %s", e)
            return None

        data = payload.get("data") if isinstance(payload, dict) else None
        user = data.get("user") if isinstance(data, dict) else None
        stats = data.get("stats") if isinstance(data, dict) else None
        if not isinstance(user, dict) or not isinstance(stats, dict):
            return None

        video_count = int(stats.get("videoCount") or 0)
        if video_count <= 0:
            return None

        avatar = user.get("avatarLarger") or user.get("avatarMedium") or user.get("avatarThumb")
        profile_url = f"https://www.tiktok.com/@{username}"
        return {
            "id": f"profile-video-count:{video_count}",
            "url": profile_url,
            "title": f"New TikTok detected from @{username}",
            "description": "Open profile to watch the latest upload.",
            "cover": avatar,
            "author_avatar": avatar,
            "create_time": int(datetime.now(timezone.utc).timestamp()),
            "play_count": 0,
            "digg_count": 0,
            "comment_count": 0,
            "share_count": 0,
            "custom_stats": (
                f"🎬 Videos: {video_count:,}  "
                f"👥 Followers: {int(stats.get('followerCount') or 0):,}  "
                f"❤️ Likes: {int(stats.get('heartCount') or 0):,}"
            ),
        }

    if not username:
        return None

    official = await _official_fetch()
    if official:
        return official

    api_url = f"https://www.tikwm.com/api/user/posts?unique_id={username}&count=12&cursor=0"
    timeout = aiohttp.ClientTimeout(total=20)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
    }

    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    logger.warning("TikTok fetch failed with status %s", resp.status)
                    return await _tikwm_profile_fallback()
                payload = await resp.json(content_type=None)
    except Exception as e:
        logger.warning("TikTok fetch error: %s", e)
        return await _tikwm_profile_fallback()

    data = payload.get("data") if isinstance(payload, dict) else None
    videos = []
    if isinstance(data, dict):
        videos = data.get("videos") or data.get("aweme_list") or []
    elif isinstance(data, list):
        videos = data

    if not videos:
        return await _tikwm_profile_fallback()

    def _timestamp(v: dict) -> int:
        try:
            return int(v.get("create_time") or 0)
        except Exception:
            return 0

    latest = max(videos, key=_timestamp)
    video_id = str(latest.get("video_id") or latest.get("aweme_id") or latest.get("id") or "")
    canonical_url = latest.get("share_url") or (f"https://www.tiktok.com/@{username}/video/{video_id}" if video_id else None)

    return {
        "id": video_id,
        "url": canonical_url,
        "title": latest.get("title") or latest.get("desc") or "New TikTok post",
        "description": latest.get("desc") or latest.get("title") or "",
        "cover": latest.get("cover") or latest.get("origin_cover") or latest.get("ai_dynamic_cover"),
        "author_avatar": (latest.get("author") or {}).get("avatar") if isinstance(latest.get("author"), dict) else None,
        "create_time": _timestamp(latest),
        "play_count": int(latest.get("play_count") or latest.get("play") or 0),
        "digg_count": int(latest.get("digg_count") or latest.get("digg") or 0),
        "comment_count": int(latest.get("comment_count") or latest.get("comment") or 0),
        "share_count": int(latest.get("share_count") or latest.get("share") or 0),
    }


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
    bot.tiktok_state = load_tiktok_state()
    bot.tiktok_username = TIKTOK_USERNAME or "p1mek"
    bot.status_messages = [
        ("playing", "🧩 /help"),
        ("listening", "support requests"),
        ("playing", "✅ solved threads"),
        ("listening", "error reports"),
        ("playing", "📌 forum triage"),
    ]

    async def check_and_post_latest_tiktok(force_post: bool = False) -> tuple[bool, str]:
        """Check latest TikTok and post to configured channel if a new video appears."""
        if not TIKTOK_CHANNEL_ID:
            return False, "TIKTOK_CHANNEL_ID is not configured"

        try:
            channel_id = int(TIKTOK_CHANNEL_ID)
        except ValueError:
            return False, "TIKTOK_CHANNEL_ID is invalid"

        channel = bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return False, f"Channel {channel_id} not found or not a text channel"

        username = bot.tiktok_username
        video = await fetch_latest_tiktok_video(username)
        if not video:
            return False, f"No TikTok data found for @{username}"

        video_id = video.get("id") or video.get("url")
        if not video_id:
            return False, "Latest TikTok item does not include id/url"

        state_key = f"{channel_id}:{username}"
        last_video_id = bot.tiktok_state.get(state_key)

        # First run seeds state to avoid posting old content.
        if not last_video_id and not force_post:
            bot.tiktok_state[state_key] = str(video_id)
            save_tiktok_state(bot.tiktok_state)
            return False, f"Seeded tracker for @{username} with current latest post"

        if str(last_video_id) == str(video_id) and not force_post:
            return False, "No new TikTok post"

        embed = build_tiktok_embed(video, username)
        role_mention = f"<@&{NOTIFY_ROLE_ID}>"
        content = f"{role_mention} New TikTok dropped from **@{username}**"

        try:
            await channel.send(
                content=content,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except Exception as e:
            return False, f"Failed to send TikTok post: {e}"

        bot.tiktok_state[state_key] = str(video_id)
        save_tiktok_state(bot.tiktok_state)
        return True, f"Posted new TikTok for @{username}"

    @tasks.loop(minutes=TIKTOK_CHECK_MINUTES)
    async def tiktok_watch_loop():
        posted, detail = await check_and_post_latest_tiktok(force_post=False)
        if posted:
            logger.info("TikTok tracker: %s", detail)
        else:
            logger.info("TikTok tracker: %s", detail)

    @tiktok_watch_loop.before_loop
    async def before_tiktok_watch_loop():
        await bot.wait_until_ready()

    @bot.tree.command(name="tiktokcheck", description="Force-check and post latest TikTok now")
    @app_commands.default_permissions(administrator=True)
    async def tiktokcheck(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        posted, detail = await check_and_post_latest_tiktok(force_post=True)
        if posted:
            await interaction.followup.send(f"✅ {detail}", ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ {detail}", ephemeral=True)

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
                stream_url = None
                for activity in member.activities:
                    if activity and activity.type == discord.ActivityType.streaming:
                        stream_url = getattr(activity, "url", None)
                        if stream_url:
                            break

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

            is_streaming = any(
                activity and activity.type == discord.ActivityType.streaming
                for activity in member.activities
            )

            try:
                if is_streaming and role not in member.roles:
                    await member.add_roles(role, reason="Streaming status detected (startup sync)")
                elif not is_streaming and role in member.roles:
                    await member.remove_roles(role, reason="Streaming status ended (startup sync)")
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
        if not tiktok_watch_loop.is_running():
            tiktok_watch_loop.start()
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
            if unsolved_tag and unsolved_tag not in thread.applied_tags:
                new_tags = list(thread.applied_tags)
                new_tags.append(unsolved_tag)
                await thread.edit(applied_tags=new_tags[:5])  # Max 5 tags
            
            helper_view = HelperView()
            bot_avatar = bot.user.display_avatar.url if bot.user else None
            await thread.send(embed=build_welcome_embed(bot_avatar), view=helper_view)
            logger.info("Posted helper embed in thread %s", thread.id)
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

        is_streaming = any(
            activity and activity.type == discord.ActivityType.streaming
            for activity in after.activities
        )

        try:
            if is_streaming and role not in after.roles:
                await after.add_roles(role, reason="Streaming status detected")
            elif not is_streaming and role in after.roles:
                await after.remove_roles(role, reason="Streaming status ended")
        except Exception as e:
            logger.warning("Failed to update streaming role: %s", e)

        await update_streaming_embed(after.guild)

    @bot.event
    async def setup_hook():
        bot.add_view(HelperView())

    return bot


def main():
    if not TOKEN:
        raise RuntimeError("HELPER_TOKEN is not set")
    bot = create_bot()
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
