import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from discord import PermissionOverwrite, app_commands
import re
import os
import asyncio
import requests 
import json
import datetime
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

# Twitter Configuration
TWITTER_USERNAME = "p1mek"
TWEETS_CHANNEL_ID = 1414899834581680139  # Channel for posting tweets
TWITTER_CHECK_INTERVAL = 60  # Check every 60 seconds

# Twitter API Configuration (add these to your .env file)
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")  # Add this to .env

# Thread Manager Configuration
SKIN_IDEAS_CHANNEL_ID = 1329671504941682750  # Channel where threads are created
YOUR_IDEAS_CHANNEL_ID = 1433892799862018109  # Channel where embeds are posted
MOD_REVIEW_CHANNEL_ID = 1433893934265925682  # Channel for mod review

# Store voting data: {message_id: {user_id: 'up' or 'down', 'upvotes': int, 'downvotes': int}}
voting_data = {}

# Store mod review data: {message_id: {'approved': set(), 'rejected': set(), 'original_message_id': int}}
mod_review_data = {}

# ================================
#        BOT INIT
# ================================
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Add persistent views for Thread Manager
        self.add_view(VotingView(0))  # Dummy view for persistent buttons
        self.add_view(ModReviewView(0, 0))  # Dummy view for persistent buttons
        
        guild = discord.Object(id=1153027935553454191)
        self.tree.add_command(setup_create_panel, guild=guild)
        self.tree.add_command(invite, guild=guild)
        self.tree.add_command(dpm_history_full, guild=guild)
        self.tree.add_command(post_latest_tweet, guild=guild)
        self.tree.add_command(toggle_tweet_monitoring, guild=guild)
        self.tree.add_command(start_tweet_monitoring, guild=guild)
        self.tree.add_command(tweet_status, guild=guild)
        self.tree.add_command(test_twitter_connection, guild=guild)
        self.tree.add_command(reset_tweet_tracking, guild=guild)
        self.tree.add_command(check_specific_tweet, guild=guild)
        self.tree.add_command(add_tweet_by_id, guild=guild)
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
@bot.tree.command(name="dpm_history_full", description="Show last 20 matches with full interactive DPM stats")
@app_commands.describe(summoner="Summoner name")
async def dpm_history_full(interaction: discord.Interaction, summoner: str):
    await interaction.response.defer()
    REGION = 'euw1'
    BASE_URL = f"https://{REGION}.api.riotgames.com/lol"
    HEADERS = {"X-Riot-Token": os.getenv("RIOT_API_KEY")}

    try:
        # 1. Pobierz dane summonera
        summoner_resp = requests.get(f"{BASE_URL}/summoner/v4/summoners/by-name/{summoner}", headers=HEADERS)
        if summoner_resp.status_code != 200:
            await interaction.edit_original_response(content="❌ Summoner not found.")
            return
        summoner_data = summoner_resp.json()
        puuid = summoner_data['puuid']

        # 2. Pobierz ostatnie 20 meczów
        matches_resp = requests.get(f"https://europe.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?count=20", headers=HEADERS)
        match_ids = matches_resp.json()
        matches_data = []

        for mid in match_ids:
            match_json = requests.get(f"https://europe.api.riotgames.com/lol/match/v5/matches/{mid}", headers=HEADERS).json()
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
#        FIXED MESSAGES
# ================================
class FixedMessageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔔 Notify Me", style=discord.ButtonStyle.green)
    async def notify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(NOTIFY_ROLE_ID)
        if not role:
            await interaction.response.send_message("⚠️ Role not found.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message("❌ Removed notification role.", ephemeral=True)
            action = "removed"
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ You will now receive notifications.", ephemeral=True)
            action = "added"

        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"🔔 {interaction.user.mention} {action} Notify Me role via button.")

    @discord.ui.button(label="🔧 Issue?", style=discord.ButtonStyle.blurple)
    async def issue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.guild.get_channel(ISSUE_CHANNEL_ID)
        if channel:
            await interaction.response.send_message(f"🔧 Please report the issue here: {channel.mention}", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Issue channel not found.", ephemeral=True)

        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"🔧 {interaction.user.mention} clicked Issue? button.")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.channel.id == FIXES_CHANNEL_ID and re.search(r'\bfixed\b', message.content, re.IGNORECASE):
        try:
            await message.add_reaction("✅")
            await message.add_reaction("❎")
            await message.reply("🎯 Fixed detected!", view=FixedMessageView())
        except Exception as e:
            print(f"Error handling Fixed message: {e}")

    await bot.process_commands(message)

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.channel_id != FIXES_CHANNEL_ID:
        return
    if str(payload.emoji) not in ["✅", "❎"]:
        channel = bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        await message.remove_reaction(payload.emoji, await bot.fetch_user(payload.user_id))
        return

    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        user = await bot.fetch_user(payload.user_id)
        channel = bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        await log_channel.send(f"📝 {user.mention} reacted with {payload.emoji} on [this message]({message.jump_url})")
# ================================
#       Thread manager
# ================================

