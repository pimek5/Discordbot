import os
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import aiohttp
from aiohttp import web
import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional

HELPER_FORUM_ID = 1464368533088768124  # Support forum channel ID
SOLVED_TAG_ID = 1464379665333620746  # Tag applied when thread is solved
UNSOLVED_TAG_ID = 1464379721272787069  # Tag applied when thread is unsolved/created
STREAM_ROLE_ID = 1470171489096564736  # Role granted while streaming
STREAM_LIST_CHANNEL_ID = 1470173597157818559  # Channel for streaming roster embed
THREAD_UPDATE_IGNORED_PARENT_IDS = {
    HELPER_FORUM_ID,
    1329671504941682750,
    1364052385470615602,
    1245400205063618570,
    1264484659765448804,
    1351150858351677480,
}
THREAD_UPDATE_LOG_CHANNEL_ID = 1372734313594093638
THREAD_UPDATE_NOTIFY_ROLE_ID = 1173564965152637018
MAIN_GUILD_ID = 1153027935553454191  # Main server — forum announcements only fire here
ORDER_BUTTON_URL = "https://ptb.discord.com/channels/1153027935553454191/1245400205063618570"
REPORT_ISSUES_BUTTON_URL = "https://ptb.discord.com/channels/1153027935553454191/1264484659765448804"
AUTO_TRIAGE_KEYWORDS = {
    "bug": ["bug", "error", "crash", "exception", "failed", "traceback"],
    "install": ["install", "setup", "launcher", "open", "start", "cannot launch"],
    "performance": ["fps", "lag", "stutter", "freeze", "performance", "slow"],
}
GUILD_ID = os.getenv("HELPER_GUILD_ID")
TOKEN = os.getenv("HELPER_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

# Ko-fi webhook
KOFI_VERIFICATION_TOKEN = os.getenv("KOFI_TOKEN", "95fcdc17-9c1e-4f7a-b66b-7c70723b3fcc")
KOFI_CHANNEL_ID = 1510163510355562566

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("helper")

VALID_STREAM_HOSTS = {
    "twitch.tv",
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


def _is_fantome_attachment(attachment: discord.Attachment) -> bool:
    filename = (attachment.filename or "").lower().strip()
    return filename.endswith(".fantome")


def _is_image_attachment(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    filename = (attachment.filename or "").lower().strip()
    return content_type.startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))


class ThreadUpdateLinksView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Order", style=discord.ButtonStyle.link, url=ORDER_BUTTON_URL))
        self.add_item(discord.ui.Button(label="Report skin issues", style=discord.ButtonStyle.link, url=REPORT_ISSUES_BUTTON_URL))


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



# ==================== KO-FI WEBHOOK SERVER ====================

KOFI_PAGE_URL = "https://ko-fi.com/pimek"
KOFI_AVATAR_URL = "https://i.imgur.com/2gmnuzl.png"


class KofiSupportView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(
            label="☕ Support on Ko-fi",
            url=KOFI_PAGE_URL,
            style=discord.ButtonStyle.link,
        ))


def build_kofi_embed(data: dict) -> tuple[discord.Embed, KofiSupportView]:
    """Build a Discord embed for a Ko-fi event."""
    event_type = data.get("type", "Donation")
    from_name = data.get("from_name") or "Anonymous"
    amount = data.get("amount", "?")
    currency = data.get("currency", "USD")
    message = data.get("message") or ""
    kofi_url = data.get("url", "https://ko-fi.com")
    tier_name = data.get("tier_name")
    is_first_sub = data.get("is_first_subscription_payment", False)

    if event_type == "Subscription":
        if is_first_sub:
            title = "🎉 New Supporter!"
            color = 0x29ABE0  # Ko-fi blue
        else:
            title = "🔄 Support Renewed!"
            color = 0x1E90FF
        description = f"**{from_name}** subscribed" + (f" · **{tier_name}**" if tier_name else "") + f"\n**{amount} {currency}/month**"
    elif event_type == "Shop Order":
        title = "🛍️ New Shop Order!"
        color = 0xF6A623
        description = f"**{from_name}** placed an order · **{amount} {currency}**"
    else:
        title = "☕ New Donation!"
        color = 0xFF5E5B
        description = f"**{from_name}** donated **{amount} {currency}**"

    embed = discord.Embed(title=title, description=description, color=color, url=kofi_url)
    embed.set_author(
        name=from_name,
        icon_url="https://storage.ko-fi.com/cdn/kofi_stroke_cup.png",
    )
    embed.set_thumbnail(url=KOFI_AVATAR_URL)

    if message:
        embed.add_field(name="💬 Message", value=message[:1024], inline=False)

    embed.set_footer(
        text="Ko-fi · Thank you for your support!",
        icon_url="https://storage.ko-fi.com/cdn/kofi_stroke_cup.png",
    )
    embed.timestamp = datetime.now(timezone.utc)
    return embed, KofiSupportView()


