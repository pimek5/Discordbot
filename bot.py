import discord
from discord.ext import commands
from discord.ui import View, Button
from discord import PermissionOverwrite, app_commands
import re
import os
import asyncio
import requests 
from dotenv import load_dotenv
load_dotenv()

# ================================
#        INTENTS
# ================================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.messages = True
intents.message_content = True

# ================================
#        CONFIG
# ================================
MAX_INVITE_USERS = 16
TEMP_CHANNEL_CATEGORY_NAME = "Temporary Channels"

FIXES_CHANNEL_ID = 1372734313594093638
NOTIFY_ROLE_ID = 1173564965152637018
ISSUE_CHANNEL_ID = 1264484659765448804
LOG_CHANNEL_ID = 1408036991454417039

# ================================
#        BOT INIT
# ================================
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        guild = discord.Object(id=1153027935553454191)
        self.tree.add_command(setup_create_panel, guild=guild)
        self.tree.add_command(invite, guild=guild)
        self.tree.add_command(dpm_history_full, guild=guild)
        await self.tree.sync(guild=guild)

bot = MyBot()

# ================================
#        CHANNEL COUNTER
# ================================
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

# ================================
#        TEMP CHANNEL HELPERS
# ================================
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
        log_channel = voice_channel.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"🕙 Auto-deleted empty channel `{voice_channel.name}` after 10s.")

# ================================
#        CREATE CHANNEL VIEWS
# ================================
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

# ================================
#        INVITE COMMAND
# ================================
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

# ================================
#        DPM COMMAND (INTERAKTYWNY)
# ================================
from urllib.parse import quote

def region_mapping(region: str) -> str:
    mapping = {
        'euw1': 'europe',
        'eun1': 'europe',
        'na1': 'americas',
        'br1': 'americas',
        'la1': 'americas',
        'la2': 'americas',
        'kr': 'asia',
        'jp1': 'asia',
        'oc1': 'sea',
        'ru': 'europe'
    }
    return mapping.get(region.lower(), 'europe')

