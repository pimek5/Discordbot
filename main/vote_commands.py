"""
Vote Commands Module
/vote, /votestart, /votestop, /voteexclude, /voteinclude
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List
import logging

from database import get_db
from riot_api import CHAMPION_ID_TO_NAME
from champion_aliases import normalize_champion_name

logger = logging.getLogger('vote_commands')

# Configuration
VOTING_THREAD_ID = 1331546029023166464
ADMIN_ROLE_ID = 1153030265782927501
GUILD_ID = 1153027935553454191  # For guild-specific commands
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
    
    def validate_champions(self, champion_names: List[str], excluded_champions: List[str] = None) -> tuple[bool, Optional[str], List[str]]:
        """
        Validate champion names using aliases.
        Returns: (is_valid, error_message, normalized_names)
        """
        if len(champion_names) != 5:
            return False, "You must vote for exactly 5 champions!", []
        
        # Get all valid champion names (values from CHAMPION_ID_TO_NAME)
        valid_champions = set(CHAMPION_ID_TO_NAME.values())
        excluded_set = set(excluded_champions or [])
        
        # Normalize and validate each champion
        normalized = []
        for name in champion_names:
            # Use alias system to normalize name
            champion = normalize_champion_name(name, valid_champions)
            
            if not champion:
                return False, f"❌ Invalid champion name: **{name}**\nTry using full names or common abbreviations (e.g., 'asol' for Aurelion Sol, 'mf' for Miss Fortune)", []
            
            # Check if champion is excluded
            if champion in excluded_set:
                return False, f"❌ **{champion}** is excluded from this voting session!", []
            
            normalized.append(champion)
        
        # Check for duplicates
        if len(set(normalized)) != 5:
            return False, "❌ You cannot vote for the same champion twice!", []
        
        return True, None, normalized
    
    def create_voting_embed(self, results: List[dict], session_id: int, excluded_champions: List[str] = None) -> discord.Embed:
        """Create the voting results embed with top 5 and others"""
        embed = discord.Embed(
            title="🗳️ Champion Voting - Live Results",
            description="Vote with `/vote [champion1] [champion2] [champion3] [champion4] [champion5]`\n"
                       "Server Boosters get 2 points per champion! 💎",
            color=0x0099ff
        )
        
        # Show excluded champions if any
        if excluded_champions:
            excluded_text = ", ".join(excluded_champions[:10])
            if len(excluded_champions) > 10:
                excluded_text += f" and {len(excluded_champions) - 10} more"
            embed.add_field(
                name="🚫 Excluded Champions",
                value=excluded_text,
                inline=False
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
    
    @app_commands.command(name="vote", description="Vote for 5 champions", guild=discord.Object(id=GUILD_ID))
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
                "An admin must use `/votestart` to begin voting.",
                ephemeral=True
            )
            return
        
        # Validate champions (with exclusions)
        champion_names = [champion1, champion2, champion3, champion4, champion5]
        excluded = session.get('excluded_champions') or []
        is_valid, error_msg, normalized_names = self.validate_champions(champion_names, excluded)
        
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
        excluded = session.get('excluded_champions') or []
        embed = self.create_voting_embed(results, session['id'], excluded)
        
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
    
    @app_commands.command(name="votestart", description="[ADMIN] Start a new voting session", guild=discord.Object(id=GUILD_ID))
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
                "Use `/votestop` to end it first.",
                ephemeral=True
            )
            return
        
        # Get winners from previous session to auto-exclude
        previous_winners = db.get_previous_session_winners(interaction.guild_id, limit=5)
        
        # Create new voting session with exclusions
        session_id = db.create_voting_session(
            interaction.guild_id,
            interaction.channel_id,
            interaction.user.id,
            excluded_champions=previous_winners
        )
        
        # Create initial embed
        embed = self.create_voting_embed([], session_id, previous_winners)
        
        # Send confirmation and embed
        if previous_winners:
            confirmation_msg = (
                f"✅ Voting session started!\n"
                f"🚫 Auto-excluded top 5 from last session: {', '.join(previous_winners)}"
            )
        else:
            confirmation_msg = "✅ Voting session started!"
        
        # Send the confirmation first
        await interaction.response.send_message(confirmation_msg, ephemeral=True)
        
        # Send the embed to the channel
        channel = self.bot.get_channel(interaction.channel_id)
        message = await channel.send(embed=embed)
        
        # Store message ID
        db.update_voting_message_id(session_id, message.id)
        
        logger.info(f"Voting session {session_id} started by {interaction.user.name} with {len(previous_winners)} exclusions")
    
    @app_commands.command(name="votestop", description="[ADMIN] Stop the current voting session", guild=discord.Object(id=GUILD_ID))
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
    
    @app_commands.command(name="voteexclude", description="[ADMIN] Exclude champions from voting", guild=discord.Object(id=GUILD_ID))
    @app_commands.describe(
        champions="Champion names to exclude (comma-separated, e.g., 'Ahri, Yasuo, asol')"
    )
    async def vote_exclude(self, interaction: discord.Interaction, champions: str):
        """Exclude champions from current voting session (admin only)"""
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
                "❌ You don't have permission to manage exclusions!",
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
        
        # Parse and validate champion names
        champion_list = [c.strip() for c in champions.split(',')]
        valid_champions = set(CHAMPION_ID_TO_NAME.values())
        
        normalized_champions = []
        invalid_champions = []
        
        for champ in champion_list:
            normalized = normalize_champion_name(champ, valid_champions)
            if normalized:
                normalized_champions.append(normalized)
            else:
                invalid_champions.append(champ)
        
        if invalid_champions:
            await interaction.response.send_message(
                f"❌ Invalid champion names: {', '.join(invalid_champions)}",
                ephemeral=True
            )
            return
        
        # Add to exclusion list
        db.add_excluded_champions(session['id'], normalized_champions)
        
        # Update the embed
        results = db.get_voting_results(session['id'])
        # Refresh session data to get updated exclusions
        session = db.get_active_voting_session(interaction.guild_id)
        excluded = session.get('excluded_champions') or []
        embed = self.create_voting_embed(results, session['id'], excluded)
        
        # Update the message
        try:
            if session['message_id']:
                channel = self.bot.get_channel(session['channel_id'])
                if channel:
                    message = await channel.fetch_message(session['message_id'])
                    await message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Failed to update voting embed: {e}")
        
        await interaction.response.send_message(
            f"✅ Excluded: {', '.join(normalized_champions)}",
            ephemeral=True
        )
        
        logger.info(f"Champions excluded by {interaction.user.name}: {normalized_champions}")
    
    @app_commands.command(name="voteinclude", description="[ADMIN] Remove champion from exclusion list", guild=discord.Object(id=GUILD_ID))
    @app_commands.describe(
        champion="Champion name to include back"
    )
    async def vote_include(self, interaction: discord.Interaction, champion: str):
        """Remove a champion from the exclusion list (admin only)"""
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
                "❌ You don't have permission to manage exclusions!",
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
        
        # Validate champion name
        valid_champions = set(CHAMPION_ID_TO_NAME.values())
        normalized = normalize_champion_name(champion, valid_champions)
        
        if not normalized:
            await interaction.response.send_message(
                f"❌ Invalid champion name: {champion}",
                ephemeral=True
            )
            return
        
        # Check if champion is actually excluded
        excluded = session.get('excluded_champions') or []
        if normalized not in excluded:
            await interaction.response.send_message(
                f"❌ **{normalized}** is not in the exclusion list!",
                ephemeral=True
            )
            return
        
        # Remove from exclusion list
        db.remove_excluded_champion(session['id'], normalized)
        
        # Update the embed
        results = db.get_voting_results(session['id'])
        # Refresh session data to get updated exclusions
        session = db.get_active_voting_session(interaction.guild_id)
        excluded = session.get('excluded_champions') or []
        embed = self.create_voting_embed(results, session['id'], excluded)
        
        # Update the message
        try:
            if session['message_id']:
                channel = self.bot.get_channel(session['channel_id'])
                if channel:
                    message = await channel.fetch_message(session['message_id'])
                    await message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Failed to update voting embed: {e}")
        
        await interaction.response.send_message(
            f"✅ **{normalized}** is now allowed for voting!",
            ephemeral=True
        )
        
        logger.info(f"Champion {normalized} included back by {interaction.user.name}")

async def setup(bot):
    await bot.add_cog(VoteCommands(bot))
