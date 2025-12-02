"""
LFG Commands Module
===================
Discord commands for the LFG (Looking For Group) system.
Includes interactive profile setup and listing creation with buttons and select menus.
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button, Select
import logging
from typing import Optional, List
from datetime import datetime, timedelta

from .lfg_database import (
    get_lfg_profile, create_lfg_profile, update_lfg_profile,
    create_lfg_listing, get_active_listings, update_listing_status,
    cleanup_expired_listings, get_all_lfg_profiles, get_lfg_profiles_count,
    update_saved_description
)
from .config import (
    LFG_LISTINGS_CHANNEL_ID, LFG_PROFILES_CHANNEL_ID, 
    LISTING_EXPIRATION_HOURS, COLORS, PROFILES_PER_PAGE,
    ROLE_EMOJIS, RANK_EMOJIS, CHAMPION_EMOJIS
)

logger = logging.getLogger(__name__)


# ================================
#       CONSTANTS
# ================================

REGIONS = {
    'eune': 'EUNE',
    'euw': 'EUW',
    'na': 'NA',
    'kr': 'KR',
    'br': 'BR',
    'lan': 'LAN',
    'las': 'LAS',
    'oce': 'OCE',
    'ru': 'RU',
    'tr': 'TR',
    'jp': 'JP'
}

ROLES = {
    'top': {'emoji': ROLE_EMOJIS.get('TOP', '⬆️'), 'name': 'Top', 'api_name': 'TOP'},
    'jungle': {'emoji': ROLE_EMOJIS.get('JUNGLE', '🌳'), 'name': 'Jungle', 'api_name': 'JUNGLE'},
    'mid': {'emoji': ROLE_EMOJIS.get('MIDDLE', '✨'), 'name': 'Mid', 'api_name': 'MIDDLE'},
    'adc': {'emoji': ROLE_EMOJIS.get('BOTTOM', '🏹'), 'name': 'ADC', 'api_name': 'BOTTOM'},
    'support': {'emoji': ROLE_EMOJIS.get('UTILITY', '🛡️'), 'name': 'Support', 'api_name': 'UTILITY'}
}

QUEUE_TYPES = {
    'ranked_solo': {'emoji': '👤', 'name': 'Ranked Solo/Duo'},
    'ranked_flex': {'emoji': '👥', 'name': 'Ranked Flex'},
    'normal': {'emoji': '🎮', 'name': 'Normal Draft'},
    'aram': {'emoji': '❄️', 'name': 'ARAM'},
    'arena': {'emoji': '⚔️', 'name': 'Arena'}
}

RANKS = [
    'Iron', 'Bronze', 'Silver', 'Gold', 'Platinum', 
    'Emerald', 'Diamond', 'Master', 'Grandmaster', 'Challenger'
]

PLAYSTYLES = {
    'casual': {'emoji': '😊', 'name': 'Casual'},
    'competitive': {'emoji': '🔥', 'name': 'Competitive'},
    'mixed': {'emoji': '⚖️', 'name': 'Mixed'}
}


# ================================
#       HELPER FUNCTIONS
# ================================

def get_role_emoji(role: str) -> str:
    """Get custom emoji for role."""
    role_data = ROLES.get(role.lower())
    if role_data:
        return role_data['emoji']
    return '❓'


def get_rank_emoji(rank_str: str) -> str:
    """Get custom emoji for rank (e.g., 'Gold II' -> Gold emoji)"""
    if not rank_str or rank_str == 'Unranked':
        return RANK_EMOJIS.get('UNRANKED', '🎮')
    
    # Extract tier from rank string (e.g., "Gold II" -> "GOLD")
    tier = rank_str.split()[0].upper()
    return RANK_EMOJIS.get(tier, '🏆')


async def region_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> List[app_commands.Choice[str]]:
    """Autocomplete for region selection."""
    return [
        app_commands.Choice(name=name, value=key)
        for key, name in REGIONS.items()
        if current.lower() in key.lower() or current.lower() in name.lower()
    ][:25]


async def queue_type_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> List[app_commands.Choice[str]]:
    """Autocomplete for queue type selection."""
    return [
        app_commands.Choice(name=f"{data['emoji']} {data['name']}", value=key)
        for key, data in QUEUE_TYPES.items()
        if current.lower() in key.lower() or current.lower() in data['name'].lower()
    ][:25]
    return RANK_EMOJIS.get(tier, '🎮')


def format_rank_with_emoji(rank_str: str) -> str:
    """Format rank string with custom emoji"""
    if not rank_str or rank_str == 'Unranked':
        return f"{RANK_EMOJIS.get('UNRANKED', '🎮')} Unranked"
    
    emoji = get_rank_emoji(rank_str)
    return f"{emoji} {rank_str}"


# ================================
#       PROFILE SETUP VIEWS
# ================================

class RoleSelectView(View):
    """Interactive view for selecting roles."""
    
    def __init__(self, bot, riot_api, user_id: int, game_name: str, tagline: str, region: str, profile_link: Optional[str] = None):
        super().__init__(timeout=300)
        self.bot = bot
        self.riot_api = riot_api
        self.user_id = user_id
        self.game_name = game_name
        self.tagline = tagline
        self.region = region
        self.profile_link = profile_link
        self.selected_roles = []
        
        # Add role buttons
        for role_id, role_data in ROLES.items():
            # Parse custom emoji from string format <:name:id>
            emoji_str = role_data['emoji']
            # Discord buttons accept emoji strings directly
            button = Button(
                label=role_data['name'],
                emoji=emoji_str,
                style=discord.ButtonStyle.secondary,
                custom_id=f"role_{role_id}"
            )
            button.callback = self.role_button_callback
            self.add_item(button)
        
        # Add confirm button
        confirm_btn = Button(
            label="Confirm",
            style=discord.ButtonStyle.success,
            custom_id="confirm",
            row=2
        )
        confirm_btn.callback = self.confirm_callback
        self.add_item(confirm_btn)
    
    async def role_button_callback(self, interaction: discord.Interaction):
        """Handle role button clicks."""
        button = [item for item in self.children if item.custom_id == interaction.data['custom_id']][0]
        role_id = button.custom_id.replace('role_', '')
        
        if role_id in self.selected_roles:
            # Deselect
            self.selected_roles.remove(role_id)
            button.style = discord.ButtonStyle.secondary
        else:
            # Select (max 3 roles)
            if len(self.selected_roles) >= 3:
                await interaction.response.send_message(
                    "❌ You can select maximum 3 roles!",
                    ephemeral=True
                )
                return
            
            self.selected_roles.append(role_id)
            button.style = discord.ButtonStyle.primary
        
        await interaction.response.edit_message(view=self)
    
    async def confirm_callback(self, interaction: discord.Interaction):
        """Handle confirm button click."""
        if not self.selected_roles:
            await interaction.response.send_message(
                "❌ You must select at least one role!",
                ephemeral=True
            )
            return
        
        # Fetch account data from Riot API
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get account info
            account_data = await self.riot_api.get_account_by_riot_id(
                self.game_name, self.tagline
            )
            
            if not account_data:
                await interaction.followup.send(
                    "❌ Riot account not found! Check your name and tag.",
                    ephemeral=True
                )
                return
            
            puuid = account_data.get('puuid')
            
            # Get ranked data
            summoner_data = await self.riot_api.get_summoner_by_puuid(puuid, self.region)
            if not summoner_data:
                await interaction.followup.send(
                    "❌ Cannot fetch data from region.",
                    ephemeral=True
                )
                return
            
            # Create profile
            success = create_lfg_profile(
                user_id=self.user_id,
                riot_id_game_name=self.game_name,
                riot_id_tagline=self.tagline,
                region=self.region,
                primary_roles=self.selected_roles,
                puuid=puuid,
                profile_link=self.profile_link
            )
            
            if success:
                # Fetch rank data using PUUID
                ranked_data = await self.riot_api.get_ranked_stats_by_puuid(puuid, self.region)
                solo_rank = "Unranked"
                flex_rank = "Unranked"
                
                if ranked_data:
                    for queue in ranked_data:
                        if queue['queueType'] == 'RANKED_SOLO_5x5':
                            solo_rank = f"{queue['tier']} {queue['rank']}"
                        elif queue['queueType'] == 'RANKED_FLEX_SR':
                            flex_rank = f"{queue['tier']} {queue['rank']}"
                
                # Update profile with rank data
                update_lfg_profile(self.user_id, solo_rank=solo_rank, flex_rank=flex_rank)
                
                # Create settings embed similar to screenshot
                embed = discord.Embed(
                    title="About you",
                    color=discord.Color.dark_gray()
                )
                
                # Language section (placeholder)
                embed.add_field(
                    name="Language(s) you speak:",
                    value="`Polish` `English`\n*You can change this with `/lfg_edit`*",
                    inline=False
                )
                
                # Discord ID section
                embed.add_field(
                    name="Your discord id *(Optional)*",
                    value=f"`{interaction.user.name}`\n*This is your Discord username*",
                    inline=False
                )
                
                embed.add_field(
                    name="━━━━━━━━━━━━━━━━━━━━━━",
                    value="**About your playstyle**",
                    inline=False
                )
                
                # Game Modes section
                roles_display = ' '.join([f'`{ROLES[r]["name"]}`' for r in self.selected_roles])
                embed.add_field(
                    name="Your roles:",
                    value=f"{roles_display}\n*Selected roles you prefer to play*",
                    inline=False
                )
                
                embed.add_field(
                    name="━━━━━━━━━━━━━━━━━━━━━━",
                    value="**Other**",
                    inline=False
                )
                
                # LoL account section
                embed.add_field(
                    name="Your LoL account",
                    value=f"\ud83c\udfae **{self.game_name}#{self.tagline}**\n"
                          f"\ud83c\udf0d **{self.region.upper()}**\n"
                          f"\ud83c\udfc6 Solo: **{solo_rank}**\n"
                          f"\ud83d\udc65 Flex: **{flex_rank}**",
                    inline=False
                )
                
                embed.set_footer(text=f"Profile created • Use /lfg_edit to customize further")
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Try to update original message (may fail if ephemeral)
                try:
                    await interaction.message.edit(
                        content="✅ Profile created!",
                        view=None
                    )
                except (discord.NotFound, discord.HTTPException):
                    pass  # Message may have been deleted or is ephemeral
            else:
                await interaction.followup.send(
                    "❌ An error occurred while creating profile.",
                    ephemeral=True
                )
        
        except Exception as e:
            logger.error(f"Error in profile creation: {e}")
            await interaction.followup.send(
                "❌ An error occurred while connecting to Riot API.",
                ephemeral=True
            )


class EditRiotIDModal(discord.ui.Modal, title="Change Riot ID"):
    """Modal for editing Riot ID."""
    
    riot_id = discord.ui.TextInput(
        label="New Riot ID",
        placeholder="PlayerName#TAG (example: 16 9 13 5 11#pimek)",
        style=discord.TextStyle.short,
        max_length=50,
        required=True
    )
    
    def __init__(self, user_id: int, current_profile: dict):
        super().__init__()
        self.user_id = user_id
        self.current_profile = current_profile
        # Set current value
        current_riot_id = f"{current_profile['riot_id_game_name']}#{current_profile['riot_id_tagline']}"
        self.riot_id.default = current_riot_id
    
    async def on_submit(self, interaction: discord.Interaction):
        riot_id_input = self.riot_id.value
        
        # Validate format
        if '#' not in riot_id_input:
            await interaction.response.send_message(
                "❌ Invalid format! Use: `PlayerName#TAG`",
                ephemeral=True
            )
            return
        
        try:
            game_name, tagline = riot_id_input.split('#', 1)
            game_name = game_name.strip()
            tagline = tagline.strip()
            
            if not game_name or not tagline:
                raise ValueError("Empty name or tag")
        except:
            await interaction.response.send_message(
                "❌ Invalid Riot ID format!",
                ephemeral=True
            )
            return
        
        # Update profile
        success = update_lfg_profile(
            self.user_id,
            riot_id_game_name=game_name,
            riot_id_tagline=tagline
        )
        
        if success:
            await interaction.response.send_message(
                f"✅ Riot ID updated to: **{game_name}#{tagline}**",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to update Riot ID. Please try again.",
                ephemeral=True
            )


class EditRegionModal(discord.ui.Modal, title="Change Region"):
    """Modal for editing region."""
    
    region = discord.ui.TextInput(
        label="New Region",
        placeholder="eune, euw, na, kr, etc.",
        style=discord.TextStyle.short,
        max_length=10,
        required=True
    )
    
    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id
    
    async def on_submit(self, interaction: discord.Interaction):
        region_input = self.region.value.lower().strip()
        
        # Validate region
        if region_input not in REGIONS:
            await interaction.response.send_message(
                f"❌ Invalid region! Valid options: {', '.join(REGIONS.keys())}",
                ephemeral=True
            )
            return
        
        # Update profile
        success = update_lfg_profile(self.user_id, region=region_input)
        
        if success:
            await interaction.response.send_message(
                f"✅ Region updated to: **{REGIONS[region_input]}**",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to update region. Please try again.",
                ephemeral=True
            )


class EditProfileLinkModal(discord.ui.Modal, title="Edit Profile Link"):
    """Modal for editing profile link."""
    
    profile_link = discord.ui.TextInput(
        label="Profile Link",
        placeholder="https://www.op.gg/summoners/... (op.gg, dpm.lol, u.gg, deeplol.gg)",
        style=discord.TextStyle.short,
        max_length=500,
        required=False
    )
    
    def __init__(self, user_id: int, current_link: str):
        super().__init__()
        self.user_id = user_id
        if current_link:
            self.profile_link.default = current_link
    
    async def on_submit(self, interaction: discord.Interaction):
        link = self.profile_link.value.strip()
        
        # Validate if not empty
        if link:
            valid_domains = ['op.gg', 'dpm.lol', 'u.gg', 'deeplol.gg']
            if not any(domain in link.lower() for domain in valid_domains):
                await interaction.response.send_message(
                    "❌ Invalid link! Please use op.gg, dpm.lol, u.gg, or deeplol.gg",
                    ephemeral=True
                )
                return
        
        # Update profile (empty string to remove link)
        success = update_lfg_profile(self.user_id, profile_link=link if link else None)
        
        if success:
            if link:
                await interaction.response.send_message(
                    f"✅ Profile link updated!\n[View Profile]({link})",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "✅ Profile link removed!",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Failed to update profile link. Please try again.",
                ephemeral=True
            )


class ConfirmDeleteModal(discord.ui.Modal, title="Delete Profile - Confirm"):
    """Modal for confirming profile deletion."""
    
    confirmation = discord.ui.TextInput(
        label="Type DELETE to confirm",
        placeholder="DELETE",
        style=discord.TextStyle.short,
        max_length=10,
        required=True
    )
    
    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmation.value.upper() != "DELETE":
            await interaction.response.send_message(
                "❌ Confirmation failed. Profile not deleted.",
                ephemeral=True
            )
            return
        
        # Delete profile from database
        from .lfg_database import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("DELETE FROM lfg_profiles WHERE user_id = %s", (self.user_id,))
            conn.commit()
            
            await interaction.response.send_message(
                "✅ Profile deleted successfully!\n\n"
                "You can create a new profile anytime with `/lfgsetup`",
                ephemeral=True
            )
        except Exception as e:
            conn.rollback()
            await interaction.response.send_message(
                "❌ Failed to delete profile. Please try again.",
                ephemeral=True
            )
        finally:
            cur.close()
            conn.close()


class ProfileEditView(View):
    """View for editing profile settings."""
    
    def __init__(self, user_id: int, current_profile: dict):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.current_profile = current_profile
    
    @discord.ui.button(label="Change Riot ID", emoji="🎮", style=discord.ButtonStyle.primary, row=0)
    async def change_riot_id(self, interaction: discord.Interaction, button: Button):
        """Change Riot ID."""
        modal = EditRiotIDModal(self.user_id, self.current_profile)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Change Region", emoji="🌍", style=discord.ButtonStyle.primary, row=0)
    async def change_region(self, interaction: discord.Interaction, button: Button):
        """Change region."""
        modal = EditRegionModal(self.user_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Change Roles", emoji="🎭", style=discord.ButtonStyle.primary, row=1)
    async def change_roles(self, interaction: discord.Interaction, button: Button):
        """Change role preferences."""
        # TODO: Implement role change modal
        await interaction.response.send_message("🚧 Under construction", ephemeral=True)
    
    @discord.ui.button(label="Profile Link", emoji="📊", style=discord.ButtonStyle.primary, row=1)
    async def edit_profile_link(self, interaction: discord.Interaction, button: Button):
        """Edit profile link (op.gg, etc)."""
        modal = EditProfileLinkModal(self.user_id, self.current_profile.get('profile_link', ''))
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Add Description", emoji="📝", style=discord.ButtonStyle.secondary, row=2)
    async def edit_description(self, interaction: discord.Interaction, button: Button):
        """Edit profile description."""
        modal = ProfileDescriptionModal(self.user_id, self.current_profile.get('description', ''))
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Voice Preferences", emoji="🎤", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_voice(self, interaction: discord.Interaction, button: Button):
        """Toggle voice requirement."""
        current_voice = self.current_profile.get('voice_required', False)
        new_voice = not current_voice
        
        update_lfg_profile(self.user_id, voice_required=new_voice)
        self.current_profile['voice_required'] = new_voice
        
        await interaction.response.send_message(
            f"✅ Voice {'required' if new_voice else 'optional'}",
            ephemeral=True
        )
    
    @discord.ui.button(label="Playstyle", emoji="🎮", style=discord.ButtonStyle.secondary, row=3)
    async def change_playstyle(self, interaction: discord.Interaction, button: Button):
        """Change playstyle preference."""
        view = PlaystyleSelectView(self.user_id)
        await interaction.response.send_message(
            "Choose your playstyle:",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(label="Delete Profile", emoji="🗑️", style=discord.ButtonStyle.danger, row=4)
    async def delete_profile(self, interaction: discord.Interaction, button: Button):
        """Delete LFG profile."""
        modal = ConfirmDeleteModal(self.user_id)
        await interaction.response.send_modal(modal)


class ProfileDescriptionModal(discord.ui.Modal, title="Profile Description"):
    """Modal for editing profile description."""
    
    description = discord.ui.TextInput(
        label="Description",
        placeholder="Write something about yourself, your playstyle, preferred champions...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False
    )
    
    def __init__(self, user_id: int, current_description: str):
        super().__init__()
        self.user_id = user_id
        if current_description:
            self.description.default = current_description
    
    async def on_submit(self, interaction: discord.Interaction):
        update_lfg_profile(self.user_id, description=self.description.value)
        await interaction.response.send_message(
            "✅ Description updated!",
            ephemeral=True
        )


class PlaystyleSelectView(View):
    """View for selecting playstyle."""
    
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        
        for style_id, style_data in PLAYSTYLES.items():
            button = Button(
                label=style_data['name'],
                emoji=style_data['emoji'],
                style=discord.ButtonStyle.secondary,
                custom_id=f"style_{style_id}"
            )
            button.callback = self.style_callback
            self.add_item(button)
    
    async def style_callback(self, interaction: discord.Interaction):
        style_id = interaction.data['custom_id'].replace('style_', '')
        update_lfg_profile(self.user_id, playstyle=style_id)
        
        style_name = PLAYSTYLES[style_id]['name']
        await interaction.response.send_message(
            f"✅ Playstyle set to: **{style_name}**",
            ephemeral=True
        )
        
        await interaction.message.edit(view=None)


# ================================
#       LFG LISTING VIEWS
# ================================

class CreateListingView(View):
    """Interactive view for creating LFG listings."""
    
    def __init__(self, user_id: int, profile: dict):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.profile = profile
        self.queue_type = None
        self.roles_needed = []
        self.spots = 1
        self.voice_required = False
        
        # Add queue type select
        queue_select = Select(
            placeholder="Choose game type",
            custom_id="queue_select",
            options=[
                discord.SelectOption(
                    label=data['name'],
                    value=queue_id,
                    emoji=data['emoji']
                )
                for queue_id, data in QUEUE_TYPES.items()
            ]
        )
        queue_select.callback = self.queue_callback
        self.add_item(queue_select)
    
    async def queue_callback(self, interaction: discord.Interaction):
        """Handle queue type selection."""
        self.queue_type = interaction.data['values'][0]
        
        # Add role selection
        self.clear_items()
        
        # Re-add queue select (disabled)
        queue_select = Select(
            placeholder=f"✅ {QUEUE_TYPES[self.queue_type]['name']}",
            custom_id="queue_select",
            disabled=True,
            options=[discord.SelectOption(label=QUEUE_TYPES[self.queue_type]['name'], value=self.queue_type)]
        )
        self.add_item(queue_select)
        
        # Add role buttons
        for role_id, role_data in ROLES.items():
            button = Button(
                label=role_data['name'],
                emoji=role_data['emoji'],
                style=discord.ButtonStyle.secondary,
                custom_id=f"role_{role_id}",
                row=1
            )
            button.callback = self.role_callback
            self.add_item(button)
        
        # Add voice toggle
        voice_btn = Button(
            label="Voice optional",
            emoji="🎤",
            style=discord.ButtonStyle.secondary,
            custom_id="voice_toggle",
            row=2
        )
        voice_btn.callback = self.voice_callback
        self.add_item(voice_btn)
        
        # Add edit profile button
        edit_profile_btn = Button(
            label="Edit Profile",
            emoji="✏️",
            style=discord.ButtonStyle.secondary,
            custom_id="edit_profile",
            row=3
        )
        edit_profile_btn.callback = self.edit_profile_callback
        self.add_item(edit_profile_btn)
        
        # Add create button
        create_btn = Button(
            label="Create Listing",
            style=discord.ButtonStyle.success,
            custom_id="create",
            row=3
        )
        create_btn.callback = self.create_callback
        self.add_item(create_btn)
        
        await interaction.response.edit_message(view=self)
    
    async def role_callback(self, interaction: discord.Interaction):
        """Handle role selection."""
        button = [item for item in self.children if item.custom_id == interaction.data['custom_id']][0]
        role_id = button.custom_id.replace('role_', '')
        
        if role_id in self.roles_needed:
            self.roles_needed.remove(role_id)
            button.style = discord.ButtonStyle.secondary
            self.spots -= 1
        else:
            if len(self.roles_needed) >= 4:
                await interaction.response.send_message(
                    "❌ Maximum 4 roles!",
                    ephemeral=True
                )
                return
            
            self.roles_needed.append(role_id)
            button.style = discord.ButtonStyle.primary
            self.spots += 1
        
        await interaction.response.edit_message(view=self)
    
    async def voice_callback(self, interaction: discord.Interaction):
        """Handle voice toggle."""
        button = [item for item in self.children if item.custom_id == 'voice_toggle'][0]
        
        self.voice_required = not self.voice_required
        
        if self.voice_required:
            button.label = "Voice required"
            button.style = discord.ButtonStyle.primary
        else:
            button.label = "Voice optional"
            button.style = discord.ButtonStyle.secondary
        
        await interaction.response.edit_message(view=self)
    
    async def edit_profile_callback(self, interaction: discord.Interaction):
        """Open profile edit menu."""
        from .lfg_database import get_lfg_profile
        
        # Refresh profile data
        profile = get_lfg_profile(self.user_id)
        if not profile:
            await interaction.response.send_message(
                "❌ Profile not found!",
                ephemeral=True
            )
            return
        
        # Update self.profile with fresh data
        self.profile = profile
        
        # Show edit view
        view = ProfileEditView(self.user_id, profile)
        embed = discord.Embed(
            title="✏️ Edit Profile",
            description="Make changes to your profile before creating the listing:",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )
    
    async def create_callback(self, interaction: discord.Interaction):
        """Create the listing."""
        if not self.queue_type:
            await interaction.response.send_message(
                "❌ Choose game type!",
                ephemeral=True
            )
            return
        
        if not self.roles_needed:
            await interaction.response.send_message(
                "❌ Choose at least one role!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Create listing in database
        listing_id = create_lfg_listing(
            creator_user_id=self.user_id,
            queue_type=self.queue_type,
            roles_needed=self.roles_needed,
            region=self.profile['region'],
            spots_available=self.spots,
            voice_required=self.voice_required,
            expires_at=datetime.now() + timedelta(hours=LISTING_EXPIRATION_HOURS)
        )
        
        if not listing_id:
            await interaction.followup.send(
                "❌ Failed to create listing.",
                ephemeral=True
            )
            return
        
        # Create public embed
        embed = create_listing_embed(self.profile, self.queue_type, self.roles_needed, self.voice_required, listing_id, self.user_id)
        view = ListingActionView(listing_id, self.user_id)
        
        # Post to channel
        channel = interaction.guild.get_channel(LFG_LISTINGS_CHANNEL_ID)
        if channel:
            message = await channel.send(embed=embed, view=view)
            update_listing_status(listing_id, 'active', message.id)
        else:
            await interaction.followup.send(
                f"⚠️ LFG channel not found (ID: {LFG_LISTINGS_CHANNEL_ID}). Contact an administrator.",
                ephemeral=True
            )
            return
        
        await interaction.followup.send(
            "✅ Listing created!",
            ephemeral=True
        )
        
        await interaction.message.edit(content="✅ Listing created!", view=None)


def create_listing_embed(profile: dict, queue_type: str, roles_needed: list, voice_required: bool, listing_id: int, user_id: int) -> discord.Embed:
    """Create embed for LFG listing."""
    queue_name = QUEUE_TYPES[queue_type]['name']
    queue_emoji = QUEUE_TYPES[queue_type]['emoji']
    
    # Create eye-catching embed
    embed = discord.Embed(
        title=f"{queue_emoji} {queue_name.upper()}",
        color=COLORS['listing'],
        timestamp=datetime.now()
    )
    
    # Player info at the top with custom styling
    riot_id = f"**{profile['riot_id_game_name']}#{profile['riot_id_tagline']}**"
    player_line = f"## {riot_id}"
    
    embed.description = player_line
    
    # Discord contact info - prominent at the top
    embed.add_field(
        name="💬 Contact",
        value=f"<@{user_id}> • [Send DM](https://discord.com/users/{user_id})",
        inline=False
    )
    
    # Looking for roles - big and clear
    roles_display = []
    for role in roles_needed:
        emoji = get_role_emoji(role)
        name = ROLES[role]['name']
        roles_display.append(f"{emoji} **{name}**")
    
    embed.add_field(
        name="🎯 LOOKING FOR",
        value=' • '.join(roles_display),
        inline=False
    )
    
    # Additional player info
    player_details = []
    
    # Solo rank
    if profile.get('solo_rank'):
        rank_display = format_rank_with_emoji(profile['solo_rank'])
        player_details.append(f"**Solo:** {rank_display}")
    else:
        player_details.append(f"**Solo:** {RANK_EMOJIS.get('UNRANKED', '🎮')} Unranked")
    
    # Flex rank if available
    if profile.get('flex_rank') and profile['flex_rank'] != 'Unranked':
        player_details.append(f"**Flex:** {format_rank_with_emoji(profile['flex_rank'])}")
    
    # Arena rank if available
    if profile.get('arena_rank') and profile['arena_rank'] != 'Unranked':
        player_details.append(f"**Arena:** {format_rank_with_emoji(profile['arena_rank'])}")
    
    # Region
    player_details.append(f"**Region:** 🌍 {profile['region'].upper()}")
    
    # Voice status
    if voice_required:
        player_details.append(f"**Voice:** 🎤 Required")
    else:
        player_details.append(f"**Voice:** 🔇 Optional")
    
    # Playstyle
    if profile.get('playstyle'):
        style = PLAYSTYLES.get(profile['playstyle'], {})
        if style:
            player_details.append(f"**Style:** {style['emoji']} {style['name']}")
    
    embed.add_field(
        name="📊 Player Info",
        value=' • '.join(player_details),
        inline=False
    )
    
    # Player roles (what they play)
    if profile.get('primary_roles'):
        player_roles = []
        for role in profile['primary_roles']:
            emoji = get_role_emoji(role)
            player_roles.append(f"{emoji}")
        embed.add_field(
            name="🎭 Player Roles",
            value=' '.join(player_roles),
            inline=True
        )
    
    # Description if available
    if profile.get('description'):
        desc_text = profile['description'][:150]
        if len(profile['description']) > 150:
            desc_text += "..."
        embed.add_field(
            name="💬 Message",
            value=f"*{desc_text}*",
            inline=False
        )
    
    # Profile link if available
    if profile.get('profile_link'):
        embed.add_field(
            name="📊 Stats",
            value=f"[View Profile]({profile['profile_link']})",
            inline=True
        )
    
    # Footer with timestamp and ID
    embed.set_footer(
        text=f"Click ✅ Join to play together • Expires in 24h • ID: {listing_id}",
        icon_url="https://cdn.discordapp.com/emojis/1441318506275536999.png"  # Could use a LoL icon
    )
    
    return embed


class EditDescriptionModal(discord.ui.Modal, title="Edit Description"):
    """Modal for editing the description that will be saved for future posts."""
    
    description_input = discord.ui.TextInput(
        label="Description",
        placeholder="Tell us about yourself, preferred playstyle, etc...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False
    )
    
    def __init__(self, listing_id: int, user_id: int, message: discord.Message):
        super().__init__()
        self.listing_id = listing_id
        self.user_id = user_id
        self.message = message
    
    async def on_submit(self, interaction: discord.Interaction):
        """Save the description to the database and update the embed."""
        new_description = self.description_input.value
        
        # Update saved description in database
        success = update_saved_description(self.user_id, new_description)
        
        if success:
            # Update the embed
            try:
                embed = self.message.embeds[0]
                
                # Find and update the Message field
                for i, field in enumerate(embed.fields):
                    if field.name == "💬 Message":
                        # Remove old message field
                        embed.remove_field(i)
                        break
                
                # Add updated message field if description exists
                if new_description:
                    desc_text = new_description[:150]
                    if len(new_description) > 150:
                        desc_text += "..."
                    embed.add_field(
                        name="💬 Message",
                        value=f"*{desc_text}*",
                        inline=False
                    )
                
                # Update the message
                await self.message.edit(embed=embed)
                
                await interaction.response.send_message(
                    f"✅ Description updated in both profile and listing!\n\n**New description:**\n{new_description[:200]}{'...' if len(new_description) > 200 else ''}",
                    ephemeral=True
                )
            except Exception as e:
                await interaction.response.send_message(
                    f"✅ Description saved to profile, but failed to update embed: {e}",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Failed to save description. Please try again.",
                ephemeral=True
            )


class ListingActionView(View):
    """Buttons for interacting with listings."""
    
    def __init__(self, listing_id: int, creator_id: int):
        super().__init__(timeout=None)  # Persistent view
        self.listing_id = listing_id
        self.creator_id = creator_id
    
    @discord.ui.button(label="Join", emoji="✅", style=discord.ButtonStyle.success, custom_id="join")
    async def join_button(self, interaction: discord.Interaction, button: Button):
        """Join the group - opens DM with creator."""
        await interaction.response.send_message(
            f"✅ Contact the group creator: <@{self.creator_id}>\n\n"
            f"[Click here to send a DM](https://discord.com/users/{self.creator_id})",
            ephemeral=True
        )
    
    @discord.ui.button(label="Edit Description", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="edit_desc")
    async def edit_desc_button(self, interaction: discord.Interaction, button: Button):
        """Edit the description (creator only)."""
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message(
                "❌ Only the creator can edit this listing!",
                ephemeral=True
            )
            return
        
        # Show modal for editing description
        modal = EditDescriptionModal(self.listing_id, interaction.user.id, interaction.message)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Close", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="close")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        """Close the listing (creator only)."""
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message(
                "❌ Only the creator can close this listing!",
                ephemeral=True
            )
            return
        
        update_listing_status(self.listing_id, 'filled')
        
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.greyple()
        embed.set_footer(text=f"ID: {self.listing_id} • Closed - Deleting in 10 seconds...")
        
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message(
            "✅ Listing closed! It will be deleted in 10 seconds.",
            ephemeral=True
        )
        
        # Delete message after 10 seconds
        import asyncio
        await asyncio.sleep(10)
        try:
            await interaction.message.delete()
        except:
            pass  # Message might already be deleted


# ================================
#       SLASH COMMANDS
# ================================

class LFGCommands(commands.Cog):
    """LFG system commands."""
    
    def __init__(self, bot: commands.Bot, riot_api):
        self.bot = bot
        self.riot_api = riot_api
        
        # Start cleanup task
        self.cleanup_task.start()
    
    def cog_unload(self):
        self.cleanup_task.cancel()
    
    @tasks.loop(minutes=30)
    async def cleanup_task(self):
        """Periodically cleanup expired listings."""
        cleanup_expired_listings()
    
    @cleanup_task.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()
    
    @app_commands.command(name="lfgsetup", description="Create your profile - takes 1 minute!")
    @app_commands.describe(
        riot_id="Your Riot ID with # tag (example: PlayerName#EUW)",
        region="Your server region",
        profile_link="Optional: Your op.gg, dpm.lol, u.gg, or deeplol.gg profile link"
    )
    @app_commands.autocomplete(region=region_autocomplete)
    async def lfgsetup(
        self,
        interaction: discord.Interaction,
        riot_id: str,
        region: str,
        profile_link: Optional[str] = None
    ):
        """Create LFG profile with interactive setup."""
        # Check if profile exists
        existing = get_lfg_profile(interaction.user.id)
        if existing:
            await interaction.response.send_message(
                "❌ You already have a profile!\n\n"
                "💡 Use `/lfgedit` to change your settings or `/lfgprofile` to view it.",
                ephemeral=True
            )
            return
        
        # Validate Riot ID format
        if '#' not in riot_id:
            await interaction.response.send_message(
                "❌ Invalid Riot ID format!\n\n"
                "✅ Correct format: `PlayerName#TAG`\n"
                "Example: `16 9 13 5 11#pimek`\n\n"
                "💡 Find your Riot ID in League client settings.",
                ephemeral=True
            )
            return
        
        # Split Riot ID
        try:
            game_name, tagline = riot_id.split('#', 1)
            game_name = game_name.strip()
            tagline = tagline.strip()
            
            if not game_name or not tagline:
                raise ValueError("Empty name or tag")
        except:
            await interaction.response.send_message(
                "❌ Invalid Riot ID format! Must be like: `16 9 13 5 11#pimek`",
                ephemeral=True
            )
            return
        
        # Validate region
        region = region.lower()
        if region not in REGIONS:
            await interaction.response.send_message(
                f"❌ Invalid region! Choose from: {', '.join(REGIONS.values())}",
                ephemeral=True
            )
            return
        
        # Validate profile link if provided
        if profile_link:
            valid_domains = ['op.gg', 'dpm.lol', 'u.gg', 'deeplol.gg']
            if not any(domain in profile_link.lower() for domain in valid_domains):
                await interaction.response.send_message(
                    "❌ Invalid profile link! Please use op.gg, dpm.lol, u.gg, or deeplol.gg",
                    ephemeral=True
                )
                return
        
        # Show role selection view with riot_id for display
        view = RoleSelectView(self.bot, self.riot_api, interaction.user.id, game_name, tagline, region, profile_link)
        
        embed = discord.Embed(
            title="🎭 Choose your League of Legends roles",
            description=f"**{game_name}#{tagline}** ({region.upper()})\n\n"
                        "Select up to 3 roles you prefer to play:\n"
                        "💡 *Tip: Choose roles you're most comfortable with*",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Your LoL account",
            value=f"🎮 **{game_name}#{tagline}**\n🌍 Region: **{region.upper()}**",
            inline=False
        )
        if profile_link:
            embed.add_field(
                name="📊 Profile Link",
                value=f"[View Stats]({profile_link})",
                inline=False
            )
        embed.set_footer(text="After selecting roles, you'll set your playstyle and preferences")
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="lfgprofile", description="View yours or someone's profile")
    @app_commands.describe(
        user="Select a user (leave empty for your profile)"
    )
    async def lfgprofile(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None
    ):
        """Display LFG profile."""
        target_user = user or interaction.user
        profile = get_lfg_profile(target_user.id)
        
        if not profile:
            if target_user == interaction.user:
                await interaction.response.send_message(
                    "❌ You don't have a profile yet!\n\n"
                    "💡 Use `/lfgsetup` to create one in 1 minute!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ {target_user.mention} doesn't have a profile yet.",
                    ephemeral=True
                )
            return
        
        # Create profile embed
        embed = discord.Embed(
            title=f"👤 Profil LFG: {profile['riot_id_game_name']}#{profile['riot_id_tagline']}",
            color=discord.Color.blue()
        )
        
        # Roles with custom emojis
        roles_text = ' '.join([
            f"{get_role_emoji(r)} {ROLES[r]['name']}"
            for r in profile['primary_roles']
        ])
        embed.add_field(name="🎭 Roles", value=roles_text or "None", inline=False)
        
        # Region & Ranks with custom emojis
        embed.add_field(name="🌍 Region", value=profile['region'].upper(), inline=True)
        
        if profile.get('solo_rank'):
            embed.add_field(name="🏆 Solo/Duo", value=format_rank_with_emoji(profile['solo_rank']), inline=True)
        
        if profile.get('flex_rank'):
            embed.add_field(name="👥 Flex", value=format_rank_with_emoji(profile['flex_rank']), inline=True)
        
        if profile.get('arena_rank'):
            embed.add_field(name="⚔️ Arena", value=format_rank_with_emoji(profile['arena_rank']), inline=True)
        
        # Preferences
        prefs = []
        if profile.get('voice_required'):
            prefs.append("🎤 Voice required")
        if profile.get('playstyle'):
            style_name = PLAYSTYLES.get(profile['playstyle'], {}).get('name', profile['playstyle'])
            prefs.append(f"🎮 {style_name}")
        
        if prefs:
            embed.add_field(name="⚙️ Preferences", value='\n'.join(prefs), inline=False)
        
        # Description
        if profile.get('description'):
            embed.add_field(name="📝 Description", value=profile['description'], inline=False)
        
        # Profile link
        if profile.get('profile_link'):
            embed.add_field(name="📊 Stats Profile", value=f"[View Profile]({profile['profile_link']})", inline=False)
        
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.set_footer(text=f"Utworzony: {profile['created_at'].strftime('%Y-%m-%d')}")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="lfgedit", description="Edit your LFG profile")
    async def lfgedit(self, interaction: discord.Interaction):
        """Edit LFG profile."""
        profile = get_lfg_profile(interaction.user.id)
        
        if not profile:
            await interaction.response.send_message(
                "❌ You don't have an LFG profile! Use `/lfgsetup` to create one.",
                ephemeral=True
            )
            return
        
        view = ProfileEditView(interaction.user.id, profile)
        
        embed = discord.Embed(
            title="✏️ Edit LFG Profile",
            description="Choose what you want to change:",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="lfg", description="Find teammates - create your listing!")
    async def lfg(self, interaction: discord.Interaction):
        """Create LFG listing."""
        profile = get_lfg_profile(interaction.user.id)
        
        if not profile:
            await interaction.response.send_message(
                "❌ You need a profile first!\n\n"
                "💡 Quick setup: `/lfgsetup riot_id region`\n"
                "Example: `/lfgsetup 16 9 13 5 11#pimek eune`",
                ephemeral=True
            )
            return
        
        view = CreateListingView(interaction.user.id, profile)
        
        embed = discord.Embed(
            title="📝 Find Teammates",
            description="Choose what you're looking for:",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="⏱️ Duration",
            value="Your listing will be visible for **24 hours**",
            inline=False
        )
        embed.set_footer(text="Select queue type and roles you need")
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="lfgbrowse", description="Browse active League of Legends LFG listings")
    @app_commands.describe(
        queue_type="Filter by queue type",
        region="Filter by region"
    )
    @app_commands.autocomplete(
        region=region_autocomplete,
        queue_type=queue_type_autocomplete
    )
    async def lfgbrowse(
        self,
        interaction: discord.Interaction,
        queue_type: Optional[str] = None,
        region: Optional[str] = None
    ):
        """Browse active LFG listings."""
        listings = get_active_listings(region=region, queue_type=queue_type, limit=10)
        
        if not listings:
            filters_text = []
            if region:
                filters_text.append(f"Region: **{region.upper()}**")
            if queue_type:
                queue_name = QUEUE_TYPES.get(queue_type, {}).get('name', queue_type)
                filters_text.append(f"Queue: **{queue_name}**")
            
            message = "❌ No active listings found"
            if filters_text:
                message += f" with filters: {', '.join(filters_text)}"
            message += "\n\nTry removing some filters or create your own listing with `/lfg`!"
            
            await interaction.response.send_message(
                message,
                ephemeral=True
            )
            return
        
        # Create embed with listings
        embed = discord.Embed(
            title="📋 Active LFG Listings",
            description=f"Found {len(listings)} listings",
            color=discord.Color.blue()
        )
        
        for listing in listings[:5]:  # Show first 5
            queue_name = QUEUE_TYPES[listing['queue_type']]['name']
            roles_text = ' '.join([get_role_emoji(r) for r in listing['roles_needed']])
            
            value = (
                f"**{listing['riot_id_game_name']}#{listing['riot_id_tagline']}**\n"
                f"{roles_text} • {listing['region'].upper()}"
            )
            
            if listing.get('solo_rank'):
                value += f" • {format_rank_with_emoji(listing['solo_rank'])}"
            
            embed.add_field(
                name=f"{QUEUE_TYPES[listing['queue_type']]['emoji']} {queue_name}",
                value=value,
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="lfghelp", description="How to use the LFG system")
    async def lfghelp(self, interaction: discord.Interaction):
        """Show comprehensive help for LFG system."""
        embed = discord.Embed(
            title="🎮 How to Find Teammates",
            description="Quick guide to using the LFG system!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🚀 Quick Start (3 steps)",
            value="**1.** `/lfgsetup` - Create your profile (1 min)\n"
                  "**2.** `/lfg` - Create listing to find players\n"
                  "**3.** `/lfgbrowse` - See who's looking for teammates",
            inline=False
        )
        
        embed.add_field(
            name="👤 Your Profile",
            value="• `/lfgprofile` - View your profile\n"
                  "• `/lfgprofile @user` - Check someone's profile\n"
                  "• `/lfgedit` - Change your settings",
            inline=False
        )
        
        embed.add_field(
            name="🎯 Finding Teammates",
            value="• `/lfgbrowse` - See all listings\n"
                  "• `/lfgbrowse queue_type:ranked_solo` - Filter by mode\n"
                  "• `/lfgbrowse region:eune` - Filter by region",
            inline=False
        )
        
        embed.add_field(
            name="⏱️ Important Info",
            value="• Listings expire after **24 hours**\n"
                  "• Use autocomplete for easy selection\n"
                  "• Your profile links to your LoL account",
            inline=False
        )
        
        embed.set_footer(text="Need more help? Ask a moderator!")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ================================
#    PROFILE LIST SYSTEM
# ================================

class ProfileListView(View):
    """Pagination view for profile list."""
    
    def __init__(self, bot: commands.Bot, page: int = 0):
        super().__init__(timeout=None)  # Persistent view
        self.bot = bot
        self.page = page
        self.profiles_per_page = PROFILES_PER_PAGE
        
        # Update button states
        self.update_buttons()
    
    def update_buttons(self):
        """Update button states based on current page."""
        total_profiles = get_lfg_profiles_count()
        total_pages = (total_profiles + self.profiles_per_page - 1) // self.profiles_per_page
        
        # Disable/enable buttons
        self.previous_button.disabled = (self.page == 0)
        self.next_button.disabled = (self.page >= total_pages - 1)
        
        # Update page label
        self.page_label.label = f"Page {self.page + 1}/{max(1, total_pages)}"
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary, custom_id="profile_list_prev")
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        """Go to previous page."""
        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            embed = await self.create_profile_list_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.primary, custom_id="profile_list_page", disabled=True)
    async def page_label(self, interaction: discord.Interaction, button: Button):
        """Page indicator (disabled button)."""
        await interaction.response.defer()
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary, custom_id="profile_list_next")
    async def next_button(self, interaction: discord.Interaction, button: Button):
        """Go to next page."""
        total_profiles = get_lfg_profiles_count()
        total_pages = (total_profiles + self.profiles_per_page - 1) // self.profiles_per_page
        
        if self.page < total_pages - 1:
            self.page += 1
            self.update_buttons()
            embed = await self.create_profile_list_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.success, custom_id="profile_list_refresh", row=1)
    async def refresh_button(self, interaction: discord.Interaction, button: Button):
        """Refresh the profile list."""
        self.update_buttons()
        embed = await self.create_profile_list_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def create_profile_list_embed(self) -> discord.Embed:
        """Create embed with profile list for current page."""
        offset = self.page * self.profiles_per_page
        profiles = get_all_lfg_profiles(limit=self.profiles_per_page, offset=offset)
        total_profiles = get_lfg_profiles_count()
        
        embed = discord.Embed(
            title="🎮 LFG Profile List",
            description=f"All registered players in the LFG system\nUse `/lfg_setup` to register!",
            color=COLORS['profile'],
            timestamp=datetime.now()
        )
        
        if not profiles:
            embed.add_field(
                name="📭 No profiles",
                value="No one has registered yet. Be the first!",
                inline=False
            )
        else:
            for profile in profiles:
                # Get user from Discord
                try:
                    user = await self.bot.fetch_user(profile['user_id'])
                    user_mention = user.mention
                except:
                    user_mention = f"<@{profile['user_id']}>"
                
                # Format roles with custom emojis
                roles_text = ' '.join([
                    get_role_emoji(r) for r in profile['primary_roles']
                ]) or "None"
                
                # Format ranks with custom emojis
                ranks = []
                if profile.get('solo_rank'):
                    ranks.append(f"Solo: {format_rank_with_emoji(profile['solo_rank'])}")
                if profile.get('flex_rank'):
                    ranks.append(f"Flex: {format_rank_with_emoji(profile['flex_rank'])}")
                if profile.get('arena_rank'):
                    ranks.append(f"Arena: {format_rank_with_emoji(profile['arena_rank'])}")
                rank_text = ' • '.join(ranks) if ranks else f"{RANK_EMOJIS.get('UNRANKED', '🎮')} Unranked"
                
                # Format playstyle
                playstyle_emoji = ""
                if profile.get('playstyle'):
                    playstyle_emoji = PLAYSTYLES.get(profile['playstyle'], {}).get('emoji', '')
                
                # Voice indicator
                voice_emoji = "🎤" if profile.get('voice_required') else "🔇"
                
                field_value = (
                    f"{user_mention} • {profile['riot_id_game_name']}#{profile['riot_id_tagline']}\n"
                    f"{roles_text} • {profile['region'].upper()} • {voice_emoji}\n"
                    f"{rank_text}"
                )
                
                if playstyle_emoji:
                    field_value += f" • {playstyle_emoji}"
                
                embed.add_field(
                    name=f"#{offset + profiles.index(profile) + 1}",
                    value=field_value,
                    inline=False
                )
        
        # Footer with stats
        total_pages = (total_profiles + self.profiles_per_page - 1) // self.profiles_per_page
        embed.set_footer(text=f"Page {self.page + 1}/{max(1, total_pages)} • Total profiles: {total_profiles}")
        
        return embed


async def setup_help_message(bot: commands.Bot):
    """Setup persistent help/commands message."""
    try:
        channel = bot.get_channel(LFG_PROFILES_CHANNEL_ID)
        if not channel:
            logger.error(f"❌ Channel {LFG_PROFILES_CHANNEL_ID} not found!")
            return
        
        # Create help embed
        embed = discord.Embed(
            title="🎮 League of Legends LFG System",
            description="Looking For Group - Find teammates for ranked, normals, ARAM and more!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🎯 Getting Started",
            value="1️⃣ `/lfgsetup riot_id region` - Create your LFG profile\n"
                  "2️⃣ `/lfg` - Create a listing to find teammates\n"
                  "3️⃣ `/lfgbrowse` - Browse active listings",
            inline=False
        )
        
        embed.add_field(
            name="👤 Profile Commands",
            value="• `/lfgprofile` - View your profile\n"
                  "• `/lfgprofile @user` - View someone's profile\n"
                  "• `/lfgedit` - Edit your profile settings",
            inline=False
        )
        
        embed.add_field(
            name="🔍 Browse & Filter",
            value="• `/lfgbrowse` - All active listings\n"
                  "• `/lfgbrowse queue_type:ranked_solo` - Filter by queue\n"
                  "• `/lfgbrowse region:eune` - Filter by region\n"
                  "• Use autocomplete for easy selection!",
            inline=False
        )
        
        embed.add_field(
            name="🎮 Queue Types",
            value="👤 Ranked Solo/Duo • 👥 Ranked Flex\n"
                  "🎮 Normal Draft • ❄️ ARAM • ⚔️ Arena",
            inline=True
        )
        
        embed.add_field(
            name="🎭 Roles",
            value=f"{ROLE_EMOJIS.get('TOP', '⬆️')} Top\n"
                  f"{ROLE_EMOJIS.get('JUNGLE', '🌳')} Jungle\n"
                  f"{ROLE_EMOJIS.get('MIDDLE', '✨')} Mid\n"
                  f"{ROLE_EMOJIS.get('BOTTOM', '🏹')} ADC\n"
                  f"{ROLE_EMOJIS.get('UTILITY', '🛡️')} Support",
            inline=True
        )
        
        embed.add_field(
            name="💡 Tips",
            value="• Setup takes only 1 minute!\n"
                  "• Your profile links to your LoL account\n"
                  "• Listings expire after 24 hours\n"
                  "• Use `/lfghelp` for detailed guide",
            inline=False
        )
        
        embed.set_footer(text="LFG listings will appear below this message")
        
        # Try to find existing message
        existing_message = None
        async for message in channel.history(limit=10):
            if message.author == bot.user and message.embeds:
                if "LFG System" in message.embeds[0].title:
                    existing_message = message
                    break
        
        if existing_message:
            await existing_message.edit(embed=embed)
            logger.info(f"✅ Updated existing help message")
        else:
            await channel.send(embed=embed)
            logger.info(f"✅ Created new help message")
        
    except Exception as e:
        logger.error(f"❌ Failed to setup help message: {e}")



async def setup(bot: commands.Bot, riot_api):
    """Setup function for loading the cog."""
    await bot.add_cog(LFGCommands(bot, riot_api))
