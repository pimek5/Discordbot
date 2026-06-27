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
  - Dealer stands on all 17s (S17 — standard European rule)
  - Bust = instant loss
  - Tie = push (bet refunded)
"""

import asyncio
import io
import random
import logging
from typing import Optional, Dict

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("hexbet.blackjack")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_BET = 10
MAX_BET = 50_000

BJ_CHANNEL_ID = 1520475228323708978

SUITS  = ["♠", "♥", "♦", "♣"]
RANKS  = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
VALUES = {"A": 11, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
          "8": 8, "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10}

SUIT_COLOR = {"♠": (20, 20, 20), "♣": (20, 20, 20),
              "♥": (200, 30, 30), "♦": (200, 30, 30)}

# Card dimensions
CARD_W, CARD_H = 72, 100
CARD_GAP       = 8
CARD_RADIUS    = 8
BG_COLOR       = (30, 32, 40)   # dark background for the image

# Colour palette (embed hex)
COLOR_PLAYING = 0x3498DB
COLOR_WIN     = 0x2ECC71
COLOR_LOSE    = 0xE74C3C
COLOR_PUSH    = 0x95A5A6
COLOR_BJ      = 0xF1C40F


# ---------------------------------------------------------------------------
# Card image renderer
# ---------------------------------------------------------------------------

def _get_font(size: int) -> ImageFont.ImageFont:
    """Load a font, fall back to PIL default."""
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            pass
    return ImageFont.load_default(size=size)


def _draw_card(draw: ImageDraw.ImageDraw, x: int, y: int,
               rank: str, suit: str, hidden: bool = False):
    """Draw a single card at position (x, y)."""
    r = CARD_RADIUS
    box = [x, y, x + CARD_W, y + CARD_H]

    if hidden:
        # Card back — dark blue with pattern
        draw.rounded_rectangle(box, radius=r, fill=(40, 60, 140), outline=(80, 100, 180), width=2)
        # Simple cross-hatch lines
        for i in range(0, CARD_W, 8):
            draw.line([(x+i, y), (x+i, y+CARD_H)], fill=(50, 75, 160), width=1)
        for j in range(0, CARD_H, 8):
            draw.line([(x, y+j), (x+CARD_W, y+j)], fill=(50, 75, 160), width=1)
        draw.rounded_rectangle(box, radius=r, fill=None, outline=(120, 150, 220), width=2)
        return

    # Card face — white background
    draw.rounded_rectangle(box, radius=r, fill=(255, 255, 255), outline=(180, 180, 180), width=1)

    color = SUIT_COLOR.get(suit, (20, 20, 20))

    # Top-left: rank + suit small
    f_small = _get_font(14)
    f_rank  = _get_font(18)
    f_suit  = _get_font(30)

    draw.text((x + 4, y + 2),  rank, fill=color, font=f_rank)
    draw.text((x + 4, y + 22), suit, fill=color, font=f_small)

    # Centre suit
    suit_w = draw.textlength(suit, font=f_suit)
    draw.text((x + (CARD_W - suit_w) / 2, y + 32), suit, fill=color, font=f_suit)

    # Bottom-right (rotated via canvas flip trick)
    f_br = _get_font(13)
    br_text = f"{rank}{suit}"
    br_w = draw.textlength(br_text, font=f_br)
    draw.text((x + CARD_W - br_w - 4, y + CARD_H - 18), br_text, fill=color, font=f_br)


def render_table(dealer_hand: list, player_hand: list,
                 hide_dealer_second: bool = False) -> io.BytesIO:
    """
    Render dealer + player hands side-by-side onto a dark background.
    Returns a BytesIO PNG ready for Discord file upload.
    """
    label_h   = 22
    row_h     = CARD_H + label_h + 6
    padding   = 12
    max_cards = max(len(dealer_hand), len(player_hand), 1)
    img_w     = padding * 2 + max_cards * (CARD_W + CARD_GAP) - CARD_GAP
    img_h     = padding * 2 + row_h * 2

    img  = Image.new("RGB", (img_w, img_h), BG_COLOR)
    draw = ImageDraw.Draw(img)
    f_label = _get_font(14)

    # Dealer row
    draw.text((padding, padding), "DEALER", fill=(180, 180, 180), font=f_label)
    for i, card in enumerate(dealer_hand):
        cx = padding + i * (CARD_W + CARD_GAP)
        cy = padding + label_h
        _draw_card(draw, cx, cy, card["rank"], card["suit"],
                   hidden=(i == 1 and hide_dealer_second))

    # Player row
    py_start = padding + row_h
    draw.text((padding, py_start), "YOU", fill=(180, 220, 255), font=f_label)
    for i, card in enumerate(player_hand):
        cx = padding + i * (CARD_W + CARD_GAP)
        cy = py_start + label_h
        _draw_card(draw, cx, cy, card["rank"], card["suit"])

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


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
    """Dealer stands on all 17s (S17 rule — standard European blackjack)."""
    while hand_value(hand) < 17:
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
        inline=True,
    )
    embed.add_field(
        name=f"👤 You  — bet: **{state['bet']:,}** 💰",
        value=hand_label(state["player"]),
        inline=True,
    )
    balance = state.get("balance_after_bet", 0)
    embed.set_footer(text=f"Balance after bet: {balance:,} tokens")
    embed.set_image(url="attachment://table.png")
    return embed


def build_result_embed(state: dict) -> tuple:
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
        inline=True,
    )
    embed.add_field(
        name=f"👤 You  — bet: **{state['bet']:,}** 💰",
        value=hand_label(state["player"]),
        inline=True,
    )
    new_bal = state.get("final_balance", 0)
    change  = f"+{profit:,}" if profit >= 0 else f"{profit:,}"
    embed.set_footer(text=f"Balance: {new_bal:,} tokens  ({change})")
    embed.set_image(url="attachment://table.png")
    return embed, outcome, payout, profit


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
# Lobby view + bet modal (for /hxbjstart channel embed)
# ---------------------------------------------------------------------------

class BetModal(discord.ui.Modal, title="🃏 Place Your Bet"):
    amount_input = discord.ui.TextInput(
        label=f"Bet Amount (tokens)",
        placeholder=f"Enter amount ({MIN_BET}–{MAX_BET:,})",
        min_length=1,
        max_length=10,
    )

    def __init__(self, cog: "BlackjackCog"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.amount_input.value.replace(",", "").replace(" ", "")
        try:
            amount = int(raw)
        except ValueError:
            await interaction.response.send_message("❌ Invalid amount.", ephemeral=True)
            return
        await self.cog.start_game(interaction, amount, followup=False)


class LobbyView(discord.ui.View):
    """Persistent 'Play Blackjack' button posted in the BJ channel."""

    def __init__(self, cog: "BlackjackCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="🃏 Play Blackjack",
        style=discord.ButtonStyle.success,
        custom_id="bj_lobby_play",
    )
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BetModal(self.cog))


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
        # Re-register persistent lobby view so buttons survive bot restart
        self.bot.add_view(LobbyView(self))

    # ------------------------------------------------------------------
    # Channel guard — delete regular messages in BJ channel

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.id != BJ_CHANNEL_ID:
            return
        if message.author.bot:
            return
        try:
            await message.delete()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # /hxbjstart — post the lobby embed in the BJ channel

    @app_commands.command(name="blackjack", description="Post the Blackjack lobby in the BJ channel")
    async def hxbjstart(self, interaction: discord.Interaction):
        channel = self.bot.get_channel(BJ_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message("❌ BJ channel not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🃏 HEXBET Blackjack",
            description=(
                "Press **🃏 Play Blackjack** to start a game against the dealer!\n\n"
                f"**Min bet:** {MIN_BET:,} tokens  |  **Max bet:** {MAX_BET:,} tokens\n\n"
                "**Rules:**\n"
                "• Blackjack pays **3:2**\n"
                "• Dealer stands on all 17s\n"
                "• Double Down available on first two cards"
            ),
            color=COLOR_PLAYING,
        )
        embed.set_footer(text="Each player plays independently against the dealer.")

        view = LobbyView(self)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(
            f"✅ Blackjack lobby posted in <#{BJ_CHANNEL_ID}>!", ephemeral=True
        )

    # ------------------------------------------------------------------
    # Helpers

    def _playing_file(self, state: dict) -> discord.File:
        buf = render_table(state["dealer"], state["player"], hide_dealer_second=True)
        return discord.File(buf, filename="table.png")

    def _result_file(self, state: dict) -> discord.File:
        buf = render_table(state["dealer"], state["player"], hide_dealer_second=False)
        return discord.File(buf, filename="table.png")

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
            f = self._result_file(state)
            if followup:
                await interaction.followup.send(embed=embed, file=f, view=view)
            else:
                await interaction.response.send_message(embed=embed, file=f, view=view)
            return

        can_double = balance_after >= bet
        embed = build_playing_embed(state)
        view  = BlackjackPlayingView(self, user_id, can_double)
        f = self._playing_file(state)

        if followup:
            msg = await interaction.followup.send(embed=embed, file=f, view=view)
        else:
            await interaction.response.send_message(embed=embed, file=f, view=view)
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
            f = self._result_file(state)
            await interaction.response.edit_message(embed=embed, attachments=[f], view=view)
            return

        can_double = (
            not state["doubled"]
            and state["balance_after_bet"] >= state["bet"]
        )
        embed = build_playing_embed(state)
        view  = BlackjackPlayingView(self, user_id, can_double)
        f = self._playing_file(state)
        await interaction.response.edit_message(embed=embed, attachments=[f], view=view)

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
        f = self._result_file(state)
        await interaction.response.edit_message(embed=embed, attachments=[f], view=view)

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

        # Draw exactly one card, then dealer plays
        state["player"].append(state["deck"].pop())
        dealer_play(state["dealer"], state["deck"])
        _, _, payout, _ = calculate_result(state["player"], state["dealer"], state["bet"])
        if payout:
            self.db.update_balance(user_id, payout)
        state["final_balance"] = self.db.get_balance(user_id)
        embed, outcome, payout, profit = build_result_embed(state)
        del self.games[user_id]
        view = BlackjackResultView(self, user_id, state["bet"] // 2)
        f = self._result_file(state)
        await interaction.response.edit_message(embed=embed, attachments=[f], view=view)


# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot, db):
    cog = BlackjackCog(bot, db)
    await bot.add_cog(cog)
    logger.info("✅ BlackjackCog loaded")
