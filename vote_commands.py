"""
Vote Commands Module
/vote, /vote start, /vote stop
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List
import logging

from database import get_db
from riot_api import CHAMPION_ID_TO_NAME

logger = logging.getLogger('vote_commands')

# Configuration
VOTING_THREAD_ID = 1331546029023166464
ADMIN_ROLE_ID = 1153030265782927501
BOOSTER_ROLE_ID = 1168616737692991499

class VoteCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    def is_voting_thread(self, interaction: discord.Interaction) -> bool:
        """Check if command is used in the voting thread"""
        return interaction.channel_id == VOTING_THREAD_ID
    
    def has_admin_role(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin role"""
        if not interaction.guild:
            return False
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return False
        return any(role.id == ADMIN_ROLE_ID for role in member.roles)
    
    def is_booster(self, interaction: discord.Interaction) -> bool:
        """Check if user is a server booster"""
        if not interaction.guild:
            return False
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return False
        return any(role.id == BOOSTER_ROLE_ID for role in member.roles)
    
    def get_points_multiplier(self, interaction: discord.Interaction) -> int:
        """Get points multiplier based on user roles (2 for boosters, 1 for others)"""
        return 2 if self.is_booster(interaction) else 1
    
    def validate_champions(self, champion_names: List[str]) -> tuple[bool, Optional[str], List[str]]:
        """
        Validate champion names.
        Returns: (is_valid, error_message, normalized_names)
        """
        if len(champion_names) != 5:
            return False, "You must vote for exactly 5 champions!", []
        
        # Get all valid champion names (values from CHAMPION_ID_TO_NAME)
        valid_champions = set(CHAMPION_ID_TO_NAME.values())
        
        # Normalize and validate each champion
        normalized = []
        for name in champion_names:
            # Find matching champion (case-insensitive)
            name_lower = name.lower()
            matching = [c for c in valid_champions if c.lower() == name_lower]
            
            if not matching:
                return False, f"❌ Invalid champion name: **{name}**\nPlease use exact champion names from League of Legends.", []
            
            normalized.append(matching[0])
        
        # Check for duplicates
        if len(set(normalized)) != 5:
            return False, "❌ You cannot vote for the same champion twice!", []
        
        return True, None, normalized
    
    def create_voting_embed(self, results: List[dict], session_id: int) -> discord.Embed:
        """Create the voting results embed with top 5 and others"""
        embed = discord.Embed(
            title="🗳️ Champion Voting - Live Results",
            description="Vote with `/vote [champion1] [champion2] [champion3] [champion4] [champion5]`\n"
                       "Server Boosters get 2 points per champion! 💎",
            color=0x0099ff
        )
        
        # Top 5 podium
        podium_emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        top_5 = results[:5]
        
        podium_text = []
        for i, result in enumerate(top_5):
            emoji = podium_emojis[i]
            champion = result['champion_name']
            points = result['total_points']
            votes = result['vote_count']
            podium_text.append(f"{emoji} **{champion}** - {points} points ({votes} votes)")
        
        if podium_text:
            embed.add_field(
                name="🏆 Top 5 Podium",
                value="\n".join(podium_text),
                inline=False
            )
        else:
            embed.add_field(
                name="🏆 Top 5 Podium",
                value="*No votes yet! Be the first to vote!*",
                inline=False
            )
        
        # Others (below top 5)
        others = results[5:]
        if others:
            others_text = []
            for result in others[:15]:  # Show max 15 others
                champion = result['champion_name']
                points = result['total_points']
                votes = result['vote_count']
                others_text.append(f"• **{champion}** - {points} points ({votes} votes)")
            
            if len(others) > 15:
                others_text.append(f"*...and {len(others) - 15} more champions*")
            
            embed.add_field(
                name="📊 Other Champions",
                value="\n".join(others_text),
                inline=False
            )
        
        embed.set_footer(text=f"Session ID: {session_id} • Use /vote stop to end voting")
        return embed
    
    @app_commands.command(name="vote", description="Vote for 5 champions")
    @app_commands.describe(
        champion1="Your #1 pick",
        champion2="Your #2 pick",
        champion3="Your #3 pick",
        champion4="Your #4 pick",
        champion5="Your #5 pick"
    )
    async def vote(
        self,
        interaction: discord.Interaction,
        champion1: str,
        champion2: str,
        champion3: str,
        champion4: str,
        champion5: str
    ):
        """Vote for 5 champions in the current voting session"""
        # Check if command is used in voting thread
        if not self.is_voting_thread(interaction):
            await interaction.response.send_message(
                f"❌ This command can only be used in <#{VOTING_THREAD_ID}>!",
                ephemeral=True
            )
            return
        
        # Check if there's an active voting session
        db = get_db()
        session = db.get_active_voting_session(interaction.guild_id)
        
        if not session:
            await interaction.response.send_message(
                "❌ There is no active voting session!\n"
                "An admin must use `/vote start` to begin voting.",
                ephemeral=True
            )
            return
        
        # Validate champions
        champion_names = [champion1, champion2, champion3, champion4, champion5]
        is_valid, error_msg, normalized_names = self.validate_champions(champion_names)
        
        if not is_valid:
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        # Get points multiplier
        points = self.get_points_multiplier(interaction)
        is_booster = points == 2
        
        # Add votes to database
        success = db.add_vote(session['id'], interaction.user.id, normalized_names, points)
        
        if not success:
            await interaction.response.send_message(
                "❌ Failed to record your vote. Please try again!",
                ephemeral=True
            )
            return
        
        # Get updated results
        results = db.get_voting_results(session['id'])
        
        # Update the voting embed
        embed = self.create_voting_embed(results, session['id'])
        
        # Update the message
        try:
            if session['message_id']:
                channel = self.bot.get_channel(session['channel_id'])
                if channel:
                    message = await channel.fetch_message(session['message_id'])
                    await message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Failed to update voting embed: {e}")
        
        # Send confirmation
        booster_text = " (💎 x2 points as Server Booster!)" if is_booster else ""
        await interaction.response.send_message(
            f"✅ Your vote has been recorded!{booster_text}\n"
            f"**Your picks:** {', '.join(normalized_names)}",
            ephemeral=True
        )
        
        logger.info(f"Vote recorded: {interaction.user.name} voted for {normalized_names} ({points} points each)")
    
    @app_commands.command(name="votestart", description="[ADMIN] Start a new voting session")
    async def vote_start(self, interaction: discord.Interaction):
        """Start a new voting session (admin only)"""
        # Check if command is used in voting thread
        if not self.is_voting_thread(interaction):
            await interaction.response.send_message(
                f"❌ This command can only be used in <#{VOTING_THREAD_ID}>!",
                ephemeral=True
            )
            return
        
        # Check admin permissions
        if not self.has_admin_role(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to start voting sessions!",
                ephemeral=True
            )
            return
        
        # Check if there's already an active session
        db = get_db()
        existing_session = db.get_active_voting_session(interaction.guild_id)
        
        if existing_session:
            await interaction.response.send_message(
                "❌ There is already an active voting session!\n"
                "Use `/vote stop` to end it first.",
                ephemeral=True
            )
            return
        
        # Create new voting session
        session_id = db.create_voting_session(
            interaction.guild_id,
            interaction.channel_id,
            interaction.user.id
        )
        
        # Create initial embed
        embed = self.create_voting_embed([], session_id)
        
        # Send the embed
        await interaction.response.send_message(embed=embed)
        
        # Get the message and store its ID
        message = await interaction.original_response()
        db.update_voting_message_id(session_id, message.id)
        
        logger.info(f"Voting session {session_id} started by {interaction.user.name}")
    
    @app_commands.command(name="votestop", description="[ADMIN] Stop the current voting session")
    async def vote_stop(self, interaction: discord.Interaction):
        """Stop the current voting session (admin only)"""
        # Check if command is used in voting thread
        if not self.is_voting_thread(interaction):
            await interaction.response.send_message(
                f"❌ This command can only be used in <#{VOTING_THREAD_ID}>!",
                ephemeral=True
            )
            return
        
        # Check admin permissions
        if not self.has_admin_role(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to stop voting sessions!",
                ephemeral=True
            )
            return
        
        # Check if there's an active session
        db = get_db()
        session = db.get_active_voting_session(interaction.guild_id)
        
        if not session:
            await interaction.response.send_message(
                "❌ There is no active voting session!",
                ephemeral=True
            )
            return
        
        # End the session
        db.end_voting_session(session['id'])
        
        # Get final results
        results = db.get_voting_results(session['id'])
        
        # Create final embed
        embed = discord.Embed(
            title="🏁 Voting Session Ended - Final Results",
            description="Thank you for participating!",
            color=0x00ff00
        )
        
        # Top 5 podium
        podium_emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        top_5 = results[:5]
        
        podium_text = []
        for i, result in enumerate(top_5):
            emoji = podium_emojis[i]
            champion = result['champion_name']
            points = result['total_points']
            votes = result['vote_count']
            podium_text.append(f"{emoji} **{champion}** - {points} points ({votes} votes)")
        
        if podium_text:
            embed.add_field(
                name="🏆 Final Top 5",
                value="\n".join(podium_text),
                inline=False
            )
        else:
            embed.add_field(
                name="🏆 Final Top 5",
                value="*No votes were cast*",
                inline=False
            )
        
        # All other champions
        others = results[5:]
        if others:
            others_text = []
            for result in others:
                champion = result['champion_name']
                points = result['total_points']
                votes = result['vote_count']
                others_text.append(f"• **{champion}** - {points} points ({votes} votes)")
            
            embed.add_field(
                name="📊 Other Champions",
                value="\n".join(others_text),
                inline=False
            )
        
        embed.set_footer(text=f"Session ID: {session['id']} • Ended by {interaction.user.name}")
        
        # Update the original message with final results
        try:
            if session['message_id']:
                channel = self.bot.get_channel(session['channel_id'])
                if channel:
                    message = await channel.fetch_message(session['message_id'])
                    await message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Failed to update final voting embed: {e}")
        
        await interaction.response.send_message(
            f"✅ Voting session ended!\nTotal champions voted for: **{len(results)}**",
            ephemeral=True
        )
        
        logger.info(f"Voting session {session['id']} ended by {interaction.user.name}")

async def setup(bot):
    await bot.add_cog(VoteCommands(bot))
