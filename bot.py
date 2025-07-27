import discord
from discord.ext import commands
from discord.ui import View, Button
from discord import PermissionOverwrite, app_commands
from typing import List  # zamiast Greedy importujemy List
import re
import os
import asyncio

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True

MAX_INVITE_USERS = 16
TEMP_CHANNEL_CATEGORY_NAME = "Temporary Channels"

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        guild = discord.Object(id=1153027935553454191)
        self.tree.add_command(setup_create_panel, guild=guild)
        self.tree.add_command(invite, guild=guild)  # Dodajemy komendę invite
        await self.tree.sync(guild=guild)
        print("Slash commands synced in setup_hook.")

bot = MyBot()

channel_counter = {
    "soloq": 1,
    "flexq": 1,
    "aram": 1,
    "arena": 1,
    "custom": 1
}

def extract_number(name):
    match = re.search(r"\b(\d+)\b", name)
    return match.group(1) if match else None

async def get_or_create_temp_category(guild):
    category = discord.utils.get(guild.categories, name=TEMP_CHANNEL_CATEGORY_NAME)
    if not category:
        category = await guild.create_category(name=TEMP_CHANNEL_CATEGORY_NAME)
    return category

async def create_temp_text_channel(guild, name, category, allowed_users=None):
    overwrites = {
        guild.default_role: PermissionOverwrite(read_messages=False)
    }
    if allowed_users:
        for user in allowed_users:
            overwrites[user] = PermissionOverwrite(read_messages=True, send_messages=True)
    return await guild.create_text_channel(name, category=category, overwrites=overwrites)

async def schedule_auto_delete_if_empty(voice_channel: discord.VoiceChannel, text_channel: discord.TextChannel = None):
    await asyncio.sleep(10)
    if len(voice_channel.members) == 0:
        await voice_channel.delete()
        if text_channel:
            await text_channel.delete()
        log_channel = voice_channel.guild.get_channel(1398986567988674704)
        if log_channel:
            await log_channel.send(f"🕙 Auto-deleted empty channel `{voice_channel.name}` after 10s.")

