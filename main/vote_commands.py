"""
Vote Commands Module
/vote, /votestart, /votestop, /voteexclude, /voteinclude
"""

import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, List
import logging

from database import get_db
from riot_api import CHAMPION_ID_TO_NAME
from champion_aliases import normalize_champion_name

logger = logging.getLogger('vote_commands')

# Configuration
VOTING_CHANNEL_ID = 1473497433336975573
ADMIN_ROLE_ID = 1153030265782927501
BOOSTER_ROLE_IDS = [1168616737692991499]  # Server Boosters

class VoteCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not self.voting_session_monitor.is_running():
            self.voting_session_monitor.start()

    def cog_unload(self):
        if self.voting_session_monitor.is_running():
            self.voting_session_monitor.cancel()
    
    def is_voting_channel(self, channel_id: int) -> bool:
        """Check if channel is the voting channel"""
        return channel_id == VOTING_CHANNEL_ID
    
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
        return any(role.id in BOOSTER_ROLE_IDS for role in member.roles)
    
    def get_points_multiplier(self, interaction: discord.Interaction) -> int:
        """Get points multiplier based on user roles (2 for boosters, 1 for others)"""
        return 2 if self.is_booster(interaction) else 1

    def parse_end_datetime(self, date_text: str, time_text: str) -> datetime.datetime:
        """Parse DD.MM[.YYYY] and HH:MM into a naive datetime."""
        date_parts = date_text.strip().split('.')
        if len(date_parts) not in (2, 3):
            raise ValueError("Date must be in format DD.MM or DD.MM.YYYY")

        day = int(date_parts[0])
        month = int(date_parts[1])
        year = int(date_parts[2]) if len(date_parts) == 3 else datetime.datetime.now().year

        time_parts = time_text.strip().split(':')
        if len(time_parts) != 2:
            raise ValueError("Time must be in format HH:MM")

        hour = int(time_parts[0])
        minute = int(time_parts[1])

        return datetime.datetime(year, month, day, hour, minute, 0)

    def format_countdown(self, end_at: datetime.datetime) -> str:
        """Format time remaining for display in the embed."""
        remaining = end_at - datetime.datetime.now()
        total_seconds = int(remaining.total_seconds())
        if total_seconds <= 0:
            return "Ends any moment now"

        days, remainder = divmod(total_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)

        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if not days and not hours:
            parts.append(f"{minutes}m")
        return "Remaining: " + " ".join(parts)

    def create_results_embed(self, results: List[dict], session: dict, title: str, description: str) -> discord.Embed:
        """Create a result embed for finished voting sessions."""
        embed = discord.Embed(title=title, description=description, color=0x00ff00)

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
            embed.add_field(name="🏆 Results", value="\n".join(podium_text), inline=False)
        else:
            embed.add_field(name="🏆 Results", value="*No votes were cast*", inline=False)

        others = results[5:]
        if others:
            others_text = []
            for result in others[:15]:
                champion = result['champion_name']
                points = result['total_points']
                votes = result['vote_count']
                others_text.append(f"• **{champion}** - {points} points ({votes} votes)")

            if len(others) > 15:
                others_text.append(f"*...and {len(others) - 15} more*")

            embed.add_field(name="📊 Other Champions", value="\n".join(others_text), inline=False)

        unique_voters = get_db().get_unique_voter_count(session['id'])
        embed.set_footer(text=f"📊 Final: {unique_voters} user{'s' if unique_voters != 1 else ''} participated")
        return embed
    
    def validate_champions(self, champion_names: List[str], excluded_champions: List[str] = None) -> tuple[bool, Optional[str], List[str]]:
        """
        Validate champion names using aliases.
        Returns: (is_valid, error_message, normalized_names)
        """
        if len(champion_names) < 1 or len(champion_names) > 5:
            return False, "You must vote for 1 to 5 champions!", []
        
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
        if len(set(normalized)) != len(normalized):
            return False, "❌ You cannot vote for the same champion twice!", []
        
        return True, None, normalized
    
    def create_voting_embed(self, results: List[dict], session: dict, excluded_champions: List[str] = None) -> discord.Embed:
        """Create the voting results embed with top 5 and others"""
        db = get_db()
        unique_voters = db.get_unique_voter_count(session['id'])
        
        embed = discord.Embed(
            title="🗳️ Champion Voting - Live Results",
            description="**How to vote:** Write one champion name per message\n"
                       "You can vote up to 5 times for different champions\n"
                       "Examples: `Ahri` | `Yasuo` | `Lee Sin` (then repeat up to 5 times)\n"
                       "💎 **Server Boosters:** Count as **1 vote but give 2 points**\n"
                       "🚫 No duplicates - each champion only counts once",
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

        end_at = session.get('end_at')
        if end_at:
            embed.add_field(
                name="⏰ Voting Ends",
                value=f"{end_at.strftime('%d.%m.%Y %H:%M')}\n{self.format_countdown(end_at)}",
                inline=False,
            )
        else:
            embed.add_field(
                name="⏰ Voting Ends",
                value="Not scheduled yet",
                inline=False,
            )
        
        embed.set_footer(text=f"📊 {unique_voters} user{'s' if unique_voters != 1 else ''} participated • Voting in progress")
        return embed

    async def refresh_voting_message(self, session: dict):
        """Rebuild and edit the live voting embed."""
        db = get_db()
        results = db.get_voting_results(session['id'])
        excluded = session.get('excluded_champions') or []
        embed = self.create_voting_embed(results, session, excluded)

        try:
            if session.get('message_id'):
                channel = self.bot.get_channel(session['channel_id'])
                if channel:
                    message_obj = await channel.fetch_message(session['message_id'])
                    await message_obj.edit(embed=embed)
        except Exception as e:
            logger.error(f"Failed to refresh voting embed: {e}")

    async def send_voting_reminder(self, session: dict, days_remaining: int):
        """Ping everyone when the voting session enters the last 3 days."""
        channel = self.bot.get_channel(session['channel_id'])
        if not channel:
            logger.warning("⚠️ Voting reminder skipped for session %s: channel %s not found", session['id'], session['channel_id'])
            return

        day_label = "Day" if days_remaining == 1 else "Days"
        logger.info("📢 Sending voting reminder for session %s: %s %s remaining", session['id'], days_remaining, day_label)
        try:
            await channel.send(
                content=f"@everyone {days_remaining} {day_label} remaining Vote",
                allowed_mentions=discord.AllowedMentions(everyone=True),
                delete_after=10,
            )
            logger.info("✅ Voting reminder sent for session %s", session['id'])
        except Exception as e:
            logger.error(f"Failed to send voting reminder: {e}")

    async def finalize_voting_session(self, session: dict, ended_by: Optional[str] = None):
        """Stop a session, block the channel, and post the final results."""
        db = get_db()
        channel = self.bot.get_channel(session['channel_id'])
        if not channel:
            return

        try:
            await channel.set_permissions(
                channel.guild.default_role,
                send_messages=False,
                reason="Voting session ended",
            )
        except Exception as e:
            logger.error(f"Failed to block voting channel: {e}")

        db.end_voting_session(session['id'])

        results = db.get_voting_results(session['id'])
        embed = self.create_results_embed(results, session, "🏁 Voting Ended", "Voting session has concluded!")

        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send final voting results: {e}")

        if ended_by:
            logger.info(f"Voting session {session['id']} ended by {ended_by}")
        else:
            logger.info(f"Voting session {session['id']} ended automatically")

    @tasks.loop(minutes=1)
    async def voting_session_monitor(self):
        """Keep countdown embeds current and auto-finish scheduled voting sessions."""
        db = get_db()
        sessions = db.get_all_active_voting_sessions()
        now = datetime.datetime.now()

        for session in sessions:
            end_at = session.get('end_at')
            if end_at:
                remaining_seconds = int((end_at - now).total_seconds())
                logger.info("🕒 Voting monitor session %s: end_at=%s, now=%s, remaining_seconds=%s", session['id'], end_at, now, remaining_seconds)
                if remaining_seconds <= 0:
                    logger.info("🛑 Voting session %s reached its end time; finalizing", session['id'])
                    await self.finalize_voting_session(session)
                    continue

                days_remaining = (end_at.date() - now.date()).days
                logger.info("⏳ Voting session %s has %s day(s) remaining", session['id'], days_remaining)
                if days_remaining in (3, 2, 1):
                    reminder_flag = f"reminder_{days_remaining}d_sent"
                    if not session.get(reminder_flag):
                        logger.info("📣 Voting session %s reached the %s-day reminder threshold", session['id'], days_remaining)
                        await self.send_voting_reminder(session, days_remaining)
                        db.mark_voting_reminder_sent(session['id'], days_remaining)
                        session[reminder_flag] = True
                    else:
                        logger.info("⏭️ Voting session %s already sent the %s-day reminder", session['id'], days_remaining)

            await self.refresh_voting_message(session)

    @voting_session_monitor.before_loop
    async def before_voting_session_monitor(self):
        await self.bot.wait_until_ready()
    
    async def process_vote_message(self, message: discord.Message) -> bool:
        """Process a vote message in the voting channel. Returns True if valid vote."""
        print(f"\n[VOTE] ===== START process_vote_message() =====")
        print(f"[VOTE] Message: '{message.content}' from {message.author}")
        print(f"[VOTE] Channel ID: {message.channel.id} (expecting 1473497433336975573)")
        
        if not self.is_voting_channel(message.channel.id):
            print(f"[VOTE] ❌ Not voting channel, returning")
            return False
        if message.author.bot:
            print(f"[VOTE] ❌ Bot message, returning")
            return False
        
        db = get_db()
        guild_id = message.guild.id if message.guild else None
        print(f"[VOTE] Guild ID: {guild_id}")
        
        if not guild_id:
            print(f"[VOTE] ❌ No guild, returning")
            return False
        
        session = db.get_active_voting_session(guild_id)
        print(f"[VOTE] Active session exists: {session is not None}")
        if not session:
            print(f"[VOTE] No session - sending notification")
            # Inform user that voting is not active
            try:
                await message.delete()
                embed = discord.Embed(
                    title="⏸️ Voting Not Active",
                    description="There is no active voting session. Wait for an admin to use `/votestart`!",
                    color=0xffa500
                )
                await message.channel.send(f"{message.author.mention}", embed=embed, delete_after=10)
            except Exception as e:
                logger.error(f"Failed to send no-session message: {e}")
            return False

        end_at = session.get('end_at')
        if end_at and datetime.datetime.now() >= end_at:
            print("[VOTE] Session expired while processing vote; finalizing now")
            await self.finalize_voting_session(session)
            return False
        
        print(f"[VOTE] ✅ Session found, ID: {session['id']}")
        
        # Parse champion names from message
        text = message.content.strip()
        champion_names = [c.strip() for c in text.split() if c.strip()]
        print(f"[VOTE] Parsed champion names: {champion_names}")
        
        # Allow only 1 champion per message (cumulative voting)
        if len(champion_names) != 1:
            print(f"[VOTE] ❌ Wrong count of champions ({len(champion_names)}), need exactly 1")
            try:
                await message.delete()
                embed = discord.Embed(
                    title="❌ One Champion Only",
                    description="Write **one champion name per message**.\nYou can vote up to 5 times (for 5 different champions) in this session!",
                    color=0xff0000
                )
                await message.channel.send(f"{message.author.mention}", embed=embed, delete_after=5)
            except Exception as e:
                logger.error(f"Failed to send error message: {e}")
            return False
        
        champion_name = champion_names[0]
        
        # Validate single champion
        excluded = session.get('excluded_champions') or []
        is_valid, error_msg, normalized_names = self.validate_champions([champion_name], excluded)
        print(f"[VOTE] Validation - Valid: {is_valid}, Normalized: {normalized_names}, Error: {error_msg}")
        
        if not is_valid:
            try:
                await message.delete()
                embed = discord.Embed(title="❌ Invalid Champion", description=error_msg, color=0xff0000)
                await message.channel.send(f"{message.author.mention}", embed=embed, delete_after=5)
            except Exception as e:
                logger.error(f"Failed to send error message: {e}")
            return False
        
        normalized_champion = normalized_names[0]
        
        # Get points multiplier
        points = 2 if await self.is_user_booster(message.guild, message.author.id) else 1
        is_booster = points == 2
        
        # Add cumulative vote
        result = db.add_vote_cumulative(session['id'], message.author.id, normalized_champion, points)
        print(f"[VOTE] add_vote_cumulative result: {result}")
        
        if not result['success']:
            try:
                await message.delete()
                embed = discord.Embed(
                    title="⚠️ Vote Not Recorded",
                    description=result['message'],
                    color=0xffa500
                )
                await message.channel.send(f"{message.author.mention}", embed=embed, delete_after=5)
            except Exception as e:
                logger.error(f"Failed to send vote error message: {e}")
            return False
        
        # Delete user's message
        try:
            await message.delete()
        except:
            pass
        
        # Get updated results
        results = db.get_voting_results(session['id'])
        
        # Update the voting embed
        await self.refresh_voting_message(session)
        
        # Send confirmation (via channel, ephemeral-like with auto-delete)
        booster_text = " (💎 x2 points as Server Booster!)" if is_booster else ""
        confirm_embed = discord.Embed(
            title="✅ Vote Recorded",
            description=f"**Voted for:** {normalized_champion}\n**Your votes:** {result['current_count']}/5{booster_text}",
            color=0x00ff00
        )
        try:
            await message.channel.send(f"{message.author.mention}", embed=confirm_embed, delete_after=5)
        except:
            pass
        
        logger.info(f"Vote recorded: {message.author.name} voted for {normalized_names} ({points} points each)")
        return True
    
    async def is_user_booster(self, guild: discord.Guild, user_id: int) -> bool:
        """Check if user is a server booster (async version)"""
        member = guild.get_member(user_id)
        if not member:
            return False
        return any(role.id in BOOSTER_ROLE_IDS for role in member.roles)
    
    @app_commands.command(name="votestart", description="[ADMIN] Start a new voting session")
    async def vote_start(self, interaction: discord.Interaction):
        """Start a new voting session (admin only) - blocks writing"""
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
        
        # Get voting channel
        channel = self.bot.get_channel(VOTING_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message(
                f"❌ Voting channel <#{VOTING_CHANNEL_ID}> not found!",
                ephemeral=True
            )
            return
        
        # Unblock channel (allow sending messages) - only modify send_messages, preserve visibility
        try:
            await channel.set_permissions(
                interaction.guild.default_role,
                send_messages=True,
                reason="Voting session started"
            )
        except Exception as e:
            logger.error(f"Failed to unblock voting channel: {e}")
            await interaction.response.send_message(
                f"❌ Failed to unblock voting channel: {e}",
                ephemeral=True
            )
            return
        
        # Get winners from previous session to auto-exclude
        previous_winners = db.get_previous_session_winners(interaction.guild_id, limit=5)
        
        # Create new voting session with exclusions
        session_id = db.create_voting_session(
            interaction.guild_id,
            VOTING_CHANNEL_ID,
            interaction.user.id,
            excluded_champions=previous_winners
        )
        session = {'id': session_id, 'end_at': None}
        
        # Create initial embed
        embed = self.create_voting_embed([], session, previous_winners)
        
        # Send the embed to the channel
        message = await channel.send(embed=embed)
        
        # Store message ID
        db.update_voting_message_id(session_id, message.id)
        
        # Ping notification roles
        pings = []
        for role_id in BOOSTER_ROLE_IDS:
            role = interaction.guild.get_role(role_id)
            if role:
                pings.append(role.mention)
        
        ping_text = f"🗳️ **Voting session started!** {' '.join(pings)}\nHead over to <#{VOTING_CHANNEL_ID}> to vote!"
        if previous_winners:
            ping_text += f"\n🚫 Auto-excluded top 5 from last session: {', '.join(previous_winners)}"
        
        try:
            await channel.send(ping_text)
        except:
            pass
        
        await interaction.response.send_message(
            f"✅ Voting session started - channel unblocked!" +
            (f"\n🚫 Auto-excluded: {', '.join(previous_winners)}" if previous_winners else "") +
            "\n⏰ Use `/votestop <date> <time>` to schedule the end.",
            ephemeral=True
        )
        
        logger.info(f"Voting session {session_id} started by {interaction.user.name}")
    
    @app_commands.command(name="votestop", description="[ADMIN] Stop the current voting session or schedule its end")
    @app_commands.describe(
        end_date="Optional end date in DD.MM or DD.MM.YYYY format, e.g. 28.07",
        end_time="Optional end time in 24h HH:MM format, e.g. 12:00",
    )
    async def vote_stop(self, interaction: discord.Interaction, end_date: Optional[str] = None, end_time: Optional[str] = None):
        """Stop now or schedule the current voting session (admin only)."""
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

        if end_date or end_time:
            if not end_date or not end_time:
                await interaction.response.send_message(
                    "❌ Provide both a date and a time, for example `28.07` and `12:00`.",
                    ephemeral=True,
                )
                return

            try:
                scheduled_end = self.parse_end_datetime(end_date, end_time)
            except ValueError as error:
                await interaction.response.send_message(f"❌ {error}", ephemeral=True)
                return

            if scheduled_end <= datetime.datetime.now():
                await interaction.response.send_message(
                    "❌ The voting end time must be in the future.",
                    ephemeral=True,
                )
                return

            db.set_voting_end_time(session['id'], scheduled_end)
            session['end_at'] = scheduled_end
            await self.refresh_voting_message(session)

            await interaction.response.send_message(
                f"✅ Voting will end on **{scheduled_end.strftime('%d.%m.%Y %H:%M')}**\n"
                f"⏳ {self.format_countdown(scheduled_end)}",
                ephemeral=True,
            )
            logger.info(f"Voting session {session['id']} scheduled to end at {scheduled_end}")
            return
        
        results = db.get_voting_results(session['id'])
        
        await self.finalize_voting_session(session, ended_by=interaction.user.name)
        
        await interaction.response.send_message(
            f"✅ Voting session ended - channel blocked!\nTotal champions: **{len(results)}**",
            ephemeral=True
        )
        
        logger.info(f"Voting session {session['id']} ended by {interaction.user.name}")
    
    @app_commands.command(name="voteexclude", description="[ADMIN] Exclude champions from voting")
    @app_commands.describe(
        champions="Champion names to exclude (comma-separated, e.g., 'Ahri, Yasuo, asol')"
    )
    async def vote_exclude(self, interaction: discord.Interaction, champions: str):
        """Exclude champions from current voting session (admin only)"""
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
        embed = self.create_voting_embed(results, session, excluded)
        
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
    
    @app_commands.command(name="voteinclude", description="[ADMIN] Remove champion from exclusion list")
    @app_commands.describe(
        champion="Champion name to include back"
    )
    async def vote_include(self, interaction: discord.Interaction, champion: str):
        """Remove a champion from the exclusion list (admin only)"""
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
        embed = self.create_voting_embed(results, session, excluded)
        
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

    @app_commands.command(name="votefixpoints", description="[ADMIN] Fix x2 points for users without Server Booster role")
    async def vote_fix_points(self, interaction: discord.Interaction):
        """Correct voting_votes rows: set points=1 for non-boosters (admin only)."""
        if not self.has_admin_role(interaction):
            await interaction.response.send_message("❌ No permission.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        db = get_db()
        session = db.get_active_voting_session(interaction.guild_id)
        if not session:
            await interaction.followup.send("❌ No active voting session.", ephemeral=True)
            return

        session_id = session['id']

        # Get all user_ids with points=2 in this session
        double_users = db.get_votes_with_double_points(session_id)
        if not double_users:
            await interaction.followup.send("✅ No votes with x2 points found.", ephemeral=True)
            return

        # Check each user against current Server Booster role
        guild = interaction.guild
        non_boosters = []
        for uid in double_users:
            member = guild.get_member(uid)
            if member is None:
                # User left server — they can't be a booster
                non_boosters.append(uid)
                continue
            if not any(role.id in BOOSTER_ROLE_IDS for role in member.roles):
                non_boosters.append(uid)

        if not non_boosters:
            await interaction.followup.send(
                f"✅ All {len(double_users)} user(s) with x2 points are valid Server Boosters. Nothing to fix.",
                ephemeral=True,
            )
            return

        updated = db.fix_non_booster_points(session_id, non_boosters)

        # Refresh the voting embed
        try:
            results = db.get_voting_results(session_id)
            session = db.get_active_voting_session(interaction.guild_id)
            excluded = session.get('excluded_champions') or []
            embed = self.create_voting_embed(results, session, excluded)
            if session['message_id']:
                channel = self.bot.get_channel(session['channel_id'])
                if channel:
                    message = await channel.fetch_message(session['message_id'])
                    await message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Failed to refresh embed after fix: {e}")

        await interaction.followup.send(
            f"✅ Fixed **{updated}** vote row(s) for **{len(non_boosters)}** non-booster user(s). Points set to 1.",
            ephemeral=True,
        )
        logger.info(f"votefixpoints: fixed {updated} rows for {len(non_boosters)} users in session {session_id}")

async def setup(bot):
    await bot.add_cog(VoteCommands(bot))
