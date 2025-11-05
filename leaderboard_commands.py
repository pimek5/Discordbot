"""
Leaderboard Commands Module  
/top champion, /top user
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import logging

from database import get_db
from riot_api import RiotAPI, CHAMPION_ID_TO_NAME

logger = logging.getLogger('leaderboard_commands')

def find_champion_id(champion_name: str) -> Optional[tuple]:
    """Find champion by name (case insensitive, partial match)"""
    champion_lower = champion_name.lower()
    
    matching = [
        (champ_id, champ_name) 
        for champ_id, champ_name in CHAMPION_ID_TO_NAME.items() 
        if champion_lower in champ_name.lower()
    ]
    
    if not matching:
        return None
    
    if len(matching) > 1:
        # Try exact match
        exact = [(cid, cn) for cid, cn in matching if cn.lower() == champion_lower]
        if exact:
            return exact[0]
        return None
    
    return matching[0]

class LeaderboardCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
        self.bot = bot
        self.riot_api = riot_api
        self.guild = discord.Object(id=guild_id)
    
    @app_commands.command(name="top", description="View champion leaderboard")
    @app_commands.describe(
        champion="The champion to show leaderboard for",
        server_only="Show only players from this server (default: global)"
    )
    async def top(self, interaction: discord.Interaction, champion: str, 
                 server_only: bool = False):
        """Show top players for a champion"""
        await interaction.response.defer()
        
        db = get_db()
        
        # Find champion
        champ_result = find_champion_id(champion)
        if not champ_result:
            matching = [(cid, cn) for cid, cn in CHAMPION_ID_TO_NAME.items() if champion.lower() in cn.lower()]
            if len(matching) > 1:
                options = ", ".join([cn for _, cn in matching[:5]])
                await interaction.followup.send(
                    f"❌ Multiple champions found: **{options}**\nPlease be more specific!",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ Champion **{champion}** not found!",
                    ephemeral=True
                )
            return
        
        champion_id, champion_name = champ_result
        
        # Check if in guild
        guild_id = interaction.guild.id if server_only and interaction.guild else None
        
        if server_only and not guild_id:
            await interaction.followup.send(
                "❌ Cannot use server-only mode in DMs!",
                ephemeral=True
            )
            return
        
        # Get leaderboard
        leaderboard = db.get_champion_leaderboard(champion_id, guild_id, limit=10)
        
        if not leaderboard:
            scope = "on this server" if server_only else "globally"
            await interaction.followup.send(
                f"❌ No data recorded for **{champion_name}** {scope}!",
                ephemeral=True
            )
            return
        
        # Create embed
        title = f"🏆 {champion_name} Leaderboard"
        if server_only:
            title += f" - {interaction.guild.name}"
        else:
            title += " - Global"
        
        embed = discord.Embed(
            title=title,
            color=0xFFD700  # Gold
        )
        
        # Medal emojis for top 3
        medals = ["🥇", "🥈", "🥉"]
        
        for i, entry in enumerate(leaderboard):
            position = i + 1
            
            # Get Discord user
            try:
                user = await self.bot.fetch_user(entry['snowflake'])
                username = user.display_name
            except:
                username = f"{entry['riot_id_game_name']}#{entry['riot_id_tagline']}"
            
            score = entry['score']
            level = entry['level']
            
            # Format score
            if score >= 1000000:
                score_str = f"{score/1000000:.2f}M"
            elif score >= 1000:
                score_str = f"{score/1000:.0f}K"
            else:
                score_str = f"{score:,}"
            
            # Mastery level emoji
            if level >= 10:
                level_emoji = "🔟"
            elif level >= 7:
                level_emoji = "⭐⭐⭐"
            elif level >= 6:
                level_emoji = "⭐⭐"
            elif level >= 5:
                level_emoji = "⭐"
            else:
                level_emoji = "💫"
            
            # Position emoji
            if position <= 3:
                pos_emoji = medals[position - 1]
            else:
                pos_emoji = f"**{position}.**"
            
            embed.add_field(
                name=f"{pos_emoji} {username}",
                value=f"{level_emoji} M{level} • **{score_str}** pts",
                inline=False
            )
        
        embed.set_footer(text=f"Requested by {interaction.user.name}")
        
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
    """Setup leaderboard commands"""
    cog = LeaderboardCommands(bot, riot_api, guild_id)
    await bot.add_cog(cog)
    
    logger.info("✅ Leaderboard commands loaded")