async def handle_kofi_webhook(request: web.Request) -> web.Response:
    """Handle incoming Ko-fi webhook POST requests."""
    bot = request.app["bot"]
    try:
        post = await request.post()
        raw = post.get("data")
        if not raw:
            # Also accept raw JSON body
            try:
                raw_bytes = await request.read()
                raw = raw_bytes.decode()
            except Exception:
                logger.warning("Ko-fi webhook: no data field and no body")
                return web.Response(status=400, text="Missing data")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Ko-fi webhook: invalid JSON")
            return web.Response(status=400, text="Invalid JSON")

        # Verify token
        if data.get("verification_token") != KOFI_VERIFICATION_TOKEN:
            logger.warning("Ko-fi webhook: invalid verification token")
            return web.Response(status=403, text="Forbidden")

        logger.info("Ko-fi event received: type=%s from=%s amount=%s %s",
                    data.get("type"), data.get("from_name"), data.get("amount"), data.get("currency"))

        channel = bot.get_channel(KOFI_CHANNEL_ID)
        if channel is None:
            try:
                channel = await bot.fetch_channel(KOFI_CHANNEL_ID)
            except Exception as e:
                logger.error("Ko-fi: cannot find channel %s: %s", KOFI_CHANNEL_ID, e)
                return web.Response(status=200, text="OK")  # Return 200 so Ko-fi doesn't retry

        embed, view = build_kofi_embed(data)
        await channel.send(embed=embed, view=view)
        logger.info("Ko-fi embed sent to channel %s", KOFI_CHANNEL_ID)

    except Exception as e:
        logger.error("Ko-fi webhook handler error: %s", e)

    return web.Response(status=200, text="OK")