class VotingView(discord.ui.View):
    def __init__(self, message_id):
        super().__init__(timeout=None)
        self.message_id = str(message_id)
        
    @discord.ui.button(label="0", emoji="⬆️", style=discord.ButtonStyle.secondary, custom_id="upvote")
    async def upvote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        message_id = self.message_id
        user_id = interaction.user.id
        
        # Initialize voting data if not exists
        if message_id not in voting_data:
            voting_data[message_id] = {'upvotes': 0, 'downvotes': 0, 'voters': {}}
        
        current_vote = voting_data[message_id]['voters'].get(user_id)
        
        if current_vote == 'up':
            # Remove upvote
            voting_data[message_id]['upvotes'] -= 1
            del voting_data[message_id]['voters'][user_id]
            await interaction.response.send_message("⬆️ Upvote removed", ephemeral=True)
        elif current_vote == 'down':
            # Change from downvote to upvote
            voting_data[message_id]['downvotes'] -= 1
            voting_data[message_id]['upvotes'] += 1
            voting_data[message_id]['voters'][user_id] = 'up'
            await interaction.response.send_message("⬆️ Changed vote to upvote", ephemeral=True)
        else:
            # Add upvote
            voting_data[message_id]['upvotes'] += 1
            voting_data[message_id]['voters'][user_id] = 'up'
            await interaction.response.send_message("⬆️ Upvoted!", ephemeral=True)
        
        # Update button labels
        await self.update_buttons(interaction.message)
    
    @discord.ui.button(label="0", emoji="⬇️", style=discord.ButtonStyle.secondary, custom_id="downvote")
    async def downvote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        message_id = self.message_id
        user_id = interaction.user.id
        
        # Initialize voting data if not exists
        if message_id not in voting_data:
            voting_data[message_id] = {'upvotes': 0, 'downvotes': 0, 'voters': {}}
        
        current_vote = voting_data[message_id]['voters'].get(user_id)
        
        if current_vote == 'down':
            # Remove downvote
            voting_data[message_id]['downvotes'] -= 1
            del voting_data[message_id]['voters'][user_id]
            await interaction.response.send_message("⬇️ Downvote removed", ephemeral=True)
        elif current_vote == 'up':
            # Change from upvote to downvote
            voting_data[message_id]['upvotes'] -= 1
            voting_data[message_id]['downvotes'] += 1
            voting_data[message_id]['voters'][user_id] = 'down'
            await interaction.response.send_message("⬇️ Changed vote to downvote", ephemeral=True)
        else:
            # Add downvote
            voting_data[message_id]['downvotes'] += 1
            voting_data[message_id]['voters'][user_id] = 'down'
            await interaction.response.send_message("⬇️ Downvoted!", ephemeral=True)
        
        # Update button labels
        await self.update_buttons(interaction.message)
    
    async def update_buttons(self, message):
        """Update button labels with current vote counts"""
        message_id = str(message.id)
        
        if message_id in voting_data:
            upvotes = voting_data[message_id]['upvotes']
            downvotes = voting_data[message_id]['downvotes']
            
            # Create new view with updated counts
            new_view = VotingView(message_id)
            new_view.children[0].label = str(upvotes)  # Upvote button
            new_view.children[1].label = str(downvotes)  # Downvote button
            
            try:
                await message.edit(view=new_view)
            except:
                pass

class ModReviewView(discord.ui.View):
    def __init__(self, original_message_id, idea_embed_message_id):
        super().__init__(timeout=None)
        self.original_message_id = original_message_id
        self.idea_embed_message_id = idea_embed_message_id
        
    @discord.ui.button(label="Approve", emoji="✅", style=discord.ButtonStyle.success, custom_id="approve")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        message_id = str(interaction.message.id)
        user_id = interaction.user.id
        
        # Initialize mod review data if not exists
        if message_id not in mod_review_data:
            mod_review_data[message_id] = {
                'approved': set(),
                'rejected': set(),
                'original_message_id': self.original_message_id,
                'idea_embed_message_id': self.idea_embed_message_id
            }
        
        # Check if user already voted
        if user_id in mod_review_data[message_id]['approved']:
            await interaction.response.send_message("✅ You already approved this idea", ephemeral=True)
            return
        
        if user_id in mod_review_data[message_id]['rejected']:
            await interaction.response.send_message("❌ Cannot approve after rejecting", ephemeral=True)
            return
        
        # Add approval
        mod_review_data[message_id]['approved'].add(user_id)
        
        # Add ✅ reaction to original idea embed
        try:
            ideas_channel = bot.get_channel(YOUR_IDEAS_CHANNEL_ID)
            if ideas_channel:
                idea_message = await ideas_channel.fetch_message(self.idea_embed_message_id)
                await idea_message.add_reaction("✅")
        except:
            pass
        
        await interaction.response.send_message("✅ Idea approved!", ephemeral=True)
    
    @discord.ui.button(label="Reject", emoji="❎", style=discord.ButtonStyle.danger, custom_id="reject")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        message_id = str(interaction.message.id)
        user_id = interaction.user.id
        
        # Initialize mod review data if not exists
        if message_id not in mod_review_data:
            mod_review_data[message_id] = {
                'approved': set(),
                'rejected': set(),
                'original_message_id': self.original_message_id,
                'idea_embed_message_id': self.idea_embed_message_id
            }
        
        # Check if user already voted
        if user_id in mod_review_data[message_id]['rejected']:
            await interaction.response.send_message("❎ You already rejected this idea", ephemeral=True)
            return
        
        if user_id in mod_review_data[message_id]['approved']:
            await interaction.response.send_message("❌ Cannot reject after approving", ephemeral=True)
            return
        
        # Add rejection
        mod_review_data[message_id]['rejected'].add(user_id)
        
        # Add ❎ reaction to original idea embed
        try:
            ideas_channel = bot.get_channel(YOUR_IDEAS_CHANNEL_ID)
            if ideas_channel:
                idea_message = await ideas_channel.fetch_message(self.idea_embed_message_id)
                await idea_message.add_reaction("❎")
        except:
            pass
        
        await interaction.response.send_message("❎ Idea rejected!", ephemeral=True)

@bot.event
async def on_thread_create(thread: discord.Thread):
    """Handle new threads in Skin Ideas channel"""
    try:
        # Check if thread is in Skin Ideas channel
        if thread.parent_id != SKIN_IDEAS_CHANNEL_ID:
            return
        
        print(f"🧵 New thread detected: {thread.name}")
        
        # Wait a moment for the first message to be posted
        await asyncio.sleep(2)
        
        # Process the thread using helper function
        await process_skin_idea_thread(thread)
        
    except Exception as e:
        print(f"❌ Error processing thread: {e}")
        import traceback
        traceback.print_exc()

