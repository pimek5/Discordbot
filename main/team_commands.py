import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db

logger = logging.getLogger("team_commands")


class TeamCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    team = app_commands.Group(name="team", description="League teams management")

    def _get_verified_accounts(self, db, db_user_id: int):
        accounts = db.get_user_accounts(db_user_id)
        return [account for account in accounts if account.get("verified")]

    @team.command(name="create", description="Create a new team")
    @app_commands.describe(name="Team name")
    async def team_create(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        clean_name = name.strip()
        if len(clean_name) < 3 or len(clean_name) > 50:
            await interaction.followup.send("❌ Team name must be between 3 and 50 characters.", ephemeral=True)
            return

        db = get_db()
        db_user = db.get_user_by_discord_id(interaction.user.id)
        if not db_user:
            await interaction.followup.send("❌ You need to link a Riot account first using `/link`.", ephemeral=True)
            return

        verified_accounts = self._get_verified_accounts(db, db_user["id"])
        if not verified_accounts:
            await interaction.followup.send("❌ You need at least one verified Riot account.", ephemeral=True)
            return

        existing_team = db.get_user_team(guild.id, db_user["id"])
        if existing_team:
            await interaction.followup.send(f"❌ You are already in team **{existing_team['name']}**.", ephemeral=True)
            return

        if db.get_team_by_name(guild.id, clean_name):
            await interaction.followup.send("❌ Team with this name already exists.", ephemeral=True)
            return

        try:
            db.create_team(guild.id, clean_name, db_user["id"], db_user["id"])
            await interaction.followup.send(
                f"✅ Team **{clean_name}** created!\n"
                f"👑 Captain: {interaction.user.mention}",
                ephemeral=True,
            )
        except Exception as error:
            logger.error("Failed to create team: %s", error)
            await interaction.followup.send("❌ Failed to create team. Try a different name.", ephemeral=True)

    @team.command(name="invite", description="Invite a user to your team")
    @app_commands.describe(user="User to invite")
    async def team_invite(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        if user.bot:
            await interaction.followup.send("❌ You cannot invite a bot.", ephemeral=True)
            return

        db = get_db()
        inviter_db_user = db.get_user_by_discord_id(interaction.user.id)
        if not inviter_db_user:
            await interaction.followup.send("❌ You need to link a Riot account first.", ephemeral=True)
            return

        inviter_team = db.get_user_team(guild.id, inviter_db_user["id"])
        if not inviter_team:
            await interaction.followup.send("❌ You are not in any team.", ephemeral=True)
            return

        if inviter_team["captain_user_id"] != inviter_db_user["id"]:
            await interaction.followup.send("❌ Only the team captain can invite members.", ephemeral=True)
            return

        target_db_user = db.get_user_by_discord_id(user.id)
        if not target_db_user:
            await interaction.followup.send(f"❌ {user.mention} has not linked any Riot account.", ephemeral=True)
            return

        target_verified = self._get_verified_accounts(db, target_db_user["id"])
        if not target_verified:
            await interaction.followup.send(f"❌ {user.mention} has no verified Riot account.", ephemeral=True)
            return

        target_team = db.get_user_team(guild.id, target_db_user["id"])
        if target_team:
            await interaction.followup.send(
                f"❌ {user.mention} is already in team **{target_team['name']}**.",
                ephemeral=True,
            )
            return

        try:
            added = db.add_team_member(inviter_team["id"], target_db_user["id"], inviter_db_user["id"])
            if not added:
                await interaction.followup.send(f"⚠️ {user.mention} is already in this team.", ephemeral=True)
                return

            await interaction.followup.send(
                f"✅ {user.mention} joined team **{inviter_team['name']}**.",
                ephemeral=True,
            )
        except Exception as error:
            logger.error("Failed to invite member: %s", error)
            await interaction.followup.send("❌ Failed to invite member.", ephemeral=True)

    @team.command(name="remove", description="Remove a user from your team")
    @app_commands.describe(user="User to remove")
    async def team_remove(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        db = get_db()
        actor_db_user = db.get_user_by_discord_id(interaction.user.id)
        if not actor_db_user:
            await interaction.followup.send("❌ You need to link a Riot account first.", ephemeral=True)
            return

        actor_team = db.get_user_team(guild.id, actor_db_user["id"])
        if not actor_team:
            await interaction.followup.send("❌ You are not in any team.", ephemeral=True)
            return

        if actor_team["captain_user_id"] != actor_db_user["id"]:
            await interaction.followup.send("❌ Only the team captain can remove members.", ephemeral=True)
            return

        target_db_user = db.get_user_by_discord_id(user.id)
        if not target_db_user:
            await interaction.followup.send(f"❌ {user.mention} has no linked account.", ephemeral=True)
            return

        target_team = db.get_user_team(guild.id, target_db_user["id"])
        if not target_team or target_team["id"] != actor_team["id"]:
            await interaction.followup.send(f"❌ {user.mention} is not in your team.", ephemeral=True)
            return

        if target_db_user["id"] == actor_team["captain_user_id"]:
            await interaction.followup.send("❌ You cannot remove the team captain.", ephemeral=True)
            return

        removed = db.remove_team_member(actor_team["id"], target_db_user["id"])
        if not removed:
            await interaction.followup.send("❌ Failed to remove member.", ephemeral=True)
            return

        await interaction.followup.send(
            f"✅ Removed {user.mention} from team **{actor_team['name']}**.",
            ephemeral=True,
        )

    @team.command(name="config", description="Configure your team")
    @app_commands.describe(name="New team name", tag="Team tag (max 12 chars)")
    async def team_config(
        self,
        interaction: discord.Interaction,
        name: Optional[str] = None,
        tag: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        db = get_db()
        actor_db_user = db.get_user_by_discord_id(interaction.user.id)
        if not actor_db_user:
            await interaction.followup.send("❌ You need to link a Riot account first.", ephemeral=True)
            return

        actor_team = db.get_user_team(guild.id, actor_db_user["id"])
        if not actor_team:
            await interaction.followup.send("❌ You are not in any team.", ephemeral=True)
            return

        if actor_team["captain_user_id"] != actor_db_user["id"]:
            await interaction.followup.send("❌ Only the team captain can configure team settings.", ephemeral=True)
            return

        if name is None and tag is None:
            members = db.get_team_members(actor_team["id"])
            member_mentions = "\n".join([f"• <@{m['snowflake']}> ({m['role']})" for m in members]) or "No members"
            embed = discord.Embed(title=f"⚙️ Team Config: {actor_team['name']}")
            embed.add_field(name="Tag", value=actor_team.get("tag") or "(none)", inline=False)
            embed.add_field(name="Members", value=member_mentions[:1024], inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        new_name = name.strip() if name is not None else None
        new_tag = tag.strip() if tag is not None else None

        if new_name is not None and (len(new_name) < 3 or len(new_name) > 50):
            await interaction.followup.send("❌ Team name must be between 3 and 50 characters.", ephemeral=True)
            return

        if new_tag is not None and len(new_tag) > 12:
            await interaction.followup.send("❌ Team tag must be max 12 characters.", ephemeral=True)
            return

        if new_name and new_name.lower() != actor_team["name"].lower():
            existing = db.get_team_by_name(guild.id, new_name)
            if existing and existing["id"] != actor_team["id"]:
                await interaction.followup.send("❌ Team with this name already exists.", ephemeral=True)
                return

        try:
            updated = db.update_team_config(actor_team["id"], name=new_name, tag=new_tag)
            if not updated:
                await interaction.followup.send("⚠️ Nothing changed.", ephemeral=True)
                return

            refreshed = db.get_user_team(guild.id, actor_db_user["id"])
            await interaction.followup.send(
                f"✅ Team updated!\n"
                f"• Name: **{refreshed['name']}**\n"
                f"• Tag: **{refreshed.get('tag') or '(none)'}**",
                ephemeral=True,
            )
        except Exception as error:
            logger.error("Failed to update team config: %s", error)
            await interaction.followup.send("❌ Failed to update team config.", ephemeral=True)
