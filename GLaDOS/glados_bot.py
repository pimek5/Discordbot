import os
import asyncio
import re
import logging
from dataclasses import dataclass
from typing import Optional, Dict, List

import discord
from discord.ext import commands
from discord import app_commands
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("GLaDOS")

EMPTY_CHANNEL_DELETE_DELAY = 3
DUO_CHANNEL_LIMIT = 2
FLEX_CHANNEL_LIMIT = 5
CUSTOM_MAIN_CHANNEL_LIMIT = 20
CUSTOM_TEAM_CHANNEL_LIMIT = 5


def env_int(name: str) -> Optional[int]:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid int for %s: %s", name, value)
        return None


def env_token(name: str) -> str:
    raw = os.getenv(name, "").strip()
    if not raw:
        return ""

    # Common Railway copy/paste issue: token surrounded with quotes.
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        raw = raw[1:-1].strip()

    # Discord.py expects raw token without the "Bot " prefix.
    if raw.lower().startswith("bot "):
        raw = raw[4:].strip()

    return raw


DISCORD_TOKEN = env_token("DISCORD_TOKEN")
GUILD_ID = env_int("GUILD_ID") or 1318383232785453076

DUO_CATEGORY_ID = env_int("DUO_CATEGORY_ID") or 1492683548329508904
FLEX_CATEGORY_ID = env_int("FLEX_CATEGORY_ID") or 1492683598325743856
CUSTOM_CATEGORY_ID = env_int("CUSTOM_CATEGORY_ID") or 1492683598325743856

DUO_GENERATOR_CHANNEL_ID = env_int("DUO_GENERATOR_CHANNEL_ID")
FLEX_GENERATOR_CHANNEL_ID = env_int("FLEX_GENERATOR_CHANNEL_ID")
CUSTOM_GENERATOR_CHANNEL_ID = env_int("CUSTOM_GENERATOR_CHANNEL_ID")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
LFM_CHANNEL_ID = env_int("LFM_CHANNEL_ID")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://glados.local/dashboard").strip()


@dataclass
class CustomGroup:
    owner_id: int
    category_id: int
    main_voice_id: int
    team1_voice_id: int
    team2_voice_id: int
    text_id: int


@dataclass
class SimpleTempChannel:
    owner_id: int
    prefix: str
    voice_id: int
    text_id: int


class SingleValueModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        title: str,
        label: str,
        placeholder: str,
        max_length: int,
        on_submit_handler,
    ):
        super().__init__(title=title)
        self._on_submit_handler = on_submit_handler
        self.value = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            required=True,
            max_length=max_length,
        )
        self.add_item(self.value)

    async def on_submit(self, interaction: discord.Interaction):
        await self._on_submit_handler(interaction, str(self.value.value).strip())


