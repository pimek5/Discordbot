# Creator Bot - RuneForge & Divine Skins Monitor

Discord bot that monitors RuneForge and Divine Skins for new mods/skins from tracked creators.

## Features

- 🔍 **Automatic Monitoring** - Checks every 5 minutes for new/updated content
- 👤 **Creator Tracking** - Track multiple creators across both platforms
- 📊 **Profile Stats** - View detailed creator statistics
- 🔔 **Instant Notifications** - Get notified when tracked creators post or update content
- 🌐 **Multi-Platform** - Supports both RuneForge.dev and DivineSkins.gg

## Commands

### `/creator add <url> [user]`
Add a creator to track for new mods/skins.

**Examples:**
```
/creator add url:https://runeforge.dev/users/p1mek
/creator add url:https://divineskins.gg/pimek user:@someone
```

### `/creator profile <platform> [user]`
View a creator's profile and statistics.

**Examples:**
```
/creator profile platform:runeforge
/creator profile platform:divineskins user:@someone
```

### `/creator remove <platform> [user]`
Stop tracking a creator.

**Examples:**
```
/creator remove platform:runeforge
/creator remove platform:divineskins user:@someone
```

### `/creator list`
List all tracked creators on the server.

### `/creator refresh <platform> <user>` (Admin only)
Manually refresh a creator's profile data.

## Setup on Railway

### Step 1: Create New Service
1. Go to Railway dashboard
2. Click "+ New" → "Empty Service"
3. Name it "Creator Bot"

### Step 2: Connect Repository
1. In service settings, connect your GitHub repository
2. Set root directory to `/` (same repo as main bot)

### Step 3: Environment Variables
Add these in Railway service settings:

```env
# Discord Bot Token (create new bot on Discord Developer Portal)
CREATOR_BOT_TOKEN=your_bot_token_here

# Server ID
GUILD_ID=your_guild_id

# Notification Channel ID (where bot posts updates)
CREATOR_NOTIFICATION_CHANNEL_ID=your_channel_id

# Database URL (use same PostgreSQL as main bot)
DATABASE_URL=postgresql://...
```

### Step 4: Deployment Settings
1. Build Command: `pip install -r creator_requirements.txt`
2. Start Command: `python creator_bot.py`
3. Or use Procfile: set to use `Procfile.creator`

### Step 5: Deploy
Click "Deploy" and wait for bot to start.

## Database Tables

The bot creates these tables automatically:

### `creators`
Stores tracked creator profiles.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| discord_user_id | BIGINT | Discord user ID |
| platform | VARCHAR(20) | 'runeforge' or 'divineskins' |
| profile_url | TEXT | Profile URL |
| username | VARCHAR(255) | Creator username |
| rank | VARCHAR(50) | Creator rank/role |
| total_mods | INTEGER | Number of mods/skins |
| total_downloads | BIGINT | Total downloads |
| total_views | BIGINT | Total views |
| followers | INTEGER | Follower count |
| following | INTEGER | Following count |
| joined_date | TEXT | Account creation date |
| last_updated | TIMESTAMP | Last profile update |
| added_at | TIMESTAMP | When added to tracking |

### `mods`
Stores tracked mods/skins.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| creator_id | INTEGER | Foreign key to creators |
| mod_id | TEXT | Mod/skin ID from platform |
| mod_name | TEXT | Mod/skin name |
| mod_url | TEXT | Direct link |
| platform | VARCHAR(20) | 'runeforge' or 'divineskins' |
| updated_at | TEXT | Last update timestamp |
| notified_at | TIMESTAMP | When notification was sent |
| is_update | BOOLEAN | True if update, false if new |

### `notification_log`
Logs all notifications sent.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| creator_id | INTEGER | Foreign key to creators |
| mod_id | TEXT | Mod/skin ID |
| action | VARCHAR(50) | 'Posted' or 'Updated' |
| notified_at | TIMESTAMP | When sent |

## How It Works

### Monitoring Loop
1. Bot checks every 5 minutes (configurable in `creator_bot.py`)
2. For each tracked creator:
   - Fetches their latest mods/skins from platform
   - Compares with database records
   - If new mod found → sends "Posted" notification
   - If mod updated → sends "Updated" notification
3. Waits 2 seconds between creators (rate limiting)

### Web Scraping
The bot uses `aiohttp` and `BeautifulSoup` to scrape profile data:

- **RuneForge**: Scrapes `/users/{username}` and `/users/{username}/mods`
- **Divine Skins**: Scrapes `/{username}` and `/{username}/skins`

⚠️ **Important**: The HTML selectors in `creator_scraper.py` are templates. You need to:
1. Inspect the actual HTML of RuneForge and Divine Skins
2. Update the CSS selectors to match the real page structure
3. Test with real profiles

### Notification Format
```
🔧 Posted new mod!
@p1mek posted new mod: Zaahen as Old Aatrox

Platform: RuneForge
Link: [View Zaahen as Old Aatrox](https://runeforge.dev/mods/...)
```

## Customization

### Change Check Interval
In `creator_bot.py`, line ~70:
```python
@tasks.loop(minutes=5)  # Change this number
async def monitor_creators(self):
```

### Update HTML Selectors
In `creator_scraper.py`, update these methods:
- `RuneForgeScraper.get_profile_data()` - Profile stats
- `RuneForgeScraper.get_user_mods()` - User's mods
- `DivineSkinsScraper.get_profile_data()` - Profile stats
- `DivineSkinsScraper.get_user_skins()` - User's skins

Use browser DevTools to find correct CSS selectors.

### Change Notification Style
In `creator_bot.py`, method `send_notification()` - customize embed colors, format, fields, etc.

## Bot Permissions

Required Discord permissions:
- ✅ Send Messages
- ✅ Embed Links
- ✅ Use Slash Commands
- ✅ Read Message History

## Troubleshooting

### Bot not posting notifications
1. Check `CREATOR_NOTIFICATION_CHANNEL_ID` is correct
2. Verify bot has permissions in that channel
3. Check Railway logs for errors

### "Failed to fetch profile data"
1. Verify the URL format is correct
2. Check if website structure changed (update selectors)
3. Look for rate limiting issues in logs

### Database errors
1. Ensure `DATABASE_URL` is set correctly
2. Check PostgreSQL connection in Railway
3. Tables should auto-create on first run

### Monitoring not starting
1. Check bot is "Ready" in logs
2. Verify `@tasks.loop` is not commented out
3. Look for errors in Railway logs

## Notes

- ⚠️ **Web scraping is fragile** - If RuneForge or Divine Skins update their HTML, you'll need to update the selectors
- 💡 Consider implementing caching to reduce unnecessary requests
- 🔄 The bot shares the PostgreSQL database with your main bot (different tables)
- 📊 You can query the database to see stats, history, etc.

## Support

For issues or questions, check:
1. Railway deployment logs
2. Bot console output
3. Database connection status
4. Website HTML structure (if scraping fails)

---

Made by p1mek • Part of the HEXRTBRXEN Bot ecosystem
