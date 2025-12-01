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
    cleanup_expired_listings
)
from .config import LFG_CHANNEL_ID, LISTING_EXPIRATION_HOURS, COLORS

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
    'top': {'emoji': '⬆️', 'name': 'Top'},
    'jungle': {'emoji': '🌳', 'name': 'Jungle'},
    'mid': {'emoji': '✨', 'name': 'Mid'},
    'adc': {'emoji': '🏹', 'name': 'ADC'},
    'support': {'emoji': '🛡️', 'name': 'Support'}
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
#       PROFILE SETUP VIEWS
# ================================

class RoleSelectView(View):
    """Interactive view for selecting roles."""
    
    def __init__(self, riot_api, user_id: int, game_name: str, tagline: str, region: str):
        super().__init__(timeout=300)
        self.riot_api = riot_api
        self.user_id = user_id
        self.game_name = game_name
        self.tagline = tagline
        self.region = region
        self.selected_roles = []
        
        # Add role buttons
        for role_id, role_data in ROLES.items():
            button = Button(
                label=role_data['name'],
                emoji=role_data['emoji'],
                style=discord.ButtonStyle.secondary,
                custom_id=f"role_{role_id}"
            )
            button.callback = self.role_button_callback
            self.add_item(button)
        
        # Add confirm button
        confirm_btn = Button(
            label="Potwierdź",
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
                    "❌ Możesz wybrać maksymalnie 3 role!",
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
                "❌ Musisz wybrać przynajmniej jedną rolę!",
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
                    "❌ Nie znaleziono konta Riot! Sprawdź swoją nazwę i tag.",
                    ephemeral=True
                )
                return
            
            puuid = account_data.get('puuid')
            
            # Get ranked data
            summoner_data = await self.riot_api.get_summoner_by_puuid(puuid, self.region)
            if not summoner_data:
                await interaction.followup.send(
                    "❌ Nie można pobrać danych z regionu.",
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
                puuid=puuid
            )
            
            if success:
                embed = discord.Embed(
                    title="✅ Profil LFG utworzony!",
                    description=f"**{self.game_name}#{self.tagline}**\n"
                                f"Region: **{self.region.upper()}**\n"
                                f"Role: {', '.join([ROLES[r]['emoji'] + ' ' + ROLES[r]['name'] for r in self.selected_roles])}",
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="📝 Dalsze kroki",
                    value="Użyj `/lfg_edit` aby uzupełnić swój profil:\n"
                          "• Dodaj opis\n"
                          "• Ustaw preferencje voice/język\n"
                          "• Wybierz styl gry",
                    inline=False
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Update original message
                await interaction.message.edit(
                    content="✅ Profil utworzony!",
                    view=None
                )
            else:
                await interaction.followup.send(
                    "❌ Wystąpił błąd podczas tworzenia profilu.",
                    ephemeral=True
                )
        
        except Exception as e:
            logger.error(f"Error in profile creation: {e}")
            await interaction.followup.send(
                "❌ Wystąpił błąd podczas łączenia z Riot API.",
                ephemeral=True
            )


class ProfileEditView(View):
    """View for editing profile settings."""
    
    def __init__(self, user_id: int, current_profile: dict):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.current_profile = current_profile
    
    @discord.ui.button(label="Zmień role", emoji="🎭", style=discord.ButtonStyle.primary, row=0)
    async def change_roles(self, interaction: discord.Interaction, button: Button):
        """Change role preferences."""
        # TODO: Implement role change modal
        await interaction.response.send_message("🚧 W trakcie budowy", ephemeral=True)
    
    @discord.ui.button(label="Dodaj opis", emoji="📝", style=discord.ButtonStyle.primary, row=0)
    async def edit_description(self, interaction: discord.Interaction, button: Button):
        """Edit profile description."""
        modal = ProfileDescriptionModal(self.user_id, self.current_profile.get('description', ''))
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Preferencje głosowe", emoji="🎤", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_voice(self, interaction: discord.Interaction, button: Button):
        """Toggle voice requirement."""
        current_voice = self.current_profile.get('voice_required', False)
        new_voice = not current_voice
        
        update_lfg_profile(self.user_id, voice_required=new_voice)
        self.current_profile['voice_required'] = new_voice
        
        await interaction.response.send_message(
            f"✅ Voice {'wymagany' if new_voice else 'opcjonalny'}",
            ephemeral=True
        )
    
    @discord.ui.button(label="Styl gry", emoji="🎮", style=discord.ButtonStyle.secondary, row=1)
    async def change_playstyle(self, interaction: discord.Interaction, button: Button):
        """Change playstyle preference."""
        view = PlaystyleSelectView(self.user_id)
        await interaction.response.send_message(
            "Wybierz swój styl gry:",
            view=view,
            ephemeral=True
        )


class ProfileDescriptionModal(discord.ui.Modal, title="Opis profilu"):
    """Modal for editing profile description."""
    
    description = discord.ui.TextInput(
        label="Opis",
        placeholder="Napisz coś o sobie, swoim stylu gry, preferowanych championach...",
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
            "✅ Opis zaktualizowany!",
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
            f"✅ Styl gry ustawiony na: **{style_name}**",
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
            placeholder="Wybierz typ gry",
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
            label="Voice opcjonalny",
            emoji="🎤",
            style=discord.ButtonStyle.secondary,
            custom_id="voice_toggle",
            row=2
        )
        voice_btn.callback = self.voice_callback
        self.add_item(voice_btn)
        
        # Add create button
        create_btn = Button(
            label="Utwórz ogłoszenie",
            style=discord.ButtonStyle.success,
            custom_id="create",
            row=2
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
                    "❌ Maksymalnie 4 role!",
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
            button.label = "Voice wymagany"
            button.style = discord.ButtonStyle.primary
        else:
            button.label = "Voice opcjonalny"
            button.style = discord.ButtonStyle.secondary
        
        await interaction.response.edit_message(view=self)
    
    async def create_callback(self, interaction: discord.Interaction):
        """Create the listing."""
        if not self.queue_type:
            await interaction.response.send_message(
                "❌ Wybierz typ gry!",
                ephemeral=True
            )
            return
        
        if not self.roles_needed:
            await interaction.response.send_message(
                "❌ Wybierz przynajmniej jedną rolę!",
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
                "❌ Nie udało się utworzyć ogłoszenia.",
                ephemeral=True
            )
            return
        
        # Create public embed
        embed = create_listing_embed(self.profile, self.queue_type, self.roles_needed, self.voice_required, listing_id)
        view = ListingActionView(listing_id, self.user_id)
        
        # Post to channel
        channel = interaction.guild.get_channel(LFG_CHANNEL_ID)
        if channel:
            message = await channel.send(embed=embed, view=view)
            update_listing_status(listing_id, 'active', message.id)
        else:
            await interaction.followup.send(
                f"⚠️ Nie znaleziono kanału LFG (ID: {LFG_CHANNEL_ID}). Skontaktuj się z administratorem.",
                ephemeral=True
            )
            return
        
        await interaction.followup.send(
            "✅ Ogłoszenie utworzone!",
            ephemeral=True
        )
        
        await interaction.message.edit(content="✅ Ogłoszenie utworzone!", view=None)


def create_listing_embed(profile: dict, queue_type: str, roles_needed: list, voice_required: bool, listing_id: int) -> discord.Embed:
    """Create embed for LFG listing."""
    queue_name = QUEUE_TYPES[queue_type]['name']
    queue_emoji = QUEUE_TYPES[queue_type]['emoji']
    
    embed = discord.Embed(
        title=f"{queue_emoji} {queue_name}",
        description=f"**{profile['riot_id_game_name']}#{profile['riot_id_tagline']}** szuka graczy!",
        color=COLORS['listing'],
        timestamp=datetime.now()
    )
    
    roles_text = ' '.join([f"{ROLES[r]['emoji']} {ROLES[r]['name']}" for r in roles_needed])
    embed.add_field(
        name="🎭 Poszukiwane role",
        value=roles_text,
        inline=False
    )
    
    embed.add_field(
        name="🌍 Region",
        value=profile['region'].upper(),
        inline=True
    )
    
    if profile.get('solo_rank'):
        embed.add_field(
            name="🏆 Ranga",
            value=profile['solo_rank'],
            inline=True
        )
    
    embed.add_field(
        name="🎤 Voice",
        value="Wymagany" if voice_required else "Opcjonalny",
        inline=True
    )
    
    if profile.get('description'):
        embed.add_field(
            name="📝 O graczu",
            value=profile['description'][:200],
            inline=False
        )
    
    embed.set_footer(text=f"ID: {listing_id}")
    
    return embed


class ListingActionView(View):
    """Buttons for interacting with listings."""
    
    def __init__(self, listing_id: int, creator_id: int):
        super().__init__(timeout=None)  # Persistent view
        self.listing_id = listing_id
        self.creator_id = creator_id
    
    @discord.ui.button(label="Dołącz", emoji="✅", style=discord.ButtonStyle.success, custom_id="join")
    async def join_button(self, interaction: discord.Interaction, button: Button):
        """Join the group."""
        # TODO: Implement join logic with application system
        await interaction.response.send_message(
            "✅ Aplikacja wysłana! Twórca grupy otrzymał powiadomienie.",
            ephemeral=True
        )
    
    @discord.ui.button(label="Zamknij", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="close")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        """Close the listing (creator only)."""
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message(
                "❌ Tylko twórca może zamknąć ogłoszenie!",
                ephemeral=True
            )
            return
        
        update_listing_status(self.listing_id, 'filled')
        
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.greyple()
        embed.set_footer(text=f"ID: {self.listing_id} • Zamknięte")
        
        await interaction.message.edit(embed=embed, view=None)
        await interaction.response.send_message(
            "✅ Ogłoszenie zamknięte!",
            ephemeral=True
        )


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
    
    @app_commands.command(name="lfg_setup", description="Utwórz swój profil LFG")
    async def lfg_setup(
        self,
        interaction: discord.Interaction,
        game_name: str,
        tagline: str,
        region: str
    ):
        """Create LFG profile with interactive setup."""
        # Check if profile exists
        existing = get_lfg_profile(interaction.user.id)
        if existing:
            await interaction.response.send_message(
                "❌ Masz już profil! Użyj `/lfg_edit` aby go edytować.",
                ephemeral=True
            )
            return
        
        # Validate region
        region = region.lower()
        if region not in REGIONS:
            await interaction.response.send_message(
                f"❌ Nieprawidłowy region! Dostępne: {', '.join(REGIONS.keys())}",
                ephemeral=True
            )
            return
        
        # Show role selection view
        view = RoleSelectView(self.riot_api, interaction.user.id, game_name, tagline, region)
        
        embed = discord.Embed(
            title="🎭 Wybierz swoje role",
            description=f"**{game_name}#{tagline}** ({region.upper()})\n\n"
                        "Wybierz do 3 ról, które preferujesz grać:",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="lfg_profile", description="Wyświetl profil LFG")
    async def lfg_profile(
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
                    "❌ Nie masz profilu LFG! Użyj `/lfg_setup` aby go utworzyć.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ {target_user.mention} nie ma profilu LFG.",
                    ephemeral=True
                )
            return
        
        # Create profile embed
        embed = discord.Embed(
            title=f"👤 Profil LFG: {profile['riot_id_game_name']}#{profile['riot_id_tagline']}",
            color=discord.Color.blue()
        )
        
        # Roles
        roles_text = ' '.join([
            f"{ROLES[r]['emoji']} {ROLES[r]['name']}"
            for r in profile['primary_roles']
        ])
        embed.add_field(name="🎭 Role", value=roles_text or "Brak", inline=False)
        
        # Region & Ranks
        embed.add_field(name="🌍 Region", value=profile['region'].upper(), inline=True)
        
        if profile.get('solo_rank'):
            embed.add_field(name="🏆 Solo/Duo", value=profile['solo_rank'], inline=True)
        
        if profile.get('flex_rank'):
            embed.add_field(name="👥 Flex", value=profile['flex_rank'], inline=True)
        
        # Preferences
        prefs = []
        if profile.get('voice_required'):
            prefs.append("🎤 Voice wymagany")
        if profile.get('playstyle'):
            style_name = PLAYSTYLES.get(profile['playstyle'], {}).get('name', profile['playstyle'])
            prefs.append(f"🎮 {style_name}")
        
        if prefs:
            embed.add_field(name="⚙️ Preferencje", value='\n'.join(prefs), inline=False)
        
        # Description
        if profile.get('description'):
            embed.add_field(name="📝 Opis", value=profile['description'], inline=False)
        
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.set_footer(text=f"Utworzony: {profile['created_at'].strftime('%Y-%m-%d')}")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="lfg_edit", description="Edytuj swój profil LFG")
    async def lfg_edit(self, interaction: discord.Interaction):
        """Edit LFG profile."""
        profile = get_lfg_profile(interaction.user.id)
        
        if not profile:
            await interaction.response.send_message(
                "❌ Nie masz profilu LFG! Użyj `/lfg_setup` aby go utworzyć.",
                ephemeral=True
            )
            return
        
        view = ProfileEditView(interaction.user.id, profile)
        
        embed = discord.Embed(
            title="✏️ Edytuj profil LFG",
            description="Wybierz, co chcesz zmienić:",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="lfg_post", description="Utwórz ogłoszenie LFG")
    async def lfg_post(self, interaction: discord.Interaction):
        """Create LFG listing."""
        profile = get_lfg_profile(interaction.user.id)
        
        if not profile:
            await interaction.response.send_message(
                "❌ Najpierw utwórz profil używając `/lfg_setup`!",
                ephemeral=True
            )
            return
        
        view = CreateListingView(interaction.user.id, profile)
        
        embed = discord.Embed(
            title="📝 Utwórz ogłoszenie LFG",
            description="Skonfiguruj swoje ogłoszenie:",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="lfg_browse", description="Przeglądaj ogłoszenia LFG")
    async def lfg_browse(
        self,
        interaction: discord.Interaction,
        queue_type: Optional[str] = None,
        region: Optional[str] = None
    ):
        """Browse active LFG listings."""
        listings = get_active_listings(region=region, queue_type=queue_type, limit=10)
        
        if not listings:
            await interaction.response.send_message(
                "❌ Brak aktywnych ogłoszeń z tymi filtrami.",
                ephemeral=True
            )
            return
        
        # Create embed with listings
        embed = discord.Embed(
            title="📋 Aktywne ogłoszenia LFG",
            description=f"Znaleziono {len(listings)} ogłoszeń",
            color=discord.Color.blue()
        )
        
        for listing in listings[:5]:  # Show first 5
            queue_name = QUEUE_TYPES[listing['queue_type']]['name']
            roles_text = ' '.join([ROLES[r]['emoji'] for r in listing['roles_needed']])
            
            value = (
                f"**{listing['riot_id_game_name']}#{listing['riot_id_tagline']}**\n"
                f"{roles_text} • {listing['region'].upper()}"
            )
            
            if listing.get('solo_rank'):
                value += f" • {listing['solo_rank']}"
            
            embed.add_field(
                name=f"{QUEUE_TYPES[listing['queue_type']]['emoji']} {queue_name}",
                value=value,
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot, riot_api):
    """Setup function for loading the cog."""
    await bot.add_cog(LFGCommands(bot, riot_api))