class PermissionSelect(discord.ui.Select):
    def __init__(self, parent_view: "TempVoiceControlView"):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label="Lock", value="lock", description="Lock the channel", emoji="🔒"),
            discord.SelectOption(label="Unlock", value="unlock", description="Unlock the channel", emoji="🔓"),
            discord.SelectOption(label="Permit", value="permit", description="Permit user/role", emoji="✅"),
            discord.SelectOption(label="Reject", value="reject", description="Reject user/role", emoji="⛔"),
            discord.SelectOption(label="Invite", value="invite", description="Invite a user", emoji="📨"),
        ]
        super().__init__(
            placeholder="Change channel permissions",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.handle_permission_action(interaction, self.values[0])


class SettingsSelect(discord.ui.Select):
    def __init__(self, parent_view: "TempVoiceControlView"):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label="Name", value="name", description="Change channel name", emoji="📝"),
            discord.SelectOption(label="Limit", value="limit", description="Change user limit", emoji="👥"),
            discord.SelectOption(label="Status", value="status", description="Set status tag", emoji="💬"),
            discord.SelectOption(label="Game", value="game", description="Set game name", emoji="🎮"),
            discord.SelectOption(label="LFM", value="lfm", description="Post looking-for-members", emoji="📣"),
        ]
        super().__init__(
            placeholder="Change channel settings",
            min_values=1,
            max_values=1,
            options=options,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.handle_settings_action(interaction, self.values[0])


class TempVoiceControlView(discord.ui.View):
    def __init__(
        self,
        *,
        bot: "GLaDOSBot",
        owner_id: int,
        voice_ids: List[int],
        text_id: int,
        kind: str,
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.owner_id = owner_id
        self.voice_ids = voice_ids
        self.text_id = text_id
        self.kind = kind

        self.add_item(PermissionSelect(self))
        self.add_item(SettingsSelect(self))

        self.refresh_btn = discord.ui.Button(label="Load Settings", style=discord.ButtonStyle.primary, emoji="💾", row=3)
        self.refresh_btn.callback = self.refresh_callback
        self.add_item(self.refresh_btn)

        self.dashboard_btn = discord.ui.Button(
            label="Dashboard",
            style=discord.ButtonStyle.link,
            url=DASHBOARD_URL,
            row=3,
        )
        self.add_item(self.dashboard_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only channel owner can use this panel.", ephemeral=True)
            return False
        return True

    def _get_voice_channels(self, guild: discord.Guild) -> List[discord.VoiceChannel]:
        channels: List[discord.VoiceChannel] = []
        for channel_id in self.voice_ids:
            ch = guild.get_channel(channel_id)
            if isinstance(ch, discord.VoiceChannel):
                channels.append(ch)
        return channels

    def _get_primary_voice(self, guild: discord.Guild) -> Optional[discord.VoiceChannel]:
        channels = self._get_voice_channels(guild)
        return channels[0] if channels else None

    def _get_text_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        ch = guild.get_channel(self.text_id)
        return ch if isinstance(ch, discord.TextChannel) else None

    @staticmethod
    def _extract_member_id(raw: str) -> Optional[int]:
        cleaned = raw.strip()
        if cleaned.isdigit():
            return int(cleaned)
        match = re.search(r"(\d{15,22})", cleaned)
        return int(match.group(1)) if match else None

    async def refresh_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("Panel is loaded and ready.", ephemeral=True)

    async def handle_permission_action(self, interaction: discord.Interaction, action: str):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Guild not found.", ephemeral=True)
            return

        voices = self._get_voice_channels(guild)
        if not voices:
            await interaction.response.send_message("Voice channel no longer exists.", ephemeral=True)
            return

        everyone = guild.default_role

        if action == "lock":
            for vc in voices:
                await vc.set_permissions(everyone, connect=False)
            await interaction.response.send_message("Channel locked.", ephemeral=True)
            return

        if action == "unlock":
            for vc in voices:
                await vc.set_permissions(everyone, connect=None)
            await interaction.response.send_message("Channel unlocked.", ephemeral=True)
            return

        if action in {"permit", "invite", "reject"}:
            label = "User mention or ID"
            placeholder = "@user or 123456789012345678"

            async def on_submit_member(modal_interaction: discord.Interaction, raw_value: str):
                member_id = self._extract_member_id(raw_value)
                if member_id is None:
                    await modal_interaction.response.send_message("Invalid member value.", ephemeral=True)
                    return

                member = guild.get_member(member_id)
                if member is None:
                    await modal_interaction.response.send_message("Member not found in this server.", ephemeral=True)
                    return

                text = self._get_text_channel(guild)

                if action in {"permit", "invite"}:
                    for vc in voices:
                        await vc.set_permissions(member, view_channel=True, connect=True, speak=True)
                    if text:
                        await text.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
                    await modal_interaction.response.send_message(f"Permitted {member.mention}.", ephemeral=True)
                    return

                # reject
                for vc in voices:
                    await vc.set_permissions(member, view_channel=False, connect=False)
                if text:
                    await text.set_permissions(member, view_channel=False, send_messages=False)
                if member.voice and member.voice.channel and member.voice.channel.id in self.voice_ids:
                    await member.move_to(None, reason="Rejected from temporary voice")
                await modal_interaction.response.send_message(f"Rejected {member.mention}.", ephemeral=True)

            modal = SingleValueModal(
                title=f"{action.title()} Member",
                label=label,
                placeholder=placeholder,
                max_length=64,
                on_submit_handler=on_submit_member,
            )
            await interaction.response.send_modal(modal)
            return

        await interaction.response.send_message("Unsupported permission action.", ephemeral=True)

    async def handle_settings_action(self, interaction: discord.Interaction, action: str):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Guild not found.", ephemeral=True)
            return

        voices = self._get_voice_channels(guild)
        primary = self._get_primary_voice(guild)
        if not voices or primary is None:
            await interaction.response.send_message("Voice channel no longer exists.", ephemeral=True)
            return

        if action == "name":
            async def on_submit_name(modal_interaction: discord.Interaction, raw_value: str):
                new_name = raw_value[:100]
                for vc in voices:
                    await vc.edit(name=new_name)
                await modal_interaction.response.send_message(f"Channel renamed to **{new_name}**.", ephemeral=True)

            modal = SingleValueModal(
                title="Change Channel Name",
                label="New name",
                placeholder="duoq-yourname",
                max_length=100,
                on_submit_handler=on_submit_name,
            )
            await interaction.response.send_modal(modal)
            return

        if action == "limit":
            async def on_submit_limit(modal_interaction: discord.Interaction, raw_value: str):
                try:
                    limit = int(raw_value)
                except ValueError:
                    await modal_interaction.response.send_message("Limit must be a number (0-99).", ephemeral=True)
                    return

                if limit < 0 or limit > 99:
                    await modal_interaction.response.send_message("Limit must be between 0 and 99.", ephemeral=True)
                    return

                for vc in voices:
                    await vc.edit(user_limit=limit)
                await modal_interaction.response.send_message(f"User limit set to **{limit}**.", ephemeral=True)

            modal = SingleValueModal(
                title="Change User Limit",
                label="User limit",
                placeholder="0-99",
                max_length=2,
                on_submit_handler=on_submit_limit,
            )
            await interaction.response.send_modal(modal)
            return

        if action in {"status", "game"}:
            title = "Set Status" if action == "status" else "Set Game"
            placeholder = "ranked grind" if action == "status" else "league of legends"

            async def on_submit_status(modal_interaction: discord.Interaction, raw_value: str):
                base = raw_value.strip()
                if not base:
                    await modal_interaction.response.send_message("Value cannot be empty.", ephemeral=True)
                    return
                new_name = f"{base}"[:100]
                await primary.edit(name=new_name)
                await modal_interaction.response.send_message(f"Primary voice updated to **{new_name}**.", ephemeral=True)

            modal = SingleValueModal(
                title=title,
                label="Value",
                placeholder=placeholder,
                max_length=100,
                on_submit_handler=on_submit_status,
            )
            await interaction.response.send_modal(modal)
            return

        if action == "lfm":
            if LFM_CHANNEL_ID is None:
                await interaction.response.send_message("LFM channel is not configured.", ephemeral=True)
                return

            lfm_channel = guild.get_channel(LFM_CHANNEL_ID)
            if not isinstance(lfm_channel, discord.TextChannel):
                await interaction.response.send_message("Configured LFM channel not found.", ephemeral=True)
                return

            owner = guild.get_member(self.owner_id)
            owner_name = owner.mention if owner else f"<@{self.owner_id}>"
            links = "\n".join(f"- <#{vc.id}>" for vc in voices)

            embed = discord.Embed(
                title="LFM - Temporary Voice",
                description=f"{owner_name} is looking for members.\n\n**Channels:**\n{links}",
                color=discord.Color.gold(),
            )
            await lfm_channel.send(embed=embed)
            await interaction.response.send_message("LFM posted.", ephemeral=True)
            return

        await interaction.response.send_message("Unsupported settings action.", ephemeral=True)


def build_owner_panel_embed(owner: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Welcome to your temporary voice channel",
        description=(
            "Control your channel using the menus below\n"
            "• Use dropdowns to manage settings and permissions\n"
            "• Owner-only controls are enforced\n"
            "• Use `/toggle_feature` style commands later if needed"
        ),
        color=discord.Color.dark_blue(),
    )
    embed.add_field(name="Channel Settings", value="Use the second dropdown for name/limit/status/game/LFM.", inline=False)
    embed.add_field(name="Permissions", value="Use the first dropdown for lock/unlock/permit/reject/invite.", inline=False)
    embed.set_footer(text=f"Owner: {owner.display_name}")
    return embed


class SharedDatabase:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def enabled(self) -> bool:
        return bool(self.database_url)

    def _connect(self):
        return psycopg2.connect(self.database_url)

    def healthcheck(self) -> bool:
        if not self.enabled():
            return False
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return True
        except Exception as exc:
            logger.error("Database healthcheck failed: %s", exc)
            return False

    def get_profile(self, user_id: int) -> Optional[dict]:
        if not self.enabled():
            return None

        query = """
            SELECT riot_id_game_name, riot_id_tagline, region, solo_rank, flex_rank
            FROM lfg_profiles
            WHERE user_id = %s
        """

        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (user_id,))
                    row = cur.fetchone()
                    return dict(row) if row else None
        except Exception as exc:
            logger.error("Failed to fetch lfg profile for %s: %s", user_id, exc)
            return None


class GLaDOSBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.voice_states = True
        intents.message_content = False

        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)

        self.db = SharedDatabase(DATABASE_URL)

        # Single temporary channels (duo/flex)
        self.simple_temp_channels: Dict[int, SimpleTempChannel] = {}
        self.simple_cleanup_tasks: Dict[int, asyncio.Task] = {}

        # Custom groups
        self.custom_groups: Dict[int, CustomGroup] = {}
        self.voice_to_group: Dict[int, int] = {}
        self.custom_cleanup_tasks: Dict[int, asyncio.Task] = {}

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        logger.info("Slash commands synced to guild %s", GUILD_ID)

    async def on_ready(self):
        logger.info("Logged in as %s (%s)", self.user, self.user.id)
        logger.info("Connected to %d guild(s)", len(self.guilds))

        guild = self.get_guild(GUILD_ID)
        if guild is not None:
            await self._pin_generator_channels(guild)

        if self.db.enabled():
            if self.db.healthcheck():
                logger.info("Database connection OK")
            else:
                logger.warning("Database configured but healthcheck failed")
        else:
            logger.warning("DATABASE_URL is not set. Shared profile/rank features are disabled")

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return

        # User joined a join-to-create channel
        if after.channel is not None:
            if DUO_GENERATOR_CHANNEL_ID and after.channel.id == DUO_GENERATOR_CHANNEL_ID:
                await self._create_and_move_simple(member, DUO_CATEGORY_ID, "duoq")
                return

            if FLEX_GENERATOR_CHANNEL_ID and after.channel.id == FLEX_GENERATOR_CHANNEL_ID:
                await self._create_and_move_simple(member, FLEX_CATEGORY_ID, "flexq")
                return

            if CUSTOM_GENERATOR_CHANNEL_ID and after.channel.id == CUSTOM_GENERATOR_CHANNEL_ID:
                await self._create_and_move_custom(member, CUSTOM_CATEGORY_ID)
                return

        # Dynamic custom chat access: update for leave / move
        if before.channel and before.channel.id in self.voice_to_group:
            group_key = self.voice_to_group[before.channel.id]
            await self._sync_member_custom_text_access(member, group_key)
            self._schedule_custom_cleanup(group_key)

        # Dynamic custom chat access: update for join / move
        if after.channel and after.channel.id in self.voice_to_group:
            group_key = self.voice_to_group[after.channel.id]
            self._cancel_custom_cleanup(group_key)
            await self._sync_member_custom_text_access(member, group_key)

        # Cleanup duo/flex temp channels and their text panel channels after a delay
        if before.channel and before.channel.id in self.simple_temp_channels:
            if len(before.channel.members) == 0:
                self._schedule_simple_cleanup(before.channel.id)

        if after.channel and after.channel.id in self.simple_temp_channels:
            self._cancel_simple_cleanup(after.channel.id)

    async def _create_and_move_simple(self, member: discord.Member, category_id: int, prefix: str):
        category = member.guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            logger.error("Category %s not found for %s", category_id, prefix)
            return

        channel_name = f"{prefix}-{member.display_name}"[:100]
        user_limit = DUO_CHANNEL_LIMIT if prefix == "duoq" else FLEX_CHANNEL_LIMIT

        try:
            voice_channel = await member.guild.create_voice_channel(
                name=channel_name,
                category=category,
                user_limit=user_limit,
                reason=f"Temporary {prefix} channel for {member}",
            )
            text_channel = await member.guild.create_text_channel(
                name=f"{channel_name}-chat"[:100],
                category=category,
                reason=f"Temporary {prefix} chat for {member}",
            )

            self.simple_temp_channels[voice_channel.id] = SimpleTempChannel(
                owner_id=member.id,
                prefix=prefix,
                voice_id=voice_channel.id,
                text_id=text_channel.id,
            )

            if member.voice and member.voice.channel:
                await member.move_to(voice_channel, reason="Move to temporary channel")

            panel = TempVoiceControlView(
                bot=self,
                owner_id=member.id,
                voice_ids=[voice_channel.id],
                text_id=text_channel.id,
                kind=prefix,
            )
            await text_channel.send(embed=build_owner_panel_embed(member), view=panel)
            await self._pin_generator_channels(member.guild)

            logger.info("Created %s temporary channel %s for user %s", prefix, voice_channel.id, member.id)
        except Exception as exc:
            logger.error("Failed creating %s temp channel for %s: %s", prefix, member.id, exc)

    async def _create_and_move_custom(self, member: discord.Member, category_id: int):
        category = member.guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            logger.error("Custom category %s not found", category_id)
            return

        base_name = member.display_name[:30]

        everyone = member.guild.default_role
        me = member.guild.me
        overwrites = {
            everyone: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                send_messages=True,
                read_message_history=True,
            ),
        }
        if me:
            overwrites[me] = discord.PermissionOverwrite(
                view_channel=True,
                manage_channels=True,
                move_members=True,
                connect=True,
                speak=True,
                send_messages=True,
            )

        try:
            main_voice = await member.guild.create_voice_channel(
                name=f"custom-{base_name}"[:100],
                category=category,
                overwrites=overwrites,
                user_limit=CUSTOM_MAIN_CHANNEL_LIMIT,
                reason=f"Custom temporary channels for {member}",
            )
            team1_voice = await member.guild.create_voice_channel(
                name=f"custom-{base_name}-team-1"[:100],
                category=category,
                overwrites=overwrites,
                user_limit=CUSTOM_TEAM_CHANNEL_LIMIT,
                reason=f"Custom temporary channels for {member}",
            )
            team2_voice = await member.guild.create_voice_channel(
                name=f"custom-{base_name}-team-2"[:100],
                category=category,
                overwrites=overwrites,
                user_limit=CUSTOM_TEAM_CHANNEL_LIMIT,
                reason=f"Custom temporary channels for {member}",
            )
            text_channel = await member.guild.create_text_channel(
                name=f"custom-{base_name}-chat"[:100],
                category=category,
                overwrites=overwrites,
                reason=f"Custom temporary channels for {member}",
            )

            group = CustomGroup(
                owner_id=member.id,
                category_id=category.id,
                main_voice_id=main_voice.id,
                team1_voice_id=team1_voice.id,
                team2_voice_id=team2_voice.id,
                text_id=text_channel.id,
            )

            group_key = main_voice.id
            self.custom_groups[group_key] = group
            self.voice_to_group[main_voice.id] = group_key
            self.voice_to_group[team1_voice.id] = group_key
            self.voice_to_group[team2_voice.id] = group_key

            if member.voice and member.voice.channel:
                await member.move_to(main_voice, reason="Move to custom temporary channel")

            await self._sync_member_custom_text_access(member, group_key)

            panel = TempVoiceControlView(
                bot=self,
                owner_id=member.id,
                voice_ids=[main_voice.id, team1_voice.id, team2_voice.id],
                text_id=text_channel.id,
                kind="custom",
            )
            await text_channel.send(embed=build_owner_panel_embed(member), view=panel)
            await self._pin_generator_channels(member.guild)

            logger.info(
                "Created custom temporary set for %s (main=%s, team1=%s, team2=%s, text=%s)",
                member.id,
                main_voice.id,
                team1_voice.id,
                team2_voice.id,
                text_channel.id,
            )
        except Exception as exc:
            logger.error("Failed creating custom temporary channels for %s: %s", member.id, exc)

    def _group_channels(self, guild: discord.Guild, group: CustomGroup):
        main = guild.get_channel(group.main_voice_id)
        team1 = guild.get_channel(group.team1_voice_id)
        team2 = guild.get_channel(group.team2_voice_id)
        text = guild.get_channel(group.text_id)
        return main, team1, team2, text

    async def _sync_member_custom_text_access(self, member: discord.Member, group_key: int):
        group = self.custom_groups.get(group_key)
        if not group:
            return

        main, team1, team2, text = self._group_channels(member.guild, group)
        if not isinstance(text, discord.TextChannel):
            return

        voice_channels = [ch for ch in (main, team1, team2) if isinstance(ch, discord.VoiceChannel)]
        is_in_any_group_voice = any(member in ch.members for ch in voice_channels)

        try:
            if is_in_any_group_voice:
                await text.set_permissions(
                    member,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )
            else:
                await text.set_permissions(member, overwrite=None)
        except Exception as exc:
            logger.error("Failed syncing custom text access for member %s: %s", member.id, exc)

    async def _cleanup_custom_group_if_empty(self, group_key: int):
        group = self.custom_groups.get(group_key)
        if not group:
            return

        guild = self.get_guild(GUILD_ID)
        if not guild:
            return

        main, team1, team2, text = self._group_channels(guild, group)
        voice_channels = [ch for ch in (main, team1, team2) if isinstance(ch, discord.VoiceChannel)]

        if not voice_channels:
            # Channels already gone; cleanup in-memory mapping
            self._remove_custom_group_mappings(group_key)
            return

        if any(len(ch.members) > 0 for ch in voice_channels):
            return

        # All empty -> delete all channels
        for ch in (main, team1, team2, text):
            if ch is None:
                continue
            try:
                await ch.delete(reason="Custom temporary group empty")
            except Exception as exc:
                logger.error("Failed deleting channel %s in custom cleanup: %s", getattr(ch, "id", "?"), exc)

        self._remove_custom_group_mappings(group_key)
        logger.info("Deleted empty custom temporary group %s", group_key)

    def _remove_custom_group_mappings(self, group_key: int):
        self._cancel_custom_cleanup(group_key)
        group = self.custom_groups.pop(group_key, None)
        if not group:
            return
        self.voice_to_group.pop(group.main_voice_id, None)
        self.voice_to_group.pop(group.team1_voice_id, None)
        self.voice_to_group.pop(group.team2_voice_id, None)

    def _schedule_simple_cleanup(self, channel_id: int):
        self._cancel_simple_cleanup(channel_id)
        self.simple_cleanup_tasks[channel_id] = self.loop.create_task(self._delayed_simple_cleanup(channel_id))

    def _cancel_simple_cleanup(self, channel_id: int):
        task = self.simple_cleanup_tasks.pop(channel_id, None)
        if task and not task.done():
            task.cancel()

    async def _delayed_simple_cleanup(self, channel_id: int):
        try:
            await asyncio.sleep(EMPTY_CHANNEL_DELETE_DELAY)

            meta = self.simple_temp_channels.get(channel_id)
            if not meta:
                return

            guild = self.get_guild(GUILD_ID)
            if guild is None:
                return

            voice_channel = guild.get_channel(channel_id)
            text_channel = guild.get_channel(meta.text_id)

            if isinstance(voice_channel, discord.VoiceChannel) and len(voice_channel.members) > 0:
                return

            try:
                if isinstance(voice_channel, discord.VoiceChannel):
                    await voice_channel.delete(reason=f"Temporary channel empty for {EMPTY_CHANNEL_DELETE_DELAY} seconds")
                if isinstance(text_channel, discord.TextChannel):
                    await text_channel.delete(reason=f"Temporary channel empty for {EMPTY_CHANNEL_DELETE_DELAY} seconds")
                self.simple_temp_channels.pop(channel_id, None)
                await self._pin_generator_channels(guild)
                logger.info("Deleted empty temporary channel %s after %s seconds", channel_id, EMPTY_CHANNEL_DELETE_DELAY)
            except Exception as exc:
                logger.error("Failed to delete temporary channel %s: %s", channel_id, exc)
        except asyncio.CancelledError:
            logger.debug("Cancelled cleanup for temporary channel %s", channel_id)
        finally:
            self.simple_cleanup_tasks.pop(channel_id, None)

    def _schedule_custom_cleanup(self, group_key: int):
        self._cancel_custom_cleanup(group_key)
        self.custom_cleanup_tasks[group_key] = self.loop.create_task(self._delayed_custom_cleanup(group_key))

    def _cancel_custom_cleanup(self, group_key: int):
        task = self.custom_cleanup_tasks.pop(group_key, None)
        if task and not task.done():
            task.cancel()

    async def _delayed_custom_cleanup(self, group_key: int):
        try:
            await asyncio.sleep(EMPTY_CHANNEL_DELETE_DELAY)
            await self._cleanup_custom_group_if_empty(group_key)
        except asyncio.CancelledError:
            logger.debug("Cancelled cleanup for custom group %s", group_key)
        finally:
            self.custom_cleanup_tasks.pop(group_key, None)

    def get_owner_panel_target(self, guild: discord.Guild, owner_id: int):
        for meta in self.simple_temp_channels.values():
            if meta.owner_id != owner_id:
                continue
            voice = guild.get_channel(meta.voice_id)
            text = guild.get_channel(meta.text_id)
            if isinstance(voice, discord.VoiceChannel) and isinstance(text, discord.TextChannel):
                return [meta.voice_id], meta.text_id, meta.prefix

        for group in self.custom_groups.values():
            if group.owner_id != owner_id:
                continue
            main = guild.get_channel(group.main_voice_id)
            team1 = guild.get_channel(group.team1_voice_id)
            team2 = guild.get_channel(group.team2_voice_id)
            text = guild.get_channel(group.text_id)
            if (
                isinstance(main, discord.VoiceChannel)
                and isinstance(team1, discord.VoiceChannel)
                and isinstance(team2, discord.VoiceChannel)
                and isinstance(text, discord.TextChannel)
            ):
                return [group.main_voice_id, group.team1_voice_id, group.team2_voice_id], group.text_id, "custom"

        return None, None, None

    async def _pin_generator_channels(self, guild: discord.Guild):
        generator_specs = [
            (DUO_GENERATOR_CHANNEL_ID, DUO_CATEGORY_ID),
            (FLEX_GENERATOR_CHANNEL_ID, FLEX_CATEGORY_ID),
            (CUSTOM_GENERATOR_CHANNEL_ID, CUSTOM_CATEGORY_ID),
        ]

        for channel_id, category_id in generator_specs:
            if not channel_id or not category_id:
                continue

            channel = guild.get_channel(channel_id)
            category = guild.get_channel(category_id)
            if not isinstance(channel, discord.VoiceChannel) or not isinstance(category, discord.CategoryChannel):
                continue

            try:
                await channel.move(category=category, beginning=True, offset=0, sync_permissions=False)
            except Exception as exc:
                logger.error("Failed to pin generator channel %s to top of category %s: %s", channel_id, category_id, exc)


