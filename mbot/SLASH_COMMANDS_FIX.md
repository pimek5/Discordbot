# 🔧 Quick Fix - Slash Commands Not Showing

## Problem: Slash commands don't appear when typing `/`

### Solution 1: Re-invite bot with correct permissions (MOST COMMON)

1. **Go to [Discord Developer Portal](https://discord.com/developers/applications)**

2. **Select your bot application**

3. **Go to OAuth2 → URL Generator**

4. **Select SCOPES:**
   - ✅ `bot`
   - ✅ `applications.commands` ← **THIS IS CRITICAL!**

5. **Select BOT PERMISSIONS:**
   - ✅ Read Messages/View Channels
   - ✅ Send Messages
   - ✅ Embed Links
   - ✅ Attach Files
   - ✅ Connect
   - ✅ Speak
   - ✅ Use Voice Activity

6. **Copy the generated URL** (should look like: `https://discord.com/oauth2/authorize?client_id=...`)

7. **Open URL in browser** and add bot to your server again
   - You don't need to kick the bot first, just authorize again

8. **Wait 1-5 minutes** for Discord to sync commands

9. **Type `/` in Discord** - commands should appear!

---

### Solution 2: Check Railway logs

Make sure bot is running:
```
🎵 MBot logged in as [bot name]
Bot is on X servers
Slash commands synchronized
```

If you see errors, check:
- BOT_TOKEN is set correctly in Railway Variables
- No syntax errors in code

---

### Solution 3: Force sync (if still not working)

If commands still don't show after 5 minutes:

1. **Kick the bot from your server**
2. **Re-invite with the URL from Solution 1**
3. **Wait 2-3 minutes**
4. **Check Railway logs** for "Slash commands synchronized"

---

### Common Mistakes:

❌ **Missing `applications.commands` scope** - commands won't work at all
❌ **Not waiting** - Discord needs 1-5 minutes to sync
❌ **Privileged intents enabled** - disable MESSAGE CONTENT, PRESENCE, SERVER MEMBERS (not needed)
❌ **Bot not running** - check Railway logs

---

### Quick Test:

1. Type `/` in any channel
2. You should see a list of bot commands with the MBot icon
3. If you see commands from other bots but not MBot → re-invite with correct permissions

---

**Still not working?**

Send me Railway logs from the Deployments tab!
