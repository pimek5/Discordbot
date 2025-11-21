# 🚂 Railway Deployment Guide - Tracker Bot

## Prerequisites
- GitHub account with Discordbot repository
- Railway account (railway.app)
- Discord Bot Token (separate from main bot)
- Riot API Key

## Step 1: Create Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create **New Application** → Name it "Tracker Bot"
3. Go to **Bot** section → Click **Add Bot**
4. Enable these **Privileged Gateway Intents**:
   - ✅ Presence Intent
   - ✅ Server Members Intent
   - ✅ Message Content Intent
5. Copy **Bot Token** (save for later)

## Step 2: Invite Bot to Server

Build invite URL:
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=2415960128&scope=bot%20applications.commands
```

Permissions needed:
- Read Messages/View Channels
- Send Messages
- Embed Links
- Attach Files
- Read Message History
- Add Reactions
- Create Public Threads
- Send Messages in Threads
- Manage Threads

## Step 3: Railway Project Setup

### A. Create New Project

1. Go to [Railway Dashboard](https://railway.app/dashboard)
2. Click **New Project**
3. Select **Deploy from GitHub repo**
4. Choose your **Discordbot** repository
5. Name service: `tracker-bot`

### B. Configure Service

In Service Settings:
- **Root Directory**: `/tracker`
- **Build Command**: (auto-detected from railway.toml)
- **Start Command**: (auto-detected from railway.toml)

## Step 4: Environment Variables

Add these variables in Railway Service Settings:

```env
TRACKER_BOT_TOKEN=your_discord_bot_token_here
DISCORD_GUILD_ID=your_guild_id_here
RIOT_API_KEY=your_riot_api_key_here
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

### Getting Values:

**TRACKER_BOT_TOKEN**:
- From Discord Developer Portal → Bot section

**DISCORD_GUILD_ID**:
1. Enable Developer Mode in Discord (Settings → Advanced)
2. Right-click your server → Copy ID

**RIOT_API_KEY**:
- From [Riot Developer Portal](https://developer.riotgames.com/)
- Personal API Key (24h expiry) or Production Key

**DATABASE_URL**:
- If you have existing Postgres service: `${{Postgres.DATABASE_URL}}`
- Otherwise, add new Postgres service to project

## Step 5: Database Setup

If using **shared database** with main bot:
1. Link existing Postgres service
2. Tables will be created automatically on first run

If creating **new database**:
1. Click **New** → **Database** → **Postgres**
2. Link to tracker-bot service
3. Bot will initialize tables on startup

### Tables Created:
- `user_balance` - Betting balances
- `active_bets` - Current bets
- `tracking_subscriptions` - Always On users
- `tracked_pros` - Pro player database

## Step 6: Deploy

1. Push changes to GitHub:
```bash
git add tracker/
git commit -m "feat: add tracker bot"
git push
```

2. Railway auto-deploys
3. Check logs: Service → **View Logs**

### Expected Log Output:
```
✅ Tracker Bot logged in as Tracker Bot (ID: ...)
✅ Database connection established
✅ Commands synced to guild ...
✅ Tracker commands loaded
```

## Step 7: Test Commands

In Discord:
```
/track
/trackpros player_name:Faker
/balance
/betleaderboard
```

## Troubleshooting

### Bot Offline
- Check Railway logs for errors
- Verify `TRACKER_BOT_TOKEN` is correct
- Check bot has proper intents enabled

### Commands Not Showing
- Wait 1-2 minutes for sync
- Verify `DISCORD_GUILD_ID` is correct
- Try re-inviting bot with correct permissions

### Database Errors
- Check `DATABASE_URL` is set
- Verify Postgres service is running
- Check connection pool settings

### Riot API Errors
- Verify `RIOT_API_KEY` is valid
- Check API key hasn't expired (24h for development keys)
- Apply for Production Key if needed

## Scaling Options

### Resource Limits
Railway default:
- 512 MB RAM
- 1 vCPU
- Sufficient for ~50-100 concurrent trackers

### Upgrade if needed:
- Settings → Resources
- Adjust RAM/CPU as needed

### Auto-Restart
Configured in `railway.toml`:
```toml
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

## Monitoring

### Logs
- Real-time: Railway Dashboard → Logs
- Download: Export logs for analysis

### Metrics
- CPU Usage
- Memory Usage
- Network I/O

### Health Checks
Bot logs these on startup:
- ✅ Database connection
- ✅ Commands synced
- ✅ Tracker loop started

## Multiple Environments

### Development
```env
TRACKER_BOT_TOKEN=dev_bot_token
DISCORD_GUILD_ID=dev_guild_id
```

### Production
```env
TRACKER_BOT_TOKEN=prod_bot_token
DISCORD_GUILD_ID=prod_guild_id
```

Deploy separate Railway services for each.

## Cost Estimate

Railway Pricing (as of 2024):
- **Hobby Plan**: $5/month
  - $5 included usage
  - Sufficient for small Discord server
  
- **Pro Plan**: $20/month
  - More resources
  - Priority support

**Shared Database**: No extra cost if linking to existing Postgres

## Support

- **Railway Docs**: [docs.railway.app](https://docs.railway.app)
- **Discord.py Docs**: [discordpy.readthedocs.io](https://discordpy.readthedocs.io)
- **Riot API Docs**: [developer.riotgames.com](https://developer.riotgames.com)

## Next Steps

1. ✅ Deploy tracker bot
2. Test all commands
3. Invite users to try betting system
4. Monitor performance
5. Scale as needed

Happy tracking! 🎮
