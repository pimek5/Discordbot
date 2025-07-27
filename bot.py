import discord
from discord.ext import commands
from discord.ui import View, Button
from discord import PermissionOverwrite
import re
import os

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Tu możesz synchronizować globalnie lub na konkretnym guildzie
        # await self.tree.sync()  # globalnie
        # Dla testów szybciej na serwerze podaj ID i odkomentuj poniżej
        # guild = discord.Object(id=123456789012345678)
        # await self.tree.sync(guild=guild)
        pass

bot = MyBot()

channel_counter = {
    "soloq": 1,
    "flexq": 1,
    "aram": 1,
    "arena": 1,
    "custom": 1
}

TEMP_CHANNEL_CATEGORY_NAME = "Temporary Channels"

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

        await guild.create_voice_channel(voice_name, category=category, user_limit=16)
        await create_temp_text_channel(guild, text_name, category, allowed_users=[interaction.user])

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

        await guild.create_voice_channel(name_main, category=category, user_limit=10)
        await guild.create_voice_channel(name_team1, category=category, user_limit=5)
        await guild.create_voice_channel(name_team2, category=category, user_limit=5)
        await create_temp_text_channel(guild, text_name, category, allowed_users=[interaction.user])

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

        await guild.create_voice_channel(name, category=category, user_limit=2)
        await interaction.response.send_message(f"✅ Created voice channel: **{name}**", ephemeral=True)

    @discord.ui.button(label="FlexQ", style=discord.ButtonStyle.green)
    async def flexq_button(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = await get_or_create_temp_category(guild)
        number = channel_counter["flexq"]
        channel_counter["flexq"] += 1
        name = f"FlexQ {number} {interaction.user.name}"

        await guild.create_voice_channel(name, category=category, user_limit=5)
        await interaction.response.send_message(f"✅ Created voice channel: **{name}**", ephemeral=True)

    @discord.ui.button(label="ARAMs", style=discord.ButtonStyle.green)
    async def aram_button(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = await get_or_create_temp_category(guild)
        number = channel_counter["aram"]
        channel_counter["aram"] += 1

        voice_name = f"ARAM {number} {interaction.user.name}"
        text_name = f"aram-{number}-{interaction.user.name}".lower().replace(" ", "-")

        await guild.create_voice_channel(voice_name, category=category, user_limit=5)
        await create_temp_text_channel(guild, text_name, category, allowed_users=[interaction.user])

        await interaction.response.send_message(f"✅ Created voice + text: **{voice_name}** / #{text_name}", ephemeral=True)

    @discord.ui.button(label="Custom", style=discord.ButtonStyle.blurple)
    async def custom_button(self, interaction: discord.Interaction, button: Button):
        view = CustomSubMenu(user=interaction.user)
        await interaction.response.send_message("🔧 Choose Custom option:", view=view, ephemeral=True)

@bot.tree.command(name="setup_create_panel", description="Wyświetl panel do tworzenia kanałów głosowych")
async def setup_create_panel(interaction: discord.Interaction):
    view = CreateChannelView()
    await interaction.response.send_message("🎮 **Create Voice Channel**", view=view, ephemeral=True)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    try:
        await bot.tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

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

    # Handle Custom + Team1 + Team2 set
    if name.startswith("Custom") or name.startswith("Team1") or name.startswith("Team2"):
        number = extract_number(name)
        if number is None:
            return

        owner = name.split(" ", 2)[-1] if " " in name and name.startswith("Custom") else None
        names = [f"Custom {number} {owner}", f"Team1 {number}", f"Team2 {number}"]
        channels = [discord.utils.get(guild.voice_channels, name=n) for n in names]

        if all(c and len(c.members) == 0 for c in channels):
            for c in channels:
                if c:
                    await c.delete()
            if owner:
                txt = get_text_channel("custom", number, owner)
                if txt:
                    await txt.delete()
        return

    # Arena
    if name.startswith("Arena"):
        number = extract_number(name)
        owner = name.split(" ", 2)[-1]
        if len(voice_channel.members) == 0:
            await voice_channel.delete()
            txt = get_text_channel("arena", number, owner)
            if txt:
                await txt.delete()
        return

    # ARAM
    if name.startswith("ARAM"):
        number = extract_number(name)
        owner = name.split(" ", 2)[-1]
        if len(voice_channel.members) == 0:
            await voice_channel.delete()
            txt = get_text_channel("aram", number, owner)
            if txt:
                await txt.delete()
        return

    # Normal cases
    if len(voice_channel.members) == 0:
        await voice_channel.delete()

import os

bot.run(os.getenv("BOT_TOKEN"))