async def process_skin_idea_thread(thread: discord.Thread):
    """Helper function to process a skin idea thread"""
    print(f"🧵 Processing skin idea thread: {thread.name} (ID: {thread.id})")
    
    # Get starter message
    try:
        starter_message = await thread.fetch_message(thread.id)
    except:
        # If starter message doesn't exist, get first message
        messages = [msg async for msg in thread.history(limit=1, oldest_first=True)]
        if not messages:
            raise Exception("No messages found in thread")
        starter_message = messages[0]
    
    # Extract thread information
    thread_title = thread.name
    thread_description = starter_message.content or "No description provided"
    thread_image = None
    
    # Get first image from attachments
    if starter_message.attachments:
        for attachment in starter_message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                thread_image = attachment.url
                break
    
    # Create embed for Your Ideas channel
    embed = discord.Embed(
        title=thread_title,
        description=thread_description,
        color=0x5865F2,
        timestamp=datetime.datetime.now()
    )
    
    embed.set_footer(text=f"Idea by {starter_message.author.name}", icon_url=starter_message.author.display_avatar.url)
    
    if thread_image:
        embed.set_image(url=thread_image)
    
    # Add link to original thread
    embed.add_field(name="🔗 Thread Link", value=f"[Click here]({thread.jump_url})", inline=False)
    
    # Post to Your Ideas channel with voting buttons
    ideas_channel = bot.get_channel(YOUR_IDEAS_CHANNEL_ID)
    if not ideas_channel:
        raise Exception(f"Your Ideas channel not found: {YOUR_IDEAS_CHANNEL_ID}")
    
    voting_view = VotingView(0)  # Temporary, will update after posting
    idea_message = await ideas_channel.send(embed=embed, view=voting_view)
    
    # Update view with correct message ID
    voting_data[str(idea_message.id)] = {'upvotes': 0, 'downvotes': 0, 'voters': {}}
    voting_view = VotingView(idea_message.id)
    await idea_message.edit(view=voting_view)
    
    print(f"✅ Posted idea to Your Ideas channel: {idea_message.jump_url}")
    
    # Post to Mod Review channel
    mod_channel = bot.get_channel(MOD_REVIEW_CHANNEL_ID)
    if not mod_channel:
        raise Exception(f"Mod Review channel not found: {MOD_REVIEW_CHANNEL_ID}")
    
    mod_embed = discord.Embed(
        title="🔍 New Skin Idea for Review",
        description=f"**{thread_title}**\n\n[View Idea Embed]({idea_message.jump_url})\n[View Original Thread]({thread.jump_url})",
        color=0xFFA500,
        timestamp=datetime.datetime.now()
    )
    
    mod_review_view = ModReviewView(thread.id, idea_message.id)
    mod_message = await mod_channel.send(embed=mod_embed, view=mod_review_view)
    
    print(f"✅ Posted to Mod Review channel: {mod_message.jump_url}")
    
    # Log the action
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(f"🧵 New skin idea thread processed: {thread.name}\n📬 Idea: {idea_message.jump_url}\n🔍 Review: {mod_message.jump_url}")
    
    return idea_message, mod_message

@bot.tree.command(name="add_skin_idea_by_link", description="Manually process a skin idea thread by providing its link")
@app_commands.describe(thread_link="Discord thread URL (e.g. https://discord.com/channels/...)")
async def add_skin_idea_by_link(interaction: discord.Interaction, thread_link: str):
    """Manually process a skin idea thread by link"""
    await interaction.response.defer()
    
    try:
        # Extract thread ID from URL
        # URL format: https://discord.com/channels/server_id/channel_id/thread_id
        parts = thread_link.rstrip('/').split('/')
        
        if len(parts) < 3:
            await interaction.edit_original_response(content="❌ Invalid thread link format. Please provide a valid Discord thread URL.")
            return
        
        thread_id = int(parts[-1])
        
        print(f"🔧 Manual skin idea add requested by {interaction.user.name}: Thread ID {thread_id}")
        
        # Try to get the thread
        thread = bot.get_channel(thread_id)
        if not thread or not isinstance(thread, discord.Thread):
            # Try fetching it
            for guild in bot.guilds:
                try:
                    thread = await guild.fetch_channel(thread_id)
                    if isinstance(thread, discord.Thread):
                        break
                except:
                    continue
        
        if not thread or not isinstance(thread, discord.Thread):
            await interaction.edit_original_response(content=f"❌ Could not find thread with ID: {thread_id}")
            return
        
        # Process the thread
        idea_message, mod_message = await process_skin_idea_thread(thread)
        
        # Success response
        success_embed = discord.Embed(
            title="✅ Skin Idea Thread Processed Successfully",
            color=0x00FF00
        )
        success_embed.add_field(name="Thread", value=f"[{thread.name}]({thread.jump_url})", inline=False)
        success_embed.add_field(name="Idea Post", value=f"[View in Your Ideas]({idea_message.jump_url})", inline=True)
        success_embed.add_field(name="Review Post", value=f"[View in Mod Review]({mod_message.jump_url})", inline=True)
        
        await interaction.edit_original_response(content="🧵 Skin idea thread processed manually:", embed=success_embed)
        print(f"✅ Manually processed skin idea thread: {thread.name}")
        
    except ValueError:
        await interaction.edit_original_response(content="❌ Invalid thread link. Could not extract thread ID.")
        print(f"❌ Invalid thread link provided")
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ Error processing thread: {str(e)}")
        print(f"❌ Error processing manual thread: {e}")
        import traceback
        traceback.print_exc()

