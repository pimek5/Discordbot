# Voting System - Setup Instructions

## Database Migration

Before using the voting commands, you need to run the database migration:

### Option 1: Using Railway CLI
```bash
railway run psql $DATABASE_URL -f migration_voting.sql
```

### Option 2: Direct PostgreSQL Connection
```bash
psql $DATABASE_URL -f migration_voting.sql
```

### Option 3: Manual SQL Execution
Connect to your PostgreSQL database and run the SQL from `migration_voting.sql`

## Commands Overview

### `/vote`
- **Usage:** `/vote champion1:Ahri champion2:Kassadin champion3:Rengar champion4:Vayne champion5:Akali`
- **Available to:** All users (in voting thread only)
- **Channel:** <#1331546029023166464> (voting thread)
- **Points:**
  - Server Boosters [1168616737692991499]: **2 points per champion** 💎
  - Regular users: **1 point per champion**

### `/votestart`
- **Usage:** `/votestart`
- **Available to:** Admin role [1153030265782927501]
- **Channel:** <#1331546029023166464> (voting thread)
- **Description:** Starts a new voting session with live leaderboard

### `/votestop`
- **Usage:** `/votestop`
- **Available to:** Admin role [1153030265782927501]
- **Channel:** <#1331546029023166464> (voting thread)
- **Description:** Ends the voting session and shows final results

## Features

✅ **Live Leaderboard**: Embed updates in real-time with each vote
✅ **Top 5 Podium**: Shows the top 5 champions with medals 🥇🥈🥉4️⃣5️⃣
✅ **All Champions Listed**: Champions outside top 5 are shown below
✅ **Point System**: Boosters get 2x points, regular users get 1x
✅ **Vote Changes**: Users can change their votes during active session
✅ **Champion Validation**: Only valid LoL champion names accepted
✅ **Thread Restriction**: Only works in designated voting thread
✅ **Admin Controls**: Only admins can start/stop voting

## How It Works

1. Admin uses `/votestart` in the voting thread
2. Bot creates an embed with empty leaderboard
3. Users vote with `/vote [5 champions]`
4. Embed updates automatically with each vote showing:
   - 🏆 Top 5 champions with current points
   - 📊 Other champions below top 5
   - Live vote counts and point totals
5. Admin uses `/votestop` to end voting
6. Final results are displayed with complete rankings

## Example Vote

```
/vote champion1:Ahri champion2:Kassadin champion3:Rengar champion4:Vayne champion5:Akali
```

Each champion in your list receives your point value (1 or 2 based on booster status).

## Notes

- You must vote for exactly 5 different champions
- Champion names must be exact (case-insensitive)
- You can change your vote anytime during active session
- Previous votes are replaced when you vote again
- Only one voting session can be active at a time per server
