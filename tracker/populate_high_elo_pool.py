"""
Populate database with high-elo players from Challenger/Grandmaster/Master
These PUUIDs will be used by HEXBET to find games
"""
import asyncio
import aiohttp
import os
import psycopg2
from psycopg2.extras import execute_batch

PLATFORM_ROUTES = {
    'euw': 'euw1',
    'eune': 'eun1',
    'na': 'na1',
    'kr': 'kr',
}

async def fetch_league(platform: str, tier: str, api_key: str):
    """Fetch Challenger/Grandmaster/Master league"""
    url = f"https://{platform}.api.riotgames.com/lol/league/v4/{tier}leagues/by-queue/RANKED_SOLO_5x5"
    headers = {'X-Riot-Token': api_key}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                entries = data.get('entries', [])
                print(f"✅ {platform} {tier}: {len(entries)} players")
                return entries
            else:
                print(f"❌ {platform} {tier}: {response.status}")
                return []

async def main():
    api_key = os.getenv('RIOT_API_KEY') or 'RGAPI-5e0f1b51-f862-4a36-bdf8-0adafdbdd7f1'
    db_url = os.getenv('DATABASE_URL')
    
    if not db_url:
        print("❌ DATABASE_URL not set")
        return
    
    # Collect all high-elo PUUIDs
    all_players = []
    
    for region, platform in PLATFORM_ROUTES.items():
        for tier in ['challenger', 'grandmaster', 'master']:
            entries = await fetch_league(platform, tier, api_key)
            for entry in entries:
                puuid = entry.get('puuid')
                if puuid:
                    all_players.append((puuid, region, tier, entry.get('leaguePoints', 0)))
            await asyncio.sleep(1)  # Rate limit
    
    print(f"\n📊 Total players collected: {len(all_players)}")
    
    # Save to database
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            # Create table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS hexbet_high_elo_pool (
                    puuid TEXT PRIMARY KEY,
                    region TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    lp INTEGER DEFAULT 0,
                    last_checked TIMESTAMP,
                    times_featured INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert players
            execute_batch(cur, """
                INSERT INTO hexbet_high_elo_pool (puuid, region, tier, lp)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (puuid) DO UPDATE SET
                    region = EXCLUDED.region,
                    tier = EXCLUDED.tier,
                    lp = EXCLUDED.lp
            """, all_players)
            
            conn.commit()
            print(f"✅ Saved {len(all_players)} players to database")
            
            # Show stats
            cur.execute("""
                SELECT region, tier, COUNT(*) 
                FROM hexbet_high_elo_pool 
                GROUP BY region, tier 
                ORDER BY region, tier
            """)
            print("\n📈 Database stats:")
            for row in cur.fetchall():
                print(f"  {row[0]} {row[1]}: {row[2]} players")
    finally:
        conn.close()

if __name__ == '__main__':
    asyncio.run(main())