bot = GLaDOSBot()


@bot.tree.command(name="glados_ping", description="Check if GLaDOS is online", guild=discord.Object(id=GUILD_ID))
async def glados_ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong: {round(bot.latency * 1000)}ms", ephemeral=True)


@bot.tree.command(name="glados_config", description="Show GLaDOS temp-channel config", guild=discord.Object(id=GUILD_ID))
async def glados_config(interaction: discord.Interaction):
    embed = discord.Embed(title="GLaDOS Config", color=discord.Color.blurple())
    embed.add_field(name="Guild", value=str(GUILD_ID), inline=False)
    embed.add_field(name="DUO category", value=str(DUO_CATEGORY_ID), inline=True)
    embed.add_field(name="FLEX category", value=str(FLEX_CATEGORY_ID), inline=True)
    embed.add_field(name="CUSTOM category", value=str(CUSTOM_CATEGORY_ID), inline=True)
    embed.add_field(name="DUO generator", value=str(DUO_GENERATOR_CHANNEL_ID), inline=True)
    embed.add_field(name="FLEX generator", value=str(FLEX_GENERATOR_CHANNEL_ID), inline=True)
    embed.add_field(name="CUSTOM generator", value=str(CUSTOM_GENERATOR_CHANNEL_ID), inline=True)
    embed.add_field(name="PostgreSQL", value="connected" if bot.db.healthcheck() else "not connected", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="lfg_profile",
    description="Show shared LFG profile/ranks from PostgreSQL",
    guild=discord.Object(id=GUILD_ID),
)
@app_commands.describe(user="User to inspect (default: you)")
async def lfg_profile(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    target = user or interaction.user

    if not bot.db.enabled():
        await interaction.response.send_message("DATABASE_URL is not configured.", ephemeral=True)
        return

    profile = bot.db.get_profile(target.id)
    if not profile:
        await interaction.response.send_message(f"No LFG profile found for {target.mention}.", ephemeral=True)
        return

    game_name = profile.get("riot_id_game_name") or "?"
    tagline = profile.get("riot_id_tagline") or "?"
    region = profile.get("region") or "?"
    solo_rank = profile.get("solo_rank") or "Unranked"
    flex_rank = profile.get("flex_rank") or "Unranked"

    embed = discord.Embed(title=f"LFG profile: {target.display_name}", color=discord.Color.green())
    embed.add_field(name="Riot ID", value=f"{game_name}#{tagline}", inline=False)
    embed.add_field(name="Region", value=region, inline=True)
    embed.add_field(name="Solo", value=solo_rank, inline=True)
    embed.add_field(name="Flex", value=flex_rank, inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="my_channel_panel",
    description="Re-send owner control panel to your temporary text channel",
    guild=discord.Object(id=GUILD_ID),
)
async def my_channel_panel(interaction: discord.Interaction):
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Guild context is required.", ephemeral=True)
        return

    voice_ids, text_id, kind = bot.get_owner_panel_target(interaction.guild, interaction.user.id)
    if not voice_ids or not text_id:
        await interaction.response.send_message("You do not own an active temporary channel.", ephemeral=True)
        return

    text_channel = interaction.guild.get_channel(text_id)
    if not isinstance(text_channel, discord.TextChannel):
        await interaction.response.send_message("Panel text channel is unavailable.", ephemeral=True)
        return

    panel = TempVoiceControlView(
        bot=bot,
        owner_id=interaction.user.id,
        voice_ids=voice_ids,
        text_id=text_id,
        kind=kind or "temp",
    )
    await text_channel.send(embed=build_owner_panel_embed(interaction.user), view=panel)
    await interaction.response.send_message(f"Panel sent in {text_channel.mention}.", ephemeral=True)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing in environment")

    if " " in DISCORD_TOKEN or len(DISCORD_TOKEN) < 50:
        raise RuntimeError(
            "DISCORD_TOKEN appears invalid. Use the raw bot token from Discord Developer Portal, without quotes and without 'Bot ' prefix."
        )

    bot.run(DISCORD_TOKEN)