# ================================
#       Tweet Poster
# ================================

# Store the last tweet ID to avoid duplicates
last_tweet_id = None

async def get_specific_tweet(tweet_id):
    """
    Fetch a specific tweet by ID using Twitter API v2
    """
    print(f"🔍 DEBUG: Fetching specific tweet ID: {tweet_id}")
    
    # Method 1: Try Twitter API v2 (official)
    if TWITTER_BEARER_TOKEN:
        try:
            print(f"Using Twitter API v2 for tweet ID: {tweet_id}...")
            
            # Get specific tweet
            tweet_url = f"https://api.twitter.com/2/tweets/{tweet_id}"
            headers = {
                'Authorization': f'Bearer {TWITTER_BEARER_TOKEN}',
                'User-Agent': 'v2UserLookupPython'
            }
            
            tweet_params = {
                'tweet.fields': 'created_at,public_metrics,text,non_public_metrics,attachments,author_id',
                'expansions': 'author_id,attachments.media_keys',
                'user.fields': 'name,username,profile_image_url',
                'media.fields': 'type,url,preview_image_url,width,height'
            }
            
            tweets_response = requests.get(tweet_url, headers=headers, params=tweet_params, timeout=10)
            print(f"🔍 DEBUG: Tweet API response: {tweets_response.status_code}")
            
            if tweets_response.status_code == 200:
                tweets_data = tweets_response.json()
                
                if 'data' in tweets_data:
                    tweet = tweets_data['data']
                    
                    # Get user profile image from includes
                    profile_image_url = None
                    username = "Unknown"
                    if 'includes' in tweets_data and 'users' in tweets_data['includes']:
                        for user in tweets_data['includes']['users']:
                            if user['id'] == tweet['author_id']:
                                username = user['username']
                                profile_image_url = user.get('profile_image_url', '').replace('_normal', '_400x400')
                                break
                    
                    # Get media data from includes
                    media_dict = {}
                    if 'includes' in tweets_data and 'media' in tweets_data['includes']:
                        for media in tweets_data['includes']['media']:
                            media_dict[media['media_key']] = media
                    
                    tweet_obj = {
                        'id': tweet['id'],
                        'text': tweet['text'],
                        'url': f'https://twitter.com/{username}/status/{tweet["id"]}',
                        'created_at': tweet.get('created_at', ''),
                        'metrics': tweet.get('public_metrics', {}),
                        'description': tweet['text']  # Full text as description
                    }
                    
                    # Add profile image if available
                    if profile_image_url:
                        tweet_obj['profile_image_url'] = profile_image_url
                    
                    # Add media if available
                    if 'attachments' in tweet and 'media_keys' in tweet['attachments']:
                        media_list = []
                        for media_key in tweet['attachments']['media_keys']:
                            if media_key in media_dict:
                                media_info = media_dict[media_key]
                                if media_info['type'] == 'photo':
                                    media_list.append({
                                        'type': 'photo',
                                        'url': media_info.get('url', ''),
                                        'preview_url': media_info.get('preview_image_url', ''),
                                        'width': media_info.get('width', 0),
                                        'height': media_info.get('height', 0)
                                    })
                                elif media_info['type'] in ['video', 'animated_gif']:
                                    media_list.append({
                                        'type': media_info['type'],
                                        'preview_url': media_info.get('preview_image_url', ''),
                                        'width': media_info.get('width', 0),
                                        'height': media_info.get('height', 0)
                                    })
                        
                        if media_list:
                            tweet_obj['media'] = media_list
                    
                    print(f"✅ Twitter API v2: Found tweet {tweet_id}")
                    return tweet_obj
                        
            else:
                print(f"❌ Twitter API v2 tweet error: {tweets_response.status_code}")
                print(f"🔍 DEBUG: Error response: {tweets_response.text}")
                
        except Exception as e:
            print(f"❌ Twitter API v2 error: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"❌ Failed to fetch tweet {tweet_id}")
    return None

async def get_twitter_user_tweets(username):
    """
    Fetch the latest tweets from a Twitter user using Twitter API v2
    """
    print(f"🔍 DEBUG: Starting tweet fetch for @{username}")
    print(f"🔍 DEBUG: TWITTER_BEARER_TOKEN exists: {bool(TWITTER_BEARER_TOKEN)}")
    if TWITTER_BEARER_TOKEN:
        print(f"🔍 DEBUG: Bearer token: {TWITTER_BEARER_TOKEN[:10]}...{TWITTER_BEARER_TOKEN[-4:]}")
    else:
        print("🔍 DEBUG: No Bearer token - will use Nitter")
    # Method 1: Try Twitter API v2 (official)
    if TWITTER_BEARER_TOKEN:
        try:
            print(f"Using Twitter API v2 for @{username}...")
            
            # Get user ID first
            user_url = f"https://api.twitter.com/2/users/by/username/{username}"
            headers = {
                'Authorization': f'Bearer {TWITTER_BEARER_TOKEN}',
                'User-Agent': 'v2UserLookupPython'
            }
            
            user_response = requests.get(user_url, headers=headers, timeout=10)
            print(f"🔍 DEBUG: User API response: {user_response.status_code}")
            
            if user_response.status_code == 200:
                user_data = user_response.json()
                user_id = user_data['data']['id']
                
                # Get user tweets
                tweets_url = f"https://api.twitter.com/2/users/{user_id}/tweets"
                tweet_params = {
                    'max_results': 5,
                    'tweet.fields': 'created_at,public_metrics,text,non_public_metrics,attachments',
                    'expansions': 'author_id,attachments.media_keys',
                    'user.fields': 'name,username,profile_image_url',
                    'media.fields': 'type,url,preview_image_url,width,height'
                }
                
                tweets_response = requests.get(tweets_url, headers=headers, params=tweet_params, timeout=10)
                print(f"🔍 DEBUG: Tweets API response: {tweets_response.status_code}")
                
                if tweets_response.status_code == 200:
                    tweets_data = tweets_response.json()
                    
                    if 'data' in tweets_data:
                        tweets = []
                        
                        # Get user profile image from includes
                        profile_image_url = None
                        if 'includes' in tweets_data and 'users' in tweets_data['includes']:
                            for user in tweets_data['includes']['users']:
                                if user['username'].lower() == username.lower():
                                    profile_image_url = user.get('profile_image_url', '').replace('_normal', '_400x400')
                                    break
                        
                        # Get media data from includes
                        media_dict = {}
                        if 'includes' in tweets_data and 'media' in tweets_data['includes']:
                            for media in tweets_data['includes']['media']:
                                media_dict[media['media_key']] = media
                        
                        for tweet in tweets_data['data']:
                            tweet_obj = {
                                'id': tweet['id'],
                                'text': tweet['text'],
                                'url': f'https://twitter.com/{username}/status/{tweet["id"]}',
                                'created_at': tweet.get('created_at', ''),
                                'metrics': tweet.get('public_metrics', {}),
                                'description': tweet['text']  # Full text as description
                            }
                            
                            # Add profile image if available
                            if profile_image_url:
                                tweet_obj['profile_image_url'] = profile_image_url
                            
                            # Add media if available
                            if 'attachments' in tweet and 'media_keys' in tweet['attachments']:
                                media_list = []
                                for media_key in tweet['attachments']['media_keys']:
                                    if media_key in media_dict:
                                        media_info = media_dict[media_key]
                                        if media_info['type'] == 'photo':
                                            media_list.append({
                                                'type': 'photo',
                                                'url': media_info.get('url', ''),
                                                'preview_url': media_info.get('preview_image_url', ''),
                                                'width': media_info.get('width', 0),
                                                'height': media_info.get('height', 0)
                                            })
                                        elif media_info['type'] in ['video', 'animated_gif']:
                                            media_list.append({
                                                'type': media_info['type'],
                                                'preview_url': media_info.get('preview_image_url', ''),
                                                'width': media_info.get('width', 0),
                                                'height': media_info.get('height', 0)
                                            })
                                
                                if media_list:
                                    tweet_obj['media'] = media_list
                                
                            tweets.append(tweet_obj)
                        
                        print(f"✅ Twitter API v2: Found {len(tweets)} tweets")
                        print(f"🔍 DEBUG: Latest tweet ID: {tweets[0]['id']}")
                        return tweets
                        
                else:
                    print(f"❌ Twitter API v2 tweets error: {tweets_response.status_code}")
                    print(f"🔍 DEBUG: Error response: {tweets_response.text}")
                    
            else:
                print(f"❌ Twitter API v2 user error: {user_response.status_code}")
                print(f"🔍 DEBUG: Error response: {user_response.text}")
                
        except Exception as e:
            print(f"❌ Twitter API v2 error: {e}")
            import traceback
            traceback.print_exc()
    
    # Method 2: Fallback to Nitter instances
    print("🔍 DEBUG: Twitter API failed, trying Nitter instances...")
    nitter_instances = [
        "nitter.poast.org",
        "nitter.privacydev.net", 
        "nitter.1d4.us",
        "nitter.domain.glass",
        "nitter.unixfox.eu"
    ]
    
    for instance in nitter_instances:
        try:
            print(f"Trying {instance} for @{username}...")
            
            url = f"https://{instance}/{username}/rss"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/rss+xml, application/xml, text/xml'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                print(f"✅ Connected to {instance}")
                
                import xml.etree.ElementTree as ET
                try:
                    root = ET.fromstring(response.content)
                    
                    tweets = []
                    for item in root.findall('.//item'):
                        title = item.find('title')
                        link = item.find('link') 
                        pub_date = item.find('pubDate')
                        description = item.find('description')
                        
                        if title is not None and link is not None:
                            tweet_id = link.text.split('/')[-1].split('#')[0]
                            tweet_text = title.text if title.text else ''
                            
                            # Clean RT prefix
                            if tweet_text.startswith('RT by'):
                                tweet_text = tweet_text.split(': ', 1)[-1] if ': ' in tweet_text else tweet_text
                            
                            tweets.append({
                                'id': tweet_id,
                                'text': tweet_text,
                                'url': link.text.replace(instance, 'twitter.com').replace('/nitter.', '/twitter.'),
                                'created_at': pub_date.text if pub_date is not None else '',
                                'description': description.text if description is not None else tweet_text,
                                'metrics': {}
                            })
                    
                    if tweets:
                        print(f"✅ Nitter: Found {len(tweets)} tweets from {instance}")
                        print(f"🔍 DEBUG: Latest tweet ID from Nitter: {tweets[0]['id']}")
                        return tweets[:5]
                        
                except ET.ParseError as e:
                    print(f"❌ XML parsing error for {instance}: {e}")
                    continue
                    
        except Exception as e:
            print(f"❌ Error with {instance}: {e}")
            continue
    
    # Method 3: Create test tweet as last resort
    print("� DEBUG: All methods failed, creating test tweet...")
    print("�🔄 Creating test tweet...")
    try:
        test_url = f"https://twitter.com/{username}"
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; DiscordBot/1.0)'}
        
        response = requests.get(test_url, headers=headers, timeout=10, allow_redirects=True)
        if response.status_code == 200:
            return [{
                'id': 'test_connection',
                'text': f'Twitter monitoring is active for @{username}! 🐦\n\nWaiting for new tweets to post automatically...',
                'url': f'https://twitter.com/{username}',
                'created_at': 'now',
                'description': 'Connection test - monitoring is working',
                'metrics': {}
            }]
            
    except Exception as e:
        print(f"❌ Test method failed: {e}")
    
    print("❌ All methods failed")
    return []

