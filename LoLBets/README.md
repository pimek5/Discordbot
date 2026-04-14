# LoLBets

LoLBets is a dedicated multi-server League of Legends betting bot scaffolded from the current HEXBET stack.

## Goal

Build a more professional, scalable betting bot that can:
- operate globally across many Discord servers
- keep per-server betting configuration
- support server-specific streamer and creator bets
- reuse the proven HEXBET core while evolving into its own brand and feature set

## Current State

This folder is a dedicated bot entrypoint and deployment scaffold.
Right now `LoLBets` boots its own Discord bot process and loads the existing HEXBET command + config system from the tracker stack.

That means you now have:
- separate bot token support via `LOLBETS_BOT_TOKEN`
- separate Railway start target
- separate folder layout like GLaDOS
- a safe base to begin migrating HEXBET into a standalone LoLBets architecture

## Files

- `lolbets_bot.py` - main bot entrypoint
- `.env.example` - environment variables
- `requirements.txt` - Python dependencies
- `railway.toml` - Railway deployment config

## Environment

Required variables:
- `LOLBETS_BOT_TOKEN`
- `RIOT_API_KEY`
- `DATABASE_URL`

Optional variables:
- `DISCORD_GUILD_ID`
- `LOLBETS_PRIMARY_GUILD_ID`
- `LOLBETS_DEFAULT_BET_CHANNEL_ID`
- `LOLBETS_DEFAULT_LEADERBOARD_CHANNEL_ID`
- `LOLBETS_DEFAULT_LOGS_CHANNEL_ID`

## Run locally

```bash
python LoLBets/lolbets_bot.py
```

## Next step

The logical next phase is to copy or extract HEXBET internals into a dedicated `LoLBets/core` structure so the new bot stops depending on `tracker/HEXBET` directly.
