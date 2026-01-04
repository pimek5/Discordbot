import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional

from database import get_db
from riot_api import RiotAPI
from emoji_dict import get_champion_emoji, get_rank_emoji

logger = logging.getLogger('betting_commands')

BET_CHANNEL_ID = 1398977064261910580
LEADERBOARD_CHANNEL_ID = 1398985421014306856

class BettingCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
        self.bot = bot
        self.riot_api = riot_api
        self.guild_id = guild_id

    @app_commands.command(name="bet", description="Postaw zakład na ostatni aktywny mecz (red/blue)")
    @app_commands.describe(side="red lub blue", amount="kwota punktów")
    async def bet(self, interaction: discord.Interaction, side: str, amount: int):
        side = side.lower()
        if side not in ["red", "blue"]:
            await interaction.response.send_message("❌ Wybierz side: red lub blue", ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message("❌ Kwota musi być dodatnia", ephemeral=True)
            return

        db = get_db()
        bet = db.get_open_bet()
        if not bet:
            await interaction.response.send_message("⚠️ Brak aktywnego zakładu w tym momencie.", ephemeral=True)
            return

        db.add_prediction(bet_id=bet['id'], user_id=interaction.user.id, side=side, amount=amount)
        odds = bet['red_odds'] if side == 'red' else bet['blue_odds']
        await interaction.response.send_message(
            f"✅ Postawiono na **{side.upper()}** za {amount} | potencjalna wypłata: ~{amount * odds:.2f}",
            ephemeral=True
        )

async def setup(bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
    cog = BettingCommands(bot, riot_api, guild_id)
    await bot.add_cog(cog)
    logger.info("✅ Betting commands loaded")