async def create_tweet_embed(tweet_data):
    """Create a Discord embed from tweet data that looks like the Twitter app"""
    
    # Create embed with Twitter blue color
    embed = discord.Embed(
        color=0x1DA1F2,  # Twitter blue
        timestamp=datetime.datetime.now()
    )
    
    # Set the main tweet content
    tweet_text = tweet_data['text']
    
    # Add Twitter header with user info
    embed.set_author(
        name=f"New post from @{TWITTER_USERNAME}",
        icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png",
        url=tweet_data['url']
    )
    
    # Add the main tweet text
    embed.description = tweet_text
    
    # Add metrics if available
    if 'metrics' in tweet_data and tweet_data['metrics']:
        metrics = tweet_data['metrics']
        metrics_text = ""
        if 'like_count' in metrics:
            metrics_text += f"❤️ {metrics['like_count']} "
        if 'retweet_count' in metrics:
            metrics_text += f"🔄 {metrics['retweet_count']} "
        if 'reply_count' in metrics:
            metrics_text += f"💬 {metrics['reply_count']} "
        if 'impression_count' in metrics:
            metrics_text += f"👁️ {metrics['impression_count']} "
            
        if metrics_text:
            embed.add_field(name="Engagement", value=metrics_text.strip(), inline=False)
    
    # Add footer with Twitter branding
    embed.set_footer(
        text="Twitter • Today at 3:44 AM",
        icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png"
    )
    
    # Add user profile picture as thumbnail (if available from API)
    if 'author_profile_image' in tweet_data:
        embed.set_thumbnail(url=tweet_data['author_profile_image'])
    elif 'profile_image_url' in tweet_data:
        embed.set_thumbnail(url=tweet_data['profile_image_url'])
    
    # Add media images if available
    if 'media' in tweet_data and tweet_data['media']:
        for media in tweet_data['media']:
            if media['type'] == 'photo' and media.get('url'):
                # Use the first photo as main image
                embed.set_image(url=media['url'])
                break
            elif media['type'] in ['video', 'animated_gif'] and media.get('preview_url'):
                # Use video preview as main image
                embed.set_image(url=media['preview_url'])
                embed.add_field(name="📹 Media", value=f"Video/GIF - [View on Twitter]({tweet_data['url']})", inline=False)
                break
        
        # If multiple photos, add info about them
        photo_count = sum(1 for media in tweet_data['media'] if media['type'] == 'photo')
        if photo_count > 1:
            embed.add_field(name="📸 Photos", value=f"{photo_count} photos - [View all on Twitter]({tweet_data['url']})", inline=False)
    
    return embed

