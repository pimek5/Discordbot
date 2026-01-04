# Railway Deployment Guide - Creator Bot

## Quick Setup Steps

### 1. Create Discord Bot
1. Go to https://discord.com/developers/applications
2. Click "New Application" → Name it "Creator Bot"
3. Go to "Bot" tab → Click "Add Bot"
4. Copy the **Token** (you'll need this)
5. Enable these Privileged Gateway Intents:
   - ✅ SERVER MEMBERS INTENT
   - ✅ MESSAGE CONTENT INTENT
6. Go to "OAuth2" → "URL Generator"
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Use Slash Commands`
7. Copy the generated URL and invite bot to your server

### 2. Create Railway Service
1. Go to your Railway project (same project as main bot)
2. Click "+ New" → "GitHub Repo"
3. Select your `Discordbot` repository
4. Click "Add Service"

### 3. Configure Service
In the new service settings:

**Environment Variables:**
```env
CREATOR_BOT_TOKEN=your_discord_bot_token_here
GUILD_ID=your_server_id
CREATOR_NOTIFICATION_CHANNEL_ID=channel_id_for_notifications
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

**Settings:**
- Root Directory: `/`
- Build Command: `pip install -r creator_requirements.txt`
- Start Command: `python creator_bot.py`

**OR** use Procfile:
- Create variable: `PROCFILE` = `Procfile.creator`

### 4. Link Database
1. In Railway project, click your PostgreSQL service
2. Copy the `DATABASE_URL` variable reference
3. In Creator Bot service, add:
   ```
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   ```
   This shares the database with your main bot!

### 5. Get Channel ID
In Discord (with Developer Mode ON):
1. Right-click the channel where you want notifications
2. Click "Copy Channel ID"
3. Use this for `CREATOR_NOTIFICATION_CHANNEL_ID`

### 6. Deploy
1. Click "Deploy" in Railway
2. Watch logs for "✅ Creator Bot logged in"
3. Bot should appear online in Discord

## Testing

1. Run `/creator add url:https://runeforge.dev/users/p1mek`
2. Check database for new tables: `creators`, `mods`, `notification_log`
3. Wait 5 minutes or restart bot to trigger first check
4. Notifications should appear in your specified channel

## Important Notes

⚠️ **HTML Selectors Need Updating!**

The web scraping code uses placeholder selectors. You MUST:

1. Open RuneForge profile page in browser
2. Right-click → Inspect Element
3. Find CSS selectors for:
   - Rank, mods count, downloads, views, followers
   - User mod cards
4. Update `creator_scraper.py` with real selectors

Same for Divine Skins!

## Cost
- Free tier should handle this easily
- Bot checks every 5 minutes
- Minimal database usage
- Shares resources with main bot

## Environment Variables Summary

| Variable | Example | Where to Get |
|----------|---------|--------------|
| `CREATOR_BOT_TOKEN` | `MTIzNDU2...` | Discord Developer Portal |
| `GUILD_ID` | `1234567890` | Right-click server → Copy ID |
| `CREATOR_NOTIFICATION_CHANNEL_ID` | `9876543210` | Right-click channel → Copy ID |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Reference from PostgreSQL service |

## Troubleshooting

**Bot offline?**
- Check Railway logs for errors
- Verify `CREATOR_BOT_TOKEN` is correct
- Check bot is invited to server

**No notifications?**
- Verify `CREATOR_NOTIFICATION_CHANNEL_ID`
- Check bot has permissions in channel
- Look for scraping errors in logs

**Database errors?**
- Ensure `DATABASE_URL` is linked correctly
- Tables auto-create on first run
- Check PostgreSQL service is running

**Scraping fails?**
- Update HTML selectors in `creator_scraper.py`
- Check if websites changed structure
- Test URLs manually in browser

---

Need help? Check CREATOR_BOT_README.md for full documentation!
