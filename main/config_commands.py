"""
Configuration System -- Main Bot (Kassalytics)
Interactive embed panels per guild.
Admin-only.  All state is stored in the guild_settings key-value table.
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
from database import get_db

logger = logging.getLogger('config_commands')

# -- helpers ----------------------------------------------------------------
_TRUE = 'true'
_FALSE = 'false'


def _bool(val, default=True) -> bool:
    if val is None:
        return default
    return val != _FALSE


def _get(guild_id: int, key: str):
    try:
        db = get_db()
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT value FROM guild_settings WHERE guild_id = %s AND key = %s",
            (guild_id, key),
        )
        row = cur.fetchone()
        db.return_connection(conn)
        return row[0] if row else None
    except Exception as e:
        logger.error("config _get %s: %s", key, e)
        return None


def _set(guild_id: int, key: str, value):
    try:
        db = get_db()
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO guild_settings (guild_id, key, value)
               VALUES (%s, %s, %s)
               ON CONFLICT (guild_id, key)
               DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()""",
            (guild_id, key, str(value)),
        )
        conn.commit()
        db.return_connection(conn)
    except Exception as e:
        logger.error("config _set %s: %s", key, e)


def _toggle(guild_id: int, key: str, default=True) -> bool:
    current = _bool(_get(guild_id, key), default)
    new = not current
    _set(guild_id, key, _TRUE if new else _FALSE)
    return new


def _st(on: bool) -> str:
    return "\u2705 Enabled" if on else "\u274c Disabled"


# -- MAIN PANEL -------------------------------------------------------------

