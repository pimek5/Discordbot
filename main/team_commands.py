import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_db
from emoji_dict import get_rank_emoji

logger = logging.getLogger("team_commands")


class TeamCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    team = app_commands.Group(name="team", description="League teams management")

    def _get_verified_accounts(self, db, db_user_id: int):
        accounts = db.get_user_accounts(db_user_id)
        return [account for account in accounts if account.get("verified")]

    def _tier_score(self, tier: str) -> int:
        order = {
            "IRON": 1,
            "BRONZE": 2,
            "SILVER": 3,
            "GOLD": 4,
            "PLATINUM": 5,
            "EMERALD": 6,
            "DIAMOND": 7,
            "MASTER": 8,
            "GRANDMASTER": 9,
            "CHALLENGER": 10,
        }
        return order.get((tier or "").upper(), 0)

    def _division_score(self, division: str) -> int:
        order = {"IV": 1, "III": 2, "II": 3, "I": 4}
        return order.get((division or "").upper(), 0)

    def _format_rank_from_score(self, score: float) -> str:
        tier_names = {
            1: "Iron",
            2: "Bronze",
            3: "Silver",
            4: "Gold",
            5: "Platinum",
            6: "Emerald",
            7: "Diamond",
            8: "Master",
            9: "Grandmaster",
            10: "Challenger",
        }
        division_names = {1: "IV", 2: "III", 3: "II", 4: "I"}

        tier_score = int(score // 10000)
        if tier_score <= 0:
            return "Unranked"

        remainder = score - (tier_score * 10000)
        division_score = int(remainder // 1000)
        lp = max(0, int(round(remainder - (division_score * 1000))))

        tier = tier_names.get(tier_score, "Unranked")
        rank_emoji = get_rank_emoji(tier.upper()) if tier != "Unranked" else ""
        emoji_prefix = f"{rank_emoji} " if rank_emoji else ""
        if tier_score >= 8:
            return f"{emoji_prefix}{tier} • {lp} LP"

        division = division_names.get(max(1, min(4, division_score)), "IV")
        return f"{emoji_prefix}{tier} {division} • {lp} LP"

    def _best_rank_stats(self, ranks: list) -> dict:
        if not ranks:
            return {"display": "Unranked", "rank_score": None, "wr_pct": None}

        best = None
        best_key = (-1, -1, -1)

        for rank_data in ranks:
            tier = rank_data.get("tier")
            division = rank_data.get("rank")
            lp = rank_data.get("league_points", 0)

            key = (self._tier_score(tier), self._division_score(division), int(lp or 0))
            if key > best_key:
                best_key = key
                best = rank_data

        if not best or best_key[0] <= 0:
            return {"display": "Unranked", "rank_score": None, "wr_pct": None}

        tier = (best.get("tier") or "").title()
        division = best.get("rank") or ""
        lp = int(best.get("league_points", 0) or 0)
        wins = int(best.get("wins", 0) or 0)
        losses = int(best.get("losses", 0) or 0)
        total = wins + losses
        wr_pct = (wins / total * 100) if total > 0 else None
        wr = f"{wr_pct:.0f}%" if wr_pct is not None else "--"

        rank_emoji = get_rank_emoji((best.get("tier") or "").upper())
        emoji_prefix = f"{rank_emoji} " if rank_emoji else ""
        display = f"{emoji_prefix}{tier} {division} • {lp} LP • {wr} WR"
        rank_score = best_key[0] * 10000 + best_key[1] * 1000 + lp
        return {"display": display, "rank_score": rank_score, "wr_pct": wr_pct}

    def _best_rank_display(self, ranks: list) -> str:
        return self._best_rank_stats(ranks)["display"]

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
            member_lines = []
            rank_scores = []
            wr_values = []
            for member in members:
                prefix = "👑" if member.get("role") == "captain" else "•"
                rank_stats = self._best_rank_stats(db.get_user_ranks(member["user_id"]))
                rank_display = rank_stats["display"]
                member_lines.append(f"{prefix} <@{member['snowflake']}> — {rank_display}")

                if rank_stats["rank_score"] is not None:
                    rank_scores.append(rank_stats["rank_score"])
                if rank_stats["wr_pct"] is not None:
                    wr_values.append(rank_stats["wr_pct"])

            member_mentions = "\n".join(member_lines) if member_lines else "No members"
            embed = discord.Embed(title=f"⚙️ Team Config: {actor_team['name']}")
            embed.add_field(name="Tag", value=actor_team.get("tag") or "(none)", inline=False)
            embed.add_field(name="Members", value=member_mentions[:1024], inline=False)
            avg_rank = self._format_rank_from_score(sum(rank_scores) / len(rank_scores)) if rank_scores else "Unranked"
            avg_wr = f"{(sum(wr_values) / len(wr_values)):.1f}%" if wr_values else "--"
            embed.add_field(
                name="Averages",
                value=f"• Rank: **{avg_rank}**\n• WR: **{avg_wr} WR**",
                inline=False,
            )
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
