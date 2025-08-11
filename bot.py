import discord
from discord.ext import commands
from discord.ui import View, Button
from discord import PermissionOverwrite, app_commands
import re
import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

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
        self.tree.add_command(invite, guild=guild)
        self.tree.add_command(dpm, guild=guild)
        await self.tree.sync(guild=guild)

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

@discord.app_commands.command(name="setup_create_panel", description="Wyświetl panel do tworzenia kanałów głosowych")
async def setup_create_panel(interaction: discord.Interaction):
    view = CreateChannelView()
    await interaction.response.send_message("🎮 **Create Voice Channel**", view=view, ephemeral=True)

@bot.tree.command(name="invite", description="Invite a user to a temporary voice or text channel")
@app_commands.describe(user="User to invite")
async def invite(interaction: discord.Interaction, user: discord.Member):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("Ta komenda działa tylko na serwerze.", ephemeral=True)
        return

    category = discord.utils.get(guild.categories, name=TEMP_CHANNEL_CATEGORY_NAME)
    if not category:
        await interaction.response.send_message("Nie znaleziono kategorii tymczasowej.", ephemeral=True)
        return

    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel) or channel.category != category:
        await interaction.response.send_message("Ta komenda działa tylko w kanale tymczasowym.", ephemeral=True)
        return

    overwrite = channel.overwrites_for(user)
    overwrite.read_messages = True
    overwrite.send_messages = True
    await channel.set_permissions(user, overwrite=overwrite)

    await interaction.response.send_message(f"{user.mention} has been added to {channel.mention}", ephemeral=False)

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

    if name.startswith("Custom") or name.startswith("Arena") or name.startswith("ARAM"):
        number = extract_number(name)
        if not number:
            return
        owner = name.split()[-1]
        text_channel = get_text_channel(name.split()[0].lower(), number, owner)
        if len(voice_channel.members) == 0 and text_channel is not None:
            await voice_channel.delete()
            await text_channel.delete()
            log_channel = guild.get_channel(1398986567988674704)
            if log_channel:
                await log_channel.send(f"🕙 Auto-delete voice + text channel {voice_channel.name} due to empty voice channel.")

async def fetch_json(url):
    headers = {"X-Riot-Token": os.getenv("RIOT_API_KEY")}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return None
            return await resp.json()

@bot.tree.command(name="dpm", description="Get DPM stats for a League of Legends summoner.")
@app_commands.describe(summoner="Summoner name")
async def dpm(interaction: discord.Interaction, summoner: str):
    await interaction.response.defer()

    REGION_ROUTING = "europe"
    PLATFORM_ROUTING = "eun1"

    summoner_data = await fetch_json(f"https://{PLATFORM_ROUTING}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{summoner}")
    if not summoner_data:
        return await interaction.followup.send("❌ Nie znaleziono summoner'a.")

    puuid = summoner_data["puuid"]

    match_ids = await fetch_json(f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?count=10")
    if not match_ids:
        return await interaction.followup.send("❌ Brak gier do analizy.")

    total_dpm = 0
    last_match_data = None

    for idx, match_id in enumerate(match_ids):
        match_data = await fetch_json(f"https://{REGION_ROUTING}.api.riotgames.com/lol/match/v5/matches/{match_id}")
        if not match_data:
            continue

        player = next((p for p in match_data["info"]["participants"] if p["puuid"] == puuid), None)
        if not player:
            continue

        game_duration_min = match_data["info"]["gameDuration"] / 60
        dpm_value = player["totalDamageDealtToChampions"] / game_duration_min
        total_dpm += dpm_value

        if idx == 0:
            last_match_data = (match_id, match_data, player, dpm_value)

    avg_dpm = total_dpm / len(match_ids)

    role = last_match_data[2].get("teamPosition", "UNKNOWN")
    median_dpm_by_role = {
        "TOP": 500,
        "JUNGLE": 400,
        "MIDDLE": 550,
        "BOTTOM": 600,
        "UTILITY": 300,
        "UNKNOWN": 500
    }
    median_dpm = median_dpm_by_role.get(role.upper(), 500)

    dpm_score = (avg_dpm / median_dpm) * 100

    match_id, match_data, player, dpm_value = last_match_data
    team_kills = sum(t["kills"] for t in match_data["info"]["participants"] if t["teamId"] == player["teamId"])
    kp = ((player["kills"] + player["assists"]) / team_kills) * 100 if team_kills > 0 else 0
    vision_score = player.get("visionScore", 0)

    player_obj_participation = player.get("challenges", {}).get("teamObjectiveParticipation", 0) * 100

    embed = discord.Embed(
        title=f"DPM Stats — {summoner}",
        description=f"Ostatnia gra: **{match_id}**\nRola: **{role}**",
        color=discord.Color.blurple()
    )
    embed.add_field(name="DPM (ostatnia gra)", value=f"{dpm_value:.1f}", inline=True)
    embed.add_field(name="Średni DPM (10 gier)", value=f"{avg_dpm:.1f}", inline=True)
    embed.add_field(name="DPM Score", value=f"{dpm_score:.1f}%", inline=True)
    embed.add_field(name="Kill Participation", value=f"{kp:.1f}%", inline=True)
    embed.add_field(name="Vision Score", value=str(vision_score), inline=True)
    embed.add_field(name="Objective Participation", value=f"{player_obj_participation:.1f}%", inline=True)
    embed.set_footer(text="Dane z Riot API - przetwarzane lokalnie")

    await interaction.followup.send(embed=embed)

bot.run(os.getenv("DISCORD_TOKEN"))
