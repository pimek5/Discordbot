"""
HEXBET Blackjack
================
Standard blackjack against the dealer, using HEXBET token balance.

Commands:
  /hxblackjack <amount>  — start a new game

Buttons (shown during game):
  🃏 Hit        — draw another card
  ✋ Stand      — end your turn, dealer plays
  ✌️ Double     — double bet, draw exactly one card, then stand
  🔄 New Game  — start again after game ends (same bet)

Rules:
  - Blackjack (21 on first 2 cards) pays 3:2
  - Dealer hits on soft 16, stands on hard 17+
  - Bust = instant loss
  - Tie = push (bet refunded)
"""

import asyncio
import random
import logging
from typing import Optional, Dict

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("hexbet.blackjack")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_BET = 10
MAX_BET = 50_000

SUITS  = ["♠", "♥", "♦", "♣"]
RANKS  = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
VALUES = {"A": 11, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
          "8": 8, "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10}

# Colour palette
COLOR_PLAYING = 0x3498DB
COLOR_WIN     = 0x2ECC71
COLOR_LOSE    = 0xE74C3C
COLOR_PUSH    = 0x95A5A6
COLOR_BJ      = 0xF1C40F   # gold for blackjack


# ---------------------------------------------------------------------------
# Card helpers
# ---------------------------------------------------------------------------

def new_deck() -> list:
    deck = [{"rank": r, "suit": s} for s in SUITS for r in RANKS] * 2
    random.shuffle(deck)
    return deck


def card_str(card: dict, hidden: bool = False) -> str:
    if hidden:
        return "🂠"
    return f"{card['rank']}{card['suit']}"


def hand_str(hand: list, hide_second: bool = False) -> str:
    cards = []
    for i, c in enumerate(hand):
        cards.append(card_str(c, hidden=(i == 1 and hide_second)))
    return "  ".join(cards)


def hand_value(hand: list) -> int:
    total = 0
    aces  = 0
    for c in hand:
        v = VALUES[c["rank"]]
        if c["rank"] == "A":
            aces += 1
        total += v
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total


def is_blackjack(hand: list) -> bool:
    return len(hand) == 2 and hand_value(hand) == 21


def is_bust(hand: list) -> bool:
    return hand_value(hand) > 21


def hand_label(hand: list, hide_second: bool = False) -> str:
    if hide_second:
        v = VALUES[hand[0]["rank"]]
        return f"{hand_str(hand, hide_second=True)}  `={v}+?`"
    v = hand_value(hand)
    soft = (
        any(c["rank"] == "A" for c in hand)
        and v <= 21
        and v - 10 >= 1
        and sum(VALUES[c["rank"]] for c in hand) != v
    )
    label = f"Soft {v}" if soft else str(v)
    return f"{hand_str(hand)}  `={label}`"


# ---------------------------------------------------------------------------
# Dealer AI
# ---------------------------------------------------------------------------

def dealer_play(hand: list, deck: list):
    """Dealer hits on soft ≤16, stands on hard 17+."""
    while True:
        v = hand_value(hand)
        if v >= 17:
            break
        # soft 17 check — dealer hits soft 17
        total_raw = sum(VALUES[c["rank"]] for c in hand)
        aces = sum(1 for c in hand if c["rank"] == "A")
        is_soft = aces > 0 and (total_raw - 10 * (aces - (total_raw - v) // 10)) != v
        if v == 17 and is_soft:
            pass  # hit soft 17
        elif v >= 17:
            break
        hand.append(deck.pop())


# ---------------------------------------------------------------------------
# Result calculation
# ---------------------------------------------------------------------------

def calculate_result(player_hand, dealer_hand, bet: int) -> tuple[str, int, int, str]:
    """
    Returns (outcome, payout, profit, label).
    outcome: 'blackjack' | 'win' | 'push' | 'lose'
    payout: total tokens returned to player (0 if they lose)
    profit: change in balance (may be negative)
    """
    pv = hand_value(player_hand)
    dv = hand_value(dealer_hand)
    pbj = is_blackjack(player_hand)
    dbj = is_blackjack(dealer_hand)

    if pbj and dbj:
        return "push", bet, 0, "🤝 Push — both Blackjack"
    if pbj:
        payout = bet + int(bet * 1.5)
        return "blackjack", payout, int(bet * 1.5), f"🎉 Blackjack! (+{int(bet*1.5):,})"
    if dbj:
        return "lose", 0, -bet, "💀 Dealer Blackjack"
    if is_bust(player_hand):
        return "lose", 0, -bet, f"💥 Bust! ({pv})"
    if is_bust(dealer_hand):
        return "win", bet * 2, bet, f"✅ Dealer bust ({dv}) — You win!"
    if pv > dv:
        return "win", bet * 2, bet, f"✅ {pv} vs {dv} — You win!"
    if pv < dv:
        return "lose", 0, -bet, f"❌ {pv} vs {dv} — Dealer wins"
    return "push", bet, 0, f"🤝 Push ({pv})"


# ---------------------------------------------------------------------------
# Embed builders
# ---------------------------------------------------------------------------

def build_playing_embed(state: dict) -> discord.Embed:
    pv = hand_value(state["player"])
    embed = discord.Embed(
        title="🃏 HEXBET Blackjack",
        color=COLOR_PLAYING,
    )
    embed.add_field(
        name="🏠 Dealer",
        value=hand_label(state["dealer"], hide_second=True),
        inline=False,
    )
    embed.add_field(
        name=f"👤 You  (bet: {state['bet']:,} 💰)",
        value=hand_label(state["player"]),
        inline=False,
    )
    balance = state.get("balance_after_bet", 0)
    embed.set_footer(text=f"Balance after bet: {balance:,} tokens")
    return embed


def build_result_embed(state: dict) -> discord.Embed:
    outcome, payout, profit, label = calculate_result(
        state["player"], state["dealer"], state["bet"]
    )
    color = {
        "blackjack": COLOR_BJ,
        "win":       COLOR_WIN,
        "push":      COLOR_PUSH,
        "lose":      COLOR_LOSE,
    }[outcome]

    embed = discord.Embed(title=f"🃏 HEXBET Blackjack — {label}", color=color)
    embed.add_field(
        name="🏠 Dealer",
        value=hand_label(state["dealer"]),
        inline=False,
    )
    embed.add_field(
        name=f"👤 You  (bet: {state['bet']:,} 💰)",
        value=hand_label(state["player"]),
        inline=False,
    )
    new_bal = state.get("final_balance", 0)
    change  = f"+{profit:,}" if profit >= 0 else f"{profit:,}"
    embed.set_footer(text=f"Balance: {new_bal:,} tokens  ({change})")
    return embed, outcome, payout, profit


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class BlackjackPlayingView(discord.ui.View):
    def __init__(self, cog: "BlackjackCog", user_id: int, can_double: bool):
        super().__init__(timeout=300)
        self.cog     = cog
        self.user_id = user_id
        if not can_double:
            # Remove double button dynamically
            for child in self.children:
                if getattr(child, "custom_id", "") == "bj_double":
                    child.disabled = True

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ This is not your game!", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="🃏 Hit", style=discord.ButtonStyle.primary, custom_id="bj_hit")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        await self.cog.do_hit(interaction)

    @discord.ui.button(label="✋ Stand", style=discord.ButtonStyle.secondary, custom_id="bj_stand")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        await self.cog.do_stand(interaction)

    @discord.ui.button(label="✌️ Double", style=discord.ButtonStyle.success, custom_id="bj_double")
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._guard(interaction):
            return
        await self.cog.do_double(interaction)


class BlackjackResultView(discord.ui.View):
    def __init__(self, cog: "BlackjackCog", user_id: int, bet: int):
        super().__init__(timeout=120)
        self.cog     = cog
        self.user_id = user_id
        self.bet     = bet

    @discord.ui.button(label="🔄 Play again (same bet)", style=discord.ButtonStyle.primary, custom_id="bj_again")
    async def play_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return
        await self.cog.start_game(interaction, self.bet, followup=False)


# ---------------------------------------------------------------------------
# BlackjackCog
# ---------------------------------------------------------------------------

class BlackjackCog(commands.Cog):

    def __init__(self, bot: commands.Bot, db):
        self.bot    = bot
        self.db     = db
        self.games: Dict[int, dict] = {}   # user_id → state

    # ------------------------------------------------------------------

    @app_commands.command(name="hxblackjack", description="Play Blackjack with your HEXBET tokens")
    @app_commands.describe(amount="Bet amount in tokens")
    async def hxblackjack(self, interaction: discord.Interaction, amount: int):
        await self.start_game(interaction, amount, followup=False)

    # ------------------------------------------------------------------

    async def start_game(self, interaction: discord.Interaction, bet: int, followup: bool = False):
        user_id = interaction.user.id

        if user_id in self.games:
            msg = "❌ You already have an active game! Finish it first."
            if followup:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        if bet < MIN_BET or bet > MAX_BET:
            msg = f"❌ Bet must be between **{MIN_BET:,}** and **{MAX_BET:,}** tokens."
            if followup:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        balance = self.db.get_balance(user_id)
        if balance < bet:
            msg = f"❌ Insufficient balance. You have **{balance:,}** tokens."
            if followup:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        # Deduct bet immediately
        self.db.update_balance(user_id, -bet)
        balance_after = balance - bet

        # Deal cards
        deck   = new_deck()
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]

        state = {
            "user_id":          user_id,
            "bet":              bet,
            "player":           player,
            "dealer":           dealer,
            "deck":             deck,
            "balance_after_bet": balance_after,
            "final_balance":    None,
            "doubled":          False,
        }
        self.games[user_id] = state

        # Check immediate blackjack
        if is_blackjack(player):
            dealer_play(dealer, deck)
            embed, outcome, payout, profit = build_result_embed(state)
            if payout:
                self.db.update_balance(user_id, payout)
            state["final_balance"] = self.db.get_balance(user_id)
            embed, outcome, payout, profit = build_result_embed(state)
            del self.games[user_id]
            view = BlackjackResultView(self, user_id, bet)
            if followup:
                await interaction.followup.send(embed=embed, view=view)
            else:
                await interaction.response.send_message(embed=embed, view=view)
            return

        can_double = balance_after >= bet  # enough for another bet
        embed = build_playing_embed(state)
        view  = BlackjackPlayingView(self, user_id, can_double)

        if followup:
            msg = await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)
            msg = await interaction.original_response()

        state["message"] = msg

    # ------------------------------------------------------------------

    async def do_hit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        state   = self.games.get(user_id)
        if not state:
            await interaction.response.send_message("❌ No active game found.", ephemeral=True)
            return

        state["player"].append(state["deck"].pop())

        if is_bust(state["player"]):
            # Player bust — game over
            dealer_play(state["dealer"], state["deck"])
            state["final_balance"] = self.db.get_balance(user_id)
            embed, outcome, payout, profit = build_result_embed(state)
            del self.games[user_id]
            view = BlackjackResultView(self, user_id, state["bet"])
            await interaction.response.edit_message(embed=embed, view=view)
            return

        can_double = (
            not state["doubled"]
            and state["balance_after_bet"] >= state["bet"]
        )
        embed = build_playing_embed(state)
        view  = BlackjackPlayingView(self, user_id, can_double)
        await interaction.response.edit_message(embed=embed, view=view)

    async def do_stand(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        state   = self.games.get(user_id)
        if not state:
            await interaction.response.send_message("❌ No active game found.", ephemeral=True)
            return

        dealer_play(state["dealer"], state["deck"])
        _, _, payout, _ = calculate_result(state["player"], state["dealer"], state["bet"])
        if payout:
            self.db.update_balance(user_id, payout)
        state["final_balance"] = self.db.get_balance(user_id)
        embed, outcome, payout, profit = build_result_embed(state)
        del self.games[user_id]
        view = BlackjackResultView(self, user_id, state["bet"])
        await interaction.response.edit_message(embed=embed, view=view)

    async def do_double(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        state   = self.games.get(user_id)
        if not state:
            await interaction.response.send_message("❌ No active game found.", ephemeral=True)
            return

        balance = self.db.get_balance(user_id)
        if balance < state["bet"]:
            await interaction.response.send_message(
                f"❌ Insufficient balance to double ({balance:,} tokens).", ephemeral=True
            )
            return

        # Double the bet
        self.db.update_balance(user_id, -state["bet"])
        state["balance_after_bet"] -= state["bet"]
        state["bet"] *= 2
        state["doubled"] = True

        # Draw exactly one card
        state["player"].append(state["deck"].pop())

        # Dealer plays regardless of bust
        dealer_play(state["dealer"], state["deck"])
        _, _, payout, _ = calculate_result(state["player"], state["dealer"], state["bet"])
        if payout:
            self.db.update_balance(user_id, payout)
        state["final_balance"] = self.db.get_balance(user_id)
        embed, outcome, payout, profit = build_result_embed(state)
        del self.games[user_id]
        view = BlackjackResultView(self, user_id, state["bet"] // 2)  # original bet for replay
        await interaction.response.edit_message(embed=embed, view=view)


# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot, db):
    cog = BlackjackCog(bot, db)
    await bot.add_cog(cog)
    logger.info("✅ BlackjackCog loaded")
