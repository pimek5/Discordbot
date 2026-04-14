import os
import sys
import logging
import asyncio

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv


load_dotenv()

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKER_DIR = os.path.join(ROOT_DIR, "tracker")

if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)
if TRACKER_DIR not in sys.path:
    sys.path.append(TRACKER_DIR)

from tracker_database import get_tracker_db
from riot_api import RiotAPI
import config_commands
from LoLBets.core.lolbets_commands import setup as setup_lolbets
from LoLBets.core.lolbets_config_commands import setup as setup_lolbets_config


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("lolbets_bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("lolbets")

LOLBETS_BOT_TOKEN = os.getenv("LOLBETS_BOT_TOKEN") or os.getenv("TRACKER_BOT_TOKEN") or os.getenv("DISCORD_TOKEN")
DISCORD_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", 0) or 0)
RIOT_API_KEY = os.getenv("RIOT_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True


class LoLBetsBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.riot_api = None
        self.db = None
        self.status_index = 0
        self.status_messages = [
            ("playing", "LoLBets"),
            ("watching", "global League bets"),
            ("listening", "{guilds} servers"),
            ("playing", "/lolbets"),
            ("listening", "{active_bets} active bets"),
            ("watching", "server streamers and pro games"),
        ]

    async def setup_hook(self):
        if not RIOT_API_KEY:
            raise ValueError("RIOT_API_KEY not found in environment variables")

        self.riot_api = RiotAPI(RIOT_API_KEY)
        self.db = get_tracker_db()

        await config_commands.setup(self)
        logger.info("ConfigCommands loaded")

        await setup_lolbets(self, self.riot_api, self.db)
        logger.info("LoLBets core loaded")

        await setup_lolbets_config(self)
        logger.info("LoLBets config commands loaded")

        commands_list = [cmd.name for cmd in self.tree.get_commands()]
        logger.info("LoLBets command tree: %s", commands_list)

    @tasks.loop(minutes=5)
    async def change_status(self):
        try:
            status_type, status_text = self.status_messages[self.status_index]

            if "{guilds}" in status_text:
                status_text = status_text.replace("{guilds}", str(len(self.guilds)))

            if "{active_bets}" in status_text:
                try:
                    conn = self.db.get_connection()
                    try:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                SELECT COUNT(*)
                                FROM hexbet_bets b
                                INNER JOIN hexbet_matches m ON b.match_id = m.id
                                WHERE b.settled = FALSE AND m.status = 'open'
                                """
                            )
                            row = cur.fetchone()
                            active_count = int(row[0]) if row else 0
                    finally:
                        self.db.return_connection(conn)
                    status_text = status_text.replace("{active_bets}", str(active_count))
                except Exception:
                    status_text = status_text.replace("{active_bets}", "0")

            if status_type == "playing":
                activity = discord.Game(name=status_text)
            elif status_type == "watching":
                activity = discord.Activity(type=discord.ActivityType.watching, name=status_text)
            elif status_type == "listening":
                activity = discord.Activity(type=discord.ActivityType.listening, name=status_text)
            else:
                activity = discord.Game(name=status_text)

            await self.change_presence(activity=activity)
            self.status_index = (self.status_index + 1) % len(self.status_messages)
        except Exception as exc:
            logger.error("Error changing LoLBets status: %s", exc, exc_info=True)

    @change_status.before_loop
    async def before_change_status(self):
        await self.wait_until_ready()


bot = LoLBetsBot()


@bot.event
async def on_ready():
    logger.info("LoLBets logged in as %s (ID: %s)", bot.user.name, bot.user.id)

    if not bot.change_status.is_running():
        bot.change_status.start()
        logger.info("LoLBets dynamic status rotation started")

    try:
        synced = await bot.tree.sync()
        logger.info("LoLBets commands synced globally: %s", [cmd.name for cmd in synced])
        logger.info("Total synced commands: %s", len(synced))
    except Exception as exc:
        logger.error("Error syncing LoLBets commands: %s", exc, exc_info=True)


@bot.event
async def on_error(event, *args, **kwargs):
    logger.error("LoLBets error in %s", event, exc_info=True)


async def main():
    if not LOLBETS_BOT_TOKEN:
        raise ValueError("LOLBETS_BOT_TOKEN or fallback bot token not found in environment variables")

    async with bot:
        await bot.start(LOLBETS_BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
