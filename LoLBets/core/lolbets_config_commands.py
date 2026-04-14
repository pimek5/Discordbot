import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from LoLBets.core.engine.lolbets_config_database import get_lolbets_config_db

logger = logging.getLogger("lolbets_config")


class LoLBetsConfig(commands.Cog):
    config_group = app_commands.Group(name="lbconfig", description="Configure LoLBets for this server")
    streamer_group = app_commands.Group(name="lbstreamer", description="Manage server streamer betting targets")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_db = get_lolbets_config_db()

    @config_group.command(name="setup", description="Set core LoLBets channels for this server")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_config(
        self,
        interaction: discord.Interaction,
        bet_channel: Optional[discord.TextChannel] = None,
        leaderboard_channel: Optional[discord.TextChannel] = None,
        logs_channel: Optional[discord.TextChannel] = None,
    ):
        self.config_db.set_guild_config(
            interaction.guild_id,
            bet_channel_id=bet_channel.id if bet_channel else None,
            leaderboard_channel_id=leaderboard_channel.id if leaderboard_channel else None,
            bet_logs_channel_id=logs_channel.id if logs_channel else None,
        )

        embed = self._build_config_embed(interaction.guild_id, interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="view", description="View current LoLBets server configuration")
    async def view_config(self, interaction: discord.Interaction):
        embed = self._build_config_embed(interaction.guild_id, interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @config_group.command(name="branding", description="Set visible brand name for this server's LoLBets instance")
    @app_commands.checks.has_permissions(administrator=True)
    async def branding(self, interaction: discord.Interaction, brand_name: str):
        self.config_db.set_guild_config(interaction.guild_id, brand_name=brand_name[:80])
        embed = self._build_config_embed(interaction.guild_id, interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @streamer_group.command(name="add", description="Add a streamer/player target for this server's custom bets")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def add_streamer(
        self,
        interaction: discord.Interaction,
        display_name: str,
        riot_id: Optional[str] = None,
        platform: Optional[str] = None,
    ):
        self.config_db.upsert_streamer(
            interaction.guild_id,
            display_name=display_name,
            riot_id=riot_id,
            platform_route=platform,
            created_by=interaction.user.id,
        )
        await interaction.response.send_message(
            f"Added streamer target **{display_name}** for this server.",
            ephemeral=True,
        )

    @streamer_group.command(name="list", description="List streamer betting targets configured for this server")
    async def list_streamers(self, interaction: discord.Interaction):
        streamers = self.config_db.get_streamers(interaction.guild_id)
        embed = discord.Embed(
            title="LoLBets Streamer Targets",
            color=0x2ECC71,
        )
        if not streamers:
            embed.description = "No streamer targets configured yet."
        else:
            lines = []
            for streamer in streamers[:25]:
                riot = streamer.get("riot_id") or "No Riot ID"
                platform = streamer.get("platform_route") or "No platform"
                lines.append(f"• **{streamer['display_name']}** — {riot} — `{platform}`")
            embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _build_config_embed(self, guild_id: int, guild: Optional[discord.Guild]) -> discord.Embed:
        config = self.config_db.get_guild_config(guild_id) or {}
        guild_name = guild.name if guild else str(guild_id)
        brand_name = config.get("brand_name") or "LoLBets"
        embed = discord.Embed(
            title=f"{brand_name} Configuration",
            description=f"Server: **{guild_name}**",
            color=0x3498DB,
        )
        embed.add_field(
            name="Bet Channel",
            value=f"<#{config['bet_channel_id']}>" if config.get("bet_channel_id") else "Not set",
            inline=True,
        )
        embed.add_field(
            name="Leaderboard",
            value=f"<#{config['leaderboard_channel_id']}>" if config.get("leaderboard_channel_id") else "Not set",
            inline=True,
        )
        embed.add_field(
            name="Logs",
            value=f"<#{config['bet_logs_channel_id']}>" if config.get("bet_logs_channel_id") else "Not set",
            inline=True,
        )
        embed.add_field(
            name="Streamer Markets",
            value="Enabled" if config.get("allow_streamer_markets", True) else "Disabled",
            inline=True,
        )
        embed.add_field(
            name="Notifications",
            value=(
                f"New bets: {'on' if config.get('notify_new_bets', True) else 'off'}\n"
                f"Results: {'on' if config.get('notify_bet_results', True) else 'off'}\n"
                f"Leaderboard: {'on' if config.get('notify_leaderboard_updates', False) else 'off'}"
            ),
            inline=False,
        )
        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(LoLBetsConfig(bot))