async def start_kofi_server(bot: commands.Bot):
    """Start the aiohttp web server to receive Ko-fi webhooks."""
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/kofi", handle_kofi_webhook)

    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Ko-fi webhook server listening on port %s at POST /kofi", port)


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
    bot.thread_update_processed_messages = set()
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
        if not getattr(bot, "_kofi_server_started", False):
            bot._kofi_server_started = True
            await start_kofi_server(bot)

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

    async def _find_thread_preview_image(thread: discord.Thread, source_message: Optional[discord.Message] = None) -> Optional[str]:
        candidate_messages: list[discord.Message] = []
        if source_message is not None:
            candidate_messages.append(source_message)

        try:
            starter_message = await thread.fetch_message(thread.id)
            if starter_message not in candidate_messages:
                candidate_messages.append(starter_message)
        except Exception:
            pass

        try:
            async for msg in thread.history(limit=15, oldest_first=True):
                if msg not in candidate_messages:
                    candidate_messages.append(msg)
        except Exception:
            pass

        for msg in candidate_messages:
            for attachment in msg.attachments:
                if _is_image_attachment(attachment):
                    return attachment.url
        return None

    def _thread_update_kind(thread: discord.Thread, force_posted: bool = False) -> str:
        if force_posted:
            return "Posted"
        created_at = thread.created_at
        if created_at is None:
            return "Fixed"
        age = datetime.now(timezone.utc) - created_at
        return "Fixed" if age >= timedelta(days=1) else "Posted"

    def _should_ignore_thread_update(thread: discord.Thread) -> bool:
        return thread.parent_id in THREAD_UPDATE_IGNORED_PARENT_IDS

    async def _post_forum_announcement(thread: discord.Thread, source_message: Optional[discord.Message], is_new: bool):
        """Post a New Post or Updated/Fixed Post embed to the forum log channel."""
        if thread.guild is None or thread.guild.id != MAIN_GUILD_ID:
            return
        if _should_ignore_thread_update(thread):
            return
        if source_message and source_message.id in bot.thread_update_processed_messages:
            return

        log_channel = bot.get_channel(THREAD_UPDATE_LOG_CHANNEL_ID)
        if log_channel is None:
            try:
                log_channel = await bot.fetch_channel(THREAD_UPDATE_LOG_CHANNEL_ID)
            except Exception as e:
                logger.warning("Could not fetch forum log channel: %s", e)
                return

        author = thread.owner
        author_name = author.display_name if author else "Unknown"
        author_avatar = author.display_avatar.url if author else None

        preview_image = await _find_thread_preview_image(thread, source_message=source_message)

        applied_tags = [tag.name for tag in (thread.applied_tags or [])]

        if is_new:
            title = f"📌 New Post — {thread.name}"
            color = discord.Color.green()
            status = "New Post"
        else:
            title = f"🔄 Updated — {thread.name}"
            color = discord.Color.orange()
            status = "Updated/Fixed Post"

        thread_link = source_message.jump_url if source_message else thread.jump_url
        embed = discord.Embed(
            title=title,
            description=f"[Open thread]({thread_link})",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=f"By {author_name}", icon_url=author_avatar)
        embed.add_field(name="Thread", value=thread.mention, inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Channel", value=f"<#{thread.parent_id}>" if thread.parent_id else "Unknown", inline=True)
        if applied_tags:
            embed.add_field(name="🏷️ Tags", value=" • ".join(f"`{t}`" for t in applied_tags[:5]), inline=False)
        if preview_image:
            embed.set_image(url=preview_image)

        view = ThreadUpdateLinksView()
        await log_channel.send(content=f"<@&{THREAD_UPDATE_NOTIFY_ROLE_ID}>", embed=embed, view=view)
        if source_message:
            bot.thread_update_processed_messages.add(source_message.id)
        logger.info("Forum announcement posted: thread=%s is_new=%s", thread.id, is_new)

    async def _post_thread_fantome_update(thread: discord.Thread, source_message: discord.Message, force_posted: bool = False):
        if not isinstance(thread, discord.Thread):
            return
        if not thread.guild:
            return
        if _should_ignore_thread_update(thread):
            return

        if source_message.id in bot.thread_update_processed_messages:
            return

        log_channel = bot.get_channel(THREAD_UPDATE_LOG_CHANNEL_ID)
        if log_channel is None:
            try:
                log_channel = await bot.fetch_channel(THREAD_UPDATE_LOG_CHANNEL_ID)
            except Exception as e:
                logger.warning("Could not fetch thread update log channel: %s", e)
                return

        if not isinstance(log_channel, discord.TextChannel):
            logger.warning("Thread update log channel %s is not a text channel", THREAD_UPDATE_LOG_CHANNEL_ID)
            return

        update_kind = _thread_update_kind(thread, force_posted=force_posted)
        clean_name = thread.name.removeprefix("[Solved] ").strip()
        thread_link = source_message.jump_url if source_message else thread.jump_url
        preview_image = await _find_thread_preview_image(thread, source_message=source_message)

        embed = discord.Embed(
            title=f"{clean_name} {update_kind}",
            description=f"[Open thread]({thread_link})",
            color=discord.Color.green() if update_kind == "Fixed" else discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Thread", value=thread.mention, inline=True)
        embed.add_field(name="Status", value=update_kind, inline=True)
        embed.add_field(name="Channel", value=f"<#{thread.parent_id}>" if thread.parent_id else "Unknown", inline=True)
        if preview_image:
            embed.set_image(url=preview_image)

        view = ThreadUpdateLinksView()
        await log_channel.send(content=f"<@&{THREAD_UPDATE_NOTIFY_ROLE_ID}>", embed=embed, view=view)
        bot.thread_update_processed_messages.add(source_message.id)
        logger.info("Posted thread update log for thread=%s status=%s message=%s", thread.id, update_kind, source_message.id)

    @bot.event
    async def on_thread_create(thread: discord.Thread):
        try:
            starter_message = None
            try:
                starter_message = await thread.fetch_message(thread.id)
            except Exception:
                messages = [msg async for msg in thread.history(limit=1, oldest_first=True)]
                starter_message = messages[0] if messages else None

            if thread.parent_id == HELPER_FORUM_ID:
                # Apply unsolved tag to new support threads only.
                forum = thread.parent
                unsolved_tag = discord.utils.get(forum.available_tags, id=UNSOLVED_TAG_ID)

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

            if starter_message and any(_is_fantome_attachment(att) for att in starter_message.attachments):
                await _post_thread_fantome_update(thread, starter_message, force_posted=True)

            # General announcement for all non-ignored threads
            if not _should_ignore_thread_update(thread):
                await _post_forum_announcement(thread, starter_message, is_new=True)
        except Exception as e:
            logger.error("Failed to process thread create flow: %s", e)

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.Thread):
            return
        if message.guild is None:
            return
        if _should_ignore_thread_update(message.channel):
            return

        # General file update announcement — all non-ignored threads (including .fantome)
        if not message.attachments:
            return

        try:
            await _post_forum_announcement(message.channel, message, is_new=False)
        except Exception as e:
            logger.error("Failed to post forum file update announcement: %s", e)

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

    # TODO: remove test command
    @bot.tree.command(name="testkofi", description="Test Ko-fi embed")
    async def testkofi(interaction: discord.Interaction):
        fake_data = {
            "type": "Donation",
            "from_name": "TestUser",
            "amount": "5.00",
            "currency": "USD",
            "message": "Test donation message!",
            "url": "https://ko-fi.com/pimek",
        }
        embed, view = build_kofi_embed(fake_data)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @bot.event
    async def setup_hook():
        bot.add_view(HelperView())
        bot.add_view(ThreadUpdateLinksView())

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
