"""
Leaderboard Commands Module  
/top champion, /top user
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional
import logging
import asyncio
from datetime import datetime
import math
import time

from database import get_db
from riot_api import RiotAPI, CHAMPION_ID_TO_NAME

logger = logging.getLogger('leaderboard_commands')
DEFAULT_RANK_LEADERBOARD_CHANNEL_ID = 1483141413666296038
RANK_PAGE_SIZE = 10
DAILY_RESET_HOURS = 24
SNAPSHOT_RETENTION_HOURS = 24 * 7
RANK_CACHE_TTL_SECONDS = 300
RANK_MANUAL_REFRESH_COOLDOWN_SECONDS = 45

async def loading_animation(interaction, messages=None):
    """Helper function for loading animation"""
    if messages is None:
        messages = ["⏳ Loading data...", "📊 Processing...", "🎮 Preparing results..."]
    
    for i, msg in enumerate(messages):
        if i > 0:
            await asyncio.sleep(2)
        try:
            await interaction.edit_original_response(content=msg)
        except:
            break

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


class RankTopView(discord.ui.View):
    def __init__(self, cog: "LeaderboardCommands", guild: discord.Guild, ranked_members: list, region: Optional[str], requested_by: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.ranked_members = ranked_members
        self.all_ranked_members = ranked_members
        self.region = region
        self.requested_by = requested_by
        self.current_page = 1

    def _max_pages(self) -> int:
        return max(1, math.ceil(len(self.ranked_members) / RANK_PAGE_SIZE))

    def _sync_buttons(self):
        total_pages = self._max_pages()
        self.prev_button.disabled = self.current_page <= 1
        self.next_button.disabled = self.current_page >= total_pages

    async def _refresh_data(self):
        self.ranked_members = await self.cog._collect_ranked_members(self.guild, region=self.region)
        max_pages = self._max_pages()
        if self.current_page > max_pages:
            self.current_page = max_pages

    async def _render(self, interaction: discord.Interaction):
        self._sync_buttons()
        embed = self.cog._build_ranked_embed(
            guild=self.guild,
            ranked_members=self.ranked_members,
            region=self.region,
            requested_by=self.requested_by,
            page=self.current_page,
            page_size=RANK_PAGE_SIZE,
            only_played_today=False,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
        await self._render(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self._max_pages():
            self.current_page += 1
        await self._render(interaction)

    @discord.ui.button(label="🔃", style=discord.ButtonStyle.primary)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            await self._refresh_data()
            self._sync_buttons()
            embed = self.cog._build_ranked_embed(
                guild=self.guild,
                ranked_members=self.ranked_members,
                region=self.region,
                requested_by=self.requested_by,
                page=self.current_page,
                page_size=RANK_PAGE_SIZE,
                only_played_today=False,
            )
            if interaction.message:
                await interaction.message.edit(embed=embed, view=self)
            self.cog._save_ranked_snapshots(self.guild.id, self.ranked_members)
            self.cog._mark_rank_refresh(self.guild.id)
        except Exception as e:
            logger.error("❌ Refresh button failed for guild %s: %s", self.guild.id, e)
            await interaction.followup.send("❌ Refresh failed. Try again in a moment.", ephemeral=True)

    @discord.ui.button(label="Setup Account", style=discord.ButtonStyle.success, emoji="🔗")
    async def setup_account_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Start account setup with `/link` and then verify it with `/verifyacc`.",
            ephemeral=True,
        )


class RankPersistentView(discord.ui.View):
    def __init__(self, cog: "LeaderboardCommands"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.select(
        custom_id="rank_region_picker",
        placeholder="🌍 Pick region filter",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="All regions", value="all", emoji="🌐"),
            discord.SelectOption(label="EUW", value="euw", emoji="🇪🇺"),
            discord.SelectOption(label="EUNE", value="eune", emoji="🇪🇺"),
            discord.SelectOption(label="NA", value="na", emoji="🇺🇸"),
            discord.SelectOption(label="KR", value="kr", emoji="🇰🇷"),
            discord.SelectOption(label="CN", value="cn", emoji="🇨🇳"),
            discord.SelectOption(label="JP", value="jp", emoji="🇯🇵"),
            discord.SelectOption(label="BR", value="br", emoji="🇧🇷"),
            discord.SelectOption(label="LAN", value="lan", emoji="🇲🇽"),
            discord.SelectOption(label="LAS", value="las", emoji="🇦🇷"),
            discord.SelectOption(label="OCE", value="oce", emoji="🇦🇺"),
            discord.SelectOption(label="RU", value="ru", emoji="🇷🇺"),
            discord.SelectOption(label="TR", value="tr", emoji="🇹🇷"),
            discord.SelectOption(label="SG", value="sg", emoji="🇸🇬"),
            discord.SelectOption(label="PH", value="ph", emoji="🇵🇭"),
            discord.SelectOption(label="TH", value="th", emoji="🇹🇭"),
            discord.SelectOption(label="TW", value="tw", emoji="🇹🇼"),
            discord.SelectOption(label="VN", value="vn", emoji="🇻🇳"),
        ],
    )
    async def region_picker(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not interaction.guild:
            await interaction.response.send_message("❌ This selector only works in a server.", ephemeral=True)
            return

        selected = (select.values or ["all"])[0]
        selected_region = None if selected == "all" else selected
        await interaction.response.defer()

        try:
            self.cog._set_persistent_rank_region(interaction.guild.id, selected_region)
            self.cog._persistent_rank_pages[interaction.guild.id] = 1
            await self.cog._update_or_create_rank_embed(interaction.guild, force_refresh=False)
        except Exception as e:
            logger.error("❌ Persistent region picker failed for guild %s: %s", interaction.guild.id, e)
            await interaction.followup.send("❌ Could not change region filter. Try again.", ephemeral=True)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="rank_prev_button")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            await interaction.response.send_message("❌ This button only works in a server.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            await self.cog._change_persistent_rank_page(interaction.guild, -1, message=interaction.message)
        except Exception as e:
            logger.error("❌ Persistent prev page failed for guild %s: %s", interaction.guild.id, e)
            await interaction.followup.send("❌ Couldn't change page. Try again.", ephemeral=True)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, custom_id="rank_next_button")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            await interaction.response.send_message("❌ This button only works in a server.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            await self.cog._change_persistent_rank_page(interaction.guild, 1, message=interaction.message)
        except Exception as e:
            logger.error("❌ Persistent next page failed for guild %s: %s", interaction.guild.id, e)
            await interaction.followup.send("❌ Couldn't change page. Try again.", ephemeral=True)

    @discord.ui.button(label="🔃", style=discord.ButtonStyle.primary, custom_id="rank_refresh_button")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            await interaction.response.send_message("❌ This button only works in a server.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            result = await self.cog._update_or_create_rank_embed(interaction.guild, force_refresh=True)
            status = result.get('status', 'updated')
            if status == 'cooldown':
                remaining = int(result.get('cooldown_remaining', 0))
                await interaction.followup.send(
                    f"⏳ Refresh cooldown: wait about {remaining}s.",
                    ephemeral=True,
                )
            elif status == 'in_progress':
                await interaction.followup.send(
                    "⏳ Refresh already in progress. Try again in a moment.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send("✅ Leaderboard refreshed.", ephemeral=True)
        except Exception as e:
            logger.error("❌ Persistent refresh failed for guild %s: %s", interaction.guild.id, e)
            await interaction.followup.send("❌ Refresh failed. Try again in a moment.", ephemeral=True)

    @discord.ui.button(label="Setup Account", style=discord.ButtonStyle.success, emoji="🔗", custom_id="rank_setup_button")
    async def setup_account_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Start account setup with `/link` and then verify it with `/verifyacc`.",
            ephemeral=True,
        )

class LeaderboardCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
        self.bot = bot
        self.riot_api = riot_api
        self.guild = discord.Object(id=guild_id)
        self._persistent_rank_pages = {}
        self._persistent_rank_cache = {}
        self._persistent_rank_last_fetch_at = {}
        self._persistent_rank_refresh_locks = {}
        self.persistent_rank_view = RankPersistentView(self)
        self.bot.add_view(self.persistent_rank_view)

        if not self.auto_update_rank_leaderboard_embed.is_running():
            self.auto_update_rank_leaderboard_embed.start()

    def cog_unload(self):
        if self.auto_update_rank_leaderboard_embed.is_running():
            self.auto_update_rank_leaderboard_embed.cancel()

    def _get_global_rank_day_key(self) -> str:
        """Return the current global UTC day key for ranked tracking."""
        return datetime.utcnow().date().isoformat()

    def _get_global_rank_window_start(self) -> str:
        """Return the ISO timestamp for current UTC day start."""
        return f"{self._get_global_rank_day_key()}T00:00:00"

    def _get_rank_window_start_for_guild(self, guild_id: int) -> str:
        """Get persisted UTC day window start for guild, fallback to current day start."""
        db = get_db()
        stored = db.get_guild_setting(guild_id, 'ranked_snapshot_window_started_at')
        return stored or self._get_global_rank_window_start()

    def _mark_rank_refresh(self, guild_id: int):
        """Persist last successful rank leaderboard refresh timestamp."""
        db = get_db()
        db.set_guild_setting(guild_id, 'rank_leaderboard_last_refresh_at', datetime.utcnow().isoformat())

    def _get_persistent_rank_region(self, guild_id: int) -> Optional[str]:
        """Get saved region filter for persistent rank leaderboard."""
        db = get_db()
        value = db.get_guild_setting(guild_id, 'rank_leaderboard_region')
        if not value:
            return None
        normalized = str(value).strip().lower()
        return normalized if normalized and normalized != 'all' else None

    def _set_persistent_rank_region(self, guild_id: int, region: Optional[str]):
        """Set saved region filter for persistent rank leaderboard."""
        db = get_db()
        if region:
            db.set_guild_setting(guild_id, 'rank_leaderboard_region', str(region).lower())
        else:
            db.set_guild_setting(guild_id, 'rank_leaderboard_region', 'all')

    def _rank_cache_key(self, guild_id: int, region: Optional[str]) -> tuple[int, str]:
        """Build cache key for guild + region."""
        return (guild_id, (region or 'all').lower())

    def _rank_priority_value(self, account_rank_data: dict) -> int:
        """Compute deterministic rank priority for sorting leaderboard entries."""
        rank_priority = {
            'CHALLENGER': 9, 'GRANDMASTER': 8, 'MASTER': 7,
            'DIAMOND': 6, 'EMERALD': 5, 'PLATINUM': 4,
            'GOLD': 3, 'SILVER': 2, 'BRONZE': 1, 'IRON': 0
        }
        division_priority = {'I': 4, 'II': 3, 'III': 2, 'IV': 1}

        tier = account_rank_data.get('tier', 'UNRANKED')
        rank = account_rank_data.get('rank', 'I')
        lp = int(account_rank_data.get('lp', 0))
        tier_priority = rank_priority.get(tier, -1)
        div_priority = division_priority.get(rank, 0) if tier not in ['MASTER', 'GRANDMASTER', 'CHALLENGER'] else 4
        return tier_priority * 1000 + div_priority * 100 + lp

    def _build_region_subset_from_cached_all(self, ranked_members_all: list, region: str) -> list:
        """Build regional leaderboard quickly from cached all-regions data."""
        target_region = region.lower()
        subset = []

        for entry in ranked_members_all:
            region_accounts = [
                a for a in entry.get('accounts', [])
                if str(a.get('region', '')).lower() == target_region
            ]
            if not region_accounts:
                continue

            best_account = max(region_accounts, key=self._rank_priority_value)
            best_priority = self._rank_priority_value(best_account)
            subset.append({
                'member': entry['member'],
                'data': dict(best_account),
                'priority': best_priority,
                'accounts': region_accounts,
                'aggregate_progress': entry.get('aggregate_progress'),
            })

        subset.sort(key=lambda x: x['priority'], reverse=True)
        return subset

    async def _get_or_refresh_persistent_rank_data(self, guild: discord.Guild, region: Optional[str], force_refresh: bool = False) -> tuple[list, str, int]:
        """Return ranked data using cache, with guarded refresh to protect bot performance."""
        guild_id = guild.id
        cache_key = self._rank_cache_key(guild_id, region)
        now = time.time()
        cached = self._persistent_rank_cache.get(cache_key)
        last_fetch = float(self._persistent_rank_last_fetch_at.get(cache_key, 0))
        cache_age = now - last_fetch

        if cached is not None and not force_refresh and cache_age <= RANK_CACHE_TTL_SECONDS:
            return cached, 'cache', 0

        if cached is not None and force_refresh and cache_age <= RANK_MANUAL_REFRESH_COOLDOWN_SECONDS:
            remaining = max(1, int(RANK_MANUAL_REFRESH_COOLDOWN_SECONDS - cache_age))
            return cached, 'cooldown', remaining

        # Fast path: if region is selected and all-regions cache is fresh, derive regional subset without API calls.
        if region and not force_refresh:
            all_key = self._rank_cache_key(guild_id, None)
            cached_all = self._persistent_rank_cache.get(all_key)
            all_last_fetch = float(self._persistent_rank_last_fetch_at.get(all_key, 0))
            all_cache_age = now - all_last_fetch
            if cached_all is not None and all_cache_age <= RANK_CACHE_TTL_SECONDS:
                derived = self._build_region_subset_from_cached_all(cached_all, region)
                self._persistent_rank_cache[cache_key] = derived
                self._persistent_rank_last_fetch_at[cache_key] = now
                return derived, 'cache', 0

        lock = self._persistent_rank_refresh_locks.setdefault(guild_id, asyncio.Lock())
        if lock.locked() and cached is not None:
            return cached, 'in_progress', 0

        async with lock:
            now = time.time()
            cached = self._persistent_rank_cache.get(cache_key)
            last_fetch = float(self._persistent_rank_last_fetch_at.get(cache_key, 0))
            cache_age = now - last_fetch

            if cached is not None and not force_refresh and cache_age <= RANK_CACHE_TTL_SECONDS:
                return cached, 'cache', 0

            if cached is not None and force_refresh and cache_age <= RANK_MANUAL_REFRESH_COOLDOWN_SECONDS:
                remaining = max(1, int(RANK_MANUAL_REFRESH_COOLDOWN_SECONDS - cache_age))
                return cached, 'cooldown', remaining

            if region and not force_refresh:
                all_key = self._rank_cache_key(guild_id, None)
                cached_all = self._persistent_rank_cache.get(all_key)
                all_last_fetch = float(self._persistent_rank_last_fetch_at.get(all_key, 0))
                all_cache_age = now - all_last_fetch
                if cached_all is not None and all_cache_age <= RANK_CACHE_TTL_SECONDS:
                    derived = self._build_region_subset_from_cached_all(cached_all, region)
                    self._persistent_rank_cache[cache_key] = derived
                    self._persistent_rank_last_fetch_at[cache_key] = now
                    return derived, 'cache', 0

            ranked_members = await self._collect_ranked_members(guild, region=region)
            self._persistent_rank_cache[cache_key] = ranked_members
            self._persistent_rank_last_fetch_at[cache_key] = time.time()
            return ranked_members, 'refreshed', 0

    def _maybe_reset_daily_snapshots(self, guild_id: int):
        """Reset ranked snapshot window by persisted global UTC day, not process uptime."""
        db = get_db()
        current_day_key = self._get_global_rank_day_key()
        stored_day_key = db.get_guild_setting(guild_id, 'ranked_snapshot_day_key')

        if not stored_day_key:
            db.set_guild_setting(guild_id, 'ranked_snapshot_day_key', current_day_key)
            db.set_guild_setting(guild_id, 'ranked_snapshot_window_started_at', self._get_global_rank_window_start())
            db.cleanup_ranked_progress_snapshots(guild_id, SNAPSHOT_RETENTION_HOURS)
            return

        if stored_day_key != current_day_key:
            db.set_guild_setting(guild_id, 'ranked_snapshot_day_key', current_day_key)
            db.set_guild_setting(guild_id, 'ranked_snapshot_window_started_at', self._get_global_rank_window_start())

        db.cleanup_ranked_progress_snapshots(guild_id, SNAPSHOT_RETENTION_HOURS)

    def _calculate_games_delta(self, current_wins: int, current_losses: int, baseline_snapshot: Optional[dict]) -> int:
        """Calculate games delta from the daily baseline snapshot."""
        if not baseline_snapshot:
            return 0

        prev_wins = int(baseline_snapshot.get('wins') or 0)
        prev_losses = int(baseline_snapshot.get('losses') or 0)
        games_delta = (int(current_wins) + int(current_losses)) - (prev_wins + prev_losses)
        return max(games_delta, 0)

    def _calculate_lp_delta(self, current_lp: int, baseline_snapshot: Optional[dict]) -> int:
        """Calculate LP delta from the daily baseline snapshot."""
        if not baseline_snapshot:
            return 0
        prev_lp = int(baseline_snapshot.get('league_points') or 0)
        return int(current_lp) - prev_lp

    def _aggregate_account_progress(self, guild_id: int, discord_user_id: int, accounts_data: list, snapshot_map: Optional[dict] = None) -> dict:
        """Aggregate daily LP and games deltas across all ranked accounts for one user."""
        db = get_db()
        total_lp_delta = 0
        total_games_delta = 0

        for account_data in accounts_data:
            puuid = account_data.get('puuid')
            if not puuid:
                continue

            baseline_snapshot = None
            if snapshot_map is not None:
                baseline_snapshot = snapshot_map.get((int(discord_user_id), str(puuid)))
            if baseline_snapshot is None:
                baseline_snapshot = db.get_daily_baseline_ranked_progress_snapshot(
                    guild_id,
                    discord_user_id,
                    puuid,
                    DAILY_RESET_HOURS,
                )
            total_lp_delta += self._calculate_lp_delta(account_data.get('lp', 0), baseline_snapshot)
            total_games_delta += self._calculate_games_delta(
                account_data.get('wins', 0),
                account_data.get('losses', 0),
                baseline_snapshot,
            )

        return {
            'lp_delta': total_lp_delta,
            'games_delta': max(total_games_delta, 0),
            'played_today': total_games_delta > 0,
        }

    def _format_aggregate_today_progress(self, aggregate_progress: dict) -> str:
        """Format aggregated daily progress across all accounts."""
        lp_delta = int(aggregate_progress.get('lp_delta', 0))
        games_delta = int(aggregate_progress.get('games_delta', 0))
        lp_prefix = "+" if lp_delta >= 0 else ""
        return f"today: {lp_prefix}{lp_delta} LP / {games_delta}G"

    def _filter_members_played_today(self, guild_id: int, ranked_members: list) -> list:
        """Keep only users with ranked activity in the current 24h window."""
        db = get_db()
        day_start = self._get_rank_window_start_for_guild(guild_id)
        snapshot_map = db.get_ranked_progress_baseline_map_for_day(guild_id, day_start)
        filtered_members = []
        for entry in ranked_members:
            aggregate_progress = entry.get('aggregate_progress') or self._aggregate_account_progress(
                guild_id,
                entry['member'].id,
                entry.get('accounts', []),
                snapshot_map=snapshot_map,
            )
            entry['aggregate_progress'] = aggregate_progress
            if aggregate_progress.get('played_today'):
                filtered_members.append(entry)
        return filtered_members

    def _format_today_progress(self, current_lp: int, current_wins: int, current_losses: int, baseline_snapshot: Optional[dict]) -> str:
        """Format LP and games delta against the daily baseline snapshot."""
        if not baseline_snapshot:
            return "today: +0 LP / 0G"

        prev_lp = int(baseline_snapshot.get('league_points') or 0)
        lp_delta = int(current_lp) - prev_lp
        games_delta = self._calculate_games_delta(current_wins, current_losses, baseline_snapshot)
        lp_prefix = "+" if lp_delta >= 0 else ""
        return f"today: {lp_prefix}{lp_delta} LP / {games_delta}G"

    async def _collect_ranked_members(self, guild: discord.Guild, region: Optional[str] = None) -> list:
        """Collect and sort ranked members in guild."""
        db = get_db()

        rank_priority = {
            'CHALLENGER': 9, 'GRANDMASTER': 8, 'MASTER': 7,
            'DIAMOND': 6, 'EMERALD': 5, 'PLATINUM': 4,
            'GOLD': 3, 'SILVER': 2, 'BRONZE': 1, 'IRON': 0
        }
        division_priority = {'I': 4, 'II': 3, 'III': 2, 'IV': 1}

        ranked_members = []
        for member in guild.members:
            if member.bot:
                continue

            db_user = await asyncio.to_thread(db.get_user_by_discord_id, member.id)
            if not db_user:
                continue

            accounts = await asyncio.to_thread(db.get_user_accounts, db_user['id'])
            if not accounts:
                continue

            best_rank_data = None
            best_priority = -1
            ranked_accounts_data = []

            for account in accounts:
                if not account.get('verified'):
                    continue
                if region and account['region'].lower() != region.lower():
                    continue

                try:
                    ranks = await self.riot_api.get_ranked_stats_by_puuid(account['puuid'], account['region'])
                    if not ranks:
                        continue

                    for rank_data in ranks:
                        if 'SOLO' not in rank_data.get('queueType', ''):
                            continue

                        tier = rank_data.get('tier', 'UNRANKED')
                        if tier == 'UNRANKED':
                            continue

                        rank = rank_data.get('rank', 'I')
                        lp = rank_data.get('leaguePoints', 0)
                        wins = rank_data.get('wins', 0)
                        losses = rank_data.get('losses', 0)

                        if (wins + losses) < 1:
                            continue

                        account_rank_data = {
                            'tier': tier,
                            'rank': rank,
                            'lp': lp,
                            'wins': wins,
                            'losses': losses,
                            'puuid': account['puuid'],
                            'region': account['region'].upper(),
                            'riot_name': f"{account['riot_id_game_name']}#{account['riot_id_tagline']}"
                        }
                        ranked_accounts_data.append(account_rank_data)

                        tier_priority = rank_priority.get(tier, -1)
                        div_priority = division_priority.get(rank, 0) if tier not in ['MASTER', 'GRANDMASTER', 'CHALLENGER'] else 4
                        total_priority = tier_priority * 1000 + div_priority * 100 + lp

                        if total_priority > best_priority:
                            best_priority = total_priority
                            best_rank_data = dict(account_rank_data)
                except Exception:
                    continue

            if best_rank_data:
                aggregate_progress = self._aggregate_account_progress(
                    guild.id,
                    member.id,
                    ranked_accounts_data,
                )
                ranked_members.append({
                    'member': member,
                    'data': best_rank_data,
                    'priority': best_priority,
                    'accounts': ranked_accounts_data,
                    'aggregate_progress': aggregate_progress,
                })

        ranked_members.sort(key=lambda x: x['priority'], reverse=True)
        return ranked_members

    def _build_ranked_embed(
        self,
        guild: discord.Guild,
        ranked_members: list,
        region: Optional[str] = None,
        requested_by: Optional[str] = None,
        page: int = 1,
        page_size: int = RANK_PAGE_SIZE,
        only_played_today: bool = False,
    ) -> discord.Embed:
        """Build ranked leaderboard embed for command and auto-updates."""
        db = get_db()
        from emoji_dict import get_rank_emoji

        region_flags = {
            'euw': '🇪🇺', 'eune': '🇪🇺', 'na': '🇺🇸', 'kr': '🇰🇷',
            'jp': '🇯🇵', 'br': '🇧🇷', 'lan': '🇲🇽', 'las': '🇦🇷',
            'oce': '🇦🇺', 'ru': '🇷🇺', 'tr': '🇹🇷', 'sg': '🇸🇬',
            'ph': '🇵🇭', 'th': '🇹🇭', 'tw': '🇹🇼', 'vn': '🇻🇳'
        }

        # Optional filter: keep only players who played at least one ranked game in current 24h window.
        filtered_members = ranked_members
        if only_played_today:
            filtered_members = self._filter_members_played_today(guild.id, ranked_members)

        total_players = len(filtered_members)
        total_pages = max(1, math.ceil(total_players / page_size))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_entries = filtered_members[start_idx:end_idx]

        region_text = f" • {region.upper()}" if region else ""
        embed = discord.Embed(
            title=f"🏆 Server Rank Leaderboard{region_text}",
            description=f"**{guild.name}** • Ranked Players • Page {page}/{total_pages}",
            color=0xC89B3C
        )

        leaderboard_parts = []
        current_part = ""

        for offset, entry in enumerate(page_entries, start=1):
            member = entry['member']
            data = entry['data']
            position = start_idx + offset

            tier = data['tier']
            rank = data['rank']
            lp = data['lp']
            wins = data['wins']
            losses = data['losses']
            total_games = wins + losses
            winrate = (wins / total_games * 100) if total_games > 0 else 0

            rank_emoji = get_rank_emoji(tier)
            region_flag = region_flags.get(data['region'].lower(), '🌍')

            if tier in ['MASTER', 'GRANDMASTER', 'CHALLENGER']:
                rank_text = f"{rank_emoji} **{tier.capitalize()}**"
            else:
                rank_text = f"{rank_emoji} **{tier.capitalize()} {rank}**"

            entry_text = f"{position}. {member.mention} {region_flag} **{data['region']}**\n"
            entry_text += f"   {rank_text} • **{lp} LP** • {wins}W {losses}L ({winrate:.0f}% WR)\n"

            if len(current_part) + len(entry_text) > 1024:
                leaderboard_parts.append(current_part)
                current_part = entry_text
            else:
                current_part += entry_text

        if current_part:
            leaderboard_parts.append(current_part)

        if leaderboard_parts:
            for idx, part in enumerate(leaderboard_parts):
                field_name = "📊 Rankings" if idx == 0 else "📊 Rankings (continued)"
                embed.add_field(name=field_name, value=part, inline=False)
        else:
            embed.add_field(name="📊 Rankings", value="No ranked players found.", inline=False)

        footer_author = requested_by or "Auto update"
        embed.set_footer(text=f"Total ranked players: {total_players} • {footer_author}")
        return embed

    def _save_ranked_snapshots(self, guild_id: int, ranked_members: list):
        """Persist snapshots after each successful leaderboard render."""
        db = get_db()
        for entry in ranked_members:
            for data in entry.get('accounts', []):
                puuid = data.get('puuid')
                if not puuid:
                    continue
                db.save_ranked_progress_snapshot(
                    guild_id,
                    entry['member'].id,
                    puuid,
                    data.get('tier', 'UNRANKED'),
                    data.get('rank', 'I'),
                    int(data.get('lp', 0)),
                    int(data.get('wins', 0)),
                    int(data.get('losses', 0)),
                )

    async def _change_persistent_rank_page(self, guild: discord.Guild, delta: int, message: Optional[discord.Message] = None):
        """Change persistent leaderboard page and update the configured message."""
        db = get_db()
        region = self._get_persistent_rank_region(guild.id)
        if message is None:
            message_id_raw = db.get_guild_setting(guild.id, 'rank_leaderboard_message_id')
            if not message_id_raw or not str(message_id_raw).isdigit():
                await self._update_or_create_rank_embed(guild)
                return

            channel_id_raw = db.get_guild_setting(guild.id, 'leaderboard_channel')
            if not channel_id_raw or not str(channel_id_raw).isdigit():
                return

            channel = guild.get_channel(int(channel_id_raw))
            if channel is None:
                return

            try:
                message = await channel.fetch_message(int(message_id_raw))
            except discord.NotFound:
                await self._update_or_create_rank_embed(guild)
                return

        ranked_members, _, _ = await self._get_or_refresh_persistent_rank_data(guild, region=region, force_refresh=False)

        total_pages = max(1, math.ceil(len(ranked_members) / RANK_PAGE_SIZE))
        current_page = int(self._persistent_rank_pages.get(guild.id, 1))
        next_page = max(1, min(current_page + delta, total_pages))
        self._persistent_rank_pages[guild.id] = next_page

        embed = self._build_ranked_embed(
            guild,
            ranked_members,
            region=region,
            requested_by="Auto update",
            page=next_page,
            page_size=RANK_PAGE_SIZE,
            only_played_today=False,
        )
        await message.edit(embed=embed, view=self.persistent_rank_view)

    async def _update_or_create_rank_embed(self, guild: discord.Guild, force_refresh: bool = False):
        """Update persistent ranked leaderboard embed, or create it if missing."""
        db = get_db()
        region = self._get_persistent_rank_region(guild.id)

        self._maybe_reset_daily_snapshots(guild.id)

        leaderboards_enabled = db.get_guild_setting(guild.id, 'leaderboards_enabled')
        if leaderboards_enabled == 'false':
            return

        auto_post = db.get_guild_setting(guild.id, 'leaderboard_auto_post')
        if auto_post != 'true':
            if guild.id == self.guild.id:
                db.set_guild_setting(guild.id, 'leaderboard_auto_post', 'true')
            else:
                return

        channel_id_raw = db.get_guild_setting(guild.id, 'leaderboard_channel')
        channel_id = None
        if channel_id_raw and str(channel_id_raw).isdigit():
            channel_id = int(channel_id_raw)

        if channel_id is None and guild.id == self.guild.id:
            channel_id = DEFAULT_RANK_LEADERBOARD_CHANNEL_ID
            db.set_guild_setting(guild.id, 'leaderboard_channel', str(channel_id))

        if channel_id is None:
            return

        channel = guild.get_channel(channel_id)
        if channel is None:
            logger.warning("⚠️ Rank leaderboard channel not found in guild %s: %s", guild.id, channel_id)
            return

        ranked_members, fetch_status, cooldown_remaining = await self._get_or_refresh_persistent_rank_data(
            guild,
            region=region,
            force_refresh=force_refresh,
        )
        total_pages = max(1, math.ceil(len(ranked_members) / RANK_PAGE_SIZE))
        current_page = int(self._persistent_rank_pages.get(guild.id, 1))
        current_page = max(1, min(current_page, total_pages))
        self._persistent_rank_pages[guild.id] = current_page
        view = self.persistent_rank_view
        embed = self._build_ranked_embed(
            guild,
            ranked_members,
            region=region,
            requested_by="Auto update",
            page=current_page,
            page_size=RANK_PAGE_SIZE,
            only_played_today=False,
        )

        message_id_raw = db.get_guild_setting(guild.id, 'rank_leaderboard_message_id')
        message_id = int(message_id_raw) if message_id_raw and str(message_id_raw).isdigit() else None

        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed, view=view)
                if fetch_status == 'refreshed':
                    self._save_ranked_snapshots(guild.id, ranked_members)
                    self._mark_rank_refresh(guild.id)
                logger.info("✅ Updated persistent rank leaderboard embed for guild %s", guild.id)
                return {'status': fetch_status, 'cooldown_remaining': cooldown_remaining}
            except discord.NotFound:
                pass
            except Exception as e:
                logger.warning("⚠️ Failed to update persistent rank leaderboard embed for guild %s: %s", guild.id, e)

        message = await channel.send(embed=embed, view=view)
        db.set_guild_setting(guild.id, 'rank_leaderboard_message_id', str(message.id))
        if fetch_status == 'refreshed':
            self._save_ranked_snapshots(guild.id, ranked_members)
            self._mark_rank_refresh(guild.id)
        logger.info("✅ Created persistent rank leaderboard embed for guild %s", guild.id)
        return {'status': fetch_status, 'cooldown_remaining': cooldown_remaining}

    @tasks.loop(hours=1)
    async def auto_update_rank_leaderboard_embed(self):
        """Auto-update permanent ranked leaderboard embeds for configured guilds."""
        for guild in self.bot.guilds:
            try:
                await self._update_or_create_rank_embed(guild)
            except Exception as e:
                logger.error("❌ Rank leaderboard auto-update failed for guild %s: %s", guild.id, e)

    @auto_update_rank_leaderboard_embed.before_loop
    async def before_auto_update_rank_leaderboard_embed(self):
        await self.bot.wait_until_ready()
        logger.info("✅ Rank leaderboard auto-update loop started (every 1 hour)")
    
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
        
        message = await interaction.followup.send(embed=embed)
        
        # Auto-delete after 60 seconds
        await asyncio.sleep(60)
        try:
            await message.delete()
        except:
            pass
    
    @app_commands.command(name="ranktop", description="View TOP10 ranked players on this server") 
    @app_commands.describe(
        user="Show specific user's position in ranking (optional)",
        region="Filter by specific region (optional)"
    )
    @app_commands.choices(region=[
        app_commands.Choice(name="🇪🇺 EUW - Europe West", value="euw"),
        app_commands.Choice(name="🇪🇺 EUNE - Europe Nordic & East", value="eune"),
        app_commands.Choice(name="🇺🇸 NA - North America", value="na"),
        app_commands.Choice(name="🇰🇷 KR - Korea", value="kr"),
        app_commands.Choice(name="🇨🇳 CN - China", value="cn"),
        app_commands.Choice(name="🇯🇵 JP - Japan", value="jp"),
        app_commands.Choice(name="🇧🇷 BR - Brazil", value="br"),
        app_commands.Choice(name="🇲🇽 LAN - Latin America North", value="lan"),
        app_commands.Choice(name="🇦🇷 LAS - Latin America South", value="las"),
        app_commands.Choice(name="🇦🇺 OCE - Oceania", value="oce"),
        app_commands.Choice(name="🇷🇺 RU - Russia", value="ru"),
        app_commands.Choice(name="🇹🇷 TR - Turkey", value="tr"),
        app_commands.Choice(name="🇸🇬 SG - Singapore", value="sg"),
        app_commands.Choice(name="🇵🇭 PH - Philippines", value="ph"),
        app_commands.Choice(name="🇹🇭 TH - Thailand", value="th"),
        app_commands.Choice(name="🇹🇼 TW - Taiwan", value="tw"),
        app_commands.Choice(name="🇻🇳 VN - Vietnam", value="vn"),
    ])
    async def ranktop(self, interaction: discord.Interaction, 
                     user: Optional[discord.User] = None,
                     region: Optional[str] = None):
        """Show TOP10 ranked players with pagination and daily activity filter."""
        await interaction.response.defer()

        try:
            if not interaction.guild:
                await interaction.followup.send(
                    "❌ This command can only be used in a server!",
                    ephemeral=True
                )
                return

            db = get_db()
            self._maybe_reset_daily_snapshots(interaction.guild.id)

            ranked_members = await self._collect_ranked_members(interaction.guild, region=region)

            if not ranked_members:
                region_text = f" in {region.upper()}" if region else ""
                await interaction.followup.send(
                    f"❌ No ranked players found{region_text}.",
                    ephemeral=True,
                )
                return

            view = None
            try:
                view = RankTopView(
                    cog=self,
                    guild=interaction.guild,
                    ranked_members=ranked_members,
                    region=region,
                    requested_by=interaction.user.name,
                )
                view._sync_buttons()
            except RuntimeError as loop_error:
                logger.warning("⚠️ Failed to initialize RankTopView (no running event loop): %s", loop_error)

            embed = self._build_ranked_embed(
                guild=interaction.guild,
                ranked_members=ranked_members,
                region=region,
                requested_by=interaction.user.name,
                page=1,
                page_size=RANK_PAGE_SIZE,
                only_played_today=False,
            )

            if user:
                user_position = None
                for i, entry in enumerate(ranked_members, start=1):
                    if entry['member'].id == user.id:
                        user_position = i
                        break
                if user_position:
                    embed.add_field(
                        name=f"📍 {user.display_name}'s Position",
                        value=f"**#{user_position}** in the server ranking",
                        inline=False,
                    )
                else:
                    embed.add_field(
                        name=f"📍 {user.display_name}'s Position",
                        value="Not ranked or not in this server.",
                        inline=False,
                    )

            try:
                if view is not None:
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send(embed=embed)
            except discord.NotFound:
                logger.warning("⚠️ Interaction followup expired in ranktop; sending message to channel fallback")
                if interaction.channel:
                    if view is not None:
                        await interaction.channel.send(embed=embed, view=view)
                    else:
                        await interaction.channel.send(embed=embed)
                else:
                    raise
            cache_key = self._rank_cache_key(interaction.guild.id, region)
            self._persistent_rank_cache[cache_key] = ranked_members
            self._persistent_rank_last_fetch_at[cache_key] = time.time()
            self._persistent_rank_pages[interaction.guild.id] = 1
            self._save_ranked_snapshots(interaction.guild.id, ranked_members)
            self._mark_rank_refresh(interaction.guild.id)

        except Exception as e:
            logger.exception("Error in ranktop: %s", e)
            try:
                if interaction.response.is_done():
                    await interaction.followup.send("❌ An error occurred while fetching leaderboard data.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ An error occurred while fetching leaderboard data.", ephemeral=True)
            except discord.NotFound:
                if interaction.channel:
                    await interaction.channel.send("❌ An error occurred while fetching leaderboard data.")

async def setup(bot: commands.Bot, riot_api: RiotAPI, guild_id: int):
    """Setup leaderboard commands"""
    cog = LeaderboardCommands(bot, riot_api, guild_id)
    await bot.add_cog(cog)
    
    logger.info("✅ Leaderboard commands loaded")
