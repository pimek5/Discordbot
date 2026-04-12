import os
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Set

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


def env_int(name: str) -> Optional[int]:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid int for %s: %s", name, value)
        return None


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = env_int("GUILD_ID") or 1318383232785453076

DUO_CATEGORY_ID = env_int("DUO_CATEGORY_ID") or 1492683548329508904
FLEX_CATEGORY_ID = env_int("FLEX_CATEGORY_ID") or 1492683598325743856
CUSTOM_CATEGORY_ID = env_int("CUSTOM_CATEGORY_ID") or 1492683598325743856

DUO_GENERATOR_CHANNEL_ID = env_int("DUO_GENERATOR_CHANNEL_ID")
FLEX_GENERATOR_CHANNEL_ID = env_int("FLEX_GENERATOR_CHANNEL_ID")
CUSTOM_GENERATOR_CHANNEL_ID = env_int("CUSTOM_GENERATOR_CHANNEL_ID")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


@dataclass
class CustomGroup:
    owner_id: int
    category_id: int
    main_voice_id: int
    team1_voice_id: int
    team2_voice_id: int
    text_id: int


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

        super().__init__(command_prefix="!", intents=intents, help_command=None)

        self.db = SharedDatabase(DATABASE_URL)

        # Single temporary channels (duo/flex)
        self.simple_temp_channels: Set[int] = set()

        # Custom groups
        self.custom_groups: Dict[int, CustomGroup] = {}
        self.voice_to_group: Dict[int, int] = {}

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        logger.info("Slash commands synced to guild %s", GUILD_ID)

    async def on_ready(self):
        logger.info("Logged in as %s (%s)", self.user, self.user.id)
        logger.info("Connected to %d guild(s)", len(self.guilds))

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
            await self._cleanup_custom_group_if_empty(group_key)

        # Dynamic custom chat access: update for join / move
        if after.channel and after.channel.id in self.voice_to_group:
            group_key = self.voice_to_group[after.channel.id]
            await self._sync_member_custom_text_access(member, group_key)

        # Cleanup duo/flex temp channels
        if before.channel and before.channel.id in self.simple_temp_channels:
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Temporary channel empty")
                    self.simple_temp_channels.discard(before.channel.id)
                    logger.info("Deleted empty temporary channel %s", before.channel.id)
                except Exception as exc:
                    logger.error("Failed to delete temporary channel %s: %s", before.channel.id, exc)

    async def _create_and_move_simple(self, member: discord.Member, category_id: int, prefix: str):
        category = member.guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            logger.error("Category %s not found for %s", category_id, prefix)
            return

        channel_name = f"{prefix}-{member.display_name}"[:100]

        try:
            voice_channel = await member.guild.create_voice_channel(
                name=channel_name,
                category=category,
                reason=f"Temporary {prefix} channel for {member}",
            )
            self.simple_temp_channels.add(voice_channel.id)

            if member.voice and member.voice.channel:
                await member.move_to(voice_channel, reason="Move to temporary channel")

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
                reason=f"Custom temporary channels for {member}",
            )
            team1_voice = await member.guild.create_voice_channel(
                name=f"custom-{base_name}-team-1"[:100],
                category=category,
                overwrites=overwrites,
                reason=f"Custom temporary channels for {member}",
            )
            team2_voice = await member.guild.create_voice_channel(
                name=f"custom-{base_name}-team-2"[:100],
                category=category,
                overwrites=overwrites,
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
        group = self.custom_groups.pop(group_key, None)
        if not group:
            return
        self.voice_to_group.pop(group.main_voice_id, None)
        self.voice_to_group.pop(group.team1_voice_id, None)
        self.voice_to_group.pop(group.team2_voice_id, None)


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


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing in environment")

    bot.run(DISCORD_TOKEN)
