# Discord Rate Limit (429) - Fix Guide

## What Happened
Your bot hit Discord's global rate limit (429 error), meaning it made too many API requests in a short time.

## Common Causes
1. **Multiple bot instances running** - Most common cause
2. **Restart loop** - Bot crashes and restarts too quickly
3. **Spam requests** - Too many API calls before the crash

## Immediate Actions

### 1. Stop All Bot Instances
```bash
# On Railway:
# - Go to your project dashboard
# - Click on the main bot service
# - Click "Stop" or "Redeploy" (don't just redeploy - STOP first)
# - Wait 5-10 minutes before restarting
```

### 2. Check for Multiple Deployments
- Verify you only have ONE instance of the main bot running
- Check if you accidentally deployed multiple times
- Make sure you don't have the bot running locally AND on Railway

### 3. Wait for Rate Limit to Clear
Discord's global rate limits typically clear after:
- **5-10 minutes** for minor violations
- **Up to 1 hour** for severe violations

## Code Fix Applied
I've updated `bot.py` to:
- Detect 429 errors specifically
- Wait **5 minutes** (300 seconds) before retrying after a rate limit
- Provide clear error messages about multiple instances
- Prevent rapid restart loops

## Prevention
1. **Never run multiple instances** of the same bot token
2. **Use proper error handling** (now implemented)
3. **Monitor your deployments** - only one should be active
4. **Don't spam redeploy** - wait for previous instances to fully stop

## Next Steps
1. **STOP** all bot instances on Railway
2. **WAIT** 10 minutes
3. **Deploy ONCE** and monitor logs
4. If still getting 429, wait another 10-15 minutes

## Checking Logs on Railway
```bash
# Look for these messages:
✅ Bot connected as [name] (ID: ...)  # Good - bot started
⚠️ Rate limited (429)                 # Bad - still rate limited
⏳ Waiting 300 seconds...              # Good - waiting properly
```

## Emergency: If Still Failing
If after 1 hour you still get 429:
1. Contact Discord support (very rare)
2. Check Discord's status page: https://discordstatus.com
3. Verify your bot token is not compromised