@bot.tree.command(name="dpm_history_full", description="Show last 20 matches with full interactive DPM stats")
@app_commands.describe(summoner="Summoner name", region="Region of the account (e.g. EUW1, NA1)")
async def dpm_history_full(interaction: discord.Interaction, summoner: str, region: str = "euw1"):
    await interaction.response.defer()
    BASE_URL = f"https://{region.lower()}.api.riotgames.com/lol"
    MATCH_BASE_URL = f"https://{region_mapping(region)}.api.riotgames.com/lol/match/v5/matches"
    HEADERS = {"X-Riot-Token": os.getenv("RIOT_API_KEY")}

    try:
        # 1. Pobierz dane summonera z zakodowaną nazwą
        summoner_safe = quote(summoner)
        summoner_resp = requests.get(f"{BASE_URL}/summoner/v4/summoners/by-name/{summoner_safe}", headers=HEADERS)
        if summoner_resp.status_code != 200:
            await interaction.edit_original_response(content="❌ Summoner not found.")
            return
        summoner_data = summoner_resp.json()
        puuid = summoner_data['puuid']

        # 2. Pobierz ostatnie 20 meczów
        matches_resp = requests.get(f"{MATCH_BASE_URL}/by-puuid/{puuid}/ids?count=20", headers=HEADERS)
        match_ids = matches_resp.json()
        matches_data = []

        for mid in match_ids:
            match_json = requests.get(f"{MATCH_BASE_URL}/{mid}", headers=HEADERS).json()
            participant = next((p for p in match_json['info']['participants'] if p['puuid'] == puuid), None)
            if participant:
                matches_data.append({
                    'champion': participant['championName'],
                    'kills': participant['kills'],
                    'deaths': participant['deaths'],
                    'assists': participant['assists'],
                    'totalDamage': participant['totalDamageDealtToChampions'],
                    'duration': match_json['info']['gameDuration'],
                    'win': participant['win'],
                    'queue': match_json['info'].get('gameMode','Unknown'),
                    'summonerName': participant['summonerName'],
                    'participantData': participant,
                    'matchId': match_json['metadata']['matchId']
                })

        if not matches_data:
            await interaction.edit_original_response(content="❌ No valid matches found.")
            return

        # 3. Stwórz view i wyświetl embed
        class PageButton(Button):
            def __init__(self, label, view, direction):
                super().__init__(label=label, style=discord.ButtonStyle.blurple)
                self.view_ref = view
                self.direction = direction

            async def callback(self, interaction: discord.Interaction):
                self.view_ref.page += self.direction
                await self.view_ref.update_embed()

        class MatchDetailButton(Button):
            def __init__(self, label, match_data):
                super().__init__(label=label, style=discord.ButtonStyle.green)
                self.match_data = match_data

            async def callback(self, interaction: discord.Interaction):
                participant = self.match_data['participantData']
                duration_min = self.match_data['duration']/60
                dpm_total = participant['totalDamageDealtToChampions']/duration_min
                dpm_physical = participant.get('physicalDamageDealtToChampions',0)/duration_min
                dpm_magic = participant.get('magicDamageDealtToChampions',0)/duration_min
                dpm_true = participant.get('trueDamageDealtToChampions',0)/duration_min

                items = [participant.get(f'item{i}',0) for i in range(7)]
                items_text = ", ".join(str(i) for i in items if i!=0) if any(items) else "None"
                spell1 = participant.get("summoner1Id","Unknown")
                spell2 = participant.get("summoner2Id","Unknown")
                keystone = participant.get("perks", {}).get("styles",[{}])[0].get("selections",[{}])[0].get("perk","Unknown")

                embed = discord.Embed(title=f"{participant['summonerName']} Full DPM", color=0x1F8B4C)
                embed.add_field(name="Champion", value=participant['championName'])
                embed.add_field(name="KDA", value=f"{participant['kills']}/{participant['deaths']}/{participant['assists']}")
                embed.add_field(name="DPM Total", value=round(dpm_total,1))
                embed.add_field(name="DPM Physical", value=round(dpm_physical,1))
                embed.add_field(name="DPM Magic", value=round(dpm_magic,1))
                embed.add_field(name="DPM True", value=round(dpm_true,1))
                embed.add_field(name="Items", value=items_text)
                embed.add_field(name="Summoner Spells", value=f"{spell1}, {spell2}")
                embed.add_field(name="Keystone Rune", value=keystone)
                embed.add_field(name="Result", value="Victory" if participant['win'] else "Defeat")
                embed.set_footer(text=f"Match ID: {self.match_data['matchId']}")

                await interaction.response.send_message(embed=embed, ephemeral=True)

        class MatchHistoryView(View):
            def __init__(self, interaction, matches_data):
                super().__init__(timeout=180)
                self.interaction = interaction
                self.matches_data = matches_data
                self.page = 0
                self.per_page = 5

            async def update_embed(self):
                start = self.page * self.per_page
                end = start + self.per_page
                page_matches = self.matches_data[start:end]

                description = ""
                self.clear_items()
                for idx, match in enumerate(page_matches, start=start+1):
                    champion = match['champion']
                    kda = f"{match['kills']}/{match['deaths']}/{match['assists']}"
                    result = "Victory" if match['win'] else "Defeat"
                    dpm = round(match['totalDamage']/ (match['duration']/60),1)
                    game_type = match.get('queue','Unknown')
                    description += f"**{idx}. {champion}** | KDA: {kda} | {result} | DPM: {dpm} | {game_type}\n"
                    self.add_item(MatchDetailButton(label=str(idx), match_data=match))

                if self.page > 0:
                    self.add_item(PageButton(label="Previous", view=self, direction=-1))
                if end < len(self.matches_data):
                    self.add_item(PageButton(label="Next", view=self, direction=1))

                embed = discord.Embed(
                    title=f"{self.matches_data[0]['summonerName']} - Last {len(self.matches_data)} Matches",
                    description=description,
                    color=0x1F8B4C
                )
                embed.set_footer(text=f"Page {self.page+1}/{(len(self.matches_data)-1)//self.per_page + 1}")
                await self.interaction.edit_original_response(embed=embed, view=self)

        view = MatchHistoryView(interaction, matches_data)
        await view.update_embed()

    except Exception as e:
        print(f"Error fetching DPM history: {e}")
        await interaction.edit_original_response(content="❌ Error fetching match history.")

# ================================
#        OTHER EVENTS
# ================================
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')

bot.run(os.getenv("BOT_TOKEN"))



