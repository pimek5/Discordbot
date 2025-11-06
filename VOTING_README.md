# Voting System - Complete Guide

## Database Migration

Before using the voting commands, run both migrations:

### Step 1: Initial Setup
```bash
railway run psql $DATABASE_URL -f migration_voting.sql
```

### Step 2: Add Exclusions (NEW)
```bash
railway run psql $DATABASE_URL -f migration_voting_exclusions.sql
```

## Commands Overview

### `/vote` - Cast Your Vote
- **Usage:** `/vote champion1:Ahri champion2:Yasuo champion3:Rengar champion4:Vayne champion5:Akali`
- **Available to:** All users
- **Channel:** <#1331546029023166464> (voting thread only)
- **Points:**
  - Server Boosters [1168616737692991499]: **2 points per champion** 💎
  - Regular users: **1 point per champion**
- **Features:**
  - Vote for 5 different champions
  - Change your vote anytime during active session
  - Supports champion aliases (see below)

### `/votestart` - Start Voting Session
- **Usage:** `/votestart`
- **Available to:** Admin role [1153030265782927501]
- **Channel:** <#1331546029023166464>
- **Description:** 
  - Starts a new voting session with live leaderboard
  - **Auto-excludes top 5 champions from previous session**
  - Creates embed that updates in real-time

### `/votestop` - End Voting Session
- **Usage:** `/votestop`
- **Available to:** Admin role [1153030265782927501]
- **Channel:** <#1331546029023166464>
- **Description:** 
  - Ends the current voting session
  - Shows final results with complete rankings
  - Top 5 from this session will be auto-excluded next time

### `/voteexclude` - Manually Exclude Champions
- **Usage:** `/voteexclude champions:Ahri, Yasuo, Zed`
- **Available to:** Admin role [1153030265782927501]
- **Channel:** <#1331546029023166464>
- **Description:**
  - Manually exclude specific champions from current voting
  - Accepts multiple champions (comma-separated)
  - Supports champion aliases
  - Updates embed immediately

### `/voteinclude` - Remove Exclusion
- **Usage:** `/voteinclude champion:Ahri`
- **Available to:** Admin role [1153030265782927501]
- **Channel:** <#1331546029023166464>
- **Description:**
  - Remove a champion from exclusion list
  - Champion becomes votable again
  - Updates embed immediately

## Champion Aliases

The system supports common champion abbreviations and nicknames:

### Popular Aliases
- `asol` → Aurelion Sol
- `mf` → Miss Fortune
- `lb` → LeBlanc
- `tf` → Twisted Fate
- `lee` → Lee Sin
- `yas` → Yasuo
- `kass` → Kassadin
- `cait` → Caitlyn
- `ez` → Ezreal
- `fiddle` → Fiddlesticks
- `hec` → Hecarim
- `heimer` → Heimerdinger
- `j4` → Jarvan IV
- `kha` → Kha'Zix
- `kog` → Kog'Maw
- `malph` → Malphite
- `malz` → Malzahar
- `morde` → Mordekaiser
- `naut` → Nautilus
- `panth` → Pantheon
- `reng` → Rengar
- `seju` → Sejuani
- `tali` → Taliyah
- `tk` or `tahm` → Tahm Kench
- `trist` → Tristana
- `trynd` → Tryndamere
- `vik` → Viktor
- `vlad` → Vladimir
- `voli` → Volibear
- `ww` → Warwick
- `xin` → Xin Zhao

### Tips
- Case insensitive: `ASOL`, `asol`, `AsOl` all work
- Spaces optional: `aurelion sol`, `aurelionsol` both work
- Apostrophes optional: `kaisa`, `kai'sa` both work

## Features

✅ **Live Leaderboard**: Embed updates in real-time with each vote  
✅ **Top 5 Podium**: Shows champions with medals 🥇🥈🥉4️⃣5️⃣  
✅ **All Champions Listed**: Champions outside top 5 shown below podium  
✅ **Point System**: Boosters get 2x points, regular users get 1x  
✅ **Vote Changes**: Users can change votes during active session  
✅ **Auto-Exclusions**: Top 5 winners automatically excluded next session  
✅ **Manual Exclusions**: Admins can exclude/include champions anytime  
✅ **Champion Aliases**: Supports 100+ common abbreviations  
✅ **Thread Restriction**: Only works in designated voting thread  
✅ **Admin Controls**: Only admins can start/stop/manage sessions

## Workflow Example

1. **Admin starts voting:**
   ```
   /votestart
   ```
   *Bot auto-excludes: Ahri, Yasuo, Zed, Jinx, Lee Sin (from last session)*

2. **Admin adds more exclusions:**
   ```
   /voteexclude champions:Vayne, Thresh
   ```

3. **Users vote:**
   ```
   /vote champion1:asol champion2:kass champion3:mf champion4:lb champion5:yone
   ```
   *Bot recognizes: Aurelion Sol, Kassadin, Miss Fortune, LeBlanc, Yone*

4. **Admin ends voting:**
   ```
   /votestop
   ```
   *Final results shown, top 5 will be excluded in next session*

## Database Schema

### `voting_sessions`
- `id`: Session ID
- `guild_id`: Discord server ID
- `channel_id`: Thread ID
- `message_id`: Leaderboard message ID
- `started_by`: Admin who started
- `started_at`: Start timestamp
- `ended_at`: End timestamp
- `status`: 'active' or 'ended'
- `excluded_champions`: Array of excluded champion names
- `auto_exclude_previous`: Boolean (always TRUE)

### `voting_votes`
- `id`: Vote ID
- `session_id`: Reference to session
- `user_id`: Discord user ID
- `champion_name`: Official champion name
- `rank_position`: 1-5 (user's ranking)
- `points`: 1 or 2 (based on booster status)
- `voted_at`: Vote timestamp

## Notes

- Exclusions reset when new session starts (except auto-excluded top 5)
- Each user's vote replaces their previous vote (5 champions at a time)
- Points are aggregated across all votes
- Tie-breaker: Alphabetical order by champion name
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
