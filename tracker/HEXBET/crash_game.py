"""
HEXBET Crash Game
A multiplier-based crash betting minigame using the shared token balance.

Flow:
  1. BETTING PHASE (30s) - players join with /hxcrash <amount> or by pressing the Join button
  2. LIVE PHASE - multiplier ticks up every second; players can cashout via button
  3. CRASH - round ends, remaining bets are lost, cashed-out players win bet * multiplier
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import random
import logging
import math
import time
import os
from typing import Optional

from HEXBET.config import RANK_EMOJIS as CFG_RANK_EMOJIS

logger = logging.getLogger('crash_game')

CRASH_CHANNEL_ID = 1510593241744019517
MIN_BET = 10
MAX_BET = 50_000
BETTING_PHASE_SECONDS = 30
TICK_INTERVAL = 1.0        # seconds between multiplier updates
HOUSE_EDGE = 0.04          # 4% house edge used in crash point generation


# ---------------------------------------------------------------------------
# Rank helper (same formula as /hxbalance)
# ---------------------------------------------------------------------------

def get_rank_info(balance: int):
    """Return (rank_name, division, rank_lp, rank_emoji) for a given balance."""
    TIER_ORDER = ['IRON', 'BRONZE', 'SILVER', 'GOLD', 'PLATINUM', 'EMERALD', 'DIAMOND']
    MASTER_THRESHOLD = 2800
    GM_THRESHOLD = 3400
    CHALLENGER_THRESHOLD = 4600

    lp_total = balance // 2

    if lp_total >= CHALLENGER_THRESHOLD:
        return 'CHALLENGER', '', lp_total - CHALLENGER_THRESHOLD, CFG_RANK_EMOJIS.get('CHALLENGER', '👑')
    elif lp_total >= GM_THRESHOLD:
        return 'GRANDMASTER', '', lp_total - GM_THRESHOLD, CFG_RANK_EMOJIS.get('GRANDMASTER', '💎')
    elif lp_total >= MASTER_THRESHOLD:
        return 'MASTER', '', lp_total - MASTER_THRESHOLD, CFG_RANK_EMOJIS.get('MASTER', '🔮')
    else:
        tier_idx = min(lp_total // 400, len(TIER_ORDER) - 1)
        div_idx = min((lp_total % 400) // 100, 3)
        divisions = ['IV', 'III', 'II', 'I']
        rank_name = TIER_ORDER[tier_idx]
        division = divisions[div_idx]
        rank_lp = lp_total % 100
        emoji = CFG_RANK_EMOJIS.get(rank_name, '🎖️')
        return rank_name, division, rank_lp, emoji


# ---------------------------------------------------------------------------
# Crash point generation
# ---------------------------------------------------------------------------

def generate_crash_point() -> float:
    """Generate a random crash point with a house edge.
    Uses the formula: crash = max(1.00, 1 / (1 - r)) * (1 - house_edge)
    where r is uniform [0, 1). Ensures ~4% of rounds crash at exactly 1.00x.
    """
    r = random.random()
    if r < HOUSE_EDGE:
        return 1.00
    crash = (1.0 - HOUSE_EDGE) / (1.0 - r)
    return round(max(1.01, crash), 2)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class BettingPhaseView(discord.ui.View):
    """Shown during betting phase - only Join button."""

    def __init__(self, cog: 'CrashCog'):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label='🚀 Join Round', style=discord.ButtonStyle.green, custom_id='crash_join')
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        round_state = self.cog.current_round
        if not round_state or round_state['phase'] != 'betting':
            await interaction.response.send_message("❌ No active betting phase right now.", ephemeral=True)
            return

        user_id = interaction.user.id
        if user_id in round_state['bets']:
            amount = round_state['bets'][user_id]['amount']
            await interaction.response.send_message(
                f"✅ Already joined with **{amount:,}** tokens. Wait for the round to start!", ephemeral=True
            )
            return

        await interaction.response.send_modal(CrashBetModal(self.cog))


class LivePhaseView(discord.ui.View):
    """Shown while multiplier is running - only Cashout button."""

    def __init__(self, cog: 'CrashCog'):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label='💸 CASHOUT', style=discord.ButtonStyle.red, custom_id='crash_cashout')
    async def cashout(self, interaction: discord.Interaction, button: discord.ui.Button):
        round_state = self.cog.current_round
        if not round_state or round_state['phase'] != 'live':
            await interaction.response.send_message("❌ Round is not live.", ephemeral=True)
            return

        user_id = interaction.user.id
        if user_id not in round_state['bets']:
            await interaction.response.send_message("❌ You didn't join this round.", ephemeral=True)
            return

        bet_info = round_state['bets'][user_id]
        if bet_info.get('cashed_out'):
            await interaction.response.send_message(
                f"✅ Already cashed out at **{bet_info['cashout_mult']:.2f}x**.", ephemeral=True
            )
            return

        current_mult = round_state['multiplier']
        bet_info['cashed_out'] = True
        bet_info['cashout_mult'] = current_mult
        payout = int(bet_info['amount'] * current_mult)
        bet_info['payout'] = payout
        self.cog.db.update_balance(user_id, payout)

        profit = payout - bet_info['amount']
        await interaction.response.send_message(
            f"💸 Cashed out at **{current_mult:.2f}x**!\n"
            f"Bet: **{bet_info['amount']:,}** → Won: **{payout:,}** (+{profit:,} tokens)",
            ephemeral=True,
        )
        logger.info(f"💸 User {interaction.user} cashed out at {current_mult:.2f}x, payout={payout}")


class CrashBetModal(discord.ui.Modal, title='🚀 Join Crash Round'):
    amount_input = discord.ui.TextInput(
        label='Bet Amount (tokens)',
        placeholder=f'Enter amount ({MIN_BET}–{MAX_BET:,})',
        min_length=1,
        max_length=10,
    )
    auto_cashout_input = discord.ui.TextInput(
        label='Auto-Cashout at (e.g. 2.00) — optional',
        placeholder='Leave empty to cashout manually',
        required=False,
        min_length=0,
        max_length=8,
    )

    def __init__(self, cog: 'CrashCog'):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        round_state = self.cog.current_round
        if not round_state or round_state['phase'] != 'betting':
            await interaction.response.send_message("❌ Betting phase has ended.", ephemeral=True)
            return

        user_id = interaction.user.id
        if user_id in round_state['bets']:
            await interaction.response.send_message("❌ You already joined this round.", ephemeral=True)
            return

        # Parse amount
        try:
            amount = int(self.amount_input.value.replace(',', '').replace(' ', ''))
        except ValueError:
            await interaction.response.send_message("❌ Invalid amount.", ephemeral=True)
            return

        if amount < MIN_BET or amount > MAX_BET:
            await interaction.response.send_message(
                f"❌ Bet must be between **{MIN_BET}** and **{MAX_BET:,}** tokens.", ephemeral=True
            )
            return

        balance = self.cog.db.get_balance(user_id)
        if balance < amount:
            await interaction.response.send_message(
                f"❌ Insufficient balance. You have **{balance:,}** tokens.", ephemeral=True
            )
            return

        # Parse auto cashout
        auto_cashout = None
        raw_ac = (self.auto_cashout_input.value or '').strip()
        if raw_ac:
            try:
                auto_cashout = float(raw_ac)
                if auto_cashout < 1.01:
                    auto_cashout = 1.01
            except ValueError:
                auto_cashout = None

        # Deduct tokens immediately
        self.cog.db.update_balance(user_id, -amount)
        round_state['bets'][user_id] = {
            'user': interaction.user,
            'amount': amount,
            'auto_cashout': auto_cashout,
            'cashed_out': False,
            'cashout_mult': None,
            'payout': 0,
        }

        ac_str = f" (auto-cashout at **{auto_cashout:.2f}x**)" if auto_cashout else ""
        rank_name, division, rank_lp, rank_emoji = get_rank_info(balance - amount)
        rank_str = f"{rank_emoji} {rank_name} {division}".strip()

        await interaction.response.send_message(
            f"✅ Joined with **{amount:,}** tokens{ac_str}!\n"
            f"Balance: **{balance - amount:,}** tokens | {rank_str} · {rank_lp} LP",
            ephemeral=True,
        )
        logger.info(f"🚀 User {interaction.user} joined crash with {amount} tokens")


# ---------------------------------------------------------------------------
# CrashCog
# ---------------------------------------------------------------------------

# Bar chart characters (8 levels + empty)
CHART_BARS = ' ▁▂▃▄▅▆▇█'


class CrashCog(commands.Cog):
    """Crash game cog. Runs automatic rounds in the configured channel."""

    def __init__(self, bot: commands.Bot, db):
        self.bot = bot
        self.db = db
        self.current_round: Optional[dict] = None
        self._round_task: Optional[asyncio.Task] = None
        self._last_result_msg: Optional[discord.Message] = None
        self._auto_runner.start()

    def cog_unload(self):
        self._auto_runner.cancel()
        if self._round_task:
            self._round_task.cancel()

    # ------------------------------------------------------------------
    # Auto runner - starts a new round every ~60s when none is active
    # ------------------------------------------------------------------

    @tasks.loop(seconds=60)
    async def _auto_runner(self):
        """Automatically start a new crash round when channel is idle."""
        if self.current_round is not None:
            return  # round already running
        channel = self.bot.get_channel(CRASH_CHANNEL_ID)
        if not channel:
            return
        await self._start_round(channel)

    @_auto_runner.before_loop
    async def _before_auto(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(10)  # small startup delay

    # ------------------------------------------------------------------
    # Round logic
    # ------------------------------------------------------------------

    async def _start_round(self, channel: discord.TextChannel):
        """Run one full crash round (betting → live → result)."""
        crash_point = generate_crash_point()

        # Delete previous result message after 5 seconds
        if self._last_result_msg is not None:
            prev = self._last_result_msg
            self._last_result_msg = None
            async def _delayed_delete(m: discord.Message):
                await asyncio.sleep(5)
                try:
                    await m.delete()
                except Exception:
                    pass
            asyncio.create_task(_delayed_delete(prev))

        closes_at = int(time.time()) + BETTING_PHASE_SECONDS

        self.current_round = {
            'phase': 'betting',
            'bets': {},
            'multiplier': 1.00,
            'crash_point': crash_point,
            'message': None,
            'history': [],  # list of mult snapshots for chart
            'closes_at': closes_at,
        }

        # ── BETTING PHASE ──────────────────────────────────────────────
        embed = self._build_betting_embed(closes_at)
        view = BettingPhaseView(self)
        msg = await channel.send(embed=embed, view=view)
        self.current_round['message'] = msg

        # Refresh player list every 5 seconds (timestamp updates client-side automatically)
        elapsed = 0
        while elapsed < BETTING_PHASE_SECONDS:
            await asyncio.sleep(5)
            elapsed += 5
            if elapsed >= BETTING_PHASE_SECONDS:
                break
            try:
                await msg.edit(embed=self._build_betting_embed(closes_at), view=view)
            except Exception:
                pass

        # ── LIVE PHASE ─────────────────────────────────────────────────
        self.current_round['phase'] = 'live'
        self.current_round['multiplier'] = 1.00
        live_view = LivePhaseView(self)

        if not self.current_round['bets']:
            # No players joined — skip silently
            try:
                await msg.delete()
            except Exception:
                pass
            self.current_round = None
            return

        start_ts = time.time()
        try:
            await msg.edit(embed=self._build_live_embed(), view=live_view)
        except Exception:
            pass

        # Tick loop
        tick_count = 0
        while True:
            await asyncio.sleep(TICK_INTERVAL)
            elapsed_live = time.time() - start_ts
            # Multiplier grows exponentially: 1.00 * e^(0.06 * t)
            mult = round(1.00 * math.exp(0.06 * elapsed_live), 2)
            self.current_round['multiplier'] = mult

            # Record snapshot for chart (max 20 points)
            history = self.current_round['history']
            history.append(mult)
            if len(history) > 20:
                history.pop(0)

            # Process auto-cashouts
            for user_id, bet_info in self.current_round['bets'].items():
                if bet_info.get('cashed_out'):
                    continue
                ac = bet_info.get('auto_cashout')
                if ac and mult >= ac:
                    payout = int(bet_info['amount'] * mult)
                    bet_info['cashed_out'] = True
                    bet_info['cashout_mult'] = mult
                    bet_info['payout'] = payout
                    self.db.update_balance(user_id, payout)

            # Update embed every tick
            tick_count += 1
            try:
                await msg.edit(embed=self._build_live_embed(), view=live_view)
            except Exception:
                pass

            if mult >= crash_point:
                self.current_round['multiplier'] = crash_point
                break

        # ── CRASH ──────────────────────────────────────────────────────
        self.current_round['phase'] = 'crashed'
        # No payout for players who didn't cash out (tokens already deducted)

        try:
            result_msg = await msg.edit(embed=self._build_result_embed(), view=None)
        except Exception:
            result_msg = msg

        self._last_result_msg = msg  # store so next round can delete it
        self.current_round = None

    # ------------------------------------------------------------------
    # Embed builders
    # ------------------------------------------------------------------

    def _build_betting_embed(self, closes_at: int) -> discord.Embed:
        embed = discord.Embed(
            title="🚀 CRASH — Betting Phase",
            description=(
                f"⏳ Zamknięcie o <t:{closes_at}:T> (<t:{closes_at}:R>)\n\n"
                f"Kliknij **🚀 Join Round** żeby dołączyć.\n"
                f"Możesz ustawić **auto-cashout** lub wychodzić ręcznie.\n\n"
                f"Min: **{MIN_BET}** | Max: **{MAX_BET:,}** tokenów"
            ),
            color=0x2ecc71,
        )
        bets = self.current_round['bets'] if self.current_round else {}
        if bets:
            players_str = '\n'.join(
                f"• {info['user'].display_name} — **{info['amount']:,}** tokens"
                + (f" (auto @ {info['auto_cashout']:.2f}x)" if info.get('auto_cashout') else "")
                for info in bets.values()
            )
            embed.add_field(name=f"👥 Players Joined ({len(bets)})", value=players_str, inline=False)
        else:
            embed.add_field(name="👥 Players Joined", value="*None yet — be the first!*", inline=False)
        embed.set_footer(text="💡 The multiplier starts at 1.00x and can crash at any moment!")
        return embed

    @staticmethod
    def _build_chart(history: list) -> str:
        """Build a text-based bar chart from multiplier history.
        Returns a string like: `▁▂▃▄▅▆▇██` padded to 20 chars.
        """
        if not history:
            return '`' + '░' * 20 + '`'
        # Normalize: min is always 1.00, max is current (last in history)
        max_val = max(history)
        min_val = 1.00
        span = max(max_val - min_val, 0.01)

        bars = []
        for v in history:
            level = int((v - min_val) / span * 8)
            level = max(0, min(8, level))
            bars.append(CHART_BARS[level])

        # Pad left side with empty if less than 20
        padded = '░' * (20 - len(bars)) + ''.join(bars)
        return f'`{padded}`'

    def _build_live_embed(self) -> discord.Embed:
        mult = self.current_round['multiplier']
        bets = self.current_round['bets']
        history = self.current_round.get('history', [])

        # Color gradient: green → yellow → red
        if mult < 2.0:
            color = 0x2ecc71
        elif mult < 5.0:
            color = 0xf39c12
        else:
            color = 0xe74c3c

        chart = self._build_chart(history)

        # Big multiplier display with chart
        embed = discord.Embed(
            title=f"📈 CRASH — **{mult:.2f}x**",
            description=(
                f"{chart}\n"
                f"Press **💸 CASHOUT** now to secure your winnings!"
            ),
            color=color,
        )

        # Players status
        lines = []
        for info in bets.values():
            name = info['user'].display_name
            if info.get('cashed_out'):
                payout = info['payout']
                profit = payout - info['amount']
                lines.append(f"✅ {name} — cashed out @ **{info['cashout_mult']:.2f}x** (+{profit:,})")
            else:
                current_val = int(info['amount'] * mult)
                lines.append(f"⏳ {name} — **{info['amount']:,}** → **{current_val:,}** (if cashout now)")

        embed.add_field(name="👥 Players", value='\n'.join(lines) if lines else '*No players*', inline=False)
        embed.set_footer(text="Don't wait too long — it WILL crash!")
        return embed

    def _build_result_embed(self) -> discord.Embed:
        crash_at = self.current_round['crash_point']
        bets = self.current_round['bets']

        embed = discord.Embed(
            title=f"💥 CRASHED at **{crash_at:.2f}x**!",
            color=0xe74c3c,
        )

        winners = [(i, b) for i, b in bets.items() if b.get('cashed_out')]
        losers = [(i, b) for i, b in bets.items() if not b.get('cashed_out')]

        if winners:
            winner_lines = []
            for _, b in winners:
                profit = b['payout'] - b['amount']
                winner_lines.append(
                    f"✅ {b['user'].display_name} — {b['amount']:,} → **{b['payout']:,}** "
                    f"(+{profit:,} @ {b['cashout_mult']:.2f}x)"
                )
            embed.add_field(name="🏆 Cashed Out", value='\n'.join(winner_lines), inline=False)

        if losers:
            loser_lines = [
                f"❌ {b['user'].display_name} — lost **{b['amount']:,}** tokens"
                for _, b in losers
            ]
            embed.add_field(name="💀 Busted", value='\n'.join(loser_lines), inline=False)

        embed.set_footer(text="Next round starts in ~60 seconds.")
        return embed

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    @app_commands.command(name="hxcrash", description="Join the current Crash round with a token bet")
    @app_commands.describe(
        amount="Amount of tokens to bet",
        auto_cashout="Auto-cashout at this multiplier (e.g. 2.0). Leave empty to cashout manually.",
    )
    async def hxcrash(
        self,
        interaction: discord.Interaction,
        amount: int,
        auto_cashout: Optional[float] = None,
    ):
        """Join crash round via slash command (alternative to button)."""
        round_state = self.current_round
        if not round_state or round_state['phase'] != 'betting':
            await interaction.response.send_message(
                "❌ No active betting phase. Wait for the next round (~60s).", ephemeral=True
            )
            return

        user_id = interaction.user.id
        if user_id in round_state['bets']:
            await interaction.response.send_message("❌ You already joined this round.", ephemeral=True)
            return

        if amount < MIN_BET or amount > MAX_BET:
            await interaction.response.send_message(
                f"❌ Bet must be between **{MIN_BET}** and **{MAX_BET:,}** tokens.", ephemeral=True
            )
            return

        balance = self.db.get_balance(user_id)
        if balance < amount:
            await interaction.response.send_message(
                f"❌ Insufficient balance. You have **{balance:,}** tokens.", ephemeral=True
            )
            return

        if auto_cashout is not None and auto_cashout < 1.01:
            auto_cashout = 1.01

        self.db.update_balance(user_id, -amount)
        round_state['bets'][user_id] = {
            'user': interaction.user,
            'amount': amount,
            'auto_cashout': auto_cashout,
            'cashed_out': False,
            'cashout_mult': None,
            'payout': 0,
        }

        ac_str = f" (auto-cashout at **{auto_cashout:.2f}x**)" if auto_cashout else ""
        await interaction.response.send_message(
            f"✅ Joined with **{amount:,}** tokens{ac_str}!", ephemeral=True
        )

    @app_commands.command(name="hxcrashstart", description="(Admin) Manually start a Crash round now")
    async def hxcrashstart(self, interaction: discord.Interaction):
        """Manually trigger a crash round — admin only."""
        admin_role_id = 1274834684429209695
        staff_role_id = 1153030265782927501
        user_role_ids = [r.id for r in interaction.user.roles]
        if admin_role_id not in user_role_ids and staff_role_id not in user_role_ids:
            await interaction.response.send_message("❌ Admin/Staff only.", ephemeral=True)
            return

        if self.current_round is not None:
            await interaction.response.send_message("❌ A round is already running.", ephemeral=True)
            return

        channel = self.bot.get_channel(CRASH_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message("❌ Crash channel not found.", ephemeral=True)
            return

        await interaction.response.send_message("🚀 Starting crash round...", ephemeral=True)
        self._round_task = asyncio.create_task(self._start_round(channel))


async def setup(bot: commands.Bot, db):
    cog = CrashCog(bot, db)
    await bot.add_cog(cog)
    logger.info("✅ CrashCog loaded")