class ConfigMainView(discord.ui.View):
    """Root config panel -- category buttons."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id

    def build_embed(self) -> discord.Embed:
        g = self.guild_id
        e = discord.Embed(
            title="\u2699\ufe0f Kassalytics \u2014 Server Configuration",
            description="Select a category to configure.\nAll changes take effect immediately.",
            color=0x5865F2,
        )
        e.add_field(name="\U0001f464 Profiles & Stats",
                     value=_st(_bool(_get(g, 'profiles_enabled'))), inline=True)
        e.add_field(name="\U0001f3c6 Leaderboards",
                     value=_st(_bool(_get(g, 'leaderboards_enabled'))), inline=True)
        e.add_field(name="\U0001f5f3\ufe0f Voting",
                     value=_st(_bool(_get(g, 'voting_enabled'))), inline=True)
        e.add_field(name="\U0001f3ae LoLdle",
                     value=_st(_bool(_get(g, 'loldle_enabled'))), inline=True)
        e.add_field(name="\U0001f4ca Tracker",
                     value=_st(_bool(_get(g, 'tracker_enabled'))), inline=True)
        e.add_field(name="\U0001f3a8 Creator",
                     value=_st(_bool(_get(g, 'creator_enabled'))), inline=True)
        e.add_field(name="\U0001f6e0\ufe0f Moderation",
                     value=f"Slowmode: {_st(_bool(_get(g, 'auto_slowmode_enabled')))}\nBans: {_st(_bool(_get(g, 'ban_system_enabled')))}",
                     inline=True)
        e.add_field(name="\U0001f4e2 Channels",
                     value="Tracker / LB / LoLdle / Allowed",
                     inline=True)
        e.set_footer(text="Admin only \u2022 Changes are per-server")
        return e

    @discord.ui.button(label="\U0001f464 Profiles & Stats", style=discord.ButtonStyle.primary, row=0)
    async def btn_profiles(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = ProfilesView(self.guild_id)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)

    @discord.ui.button(label="\U0001f3c6 Leaderboards", style=discord.ButtonStyle.primary, row=0)
    async def btn_lb(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = LeaderboardsView(self.guild_id)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)

    @discord.ui.button(label="\U0001f5f3\ufe0f Voting", style=discord.ButtonStyle.primary, row=0)
    async def btn_vote(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = VotingView(self.guild_id)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)

    @discord.ui.button(label="\U0001f3ae LoLdle", style=discord.ButtonStyle.success, row=1)
    async def btn_loldle(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = LoldleView(self.guild_id)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)

    @discord.ui.button(label="\U0001f4ca Tracker", style=discord.ButtonStyle.success, row=1)
    async def btn_tracker(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = TrackerView(self.guild_id)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)

    @discord.ui.button(label="\U0001f3a8 Creator", style=discord.ButtonStyle.success, row=1)
    async def btn_creator(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = CreatorView(self.guild_id)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)

    @discord.ui.button(label="\U0001f6e0\ufe0f Moderation", style=discord.ButtonStyle.secondary, row=2)
    async def btn_mod(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = ModerationView(self.guild_id)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)

    @discord.ui.button(label="\U0001f4e2 Channels", style=discord.ButtonStyle.secondary, row=2)
    async def btn_channels(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = ChannelsView(self.guild_id)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)


# -- SUB-PANELS -------------------------------------------------------------

class _SubView(discord.ui.View):
    """Base with Back button."""
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id

    @discord.ui.button(label="\u25c0\ufe0f Back", style=discord.ButtonStyle.secondary, row=4)
    async def btn_back(self, interaction: discord.Interaction, btn: discord.ui.Button):
        v = ConfigMainView(self.guild_id)
        await interaction.response.edit_message(embed=v.build_embed(), view=v)


class ProfilesView(_SubView):
    def build_embed(self) -> discord.Embed:
        g = self.guild_id
        e = discord.Embed(title="\U0001f464 Profiles & Stats", color=0x5865F2,
                          description="Toggle profile-related features.")
        e.add_field(name="Profile Commands", value=_st(_bool(_get(g, 'profiles_enabled'))), inline=True)
        e.add_field(name="Stats Commands", value=_st(_bool(_get(g, 'stats_enabled'))), inline=True)
        e.add_field(name="Verification Required", value=_st(_bool(_get(g, 'verification_required'), False)), inline=True)
        e.add_field(name="Affected Commands",
                     value="`/profile` `/stats` `/link` `/autolink` `/verifyacc` `/unlink` `/lp` `/matches` `/decay`",
                     inline=False)
        return e

    @discord.ui.button(label="Toggle Profiles", style=discord.ButtonStyle.primary, row=0)
    async def toggle_profiles(self, interaction: discord.Interaction, btn: discord.ui.Button):
        _toggle(self.guild_id, 'profiles_enabled')
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Toggle Stats", style=discord.ButtonStyle.primary, row=0)
    async def toggle_stats(self, interaction: discord.Interaction, btn: discord.ui.Button):
        _toggle(self.guild_id, 'stats_enabled')
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Toggle Verification", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_verify(self, interaction: discord.Interaction, btn: discord.ui.Button):
        _toggle(self.guild_id, 'verification_required', False)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class LeaderboardsView(_SubView):
    def build_embed(self) -> discord.Embed:
        g = self.guild_id
        e = discord.Embed(title="\U0001f3c6 Leaderboards", color=0xFFD700,
                          description="Configure leaderboard displays and auto-posting.")
        e.add_field(name="Leaderboards", value=_st(_bool(_get(g, 'leaderboards_enabled'))), inline=True)
        e.add_field(name="Auto-Post Daily", value=_st(_bool(_get(g, 'leaderboard_auto_post'), False)), inline=True)
        ch = _get(g, 'leaderboard_channel')
        e.add_field(name="Channel", value=f"<#{ch}>" if ch else "Not set", inline=True)
        e.add_field(name="Affected Commands",
                     value="`/leaderboard` `/globalleaderboard` `/top`", inline=False)
        return e

    @discord.ui.button(label="Toggle Leaderboards", style=discord.ButtonStyle.primary, row=0)
    async def toggle_lb(self, interaction: discord.Interaction, btn: discord.ui.Button):
        _toggle(self.guild_id, 'leaderboards_enabled')
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Toggle Auto-Post", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_auto(self, interaction: discord.Interaction, btn: discord.ui.Button):
        _toggle(self.guild_id, 'leaderboard_auto_post', False)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Set Leaderboard Channel", style=discord.ButtonStyle.success, row=1)
    async def set_channel(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(ChannelModal(self.guild_id, 'leaderboard_channel', self))


class VotingView(_SubView):
    def build_embed(self) -> discord.Embed:
        g = self.guild_id
        e = discord.Embed(title="\U0001f5f3\ufe0f Voting System", color=0xE74C3C,
                          description="Toggle champion voting features.")
        e.add_field(name="Voting", value=_st(_bool(_get(g, 'voting_enabled'))), inline=True)
        e.add_field(name="Affected Commands",
                     value="`/vote` `/endvote` `/votestatus`", inline=False)
        return e

    @discord.ui.button(label="Toggle Voting", style=discord.ButtonStyle.primary, row=0)
    async def toggle(self, interaction: discord.Interaction, btn: discord.ui.Button):
        _toggle(self.guild_id, 'voting_enabled')
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class LoldleView(_SubView):
    def build_embed(self) -> discord.Embed:
        g = self.guild_id
        e = discord.Embed(title="\U0001f3ae LoLdle Game", color=0x3498DB,
                          description="Configure daily LoL guessing game.")
        e.add_field(name="LoLdle", value=_st(_bool(_get(g, 'loldle_enabled'))), inline=True)
        ch = _get(g, 'loldle_channel')
        e.add_field(name="Channel", value=f"<#{ch}>" if ch else "Not set", inline=True)
        e.add_field(name="Modes", value="Classic \u00b7 Quote \u00b7 Emoji \u00b7 Ability \u00b7 Splash", inline=False)
        return e

    @discord.ui.button(label="Toggle LoLdle", style=discord.ButtonStyle.primary, row=0)
    async def toggle(self, interaction: discord.Interaction, btn: discord.ui.Button):
        _toggle(self.guild_id, 'loldle_enabled')
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Set LoLdle Channel", style=discord.ButtonStyle.success, row=0)
    async def set_ch(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(ChannelModal(self.guild_id, 'loldle_channel', self))


class TrackerView(_SubView):
    def build_embed(self) -> discord.Embed:
        g = self.guild_id
        e = discord.Embed(title="\U0001f4ca Tracker Bot", color=0x1ABC9C,
                          description="Configure pro player tracking and betting.")
        e.add_field(name="Tracker", value=_st(_bool(_get(g, 'tracker_enabled'))), inline=True)
        e.add_field(name="Betting", value=_st(_bool(_get(g, 'tracker_betting_enabled'))), inline=True)
        e.add_field(name="Auto-Monitoring", value=_st(_bool(_get(g, 'tracker_auto_monitoring'))), inline=True)
        ch = _get(g, 'tracker_channel')
        e.add_field(name="Tracker Channel", value=f"<#{ch}>" if ch else "Not set", inline=True)
        e.add_field(name="Affected Commands",
                     value="`/track` `/trackpros` `/playerinfo` `/players` `/bet` `/balance` `/betleaderboard`",
                     inline=False)
        return e

    @discord.ui.button(label="Toggle Tracker", style=discord.ButtonStyle.primary, row=0)
    async def toggle_tracker(self, interaction: discord.Interaction, btn: discord.ui.Button):
        _toggle(self.guild_id, 'tracker_enabled')
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Toggle Betting", style=discord.ButtonStyle.primary, row=0)
    async def toggle_betting(self, interaction: discord.Interaction, btn: discord.ui.Button):
        _toggle(self.guild_id, 'tracker_betting_enabled')
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Toggle Auto-Monitor", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_monitor(self, interaction: discord.Interaction, btn: discord.ui.Button):
        _toggle(self.guild_id, 'tracker_auto_monitoring')
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Set Tracker Channel", style=discord.ButtonStyle.success, row=1)
    async def set_ch(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(ChannelModal(self.guild_id, 'tracker_channel', self))


class CreatorView(_SubView):
    def build_embed(self) -> discord.Embed:
        g = self.guild_id
        e = discord.Embed(title="\U0001f3a8 Creator Bot", color=0x9B59B6,
                          description="Configure content creation tools.")
        e.add_field(name="Creator", value=_st(_bool(_get(g, 'creator_enabled'))), inline=True)
        e.add_field(name="Features", value="Video editing, thumbnails, media processing", inline=False)
        return e

    @discord.ui.button(label="Toggle Creator", style=discord.ButtonStyle.primary, row=0)
    async def toggle(self, interaction: discord.Interaction, btn: discord.ui.Button):
        _toggle(self.guild_id, 'creator_enabled')
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class ModerationView(_SubView):
    def build_embed(self) -> discord.Embed:
        g = self.guild_id
        e = discord.Embed(title="\U0001f6e0\ufe0f Moderation", color=0xE67E22,
                          description="Configure auto-mod features.")
        e.add_field(name="Auto-Slowmode", value=_st(_bool(_get(g, 'auto_slowmode_enabled'))), inline=True)
        e.add_field(name="Ban System", value=_st(_bool(_get(g, 'ban_system_enabled'))), inline=True)
        threshold = _get(g, 'slowmode_threshold') or '10'
        delay = _get(g, 'slowmode_delay') or '5'
        e.add_field(name="Slowmode Settings",
                     value=f"Threshold: **{threshold}** msg/10s\nDelay: **{delay}**s",
                     inline=False)
        e.add_field(name="Affected Commands",
                     value="`/ban` `/unban` `/kick` `/mute` `/unmute` `/clear` `/lock` `/unlock`",
                     inline=False)
        return e

    @discord.ui.button(label="Toggle Auto-Slowmode", style=discord.ButtonStyle.primary, row=0)
    async def toggle_sm(self, interaction: discord.Interaction, btn: discord.ui.Button):
        _toggle(self.guild_id, 'auto_slowmode_enabled')
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Toggle Ban System", style=discord.ButtonStyle.primary, row=0)
    async def toggle_ban(self, interaction: discord.Interaction, btn: discord.ui.Button):
        _toggle(self.guild_id, 'ban_system_enabled')
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Set Slowmode Threshold", style=discord.ButtonStyle.secondary, row=1)
    async def set_thresh(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(NumberModal(self.guild_id, 'slowmode_threshold', 'Slowmode Threshold (msg/10s)', self))

    @discord.ui.button(label="Set Slowmode Delay", style=discord.ButtonStyle.secondary, row=1)
    async def set_delay(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(NumberModal(self.guild_id, 'slowmode_delay', 'Slowmode Delay (seconds)', self))


class ChannelsView(_SubView):
    def build_embed(self) -> discord.Embed:
        g = self.guild_id
        e = discord.Embed(title="\U0001f4e2 Channel Configuration", color=0x95A5A6,
                          description="Set designated channels for each feature.\nClick a button and enter a channel ID.")
        for label, key in [("Tracker", "tracker_channel"),
                           ("Leaderboard", "leaderboard_channel"),
                           ("LoLdle", "loldle_channel")]:
            ch = _get(g, key)
            e.add_field(name=label, value=f"<#{ch}>" if ch else "Not set", inline=True)
        try:
            db = get_db()
            allowed = db.get_allowed_channels(g)
            if allowed:
                mentions = " ".join(f"<#{c}>" for c in allowed[:10])
                extra = f" (+{len(allowed)-10} more)" if len(allowed) > 10 else ""
                e.add_field(name="\U0001f512 Allowed Bot Channels", value=mentions + extra, inline=False)
            else:
                e.add_field(name="\U0001f512 Allowed Bot Channels", value="All channels (no restriction)", inline=False)
        except Exception:
            e.add_field(name="\U0001f512 Allowed Bot Channels", value="All channels (no restriction)", inline=False)
        return e

    @discord.ui.button(label="Set Tracker Channel", style=discord.ButtonStyle.primary, row=0)
    async def set_tracker(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(ChannelModal(self.guild_id, 'tracker_channel', self))

    @discord.ui.button(label="Set Leaderboard Channel", style=discord.ButtonStyle.primary, row=0)
    async def set_lb(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(ChannelModal(self.guild_id, 'leaderboard_channel', self))

    @discord.ui.button(label="Set LoLdle Channel", style=discord.ButtonStyle.primary, row=1)
    async def set_loldle(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(ChannelModal(self.guild_id, 'loldle_channel', self))

    @discord.ui.button(label="Add Allowed Channel", style=discord.ButtonStyle.success, row=1)
    async def add_allowed(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(AllowedChannelModal(self.guild_id, 'add', self))

    @discord.ui.button(label="Remove Allowed Channel", style=discord.ButtonStyle.danger, row=2)
    async def rm_allowed(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(AllowedChannelModal(self.guild_id, 'remove', self))

    @discord.ui.button(label="Reset (Allow All)", style=discord.ButtonStyle.danger, row=2)
    async def reset_allowed(self, interaction: discord.Interaction, btn: discord.ui.Button):
        try:
            db = get_db()
            conn = db.get_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM allowed_channels WHERE guild_id = %s", (self.guild_id,))
            conn.commit()
            db.return_connection(conn)
        except Exception as ex:
            logger.error("reset allowed channels: %s", ex)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


# -- MODALS ------------------------------------------------------------------

class ChannelModal(discord.ui.Modal, title="Set Channel"):
    channel_input = discord.ui.TextInput(
        label="Channel ID or #mention",
        placeholder="e.g. 123456789012345678",
        max_length=30,
    )

    def __init__(self, guild_id: int, key: str, parent_view: _SubView):
        super().__init__()
        self.guild_id = guild_id
        self.key = key
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.channel_input.value.strip().replace('<#', '').replace('>', '')
        if not raw.isdigit():
            await interaction.response.send_message("\u274c Invalid channel ID.", ephemeral=True)
            return
        _set(self.guild_id, self.key, raw)
        await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)


class NumberModal(discord.ui.Modal, title="Set Value"):
    num_input = discord.ui.TextInput(
        label="Value",
        placeholder="Enter a number",
        max_length=10,
    )

    def __init__(self, guild_id: int, key: str, label: str, parent_view: _SubView):
        super().__init__(title=label)
        self.guild_id = guild_id
        self.key = key
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.num_input.value.strip()
        if not raw.isdigit():
            await interaction.response.send_message("\u274c Must be a number.", ephemeral=True)
            return
        _set(self.guild_id, self.key, raw)
        await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)


class AllowedChannelModal(discord.ui.Modal, title="Allowed Channel"):
    channel_input = discord.ui.TextInput(
        label="Channel ID",
        placeholder="e.g. 123456789012345678",
        max_length=30,
    )

    def __init__(self, guild_id: int, action: str, parent_view: _SubView):
        super().__init__(title=f"{'Add' if action == 'add' else 'Remove'} Allowed Channel")
        self.guild_id = guild_id
        self.action = action
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.channel_input.value.strip().replace('<#', '').replace('>', '')
        if not raw.isdigit():
            await interaction.response.send_message("\u274c Invalid channel ID.", ephemeral=True)
            return
        db = get_db()
        cid = int(raw)
        if self.action == 'add':
            db.add_allowed_channel(self.guild_id, cid)
        else:
            db.remove_allowed_channel(self.guild_id, cid)
        await interaction.response.edit_message(embed=self.parent_view.build_embed(), view=self.parent_view)


# -- SETUP -------------------------------------------------------------------

async def setup(bot: commands.Bot):
    @bot.tree.command(name="config", description="\u2699\ufe0f Configure bot features for your server")
    @app_commands.checks.has_permissions(administrator=True)
    async def config(interaction: discord.Interaction):
        view = ConfigMainView(interaction.guild_id)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    logger.info("\u2705 Configuration commands loaded")