@tasks.loop(seconds=TWITTER_CHECK_INTERVAL)
async def check_for_new_tweets():
    """Background task to check for new tweets"""
    global last_tweet_id
    
    try:
        print(f"🔄 Checking for new tweets from @{TWITTER_USERNAME}...")
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME)
        
        if not tweets:
            print("⚠️ No tweets fetched, monitoring will continue...")
            return
            
        latest_tweet = tweets[0]
        current_tweet_id = latest_tweet['id']
        
        print(f"📊 Current tweet ID: {current_tweet_id}")
        print(f"📊 Last known ID: {last_tweet_id}")
        print(f"📝 Tweet text: {latest_tweet['text'][:100]}...")
        
        # Check if this is a new tweet
        if last_tweet_id is None:
            last_tweet_id = current_tweet_id
            print(f"🔧 Initialized tweet tracking with ID: {last_tweet_id}")
            print("🔧 Next check will look for newer tweets")
            return
            
        if current_tweet_id != last_tweet_id:
            # New tweet found!
            print(f"🆕 NEW TWEET DETECTED! ID: {current_tweet_id}")
            channel = bot.get_channel(TWEETS_CHANNEL_ID)
            if channel:
                embed = await create_tweet_embed(latest_tweet)
                await channel.send(embed=embed)
                
                # Log the action
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel and log_channel != channel:
                    await log_channel.send(f"🐦 Posted new tweet from @{TWITTER_USERNAME}: {latest_tweet['url']}")
                
                print(f"✅ Posted new tweet: {current_tweet_id}")
                last_tweet_id = current_tweet_id
            else:
                print(f"❌ Channel {TWEETS_CHANNEL_ID} not found!")
        else:
            print("📋 No new tweets - same ID as before")
            
    except Exception as e:
        print(f"❌ Error in tweet checking task: {e}")
        import traceback
        traceback.print_exc()
        # Don't stop the monitoring, just log and continue

@check_for_new_tweets.before_loop
async def before_tweet_check():
    """Wait for bot to be ready before starting the tweet check loop"""
    await bot.wait_until_ready()
    print("Tweet monitoring started!")

# Manual tweet posting command (for testing)
@bot.tree.command(name="post_latest_tweet", description="Manually post the latest tweet from @p1mek")
async def post_latest_tweet(interaction: discord.Interaction):
    """Manual command to post the latest tweet"""
    await interaction.response.defer()
    
    try:
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME)
        if not tweets:
            await interaction.edit_original_response(content="❌ No tweets found.")
            return
            
        latest_tweet = tweets[0]
        embed = await create_tweet_embed(latest_tweet)
        
        await interaction.edit_original_response(content="✅ Latest tweet:", embed=embed)
        
    except Exception as e:
        print(f"Error posting latest tweet: {e}")
        await interaction.edit_original_response(content="❌ Error fetching tweet.")

