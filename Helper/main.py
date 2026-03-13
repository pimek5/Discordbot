import os
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import aiohttp
import discord
from discord.ext import commands, tasks

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
            elif not is_streaming and role in after.roles:
                await after.remove_roles(role, reason="Streaming status ended")
        except Exception as e:
            logger.warning("Failed to update streaming role: %s", e)

        await update_streaming_embed(after.guild)

    @bot.event
    async def setup_hook():
        bot.add_view(HelperView())

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
