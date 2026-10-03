"""
Unlucky or Bad Commands Module
/unlucky - Analyze if you're the problem or your team is
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Dict
import logging
from collections import defaultdict

from riot_api import RiotAPI, CHAMPION_ID_TO_NAME

logger = logging.getLogger('unlucky_commands')

class GameCountSelect(discord.ui.Select):
    def __init__(self, callback):
        self.callback_func = callback
        options = [
            discord.SelectOption(label="Last 10 games", value="10"),
            discord.SelectOption(label="Last 15 games", value="15"),
            discord.SelectOption(label="Last 20 games", value="20"),
        ]
        super().__init__(
            placeholder="Select number of games to analyze",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.callback_func(interaction, int(self.values[0]))

class GameCountView(discord.ui.View):
    def __init__(self, callback):
        super().__init__()
        self.add_item(GameCountSelect(callback))

class UnluckyCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, riot_api: RiotAPI):
        self.bot = bot
        self.riot_api = riot_api

    def create_verdict_bar(self, score: float) -> str:
        """Create a verdict bar like on unluckyorbad.lol (0-5 scale)"""
        # Thresholds: 0-1 "Just trash", 1-2 "Bad as mates", 2-3 "Normal", 3-4 "Bit of point", 4-5 "Team diff"

        bar_width = 40
        filled = int((score / 5) * bar_width)
        empty = bar_width - filled

        bar = "█" * filled + "░" * empty

        if score < 1:
            label = "Just trash"
            color = "🔴"
        elif score < 2:
            label = "Bad as your mates"
            color = "🟠"
        elif score < 3:
            label = "Normal"
            color = "⚪"
        elif score < 4:
            label = "Bit of a point"
            color = "🟢"
        else:
            label = "Team diff"
            color = "🔵"

        return f"{color} [{bar}] {score:.1f}/5\n{label}"

    def calculate_lane_stats(self, matches: List[Dict], player_puuid: str) -> tuple:
        """Calculate stats per lane and timeline from match data
        Returns: (lane_stats, gold_timeline, deaths_timeline, first_blood_count, surrender_count, dragons_total)
        Filters for Ranked Solo/Duo only
        """
        lane_stats = defaultdict(lambda: {
            'gold_diff': [],
            'deaths_diff': [],
            'kills': [],
            'deaths': [],
            'cs': [],
            'games': 0,
        })

        gold_timeline = {'10min': [], '20min': [], 'end': []}
        deaths_timeline = {'10min': [], '20min': [], 'end': []}
        first_blood_count = 0
        surrender_count = 0
        dragons_total = 0
        total_games = 0
        valid_games = 0

        logger.info(f"🔄 Processing {len(matches)} matches for PUUID {player_puuid}")

        for match_idx, match in enumerate(matches):
            info = match.get('info', {})

            # Filter for Ranked Solo/Duo only
            queue_id = info.get('queueId')
            logger.info(f"  Match {match_idx}: queueId={queue_id}")
            if queue_id not in [420, 440]:  # 420 = Ranked Solo/Duo, 440 = Ranked Flex
                logger.info(f"    ❌ Skipped (not ranked)")
                continue

            total_games += 1
            participants = info.get('participants', [])
            frames = match.get('timeline', {}).get('frames', [])

            # Find player in match
            player_data = None
            player_idx = None
            for idx, p in enumerate(participants):
                if p.get('puuid') == player_puuid:
                    player_data = p
                    player_idx = idx
                    break

            if not player_data:
                logger.info(f"    ❌ Player not found in match")
                continue

            valid_games += 1

            lane = player_data.get('lane', 'UNKNOWN')
            logger.info(f"    ✅ Found player in lane: {lane}")

            if lane == 'UNKNOWN':
                logger.info(f"    ❌ Unknown lane")
                continue

            # Get team average for comparison
            team_id = player_data.get('teamId')
            player_team_members = [p for p in participants if p.get('teamId') == team_id and p.get('puuid') != player_puuid]

            if not player_team_members:
                logger.info(f"    ❌ No teammates found")
                continue

            team_gold = sum(p.get('goldEarned', 0) for p in player_team_members)
            team_deaths = sum(p.get('deaths', 0) for p in player_team_members)
            team_count = len(player_team_members)

            avg_gold = team_gold / team_count
            avg_deaths = team_deaths / team_count

            gold_diff = player_data.get('goldEarned', 0) - avg_gold
            deaths_diff = player_data.get('deaths', 0) - avg_deaths

            logger.info(f"    💰 Gold diff: {gold_diff:.0f}, Deaths diff: {deaths_diff:.1f}")

            lane_stats[lane]['gold_diff'].append(gold_diff)
            lane_stats[lane]['deaths_diff'].append(deaths_diff)
            lane_stats[lane]['kills'].append(player_data.get('kills', 0))
            lane_stats[lane]['deaths'].append(player_data.get('deaths', 0))
            lane_stats[lane]['cs'].append(player_data.get('totalMinionsKilled', 0) + player_data.get('neutralMinionsKilled', 0))
            lane_stats[lane]['games'] += 1

            # Timeline analysis (gold at 10min, 20min, end)
            if frames and len(frames) > 1:
                logger.info(f"    📊 Timeline frames: {len(frames)}")
                for frame in frames:
                    frame_timeline = frame.get('participantFrames', {})
                    player_frame = frame_timeline.get(str(player_idx + 1), {})  # participantFrames use 1-indexed keys

                    if not player_frame:
                        continue

                    timestamp = frame.get('timestamp', 0)
                    minutes = timestamp // 60000 if timestamp else 0

                    if minutes == 10:
                        player_gold_10 = player_frame.get('totalGold', 0)
                        team_gold_10 = sum(frame_timeline.get(str(i + 1), {}).get('totalGold', 0)
                                          for i, p in enumerate(participants)
                                          if p.get('teamId') == team_id and i != player_idx)
                        if team_count > 0:
                            diff_10 = player_gold_10 - (team_gold_10 / team_count)
                            gold_timeline['10min'].append(diff_10)
                            logger.info(f"      10min gold: {diff_10:.0f}")
                    elif minutes == 20:
                        player_gold_20 = player_frame.get('totalGold', 0)
                        team_gold_20 = sum(frame_timeline.get(str(i + 1), {}).get('totalGold', 0)
                                          for i, p in enumerate(participants)
                                          if p.get('teamId') == team_id and i != player_idx)
                        if team_count > 0:
                            diff_20 = player_gold_20 - (team_gold_20 / team_count)
                            gold_timeline['20min'].append(diff_20)
                            logger.info(f"      20min gold: {diff_20:.0f}")

            # End game gold/deaths diff
            gold_timeline['end'].append(gold_diff)
            deaths_timeline['end'].append(deaths_diff)

            # First blood
            first_blood_killer = None
            for event in match.get('timeline', {}).get('events', []):
                if event.get('type') == 'CHAMPION_KILL':
                    first_blood_killer = event.get('killerId')
                    break

            if first_blood_killer == player_idx + 1:  # killerId is 1-indexed
                first_blood_count += 1

            # Surrender (games under 15 minutes)
            game_duration = info.get('gameDuration', 0) // 60  # in minutes
            if game_duration < 15:
                surrender_count += 1

            # Dragons
            for event in match.get('timeline', {}).get('events', []):
                if event.get('type') == 'ELITE_MONSTER_KILL' and event.get('monsterType') == 'DRAGON':
                    if event.get('killerTeamId') == team_id:
                        dragons_total += 1

        logger.info(f"📊 Results: {total_games} ranked games, {valid_games} valid, lanes={dict(lane_stats)}")

        # Calculate averages
        result = {}
        for lane, stats in lane_stats.items():
            if stats['games'] > 0:
                result[lane] = {
                    'avg_gold_diff': sum(stats['gold_diff']) / stats['games'],
                    'avg_deaths_diff': sum(stats['deaths_diff']) / stats['games'],
                    'avg_kills': sum(stats['kills']) / stats['games'],
                    'avg_deaths': sum(stats['deaths']) / stats['games'],
                    'avg_cs': sum(stats['cs']) / stats['games'],
                    'avg_kda': f"{sum(stats['kills'])/stats['games']:.1f}/{sum(stats['deaths'])/stats['games']:.1f}/{sum(stats['cs'])/stats['games']:.0f}",
                    'games': stats['games'],
                }

        # Timeline averages
        gold_timeline_avg = {k: sum(v)/len(v) if v else 0 for k, v in gold_timeline.items()}
        deaths_timeline_avg = {k: sum(v)/len(v) if v else 0 for k, v in deaths_timeline.items()}

        return result, gold_timeline_avg, deaths_timeline_avg, first_blood_count, surrender_count, dragons_total, valid_games

    def format_gold_bar(self, value: float, width: int = 20) -> str:
        """Format a bar for gold diff"""
        if value >= 0:
            filled = min(int((value / 5000) * width), width)
            return "🟦" * filled + "⬜" * (width - filled) + f" +{value:.0f}"
        else:
            filled = min(int((abs(value) / 5000) * width), width)
            return "🟥" * filled + "⬜" * (width - filled) + f" {value:.0f}"

    def calculate_overall_verdict(self, lane_stats: Dict) -> float:
        """Calculate overall verdict score (0-5)"""
        if not lane_stats:
            return 2.5

        # Average gold diff across all lanes (positive = you're doing well)
        avg_gold_diff = sum(s['avg_gold_diff'] for s in lane_stats.values()) / len(lane_stats)

        # Score: -5000+ = 0, 0 = 2.5, 5000+ = 5
        # Normalize to 0-5 scale
        score = 2.5 + (avg_gold_diff / 5000) * 2.5
        return max(0, min(5, score))

    async def analyze_unlucky(self, interaction: discord.Interaction, summoner_name: str, region: str, game_count: int):
        """Analyze player's recent games"""
        await interaction.response.defer()

        try:
            # Parse game name and tag
            if '#' in summoner_name:
                game_name, tag_line = summoner_name.split('#', 1)
            else:
                game_name = summoner_name
                tag_line = None

            # Get player account info
            account = await self.riot_api.get_account_by_riot_id(game_name, tag_line, region)
            if not account:
                await interaction.followup.send(f"❌ Player **{summoner_name}** not found")
                return

            puuid = account.get('puuid')

            # Get match history
            matches_ids = await self.riot_api.get_match_history(puuid, region, count=game_count)
            if not matches_ids:
                await interaction.followup.send(f"❌ No recent matches found for **{summoner_name}**")
                return

            # Get match details
            matches = []
            for match_id in matches_ids:
                match = await self.riot_api.get_match_details(match_id, region)
                if match:
                    matches.append(match)

            if not matches:
                await interaction.followup.send(f"❌ Could not load match details")
                return

            # Calculate stats
            lane_stats, gold_timeline, deaths_timeline, fb_count, surrender_count, dragons_total, total_games = self.calculate_lane_stats(matches, puuid)
            if not lane_stats:
                await interaction.followup.send(f"❌ Could not parse lane data from matches")
                return

            verdict_score = self.calculate_overall_verdict(lane_stats)

            # Create embeds
            embeds = []

            # Embed 1: Verdict + Gold Timeline
            embed1 = discord.Embed(
                title=f"🔍 Unlucky or Bad? — {summoner_name}",
                description=f"Analysis of last **{len(matches)}** games in **{region.upper()}**",
                color=0x0099ff
            )

            # Verdict bar
            verdict_bar = self.create_verdict_bar(verdict_score)
            embed1.add_field(name="📊 Your Verdict", value=verdict_bar, inline=False)

            # Gold Timeline (10min, 20min, end)
            gold_text = "```\n"
            gold_text += f"10 MIN:  {gold_timeline.get('10min', 0):+7.0f}g\n"
            gold_text += f"20 MIN:  {gold_timeline.get('20min', 0):+7.0f}g\n"
            gold_text += f"END:     {gold_timeline.get('end', 0):+7.0f}g\n"
            gold_text += "```"
            embed1.add_field(name="💰 GOLD vs MATCHUP", value=gold_text, inline=True)

            # Deaths Timeline
            deaths_text = "```\n"
            deaths_text += f"10 MIN:  {deaths_timeline.get('10min', 0):+5.1f}d\n"
            deaths_text += f"20 MIN:  {deaths_timeline.get('20min', 0):+5.1f}d\n"
            deaths_text += f"END:     {deaths_timeline.get('end', 0):+5.1f}d\n"
            deaths_text += "```"
            embed1.add_field(name="💀 DEATHS vs MATCHUP", value=deaths_text, inline=True)

            embeds.append(embed1)

            # Embed 2: Lane breakdown
            embed2 = discord.Embed(
                title="🗺️ Lane Breakdown",
                color=0x00ff00
            )

            # Gold per lane
            gold_breakdown = "```\n"
            for lane in ['TOP', 'JGL', 'MID', 'BOT', 'SUP']:
                if lane in lane_stats:
                    stats = lane_stats[lane]
                    gold_diff = stats['avg_gold_diff']
                    color = "🔵" if gold_diff >= 0 else "🔴"
                    gold_breakdown += f"{lane:3} {color} {gold_diff:+7.0f}g\n"
            gold_breakdown += "```"
            embed2.add_field(name="💰 Gold Diff per Lane", value=gold_breakdown, inline=True)

            # Deaths per lane
            deaths_breakdown = "```\n"
            for lane in ['TOP', 'JGL', 'MID', 'BOT', 'SUP']:
                if lane in lane_stats:
                    stats = lane_stats[lane]
                    deaths_diff = stats['avg_deaths_diff']
                    color = "🔴" if deaths_diff >= 0 else "🟢"
                    deaths_breakdown += f"{lane:3} {color} {deaths_diff:+5.1f}d\n"
            deaths_breakdown += "```"
            embed2.add_field(name="💀 Deaths Diff per Lane", value=deaths_breakdown, inline=True)

            # KDA per lane
            kda_breakdown = "```\n"
            for lane in ['TOP', 'JGL', 'MID', 'BOT', 'SUP']:
                if lane in lane_stats:
                    stats = lane_stats[lane]
                    kda_breakdown += f"{lane}: {stats['avg_kda']}\n"
            kda_breakdown += "```"
            embed2.add_field(name="⚔️ KDA/CS per Lane", value=kda_breakdown, inline=False)

            embeds.append(embed2)

            # Embed 3: Team stats
            embed3 = discord.Embed(
                title="👥 Team Statistics",
                color=0xff9900
            )

            fb_rate = (fb_count / len(matches) * 100) if matches else 0
            surrender_rate = (surrender_count / len(matches) * 100) if matches else 0
            avg_dragons = dragons_total / len(matches) if matches else 0

            embed3.add_field(
                name="🩸 First Blood",
                value=f"**{fb_rate:.0f}%**\nYour team gets first blood in {fb_rate:.0f}% of games",
                inline=True
            )

            embed3.add_field(
                name="🐉 Dragons per Game",
                value=f"**{avg_dragons:.1f}**\nYour team takes {avg_dragons:.1f} dragons per game",
                inline=True
            )

            embed3.add_field(
                name="⛔ Surrender Rate",
                value=f"**{surrender_rate:.0f}%**\nYour team surrenders in {surrender_rate:.0f}% of games",
                inline=True
            )

            embed3.set_footer(text=f"Analyzed {len(matches)} games • Data from Riot API")

            embeds.append(embed3)

            # Send all embeds
            await interaction.followup.send(embeds=embeds)

        except Exception as e:
            logger.error(f"Error in analyze_unlucky: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")

    @app_commands.command(name="unlucky", description="Analyze if it's you or your team that's the problem")
    @app_commands.describe(
        summoner="Summoner name",
        region="Region (na, euw, eune, kr, etc.)"
    )
    async def unlucky(self, interaction: discord.Interaction, summoner: str, region: str):
        """Start unlucky analysis with game count selector"""
        view = GameCountView(lambda inter, count: self.analyze_unlucky(inter, summoner, region, count))
        await interaction.response.send_message(
            f"**{summoner}** in **{region.upper()}** - Select how many games to analyze:",
            view=view,
            ephemeral=True
        )

async def setup(bot):
    riot_api = bot.riot_api
    await bot.add_cog(UnluckyCommands(bot, riot_api))