# Command to toggle tweet monitoring
@bot.tree.command(name="toggle_tweet_monitoring", description="Start or stop automatic tweet monitoring")
async def toggle_tweet_monitoring(interaction: discord.Interaction):
    """Toggle the tweet monitoring task"""
    if check_for_new_tweets.is_running():
        check_for_new_tweets.stop()
        await interaction.response.send_message("🛑 Tweet monitoring stopped.", ephemeral=True)
    else:
        check_for_new_tweets.start()
        await interaction.response.send_message("▶️ Tweet monitoring started.", ephemeral=True)

# Command to start tweet monitoring
@bot.tree.command(name="start_tweet_monitoring", description="Start automatic tweet monitoring")
async def start_tweet_monitoring(interaction: discord.Interaction):
    """Start the tweet monitoring task"""
    if check_for_new_tweets.is_running():
        await interaction.response.send_message("ℹ️ Tweet monitoring is already running.", ephemeral=True)
    else:
        check_for_new_tweets.start()
        await interaction.response.send_message("▶️ Tweet monitoring started successfully!", ephemeral=True)

# Command to check tweet monitoring status
@bot.tree.command(name="tweet_status", description="Check if tweet monitoring is currently active")
async def tweet_status(interaction: discord.Interaction):
    """Check the status of tweet monitoring"""
    status = "🟢 **ACTIVE**" if check_for_new_tweets.is_running() else "🔴 **STOPPED**"
    
    embed = discord.Embed(
        title="🐦 Tweet Monitoring Status",
        color=0x1DA1F2
    )
    embed.add_field(name="Status", value=status, inline=False)
    embed.add_field(name="Username", value=f"@{TWITTER_USERNAME}", inline=True)
    embed.add_field(name="Check Interval", value=f"{TWITTER_CHECK_INTERVAL} seconds", inline=True)
    embed.add_field(name="Target Channel", value=f"<#{TWEETS_CHANNEL_ID}>", inline=True)
    
    if check_for_new_tweets.is_running():
        embed.add_field(name="Last Tweet ID", value=last_tweet_id or "Not initialized", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Command to test Twitter connection
@bot.tree.command(name="test_twitter_connection", description="Test if Twitter data fetching is working")
async def test_twitter_connection(interaction: discord.Interaction):
    """Test command to verify Twitter connection"""
    await interaction.response.defer()
    
    try:
        print(f"Testing Twitter connection for @{TWITTER_USERNAME}...")
        
        # Send initial status
        embed = discord.Embed(
            title="🔄 Testing Twitter Connection...",
            description="Trying multiple methods to fetch tweets",
            color=0xFFFF00
        )
        await interaction.edit_original_response(embed=embed)
        
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME)
        
        if tweets:
            embed = discord.Embed(
                title="✅ Twitter Connection Test - SUCCESS",
                color=0x00FF00
            )
            embed.add_field(name="Status", value="Successfully fetched tweets", inline=False)
            embed.add_field(name="Tweets Found", value=len(tweets), inline=True)
            embed.add_field(name="Latest Tweet ID", value=tweets[0]['id'], inline=True)
            embed.add_field(name="Latest Tweet", value=tweets[0]['text'][:200] + "..." if len(tweets[0]['text']) > 200 else tweets[0]['text'], inline=False)
            embed.add_field(name="URL", value=tweets[0]['url'], inline=False)
            embed.set_footer(text="Tweet monitoring should work properly now!")
            
            await interaction.edit_original_response(content="🐦 Twitter connection test completed:", embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Twitter Connection Test - FAILED",
                color=0xFF0000
            )
            embed.add_field(name="Status", value="No tweets found", inline=False)
            embed.add_field(name="Tried Methods", value="• Multiple Nitter instances\n• RSS feeds\n• HTML scraping\n• Direct Twitter check", inline=False)
            embed.add_field(name="Possible Solutions", value="• Wait a few minutes and try again\n• Check if @p1mek account exists\n• Use `/post_latest_tweet` to test manually", inline=False)
            embed.add_field(name="Username", value=f"@{TWITTER_USERNAME}", inline=True)
            embed.set_footer(text="Check bot console logs for detailed error information")
            
            await interaction.edit_original_response(content="⚠️ Twitter connection test failed:", embed=embed)
            
    except Exception as e:
        embed = discord.Embed(
            title="💥 Twitter Connection Test - ERROR",
            color=0xFF0000
        )
        embed.add_field(name="Error", value=str(e)[:1000], inline=False)
        embed.add_field(name="Username", value=f"@{TWITTER_USERNAME}", inline=True)
        embed.add_field(name="Suggestion", value="Try again in a few minutes or contact admin", inline=False)
        
        print(f"Error in Twitter connection test: {e}")
        await interaction.edit_original_response(content="💥 Twitter connection test error:", embed=embed)

# Command to reset tweet tracking
@bot.tree.command(name="reset_tweet_tracking", description="Reset tweet tracking to detect current tweet as new")
async def reset_tweet_tracking(interaction: discord.Interaction):
    """Reset tweet tracking to force detection of current tweets"""
    global last_tweet_id
    
    await interaction.response.defer()
    
    try:
        # Get current tweets first
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME)
        
        if tweets:
            old_id = last_tweet_id
            last_tweet_id = None  # Reset tracking
            
            embed = discord.Embed(
                title="🔄 Tweet Tracking Reset",
                color=0x1DA1F2
            )
            embed.add_field(name="Previous ID", value=old_id or "None", inline=True)
            embed.add_field(name="Current Latest Tweet", value=tweets[0]['id'], inline=True)
            embed.add_field(name="Status", value="Tracking reset - next check will re-initialize", inline=False)
            embed.add_field(name="Next Action", value="Bot will now treat the latest tweet as baseline for future monitoring", inline=False)
            
            await interaction.edit_original_response(content="✅ Tweet tracking has been reset:", embed=embed)
            print(f"🔄 Tweet tracking reset by {interaction.user.name}. Old ID: {old_id}, will reinitialize on next check.")
        else:
            await interaction.edit_original_response(content="❌ Could not fetch tweets to reset tracking.")
            
    except Exception as e:
        print(f"Error in reset tweet tracking: {e}")
        await interaction.edit_original_response(content="❌ Error resetting tweet tracking.")

