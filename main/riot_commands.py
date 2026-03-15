"""
Riot Commands Module
/recent, /livegame, /rankhistory, /mastery_top, /champion_stats, /compare, /decay, /whois
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
import logging
import asyncio

from database import get_db
from riot_api import RiotAPI, CHAMPION_ID_TO_NAME, get_champion_icon_url, get_rank_icon_url
from emoji_dict import get_champion_emoji, get_rank_emoji, get_mastery_emoji, RANK_EMOJIS

logger = logging.getLogger('riot_commands')

QUEUE_NAMES = {
    420: "Ranked Solo/Duo",
    440: "Ranked Flex",
    450: "ARAM",
    400: "Normal Draft",
    430: "Normal Blind",
    490: "Quickplay",
    700: "Clash",
    1700: "Arena",
    0: "Custom",
}

TIER_ORDER = {
    'IRON': 0, 'BRONZE': 1, 'SILVER': 2, 'GOLD': 3,
    'PLATINUM': 4, 'EMERALD': 5, 'DIAMOND': 6,
    'MASTER': 7, 'GRANDMASTER': 8, 'CHALLENGER': 9,
}

RANK_ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4}


def format_rank(tier: str, rank: str, lp: int) -> str:
    if not tier or tier == 'UNRANKED':
        return 'Unranked'
    if tier in ('MASTER', 'GRANDMASTER', 'CHALLENGER'):
        return f"{tier.capitalize()} {lp} LP"
    return f"{tier.capitalize()} {rank} {lp} LP"


def format_kda(kills: int, deaths: int, assists: int) -> str:
    ratio = (kills + assists) / max(deaths, 1)
    return f"{kills}/{deaths}/{assists} ({ratio:.1f} KDA)"


def get_position_name(role: str, lane: str) -> str:
    mapping = {
        ('TOP', 'TOP'): 'Top',
        ('JUNGLE', 'JUNGLE'): 'Jungle',
        ('MIDDLE', 'MID'): 'Mid',
        ('BOTTOM', 'BOT'): 'Bot',
        ('UTILITY', 'BOT'): 'Support',
    }
    return mapping.get((role, lane), f"{lane}".capitalize() or role.capitalize())


async def resolve_user(interaction: discord.Interaction, user: Optional[discord.Member]) -> Optional[Dict]:
    """Resolve the target user from interaction or mention, returning db user dict."""
    db = get_db()
    target = user or interaction.user
    db_user = db.get_user_by_discord_id(target.id)
    if not db_user:
        name = target.display_name
        await interaction.followup.send(
            f"❌ **{name}** has no linked Riot account. Use `/link` to connect.",
            ephemeral=True
        )
        return None
    return db_user


async def get_primary_account_with_error(interaction: discord.Interaction, user: Optional[discord.Member]) -> Optional[Dict]:
    """Get primary account for a user or send error if missing."""
    db = get_db()
    db_user = await resolve_user(interaction, user)
    if not db_user:
        return None
    account = db.get_primary_account(db_user['id'])
    if not account:
        name = (user or interaction.user).display_name
        await interaction.followup.send(
            f"❌ **{name}** has no verified accounts.",
            ephemeral=True
        )
        return None
    if not account.get('verified'):
        await interaction.followup.send(
            "❌ Account not verified. Use `/verify` to verify it first.",
            ephemeral=True
        )
        return None
    return account


# ==================== REGION CHOICES ====================

REGION_CHOICES = [
    app_commands.Choice(name="EUW", value="euw"),
    app_commands.Choice(name="EUNE", value="eune"),
    app_commands.Choice(name="NA", value="na"),
    app_commands.Choice(name="KR", value="kr"),
    app_commands.Choice(name="BR", value="br"),
    app_commands.Choice(name="LAN", value="lan"),
    app_commands.Choice(name="LAS", value="las"),
    app_commands.Choice(name="JP", value="jp"),
    app_commands.Choice(name="OCE", value="oce"),
    app_commands.Choice(name="TR", value="tr"),
    app_commands.Choice(name="RU", value="ru"),
]


class RiotCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
        self.bot = bot
        self.riot_api = riot_api
        self.guild_id = guild_id

    # ==================== /recent ====================

    @app_commands.command(name="recent", description="Show your recent matches with KDA, champion, result")
    @app_commands.describe(user="User to check (default: yourself)", count="Number of games (1-15, default 5)")
    async def recent(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
        count: Optional[int] = 5,
    ):
        await interaction.response.defer()
        count = max(1, min(count, 15))
        account = await get_primary_account_with_error(interaction, user)
        if not account:
            return

        target = user or interaction.user
        match_ids = await self.riot_api.get_match_history(account['puuid'], account['region'], count=count)
        if not match_ids:
            await interaction.followup.send("❌ No recent matches found.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🎮 Recent Matches — {account['riot_id_game_name']}#{account['riot_id_tagline']}",
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        lines = []
        for match_id in match_ids:
            try:
                match = await self.riot_api.get_match_details(match_id, account['region'])
                if not match:
                    continue

                participants = match['info'].get('participants', [])
                p = next((x for x in participants if x.get('puuid') == account['puuid']), None)
                if not p:
                    continue

                champ_name = p.get('championName', '?')
                champ_emoji = get_champion_emoji(champ_name)
                kills = p.get('kills', 0)
                deaths = p.get('deaths', 0)
                assists = p.get('assists', 0)
                win = p.get('win', False)
                result = '✅' if win else '❌'
                queue_id = match['info'].get('queueId', 0)
                queue_name = QUEUE_NAMES.get(queue_id, 'Unknown')
                duration_s = match['info'].get('gameDuration', 0)
                if duration_s > 10000:
                    duration_s //= 1000
                mins = duration_s // 60
                secs = duration_s % 60
                cs = p.get('totalMinionsKilled', 0) + p.get('neutralMinionsKilled', 0)
                cs_min = cs / max(mins, 1)
                vision = p.get('visionScore', 0)

                lines.append(
                    f"{result} {champ_emoji} **{champ_name}** | {queue_name} | "
                    f"`{kills}/{deaths}/{assists}` | CS {cs} ({cs_min:.1f}/m) | "
                    f"Vision {vision} | {mins}m{secs:02d}s"
                )
            except Exception as e:
                logger.warning("Error parsing match %s: %s", match_id, e)
                continue

        if not lines:
            await interaction.followup.send("❌ Could not parse any recent matches.", ephemeral=True)
            return

        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Showing {len(lines)} games • {account['region'].upper()}")
        await interaction.followup.send(embed=embed)

    # ==================== /livegame ====================

    @app_commands.command(name="livegame", description="Check if a player is currently in a League game")
    @app_commands.describe(user="User to check (default: yourself)")
    async def livegame(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
    ):
        await interaction.response.defer()
        account = await get_primary_account_with_error(interaction, user)
        if not account:
            return

        target = user or interaction.user
        game = await self.riot_api.get_active_game(account['puuid'], account['region'])

        if not game:
            embed = discord.Embed(
                title=f"🔵 Not in game",
                description=f"**{account['riot_id_game_name']}#{account['riot_id_tagline']}** is not currently in a game.",
                color=discord.Color.greyple(),
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            await interaction.followup.send(embed=embed)
            return

        queue_id = game.get('gameQueueConfigId', 0)
        queue_name = QUEUE_NAMES.get(queue_id, f"Queue {queue_id}")
        started_at = game.get('gameStartTime', 0)
        if started_at:
            elapsed = int((datetime.now(timezone.utc).timestamp() * 1000 - started_at) / 1000)
            mins, secs = elapsed // 60, elapsed % 60
            duration_str = f"{mins}m {secs:02d}s"
        else:
            duration_str = "Unknown"

        embed = discord.Embed(
            title=f"🔴 Live Game — {account['riot_id_game_name']}#{account['riot_id_tagline']}",
            description=f"**Mode:** {queue_name} | **Time:** {duration_str}",
            color=discord.Color.red(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        participants = game.get('participants', [])
        team_100 = [p for p in participants if p.get('teamId') == 100]
        team_200 = [p for p in participants if p.get('teamId') == 200]

        def format_participant(p: dict) -> str:
            champ_id = p.get('championId', 0)
            champ_name = CHAMPION_ID_TO_NAME.get(champ_id, f"Champ#{champ_id}")
            emoji = get_champion_emoji(champ_name)
            name_tag = p.get('riotId', p.get('summonerName', 'Unknown'))
            return f"{emoji} {champ_name} — {name_tag}"

        if team_100:
            embed.add_field(
                name="🔵 Blue Team",
                value="\n".join(format_participant(p) for p in team_100),
                inline=True,
            )
        if team_200:
            embed.add_field(
                name="🔴 Red Team",
                value="\n".join(format_participant(p) for p in team_200),
                inline=True,
            )

        embed.set_footer(text=f"Region: {account['region'].upper()}")
        await interaction.followup.send(embed=embed)

    # ==================== /rankhistory ====================

    @app_commands.command(name="rankhistory", description="Show rank history stored in the database")
    @app_commands.describe(user="User to check (default: yourself)")
    async def rankhistory(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
    ):
        await interaction.response.defer()
        db = get_db()
        db_user = await resolve_user(interaction, user)
        if not db_user:
            return

        target = user or interaction.user
        ranks = db.get_user_ranks(db_user['id'])

        if not ranks:
            await interaction.followup.send("❌ No rank data found. Run `/rankupdate` first.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📊 Rank History — {target.display_name}",
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        # Group by season
        seasons: Dict[str, list] = {}
        for r in ranks:
            season = r.get('season', '?')
            seasons.setdefault(season, []).append(r)

        for season in sorted(seasons.keys(), reverse=True):
            lines = []
            for r in sorted(seasons[season], key=lambda x: x.get('queue', '')):
                tier = r.get('tier', 'UNRANKED')
                rank = r.get('rank', '')
                lp = r.get('league_points', 0)
                wins = r.get('wins', 0)
                losses = r.get('losses', 0)
                games = wins + losses
                wr = round(wins / games * 100) if games else 0
                queue = r.get('queue', 'Unknown')
                rank_emoji = get_rank_emoji(tier)
                rank_str = format_rank(tier, rank, lp)
                lines.append(f"{rank_emoji} **{queue}** → {rank_str} | {wins}W {losses}L ({wr}% WR)")
            embed.add_field(name=f"Season {season}", value="\n".join(lines), inline=False)

        await interaction.followup.send(embed=embed)

    # ==================== /mastery_top ====================

    @app_commands.command(name="mastery_top", description="Show top champion masteries for a player")
    @app_commands.describe(user="User to check (default: yourself)", top="Number of champions (1-15, default 10)")
    async def mastery_top(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
        top: Optional[int] = 10,
    ):
        await interaction.response.defer()
        top = max(1, min(top, 15))
        account = await get_primary_account_with_error(interaction, user)
        if not account:
            return

        target = user or interaction.user
        mastery_data = await self.riot_api.get_champion_mastery(account['puuid'], account['region'], count=top)

        if not mastery_data:
            await interaction.followup.send("❌ No mastery data found.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"👑 Top Champion Masteries — {account['riot_id_game_name']}#{account['riot_id_tagline']}",
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        lines = []
        for i, champ in enumerate(mastery_data[:top], 1):
            champ_id = champ.get('championId', 0)
            champ_name = CHAMPION_ID_TO_NAME.get(champ_id, f"ID:{champ_id}")
            points = champ.get('championPoints', 0)
            level = champ.get('championLevel', 0)
            mastery_emoji = get_mastery_emoji(level)
            champ_emoji = get_champion_emoji(champ_name)
            chest = "🎁" if champ.get('chestGranted') else ""
            lines.append(f"`{i:2d}.` {mastery_emoji} {champ_emoji} **{champ_name}** — {points:,} pts (Lv{level}) {chest}")

        embed.description = "\n".join(lines)
        total_points = sum(c.get('championPoints', 0) for c in mastery_data)
        embed.set_footer(text=f"Total mastery shown: {total_points:,} pts • {account['region'].upper()}")
        await interaction.followup.send(embed=embed)

    # ==================== /champion_stats ====================

    @app_commands.command(name="champion_stats", description="Show detailed stats for a specific champion")
    @app_commands.describe(champion="Champion name", user="User to check (default: yourself)")
    async def champion_stats(
        self,
        interaction: discord.Interaction,
        champion: str,
        user: Optional[discord.Member] = None,
    ):
        await interaction.response.defer()

        # Fuzzy match champion name
        champion_lower = champion.strip().lower().replace(' ', '').replace("'", '')
        champ_id = None
        champ_name = None
        for cid, cname in CHAMPION_ID_TO_NAME.items():
            if cname.lower().replace("'", '') == champion_lower or cname.lower() == champion.lower():
                champ_id = cid
                champ_name = cname
                break
        if not champ_id:
            # Partial match fallback
            for cid, cname in CHAMPION_ID_TO_NAME.items():
                if champion_lower in cname.lower().replace("'", ''):
                    champ_id = cid
                    champ_name = cname
                    break

        if not champ_id:
            await interaction.followup.send(f"❌ Champion `{champion}` not found.", ephemeral=True)
            return

        db = get_db()
        db_user = await resolve_user(interaction, user)
        if not db_user:
            return

        target = user or interaction.user
        account = await get_primary_account_with_error(interaction, user)
        if not account:
            return

        # Fetch live mastery for this specific champ
        mastery_data = await self.riot_api.get_champion_mastery(account['puuid'], account['region'], count=200)
        champ_mastery = None
        if mastery_data:
            champ_mastery = next((c for c in mastery_data if c.get('championId') == champ_id), None)

        embed = discord.Embed(
            title=f"{get_champion_emoji(champ_name)} {champ_name} — {target.display_name}",
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=get_champion_icon_url(champ_id))

        if champ_mastery:
            points = champ_mastery.get('championPoints', 0)
            level = champ_mastery.get('championLevel', 0)
            tokens = champ_mastery.get('tokensEarned', 0)
            chest = "✅ Chest earned" if champ_mastery.get('chestGranted') else "❌ Chest not earned"
            last_played_ts = champ_mastery.get('lastPlayTime', 0)
            last_played = "Unknown"
            if last_played_ts:
                last_played = datetime.fromtimestamp(last_played_ts / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            embed.add_field(name="Mastery", value=(
                f"Level {level} {get_mastery_emoji(level)}\n"
                f"**{points:,}** points\n"
                f"Tokens: {tokens}\n"
                f"{chest}\n"
                f"Last played: {last_played}"
            ), inline=True)
        else:
            embed.add_field(name="Mastery", value="No data for this champion.", inline=True)

        # DB champion stats (from match history cache)
        db_stats = db.get_user_champion_stats(db_user['id'], champ_id)
        if db_stats and db_stats[0]:
            s = db_stats[0]
            score = s.get('score', 0)
            embed.add_field(name="Database Stats", value=f"Score: **{score:,}**", inline=True)

        embed.set_footer(text=f"{account['region'].upper()} • {account['riot_id_game_name']}#{account['riot_id_tagline']}")
        await interaction.followup.send(embed=embed)

    # ==================== /compare ====================

    @app_commands.command(name="compare", description="Compare two players' rank and mastery")
    @app_commands.describe(user1="First player", user2="Second player")
    async def compare(
        self,
        interaction: discord.Interaction,
        user1: discord.Member,
        user2: discord.Member,
    ):
        await interaction.response.defer()
        db = get_db()

        async def get_data(member: discord.Member):
            db_user = db.get_user_by_discord_id(member.id)
            if not db_user:
                return None, None, None
            account = db.get_primary_account(db_user['id'])
            if not account or not account.get('verified'):
                return db_user, None, None
            ranks = db.get_user_ranks(db_user['id'])
            return db_user, account, ranks

        db1, acc1, ranks1 = await get_data(user1)
        db2, acc2, ranks2 = await get_data(user2)

        embed = discord.Embed(
            title=f"⚔️ Compare — {user1.display_name} vs {user2.display_name}",
            color=discord.Color.blurple(),
        )

        def format_user_info(member: discord.Member, db_user, acc, ranks) -> str:
            if not db_user:
                return "❌ Not linked"
            if not acc:
                return "❌ No verified account"
            riot_id = f"{acc['riot_id_game_name']}#{acc['riot_id_tagline']}"
            region = acc['region'].upper()
            solo = None
            if ranks:
                for r in ranks:
                    if 'SOLO' in r.get('queue', ''):
                        solo = r
                        break
            if solo:
                rank_str = format_rank(solo.get('tier', 'UNRANKED'), solo.get('rank', ''), solo.get('league_points', 0))
                wins = solo.get('wins', 0)
                losses = solo.get('losses', 0)
                games = wins + losses
                wr = round(wins / games * 100) if games else 0
                rank_emoji = get_rank_emoji(solo.get('tier', 'UNRANKED'))
                return f"**{riot_id}** ({region})\n{rank_emoji} {rank_str}\n{wins}W {losses}L ({wr}% WR)"
            return f"**{riot_id}** ({region})\n🎮 No solo queue data"

        embed.add_field(name=user1.display_name, value=format_user_info(user1, db1, acc1, ranks1), inline=True)
        embed.add_field(name="vs", value="—", inline=True)
        embed.add_field(name=user2.display_name, value=format_user_info(user2, db2, acc2, ranks2), inline=True)

        # Rank comparison winner
        def tier_score(ranks) -> int:
            if not ranks:
                return -1
            best = -1
            for r in ranks:
                if 'SOLO' in r.get('queue', ''):
                    tier = r.get('tier', 'UNRANKED')
                    rank = r.get('rank', 'IV')
                    lp = r.get('league_points', 0)
                    score = TIER_ORDER.get(tier, -1) * 10000 + (5 - RANK_ROMAN.get(rank, 5)) * 100 + lp
                    best = max(best, score)
            return best

        s1, s2 = tier_score(ranks1), tier_score(ranks2)
        if s1 > s2:
            verdict = f"🏆 **{user1.display_name}** has higher rank"
        elif s2 > s1:
            verdict = f"🏆 **{user2.display_name}** has higher rank"
        else:
            verdict = "🤝 Same rank!"
        embed.add_field(name="Verdict", value=verdict, inline=False)

        # Top mastery comparison if both have accounts
        if acc1 and acc2:
            async def top_mastery(acc) -> Optional[list]:
                data = await self.riot_api.get_champion_mastery(acc['puuid'], acc['region'], count=3)
                return data

            m1, m2 = await asyncio.gather(top_mastery(acc1), top_mastery(acc2))

            def fmt_mastery(data) -> str:
                if not data:
                    return "No data"
                lines = []
                for c in data[:3]:
                    cname = CHAMPION_ID_TO_NAME.get(c.get('championId', 0), '?')
                    pts = c.get('championPoints', 0)
                    lvl = c.get('championLevel', 0)
                    lines.append(f"{get_champion_emoji(cname)} {cname} M{lvl} ({pts:,})")
                return "\n".join(lines)

            embed.add_field(name=f"Top 3 Mastery — {user1.display_name}", value=fmt_mastery(m1), inline=True)
            embed.add_field(name=f"Top 3 Mastery — {user2.display_name}", value=fmt_mastery(m2), inline=True)

        await interaction.followup.send(embed=embed)

    # ==================== /decay ====================

    @app_commands.command(name="decay", description="Check LP decay status for Diamond+ players")
    @app_commands.describe(user="User to check (default: yourself)")
    async def decay(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
    ):
        await interaction.response.defer()
        account = await get_primary_account_with_error(interaction, user)
        if not account:
            return

        target = user or interaction.user
        result = await self.riot_api.check_decay_status(account['puuid'], account['region'])

        tier = result.get('tier', 'UNRANKED')
        at_risk = result.get('at_risk', False)
        message = result.get('message', '?')
        lp = result.get('lp', 0)
        days_remaining = result.get('days_remaining')

        color = discord.Color.red() if at_risk else discord.Color.green()
        embed = discord.Embed(
            title=f"⏳ Decay Status — {account['riot_id_game_name']}#{account['riot_id_tagline']}",
            description=message,
            color=color,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        rank_emoji = get_rank_emoji(tier.split()[0] if tier else 'UNRANKED')
        embed.add_field(name="Current Rank", value=f"{rank_emoji} {tier} — {lp} LP", inline=True)
        if days_remaining is not None:
            embed.add_field(name="Days until decay triggers", value=f"**{days_remaining}**", inline=True)

        embed.set_footer(text=f"Region: {account['region'].upper()}")
        await interaction.followup.send(embed=embed)

    # ==================== /whois ====================

    @app_commands.command(name="whois", description="Look up which Discord user has a given Riot account linked")
    @app_commands.describe(riot_id="Riot ID to search (Name#TAG)")
    async def whois(
        self,
        interaction: discord.Interaction,
        riot_id: str,
    ):
        await interaction.response.defer(ephemeral=True)
        if '#' not in riot_id:
            await interaction.followup.send("❌ Use format `Name#TAG`", ephemeral=True)
            return

        game_name, tag_line = riot_id.split('#', 1)
        db = get_db()
        conn = db.get_connection()
        try:
            from psycopg2.extras import RealDictCursor
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT u.snowflake, la.region, la.riot_id_game_name, la.riot_id_tagline, la.verified
                    FROM league_accounts la
                    JOIN users u ON la.user_id = u.id
                    WHERE LOWER(la.riot_id_game_name) = LOWER(%s) AND LOWER(la.riot_id_tagline) = LOWER(%s)
                """, (game_name, tag_line))
                results = cur.fetchall()
        finally:
            db.return_connection(conn)

        if not results:
            await interaction.followup.send(f"❌ No linked account found for `{riot_id}`.", ephemeral=True)
            return

        guild = interaction.guild
        lines = []
        for r in results:
            member = guild.get_member(r['snowflake']) if guild else None
            mention = member.mention if member else f"<@{r['snowflake']}>"
            verified = "✅" if r['verified'] else "⚠️"
            lines.append(f"{verified} {mention} — {r['riot_id_game_name']}#{r['riot_id_tagline']} ({r['region'].upper()})")

        embed = discord.Embed(
            title=f"🔍 Who is {riot_id}?",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==================== /account_status ====================

    @app_commands.command(name="account_status", description="Full overview of a player's linked accounts and ranks")
    @app_commands.describe(user="User to check (default: yourself)")
    async def account_status(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
    ):
        await interaction.response.defer()
        db = get_db()
        db_user = await resolve_user(interaction, user)
        if not db_user:
            return

        target = user or interaction.user
        accounts = db.get_user_accounts(db_user['id'])
        if not accounts:
            await interaction.followup.send("❌ No linked accounts found.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📋 Account Status — {target.display_name}",
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        ranks = db.get_user_ranks(db_user['id'])
        rank_map = {}
        for r in ranks:
            uid = r.get('user_id')
            if 'SOLO' in r.get('queue', ''):
                rank_map[uid] = r

        for acc in accounts:
            verified = "✅" if acc.get('verified') else "⚠️ Unverified"
            primary = "⭐ Primary" if acc.get('primary_account') else ""
            riot_id = f"{acc['riot_id_game_name']}#{acc['riot_id_tagline']}"
            region = acc['region'].upper()
            level = acc.get('summoner_level', '?')

            rank_str = "No rank data"
            r = rank_map.get(db_user['id'])
            if r:
                rank_str = format_rank(r.get('tier', 'UNRANKED'), r.get('rank', ''), r.get('league_points', 0))
                wins = r.get('wins', 0)
                losses = r.get('losses', 0)
                games = wins + losses
                wr = round(wins / games * 100) if games else 0
                rank_str += f"\n{wins}W {losses}L ({wr}% WR)"

            embed.add_field(
                name=f"{verified} {primary} {riot_id}",
                value=f"Region: **{region}** | Level: **{level}**\n{rank_str}",
                inline=False,
            )

        embed.set_footer(text="Use /rankupdate to refresh rank data")
        await interaction.followup.send(embed=embed)

    # ==================== /riot_health ====================

    @app_commands.command(name="riot_health", description="Check Riot API health and recent errors (Admin only)")
    async def riot_health(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not any(r.permissions.administrator for r in getattr(interaction.user, 'roles', [])):
            perms = interaction.user.guild_permissions if interaction.guild else None
            if not perms or not perms.administrator:
                await interaction.followup.send("❌ Admin only.", ephemeral=True)
                return

        # Ping Riot API with a lightweight platform status check
        import aiohttp
        status_lines = []
        platforms = [('EUW', 'euw1'), ('NA', 'na1'), ('KR', 'kr')]
        for label, host in platforms:
            url = f"https://{host}.api.riotgames.com/lol/status/v4/platform-data"
            try:
                t0 = datetime.now(timezone.utc)
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.riot_api.headers, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                        t1 = datetime.now(timezone.utc)
                        ms = int((t1 - t0).total_seconds() * 1000)
                        if resp.status == 200:
                            status_lines.append(f"✅ {label}: **{ms}ms**")
                        else:
                            status_lines.append(f"⚠️ {label}: HTTP {resp.status}")
            except Exception as e:
                status_lines.append(f"❌ {label}: {e}")

        api_key_set = "✅ Set" if self.riot_api.api_key else "❌ Not set"
        embed = discord.Embed(title="🏥 Riot API Health", color=discord.Color.green())
        embed.add_field(name="API Key", value=api_key_set, inline=True)
        embed.add_field(name="Platform Latency", value="\n".join(status_lines), inline=False)
        embed.set_footer(text=f"Checked at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
    """Register RiotCommands cog on the bot."""
    cog = RiotCommands(bot, riot_api, guild_id)
    await bot.add_cog(cog)
    logger.info("✅ RiotCommands cog loaded")
