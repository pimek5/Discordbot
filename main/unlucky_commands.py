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

    def calculate_lane_stats(self, matches: List[Dict], player_puuid: str) -> Dict:
        """Calculate stats per lane from match data"""
        lane_stats = defaultdict(lambda: {
            'gold_diff': [],
            'deaths_diff': [],
            'kills': [],
            'deaths': [],
            'cs': [],
            'games': 0,
        })

        for match in matches:
            info = match.get('info', {})
            participants = info.get('participants', [])

            # Find player in match
            player_data = None
            for p in participants:
                if p.get('puuid') == player_puuid:
                    player_data = p
                    break

            if not player_data:
                continue

            lane = player_data.get('lane', 'UNKNOWN')
            if lane == 'UNKNOWN':
                continue

            # Get team average for comparison
            team_id = player_data.get('teamId')
            team_gold = 0
            team_deaths = 0
            team_count = 0

            player_team_members = [p for p in participants if p.get('teamId') == team_id and p.get('puuid') != player_puuid]
            for teammate in player_team_members:
                team_gold += teammate.get('goldEarned', 0)
                team_deaths += teammate.get('deaths', 0)
                team_count += 1

            if team_count > 0:
                avg_gold = team_gold / team_count
                avg_deaths = team_deaths / team_count

                gold_diff = player_data.get('goldEarned', 0) - avg_gold
                deaths_diff = player_data.get('deaths', 0) - avg_deaths

                lane_stats[lane]['gold_diff'].append(gold_diff)
                lane_stats[lane]['deaths_diff'].append(deaths_diff)
                lane_stats[lane]['kills'].append(player_data.get('kills', 0))
                lane_stats[lane]['deaths'].append(player_data.get('deaths', 0))
                lane_stats[lane]['cs'].append(player_data.get('totalMinionsKilled', 0) + player_data.get('neutralMinionsKilled', 0))
                lane_stats[lane]['games'] += 1

        # Calculate averages
        result = {}
        for lane, stats in lane_stats.items():
            if stats['games'] > 0:
                result[lane] = {
                    'avg_gold_diff': sum(stats['gold_diff']) / stats['games'],
                    'avg_deaths_diff': sum(stats['deaths_diff']) / stats['games'],
                    'avg_kda': f"{sum(stats['kills'])/stats['games']:.1f}/{sum(stats['deaths'])/stats['games']:.1f}/{sum(stats['cs'])/stats['games']:.0f}",
                    'games': stats['games'],
                }

        return result

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
            account = await self.riot_api.get_account(game_name, tag_line, region)
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
            lane_stats = self.calculate_lane_stats(matches, puuid)
            if not lane_stats:
                await interaction.followup.send(f"❌ Could not parse lane data from matches")
                return

            verdict_score = self.calculate_overall_verdict(lane_stats)

            # Create embed
            embed = discord.Embed(
                title=f"🔍 Unlucky or Bad? — {summoner_name}",
                description=f"Analysis of last **{len(matches)}** games in **{region.upper()}**",
                color=0x0099ff
            )

            # Verdict bar
            verdict_bar = self.create_verdict_bar(verdict_score)
            embed.add_field(name="📊 Your Verdict", value=verdict_bar, inline=False)

            # Lane breakdown - Gold
            gold_breakdown = "```\n"
            for lane in ['TOP', 'JGL', 'MID', 'BOT', 'SUP']:
                if lane in lane_stats:
                    stats = lane_stats[lane]
                    gold_diff = stats['avg_gold_diff']
                    color = "🔵" if gold_diff >= 0 else "🔴"
                    gold_breakdown += f"{lane:3} {color} {gold_diff:+7.0f}g\n"
            gold_breakdown += "```"
            embed.add_field(name="💰 Gold Diff per Lane", value=gold_breakdown, inline=True)

            # Lane breakdown - Deaths
            deaths_breakdown = "```\n"
            for lane in ['TOP', 'JGL', 'MID', 'BOT', 'SUP']:
                if lane in lane_stats:
                    stats = lane_stats[lane]
                    deaths_diff = stats['avg_deaths_diff']
                    color = "🔴" if deaths_diff >= 0 else "🟢"
                    deaths_breakdown += f"{lane:3} {color} {deaths_diff:+5.1f}d\n"
            deaths_breakdown += "```"
            embed.add_field(name="💀 Deaths Diff per Lane", value=deaths_breakdown, inline=True)

            # Lane KDA/CS
            kda_breakdown = "```\n"
            for lane in ['TOP', 'JGL', 'MID', 'BOT', 'SUP']:
                if lane in lane_stats:
                    stats = lane_stats[lane]
                    kda_breakdown += f"{lane}: {stats['avg_kda']}\n"
            kda_breakdown += "```"
            embed.add_field(name="⚔️ KDA/CS per Lane", value=kda_breakdown, inline=False)

            embed.set_footer(text=f"Analyzed {len(matches)} games • Data from Riot API")

            await interaction.followup.send(embed=embed)

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
    riot_api = RiotAPI()
    await bot.add_cog(UnluckyCommands(bot, riot_api))