class CustomSubMenu(View):
    def __init__(self, user):
        super().__init__(timeout=60)
        self.user = user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.user

    @discord.ui.button(label="Arena (max 16)", style=discord.ButtonStyle.blurple)
    async def arena_button(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = await get_or_create_temp_category(guild)
        number = channel_counter["arena"]
        channel_counter["arena"] += 1

        voice_name = f"Arena {number} {interaction.user.name}"
        text_name = f"arena-{number}-{interaction.user.name}".lower().replace(" ", "-")

        vc = await guild.create_voice_channel(voice_name, category=category, user_limit=16)
        tc = await create_temp_text_channel(guild, text_name, category, allowed_users=[interaction.user])

        asyncio.create_task(schedule_auto_delete_if_empty(vc, tc))

        await interaction.response.send_message(f"✅ Created voice + text: **{voice_name}** / #{text_name}", ephemeral=True)

    @discord.ui.button(label="Custom (max 10)", style=discord.ButtonStyle.blurple)
    async def custom_button(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = await get_or_create_temp_category(guild)
        number = channel_counter["custom"]
        channel_counter["custom"] += 1

        name_main = f"Custom {number} {interaction.user.name}"
        name_team1 = f"Team1 {number}"
        name_team2 = f"Team2 {number}"
        text_name = f"custom-{number}-{interaction.user.name}".lower().replace(" ", "-")

        vc_main = await guild.create_voice_channel(name_main, category=category, user_limit=10)
        vc_team1 = await guild.create_voice_channel(name_team1, category=category, user_limit=5)
        vc_team2 = await guild.create_voice_channel(name_team2, category=category, user_limit=5)
        tc = await create_temp_text_channel(guild, text_name, category, allowed_users=[interaction.user])

        asyncio.create_task(schedule_auto_delete_if_empty(vc_main, tc))
        asyncio.create_task(schedule_auto_delete_if_empty(vc_team1))
        asyncio.create_task(schedule_auto_delete_if_empty(vc_team2))

        await interaction.response.send_message(
            f"✅ Created custom setup:\n- **{name_main}** (10)\n- **{name_team1}**, **{name_team2}** (5)\n- **#{text_name}**",
            ephemeral=True
        )

class CreateChannelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="SoloQ", style=discord.ButtonStyle.green)
    async def soloq_button(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = await get_or_create_temp_category(guild)
        number = channel_counter["soloq"]
        channel_counter["soloq"] += 1
        name = f"SoloQ {number} {interaction.user.name}"

        vc = await guild.create_voice_channel(name, category=category, user_limit=2)
        asyncio.create_task(schedule_auto_delete_if_empty(vc))
        await interaction.response.send_message(f"✅ Created voice channel: **{name}**", ephemeral=True)

    @discord.ui.button(label="FlexQ", style=discord.ButtonStyle.green)
    async def flexq_button(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = await get_or_create_temp_category(guild)
        number = channel_counter["flexq"]
        channel_counter["flexq"] += 1
        name = f"FlexQ {number} {interaction.user.name}"

        vc = await guild.create_voice_channel(name, category=category, user_limit=5)
        asyncio.create_task(schedule_auto_delete_if_empty(vc))
        await interaction.response.send_message(f"✅ Created voice channel: **{name}**", ephemeral=True)

    @discord.ui.button(label="ARAMs", style=discord.ButtonStyle.green)
    async def aram_button(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = await get_or_create_temp_category(guild)
        number = channel_counter["aram"]
        channel_counter["aram"] += 1

        voice_name = f"ARAM {number} {interaction.user.name}"
        text_name = f"aram-{number}-{interaction.user.name}".lower().replace(" ", "-")

        vc = await guild.create_voice_channel(voice_name, category=category, user_limit=5)
        tc = await create_temp_text_channel(guild, text_name, category, allowed_users=[interaction.user])
        asyncio.create_task(schedule_auto_delete_if_empty(vc, tc))

        await interaction.response.send_message(f"✅ Created voice + text: **{voice_name}** / #{text_name}", ephemeral=True)

    @discord.ui.button(label="Custom", style=discord.ButtonStyle.blurple)
    async def custom_button(self, interaction: discord.Interaction, button: Button):
        view = CustomSubMenu(user=interaction.user)
        await interaction.response.send_message("🔧 Choose Custom option:", view=view, ephemeral=True)

@bot.tree.command(name="setup_create_panel", description="Wyświetl panel do tworzenia kanałów głosowych")
async def setup_create_panel(interaction: discord.Interaction):
    view = CreateChannelView()
    await interaction.response.send_message("🎮 **Create Voice Channel**", view=view, ephemeral=True)

# NOWA KOMENDA /invite
@bot.tree.command(name="invite", description="Dodaj użytkowników do aktualnego kanału tekstowego (max 16 osób)")
@app_commands.describe(users="Użytkownicy do dodania")
async def invite(interaction: discord.Interaction, users: List[discord.Member]):
    channel = interaction.channel
    guild = interaction.guild

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("Ta komenda działa tylko w kanałach tekstowych.", ephemeral=True)
        return

    # Sprawdź kategorię
    if not channel.category or channel.category.name != TEMP_CHANNEL_CATEGORY_NAME:
        await interaction.response.send_message("Ta komenda działa tylko w kanałach tymczasowych.", ephemeral=True)
        return

    # Pobierz obecnie mających dostęp użytkowników
    overwrites = channel.overwrites
    current_allowed_users = [user for user, perms in overwrites.items()
                             if isinstance(user, discord.Member) and perms.read_messages]

    if len(current_allowed_users) >= MAX_INVITE_USERS:
        await interaction.response.send_message(f"Limit {MAX_INVITE_USERS} osób już został osiągnięty.", ephemeral=True)
        return

    to_add = [u for u in users if u not in current_allowed_users]

    if len(current_allowed_users) + len(to_add) > MAX_INVITE_USERS:
        await interaction.response.send_message(f"Nie można dodać tylu użytkowników, limit to {MAX_INVITE_USERS}.", ephemeral=True)
        return

    for member in to_add:
        await channel.set_permissions(member, read_messages=True, send_messages=True)

    await interaction.response.send_message(f"Dodano {len(to_add)} użytkowników do kanału.", ephemeral=True)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel is None:
        return

    voice_channel = before.channel
    guild = voice_channel.guild
    category = discord.utils.get(guild.categories, name=TEMP_CHANNEL_CATEGORY_NAME)
    if voice_channel.category != category:
        return

    name = voice_channel.name

    def get_text_channel(prefix, number, owner):
        text_name = f"{prefix}-{number}-{owner}".lower().replace(" ", "-")
        return discord.utils.get(guild.text_channels, name=text_name)

    if voice_channel.user_limit == 2:
        # SoloQ
        number = extract_number(name)
        owner = name.split()[-1]
        text_channel = get_text_channel("soloq", number, owner)
        if voice_channel.id and text_channel and len(voice_channel.members) == 0:
            await voice_channel.delete()
            await text_channel.delete()

    elif voice_channel.user_limit == 5:
        # FlexQ or ARAM
        if name.startswith("FlexQ"):
            number = extract_number(name)
            owner = name.split()[-1]
            text_channel = get_text_channel("flexq", number, owner)
            if voice_channel.id and text_channel and len(voice_channel.members) == 0:
                await voice_channel.delete()
                await text_channel.delete()

        elif name.startswith("ARAM"):
            number = extract_number(name)
            owner = name.split()[-1]
            text_channel = get_text_channel("aram", number, owner)
            if voice_channel.id and text_channel and len(voice_channel.members) == 0:
                await voice_channel.delete()
                await text_channel.delete()

    elif voice_channel.user_limit == 10 and "Custom" in name:
        # Custom channels, kilka kanałów
        number = extract_number(name)
        owner = name.split()[-1]

        text_channel = get_text_channel("custom", number, owner)

        if voice_channel.id and text_channel and len(voice_channel.members) == 0:
            await voice_channel.delete()
            await text_channel.delete()

    elif voice_channel.user_limit == 16 and "Arena" in name:
        number = extract_number(name)
        owner = name.split()[-1]
        text_channel = get_text_channel("arena", number, owner)
        if voice_channel.id and text_channel and len(voice_channel.members) == 0:
            await voice_channel.delete()
            await text_channel.delete()

bot.run(os.getenv("TOKEN"))
