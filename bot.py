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
        self.tree.add_command(post_latest_tweet, guild=guild)
        self.tree.add_command(toggle_tweet_monitoring, guild=guild)
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
#       Tweet Poster
# ================================

# Store the last tweet ID to avoid duplicates
last_tweet_id = None

async def get_twitter_user_tweets(username):
    """
    Fetch the latest tweets from a Twitter user using web scraping approach
    Since Twitter API requires authentication, we'll use a simple RSS-like approach
    """
    try:
        # Using nitter.net as a proxy to get tweet data without API keys
        url = f"https://nitter.net/{username}/rss"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            # Parse RSS feed for tweets
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.content)
            
            tweets = []
            for item in root.findall('.//item'):
                title = item.find('title')
                link = item.find('link') 
                pub_date = item.find('pubDate')
                description = item.find('description')
                
                if title is not None and link is not None:
                    tweet_id = link.text.split('/')[-1].split('#')[0]
                    tweets.append({
                        'id': tweet_id,
                        'text': title.text if title.text else '',
                        'url': link.text,
                        'created_at': pub_date.text if pub_date is not None else '',
                        'description': description.text if description is not None else ''
                    })
            
            return tweets[:5]  # Return latest 5 tweets
            
    except Exception as e:
        print(f"Error fetching tweets: {e}")
        return []

async def create_tweet_embed(tweet_data):
    """Create a Discord embed from tweet data"""
    embed = discord.Embed(
        title="🐦 New Tweet from @p1mek",
        description=tweet_data['text'],
        url=tweet_data['url'],
        color=0x1DA1F2,  # Twitter blue
        timestamp=datetime.datetime.now()
    )
    
    embed.set_author(
        name=f"@{TWITTER_USERNAME}",
        icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png",
        url=f"https://twitter.com/{TWITTER_USERNAME}"
    )
    
    embed.set_footer(
        text="Twitter",
        icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png"
    )
    
    # Add tweet ID for reference
    embed.add_field(name="Tweet ID", value=tweet_data['id'], inline=True)
    
    return embed

@tasks.loop(seconds=TWITTER_CHECK_INTERVAL)
async def check_for_new_tweets():
    """Background task to check for new tweets"""
    global last_tweet_id
    
    try:
        tweets = await get_twitter_user_tweets(TWITTER_USERNAME)
        if not tweets:
            return
            
        latest_tweet = tweets[0]
        
        # Check if this is a new tweet
        if last_tweet_id is None:
            last_tweet_id = latest_tweet['id']
            print(f"Initialized tweet tracking with ID: {last_tweet_id}")
            return
            
        if latest_tweet['id'] != last_tweet_id:
            # New tweet found!
            channel = bot.get_channel(TWEETS_CHANNEL_ID)
            if channel:
                embed = await create_tweet_embed(latest_tweet)
                await channel.send(embed=embed)
                
                # Log the action
                log_channel = bot.get_channel(LOG_CHANNEL_ID)
                if log_channel and log_channel != channel:
                    await log_channel.send(f"🐦 Posted new tweet from @{TWITTER_USERNAME}: {latest_tweet['url']}")
                
                print(f"Posted new tweet: {latest_tweet['id']}")
            
            last_tweet_id = latest_tweet['id']
            
    except Exception as e:
        print(f"Error in tweet checking task: {e}")

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

