"""
HEXBET Configuration Commands
Interactive embed-based per-guild configuration for HEXBET.
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional

from LoLBets.core.engine.lolbets_config_database import get_hexbet_config_db

logger = logging.getLogger('lolbets_config')


def _st(on: bool) -> str:
    return "\u2705 Enabled" if on else "\u274c Disabled"


# -- MAIN PANEL ---------------------------------------------------------------

class HexbetMainView(discord.ui.View):
    """Root HEXBET config panel."""

    def __init__(self, guild_id: int, config_db, guild: discord.Guild):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.db = config_db
        self.guild = guild

    def _cfg(self):
        return self.db.get_guild_config(self.guild_id) or {}

    def build_embed(self) -> discord.Embed:
        c = self._cfg()
        e = discord.Embed(
            title="\u2699\ufe0f HEXBET \u2014 Server Configuration",
            description="Configure HEXBET channels, notifications, and webhooks.\nAll changes take effect immediately.",
            color=0xF1C40F,
        )
        bet_ch = f"<#{c['bet_channel_id']}>" if c.get('bet_channel_id') else "Not set"
        lb_ch = f"<#{c['leaderboard_channel_id']}>" if c.get('leaderboard_channel_id') else "Not set"
        logs_ch = f"<#{c['bet_logs_channel_id']}>" if c.get('bet_logs_channel_id') else "Not set"

        e.add_field(name="\U0001f3b2 Bet Channel", value=bet_ch, inline=True)
        e.add_field(name="\U0001f3c6 Leaderboard Channel", value=lb_ch, inline=True)
        e.add_field(name="\U0001f4cb Logs Channel", value=logs_ch, inline=True)

        notify_new = _st(c.get('notify_new_bets', True))
        notify_res = _st(c.get('notify_bet_results', True))
        notify_lb = _st(c.get('notify_leaderboard_updates', False))
        e.add_field(name="\U0001f514 Notifications",
                     value=f"New Bets: {notify_new}\nResults: {notify_res}\nLeaderboard: {notify_lb}",
                     inline=False)

        wh_status = _st(c.get('webhook_enabled', False))
        webhooks = self.db.get_guild_webhooks(self.guild_id)
        wh_count = len(webhooks)
        e.add_field(name="\U0001fa9d Webhooks",
                     value=f"{wh_status} \u00b7 {wh_count} endpoint(s)",
                     inline=False)

        e.set_footer(text="Admin only \u2022 Changes are per-server")
        return e

    # row 0 -- channels
    @discord.ui.button(label="\U0001f3b2 Channels", style=discord.ButtonStyle.primary, row=0)
    async def btn_channels(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = HexbetChannelsView(self.guild_id, self.db, self.guild)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)

    @discord.ui.button(label="\U0001f514 Notifications", style=discord.ButtonStyle.primary, row=0)
    async def btn_notifs(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = HexbetNotificationsView(self.guild_id, self.db, self.guild)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)

    @discord.ui.button(label="\U0001fa9d Webhooks", style=discord.ButtonStyle.primary, row=0)
    async def btn_webhooks(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = HexbetWebhooksView(self.guild_id, self.db, self.guild)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)

    @discord.ui.button(label="\U0001f195 Quick Setup", style=discord.ButtonStyle.success, row=1)
    async def btn_quick(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = HexbetQuickSetupView(self.guild_id, self.db, self.guild)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)


# -- SUB VIEWS ----------------------------------------------------------------

class _HexSub(discord.ui.View):
    def __init__(self, guild_id: int, config_db, guild: discord.Guild):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.db = config_db
        self.guild = guild

    def _cfg(self):
        return self.db.get_guild_config(self.guild_id) or {}

    def _ensure(self):
        if not self.db.get_guild_config(self.guild_id):
            self.db.set_guild_config(self.guild_id)

    @discord.ui.button(label="\u25c0\ufe0f Back", style=discord.ButtonStyle.secondary, row=4)
    async def btn_back(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = HexbetMainView(self.guild_id, self.db, self.guild)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)


class HexbetChannelsView(_HexSub):
    def build_embed(self) -> discord.Embed:
        c = self._cfg()
        e = discord.Embed(title="\U0001f3b2 HEXBET Channels", color=0xF1C40F,
                          description="Set channels for betting features.\nClick a button and enter a channel ID, or use Quick Setup to auto-create.")
        for label, key in [("\U0001f3b2 Bet Channel", "bet_channel_id"),
                           ("\U0001f3c6 Leaderboard", "leaderboard_channel_id"),
                           ("\U0001f4cb Logs", "bet_logs_channel_id")]:
            ch = c.get(key)
            e.add_field(name=label, value=f"<#{ch}>" if ch else "Not set", inline=True)
        return e

    @discord.ui.button(label="Set Bet Channel", style=discord.ButtonStyle.primary, row=0)
    async def set_bet(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(HexChannelModal(self.guild_id, 'bet_channel_id', self.db, self))

    @discord.ui.button(label="Set Leaderboard Channel", style=discord.ButtonStyle.primary, row=0)
    async def set_lb(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(HexChannelModal(self.guild_id, 'leaderboard_channel_id', self.db, self))

    @discord.ui.button(label="Set Logs Channel", style=discord.ButtonStyle.primary, row=1)
    async def set_logs(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(HexChannelModal(self.guild_id, 'bet_logs_channel_id', self.db, self))


class HexbetNotificationsView(_HexSub):
    def build_embed(self) -> discord.Embed:
        c = self._cfg()
        e = discord.Embed(title="\U0001f514 HEXBET Notifications", color=0x3498DB,
                          description="Toggle notification types for this server.")
        e.add_field(name="New Bets", value=_st(c.get('notify_new_bets', True)), inline=True)
        e.add_field(name="Bet Results", value=_st(c.get('notify_bet_results', True)), inline=True)
        e.add_field(name="Leaderboard Updates", value=_st(c.get('notify_leaderboard_updates', False)), inline=True)
        e.add_field(name="Webhooks", value=_st(c.get('webhook_enabled', False)), inline=True)
        return e

    @discord.ui.button(label="Toggle New Bets", style=discord.ButtonStyle.primary, row=0)
    async def t_new(self, interaction: discord.Interaction, btn: discord.ui.Button):
        self._ensure()
        c = self._cfg()
        self.db.set_guild_config(self.guild_id, notify_new_bets=not c.get('notify_new_bets', True))
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Toggle Results", style=discord.ButtonStyle.primary, row=0)
    async def t_res(self, interaction: discord.Interaction, btn: discord.ui.Button):
        self._ensure()
        c = self._cfg()
        self.db.set_guild_config(self.guild_id, notify_bet_results=not c.get('notify_bet_results', True))
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Toggle Leaderboard", style=discord.ButtonStyle.primary, row=1)
    async def t_lb(self, interaction: discord.Interaction, btn: discord.ui.Button):
        self._ensure()
        c = self._cfg()
        self.db.set_guild_config(self.guild_id, notify_leaderboard_updates=not c.get('notify_leaderboard_updates', False))
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Toggle Webhooks", style=discord.ButtonStyle.secondary, row=1)
    async def t_wh(self, interaction: discord.Interaction, btn: discord.ui.Button):
        self._ensure()
        c = self._cfg()
        self.db.set_guild_config(self.guild_id, webhook_enabled=not c.get('webhook_enabled', False))
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class HexbetWebhooksView(_HexSub):
    def build_embed(self) -> discord.Embed:
        webhooks = self.db.get_guild_webhooks(self.guild_id)
        e = discord.Embed(title="\U0001fa9d HEXBET Webhooks", color=0x9B59B6,
                          description="Manage webhook endpoints for external integrations.")
        if webhooks:
            for wh in webhooks[:10]:
                masked = wh['webhook_url'][:30] + "..." if len(wh['webhook_url']) > 30 else wh['webhook_url']
                notifs = []
                if wh.get('notify_new_bets'):
                    notifs.append("\U0001f195 New Bets")
                if wh.get('notify_bet_results'):
                    notifs.append("\u2705 Results")
                if wh.get('notify_leaderboard'):
                    notifs.append("\U0001f3c6 LB")
                notif_text = ", ".join(notifs) if notifs else "None"
                e.add_field(name=f"Webhook #{wh['id']}",
                            value=f"`{masked}`\n{notif_text}", inline=False)
        else:
            e.add_field(name="No Webhooks", value="Use the buttons below to add one.", inline=False)
        return e

    @discord.ui.button(label="Add Webhook", style=discord.ButtonStyle.success, row=0)
    async def add_wh(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(WebhookAddModal(self.guild_id, self.db, self))

    @discord.ui.button(label="Remove Webhook", style=discord.ButtonStyle.danger, row=0)
    async def rm_wh(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(WebhookRemoveModal(self.guild_id, self.db, self))


class HexbetQuickSetupView(_HexSub):
    def build_embed(self) -> discord.Embed:
        c = self._cfg()
        e = discord.Embed(title="\U0001f195 HEXBET Quick Setup", color=0x2ECC71,
                          description="Auto-create channels for HEXBET.\n"
                                      "Clicking a button will create the channel and save it.")
        for label, key in [("\U0001f3b2 Bet Channel", "bet_channel_id"),
                           ("\U0001f3c6 Leaderboard", "leaderboard_channel_id"),
                           ("\U0001f4cb Logs", "bet_logs_channel_id")]:
            ch = c.get(key)
            e.add_field(name=label, value=f"<#{ch}> \u2705" if ch else "\u274c Not created", inline=True)
        return e

    @discord.ui.button(label="Create Bet Channel", style=discord.ButtonStyle.primary, row=0)
    async def create_bet(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await self._create_channel(interaction, "betting", "\U0001f3ae HEXBET - Place your bets!", "bet_channel_id")

    @discord.ui.button(label="Create Leaderboard", style=discord.ButtonStyle.primary, row=0)
    async def create_lb(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await self._create_channel(interaction, "leaderboard", "\U0001f3c6 HEXBET - Leaderboard", "leaderboard_channel_id")

    @discord.ui.button(label="Create Logs", style=discord.ButtonStyle.primary, row=1)
    async def create_logs(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await self._create_channel(interaction, "bet-logs", "\U0001f4cb HEXBET - Bet logs", "bet_logs_channel_id")

    async def _create_channel(self, interaction: discord.Interaction, name: str, topic: str, key: str):
        await interaction.response.defer(ephemeral=True)
        try:
            self._ensure()
            channel = await interaction.guild.create_text_channel(name=name, topic=topic, reason="HEXBET Quick Setup")
            kwargs = {key: channel.id}
            self.db.set_guild_config(self.guild_id, **kwargs)
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=self.build_embed(),
                view=self,
            )
        except discord.Forbidden:
            await interaction.followup.send("\u274c Missing **Manage Channels** permission.", ephemeral=True)
        except Exception as ex:
            logger.error("quick setup %s: %s", key, ex)
            await interaction.followup.send(f"\u274c Error: {ex}", ephemeral=True)


# -- MODALS --------------------------------------------------------------------

class HexChannelModal(discord.ui.Modal, title="Set Channel"):
    channel_input = discord.ui.TextInput(
        label="Channel ID",
        placeholder="e.g. 123456789012345678",
        max_length=30,
    )

    def __init__(self, guild_id: int, key: str, config_db, parent_view):
        super().__init__()
        self.guild_id = guild_id
        self.key = key
        self.db = config_db
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.channel_input.value.strip().replace('<#', '').replace('>', '')
        if not raw.isdigit():
            await interaction.response.send_message("\u274c Invalid channel ID.", ephemeral=True)
            return
        if not self.db.get_guild_config(self.guild_id):
            self.db.set_guild_config(self.guild_id)
        kwargs = {self.key: int(raw)}
        self.db.set_guild_config(self.guild_id, **kwargs)
        await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)


class WebhookAddModal(discord.ui.Modal, title="Add Webhook"):
    url_input = discord.ui.TextInput(
        label="Webhook URL",
        placeholder="https://...",
        max_length=500,
    )

    def __init__(self, guild_id: int, config_db, parent_view):
        super().__init__()
        self.guild_id = guild_id
        self.db = config_db
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        url = self.url_input.value.strip()
        if not (url.startswith('http://') or url.startswith('https://')):
            await interaction.response.send_message("\u274c URL must start with http:// or https://", ephemeral=True)
            return
        try:
            if not self.db.get_guild_config(self.guild_id):
                self.db.set_guild_config(self.guild_id)
            self.db.add_webhook(self.guild_id, url)
            await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)
        except Exception as ex:
            logger.error("add webhook: %s", ex)
            await interaction.response.send_message(f"\u274c Error: {ex}", ephemeral=True)


class WebhookRemoveModal(discord.ui.Modal, title="Remove Webhook"):
    id_input = discord.ui.TextInput(
        label="Webhook ID (from list above)",
        placeholder="e.g. 1",
        max_length=10,
    )

    def __init__(self, guild_id: int, config_db, parent_view):
        super().__init__()
        self.guild_id = guild_id
        self.db = config_db
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.id_input.value.strip()
        if not raw.isdigit():
            await interaction.response.send_message("\u274c Must be a number.", ephemeral=True)
            return
        success = self.db.remove_webhook(int(raw), self.guild_id)
        if success:
            await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)
        else:
            await interaction.response.send_message("\u274c Webhook not found.", ephemeral=True)


# -- COG + SETUP ---------------------------------------------------------------

class HexbetConfig(commands.Cog):
    """HEXBET configuration commands"""

    config_group = app_commands.Group(name="lbconfig", description="Configure LoLBets for this server")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_db = get_hexbet_config_db()

    @config_group.command(name="setup", description="Interactive setup for HEXBET channels and settings")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_config(self, interaction: discord.Interaction):
        view = HexbetMainView(interaction.guild_id, self.config_db, interaction.guild)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    @config_group.command(name="view", description="View current HEXBET configuration")
    async def view_config(self, interaction: discord.Interaction):
        config = self.config_db.get_guild_config(interaction.guild_id)
        if not config:
            await interaction.response.send_message(
                "❌ LoLBets is not configured yet. Use `/lbconfig setup` to get started.",
                ephemeral=True,
            )
            return
        view = HexbetMainView(interaction.guild_id, self.config_db, interaction.guild)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HexbetConfig(bot))