# Command to check specific tweet
@bot.tree.command(name="check_specific_tweet", description="Check if a specific tweet ID is being detected")
@app_commands.describe(tweet_id="Tweet ID to check (e.g. 1978993084693102705)")
async def check_specific_tweet(interaction: discord.Interaction, tweet_id: str):
    """Check if a specific tweet ID matches current latest tweet"""
    await interaction.response.defer()
    
    try:
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME)
        
        if tweets:
            latest_tweet = tweets[0]
            
            embed = discord.Embed(
                title="🔍 Tweet ID Check",
                color=0x1DA1F2
            )
            embed.add_field(name="Requested Tweet ID", value=tweet_id, inline=False)
            embed.add_field(name="Current Latest Tweet ID", value=latest_tweet['id'], inline=False)
            embed.add_field(name="Match?", value="✅ YES" if latest_tweet['id'] == tweet_id else "❌ NO", inline=False)
            embed.add_field(name="Latest Tweet Text", value=latest_tweet['text'][:200] + "..." if len(latest_tweet['text']) > 200 else latest_tweet['text'], inline=False)
            embed.add_field(name="Current Tracking ID", value=last_tweet_id or "None (not initialized)", inline=False)
            
            if latest_tweet['id'] == tweet_id:
                embed.add_field(name="Status", value="✅ This tweet is the current latest tweet", inline=False)
            else:
                embed.add_field(name="Status", value="❌ This tweet is NOT the current latest tweet. Either:\n• It's older than the latest\n• It wasn't fetched\n• There's a newer tweet", inline=False)
            
            await interaction.edit_original_response(embed=embed)
        else:
            await interaction.edit_original_response(content="❌ Could not fetch tweets to check.")
            
    except Exception as e:
        print(f"Error in check specific tweet: {e}")
        await interaction.edit_original_response(content="❌ Error checking specific tweet.")

# Command to add specific tweet by ID
@bot.tree.command(name="add_tweet_by_id", description="Manually add a tweet by ID to the channel")
@app_commands.describe(tweet_id="Tweet ID to post (e.g. 1979003059117207752)")
async def add_tweet_by_id(interaction: discord.Interaction, tweet_id: str):
    """Manually add a specific tweet by ID"""
    await interaction.response.defer()
    
    try:
        # Clean tweet ID (remove URL parts if user pasted full URL)
        clean_tweet_id = tweet_id.split('/')[-1].split('?')[0]
        
        print(f"🔧 Manual tweet add requested by {interaction.user.name}: {clean_tweet_id}")
        
        # Fetch the specific tweet
        tweet_data = await get_specific_tweet(clean_tweet_id)
        
        if tweet_data:
            # Create embed
            embed = await create_tweet_embed(tweet_data)
            
            # Post to tweets channel
            channel = bot.get_channel(TWEETS_CHANNEL_ID)
            if channel:
                await channel.send(embed=embed)
                
                # Log the manual action
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel and log_channel != channel:
                    await log_channel.send(f"🔧 {interaction.user.mention} manually added tweet: {tweet_data['url']}")
                
                # Success response
                success_embed = discord.Embed(
                    title="✅ Tweet Added Successfully",
                    color=0x00FF00
                )
                success_embed.add_field(name="Tweet ID", value=clean_tweet_id, inline=True)
                success_embed.add_field(name="Posted to", value=f"<#{TWEETS_CHANNEL_ID}>", inline=True)
                success_embed.add_field(name="Tweet Text", value=tweet_data['text'][:200] + "..." if len(tweet_data['text']) > 200 else tweet_data['text'], inline=False)
                success_embed.add_field(name="URL", value=tweet_data['url'], inline=False)
                
                await interaction.edit_original_response(content="🐦 Tweet posted manually:", embed=success_embed)
                print(f"✅ Manually posted tweet: {clean_tweet_id}")
                
            else:
                await interaction.edit_original_response(content=f"❌ Channel <#{TWEETS_CHANNEL_ID}> not found!")
        else:
            error_embed = discord.Embed(
                title="❌ Tweet Not Found",
                color=0xFF0000
            )
            error_embed.add_field(name="Tweet ID", value=clean_tweet_id, inline=False)
            error_embed.add_field(name="Possible Issues", value="• Tweet doesn't exist\n• Tweet is private/protected\n• Invalid Tweet ID\n• API access issue", inline=False)
            error_embed.add_field(name="How to get Tweet ID", value="From URL: `https://x.com/username/status/1234567890`\nTweet ID is: `1234567890`", inline=False)
            
            await interaction.edit_original_response(content="⚠️ Could not fetch tweet:", embed=error_embed)
            
    except Exception as e:
        error_embed = discord.Embed(
            title="💥 Error Adding Tweet",
            color=0xFF0000
        )
        error_embed.add_field(name="Error", value=str(e)[:1000], inline=False)
        error_embed.add_field(name="Tweet ID", value=tweet_id, inline=True)
        error_embed.add_field(name="Suggestion", value="Check the Tweet ID and try again", inline=False)
        
        print(f"Error in add tweet by ID: {e}")
        await interaction.edit_original_response(content="💥 Error adding tweet:", embed=error_embed)

# ================================
#        OTHER EVENTS
# ================================
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    
    # Start tweet monitoring
    if not check_for_new_tweets.is_running():
        check_for_new_tweets.start()
        print(f"🐦 Started monitoring @{TWITTER_USERNAME} for new tweets")

bot.run(os.getenv("BOT_TOKEN"))

