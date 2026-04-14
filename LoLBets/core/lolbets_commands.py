import logging

from discord.ext import commands

from tracker_database import TrackerDatabase
from riot_api import RiotAPI
from LoLBets.core.engine.lolbets_commands import Hexbet

logger = logging.getLogger("lolbets")


class LoLBets(Hexbet):
    """Standalone LoLBets core built on top of a local fork of the proven HEXBET engine.

    This keeps LoLBets behavior aligned with the current betting system while
    all code now lives under the LoLBets package.
    """

    pass


async def setup(bot: commands.Bot, riot_api: RiotAPI, db: TrackerDatabase):
    cog = LoLBets(bot, riot_api, db)
    await bot.add_cog(cog)

    cog_commands = [cmd.name for cmd in cog.__cog_app_commands__]
    logger.info("LoLBets core commands registered: %s", cog_commands)
