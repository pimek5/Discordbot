import logging
import re
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

        solo_queues = [
            rank_data
            for rank_data in ranks
            if "SOLO" in ((rank_data.get("queueType") or rank_data.get("queue") or "").upper())
        ]
        flex_queues = [
            rank_data
            for rank_data in ranks
            if "FLEX" in ((rank_data.get("queueType") or rank_data.get("queue") or "").upper())
        ]

        def rank_key(rank_data: dict):
            tier = rank_data.get("tier")
            division = rank_data.get("rank")
            lp = rank_data.get("league_points")
            if lp is None:
                lp = rank_data.get("leaguePoints", 0)
            return (self._tier_score(tier), self._division_score(division), int(lp or 0))

        highest_solo = max(solo_queues, key=rank_key) if solo_queues else None
        highest_flex = max(flex_queues, key=rank_key) if flex_queues else None

        best = highest_solo or highest_flex or max(ranks, key=rank_key)
        best_key = rank_key(best) if best else (-1, -1, -1)

        if not best or best_key[0] <= 0:
            return {"display": "Unranked", "rank_score": None, "wr_pct": None}

        tier = (best.get("tier") or "").title()
        division = best.get("rank") or ""
        lp = best.get("league_points")
        if lp is None:
            lp = best.get("leaguePoints", 0)
        lp = int(lp or 0)
        wins = int(best.get("wins", 0) or 0)
        losses = int(best.get("losses", 0) or 0)
        total = wins + losses
        wr_pct = (wins / total * 100) if total > 0 else None
        wr = f"{wr_pct:.0f}%" if wr_pct is not None else "--"

        rank_emoji = get_rank_emoji((best.get("tier") or "").upper())
        emoji_prefix = f"{rank_emoji} " if rank_emoji else ""
        rank_label = f"{tier} {division}".strip()
        display = f"{emoji_prefix}{rank_label} • {lp} LP • {wr} WR"
        rank_score = best_key[0] * 10000 + best_key[1] * 1000 + lp
        return {"display": display, "rank_score": rank_score, "wr_pct": wr_pct}

    def _best_rank_display(self, ranks: list) -> str:
        return self._best_rank_stats(ranks)["display"]

    def _resolve_member_from_query(self, guild: discord.Guild, query: str) -> Optional[discord.Member]:
        match = re.match(r"^<@!?(\d+)>$", query)
        if match:
            member_id = int(match.group(1))
            return guild.get_member(member_id)

        normalized = query.strip().lower()
        if not normalized:
            return None

        def member_name_candidates(member: discord.Member) -> list:
            values = [member.display_name, member.name]
            global_name = getattr(member, "global_name", None)
            if global_name:
                values.append(global_name)
            return [v.lower() for v in values if v]

        for member in guild.members:
            names = member_name_candidates(member)
            if normalized in names:
                return member

        for member in guild.members:
            names = member_name_candidates(member)
            if any(name.startswith(normalized) for name in names):
                return member

        for member in guild.members:
            names = member_name_candidates(member)
            if any(normalized in name for name in names):
                return member

        return None

    async def _get_effective_ranks(self, db, user_id: int) -> list:
        cached_ranks = db.get_user_ranks(user_id)
        cached_best = self._best_rank_stats(cached_ranks)
        if cached_best["rank_score"] is not None:
            return cached_ranks

        riot_api = getattr(self.bot, "riot_api", None)
        if not riot_api:
            return cached_ranks

        accounts = self._get_verified_accounts(db, user_id)
        if not accounts:
            return cached_ranks

        all_live_ranks = []
        for account in accounts:
            puuid = account.get("puuid")
            region = account.get("region")
            if not puuid or not region:
                continue
            try:
                live_ranks = await riot_api.get_ranked_stats_by_puuid(puuid, region)
                if live_ranks:
                    all_live_ranks.extend(live_ranks)
                    for queue in live_ranks:
                        db.update_ranked_stats(
                            user_id,
                            queue.get("queueType", ""),
                            queue.get("tier", "UNRANKED"),
                            queue.get("rank", ""),
                            int(queue.get("leaguePoints", 0) or 0),
                            int(queue.get("wins", 0) or 0),
                            int(queue.get("losses", 0) or 0),
                            bool(queue.get("hotStreak", False)),
                            bool(queue.get("veteran", False)),
                            bool(queue.get("freshBlood", False)),
                        )
            except Exception as error:
                logger.warning("Failed live rank fetch for user %s account %s: %s", user_id, account.get("id"), error)

        return all_live_ranks if all_live_ranks else cached_ranks

    async def _build_team_overview_embed(self, team: dict, db, title_prefix: str) -> discord.Embed:
        members = db.get_team_members(team["id"])
        member_lines = []
        rank_scores = []
        wr_values = []

        for member in members:
            prefix = "👑" if member.get("role") == "captain" else "•"
            member_ranks = await self._get_effective_ranks(db, member["user_id"])
            rank_stats = self._best_rank_stats(member_ranks)
            member_lines.append(f"{prefix} <@{member['snowflake']}> — {rank_stats['display']}")

            if rank_stats["rank_score"] is not None:
                rank_scores.append(rank_stats["rank_score"])
            if rank_stats["wr_pct"] is not None:
                wr_values.append(rank_stats["wr_pct"])

        member_mentions = "\n".join(member_lines) if member_lines else "No members"
        avg_rank = self._format_rank_from_score(sum(rank_scores) / len(rank_scores)) if rank_scores else "Unranked"
        avg_wr = f"{(sum(wr_values) / len(wr_values)):.1f}%" if wr_values else "--"

        embed = discord.Embed(title=f"{title_prefix}: {team['name']}")
        embed.add_field(name="Tag", value=team.get("tag") or "(none)", inline=False)
        embed.add_field(name="Description", value=team.get("description") or "(none)", inline=False)
        embed.add_field(
            name="Recruiting",
            value="✅ Open" if team.get("recruiting", True) else "⛔ Closed",
            inline=False,
        )
        embed.add_field(name="Members", value=member_mentions[:1024], inline=False)
        embed.add_field(
            name="Averages",
            value=f"• Rank: **{avg_rank}**\n• WR: **{avg_wr} WR**",
            inline=False,
        )
        return embed

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
    @app_commands.describe(
        name="New team name",
        tag="Team tag (max 12 chars)",
        description="Team description (max 180 chars)",
        recruiting="Open recruitment: true/false",
    )
    async def team_config(
        self,
        interaction: discord.Interaction,
        name: Optional[str] = None,
        tag: Optional[str] = None,
        description: Optional[str] = None,
        recruiting: Optional[bool] = None,
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

        if name is None and tag is None and description is None and recruiting is None:
            embed = await self._build_team_overview_embed(actor_team, db, "⚙️ Team Config")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        new_name = name.strip() if name is not None else None
        new_tag = tag.strip() if tag is not None else None
        new_description = description.strip() if description is not None else None

        if new_name is not None and (len(new_name) < 3 or len(new_name) > 50):
            await interaction.followup.send("❌ Team name must be between 3 and 50 characters.", ephemeral=True)
            return

        if new_tag is not None and len(new_tag) > 12:
            await interaction.followup.send("❌ Team tag must be max 12 characters.", ephemeral=True)
            return

        if new_description is not None and len(new_description) > 180:
            await interaction.followup.send("❌ Team description must be max 180 characters.", ephemeral=True)
            return

        if new_name and new_name.lower() != actor_team["name"].lower():
            existing = db.get_team_by_name(guild.id, new_name)
            if existing and existing["id"] != actor_team["id"]:
                await interaction.followup.send("❌ Team with this name already exists.", ephemeral=True)
                return

        try:
            updated = db.update_team_config(
                actor_team["id"],
                name=new_name,
                tag=new_tag,
                description=new_description,
                recruiting=recruiting,
            )
            if not updated:
                await interaction.followup.send("⚠️ Nothing changed.", ephemeral=True)
                return

            refreshed = db.get_user_team(guild.id, actor_db_user["id"])
            await interaction.followup.send(
                f"✅ Team updated!\n"
                f"• Name: **{refreshed['name']}**\n"
                f"• Tag: **{refreshed.get('tag') or '(none)'}**\n"
                f"• Description: **{refreshed.get('description') or '(none)'}**\n"
                f"• Recruiting: **{'Open' if refreshed.get('recruiting', True) else 'Closed'}**",
                ephemeral=True,
            )
        except Exception as error:
            logger.error("Failed to update team config: %s", error)
            await interaction.followup.send("❌ Failed to update team config.", ephemeral=True)

    @team.command(name="info", description="Show team overview")
    @app_commands.describe(query="Team name, tag (e.g. HXRT), member mention or nickname")
    async def team_info(self, interaction: discord.Interaction, query: Optional[str] = None):
        await interaction.response.defer(ephemeral=False)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
            return

        db = get_db()
        team = None

        if query and query.strip():
            lookup = query.strip()

            member = self._resolve_member_from_query(guild, lookup)
            if member:
                member_db_user = db.get_user_by_discord_id(member.id)
                if member_db_user:
                    team = db.get_user_team(guild.id, member_db_user["id"])

            if not team:
                team = db.get_team_by_name(guild.id, lookup)

            if not team:
                teams_by_tag = db.get_teams_by_tag(guild.id, lookup)
                if len(teams_by_tag) == 1:
                    team = teams_by_tag[0]
                elif len(teams_by_tag) > 1:
                    names = ", ".join(team_row["name"] for team_row in teams_by_tag[:5])
                    await interaction.followup.send(
                        f"⚠️ Found multiple teams with tag **{lookup.upper()}**: {names}. Use exact team name.",
                        ephemeral=True,
                    )
                    return

            if not team:
                await interaction.followup.send("❌ Team not found. Search by team name, tag, or member.", ephemeral=True)
                return
        else:
            actor_db_user = db.get_user_by_discord_id(interaction.user.id)
            if not actor_db_user:
                await interaction.followup.send("❌ You need to link a Riot account first.", ephemeral=True)
                return

            team = db.get_user_team(guild.id, actor_db_user["id"])
            if not team:
                await interaction.followup.send("❌ You are not in any team. Pass a team name to view another team.", ephemeral=True)
                return

        embed = await self._build_team_overview_embed(team, db, "👥 Team")
        await interaction.followup.send(embed=embed, ephemeral=False)
