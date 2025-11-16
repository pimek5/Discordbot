"""
Batch forcelink script - adds multiple accounts to a user
"""
import asyncio
import os
from database import initialize_database, get_db
from riot_api import RiotAPI

# Your Discord ID (replace with actual ID)
DISCORD_USER_ID = 428568782535655425  # Replace this with your Discord ID

# Account list
ACCOUNTS = [
    # EUNE accounts
    ("16 9 13 5 11#pimek", "eune"),
    ("LF COSPLAYGIRL#pimek", "eune"),
    ("pimek#EUNE", "eune"),
    ("大天使号 333#pimek", "eune"),
    ("pimek532#pimek", "eune"),
    ("5P4C3G71D3R#pimek", "eune"),
    ("RATIRL#pimek", "eune"),
    ("EL0GR1ND3R#pimek", "eune"),
    ("knifeplay#pimek", "eune"),
    ("CSX BABYSTARZ#pimek", "eune"),
    ("SPACEGLIDER#pimek", "eune"),
    ("cυmsIut#pimek", "eune"),
    ("Marshebe#pimek", "eune"),
    ("Luna#pimek", "eune"),
    ("pbqjry#pimek", "eune"),
    
    # EUW accounts
    ("デトアライブ#pimek", "euw"),
    ("DiscoNunu#pimek", "euw"),
    ("유나탈카 사랑해요#pimek", "euw"),
    ("1412011211#pimek", "euw"),
    ("AP0CALYPSE#pimek", "euw"),
    ("CSXX XDDDDDDDDD#pimek", "euw"),
    ("L9 RATIRL#pimek", "euw"),
    ("BR3AKTH3RUL3S#GLIDE", "euw"),
    
    # RU account
    ("love you L9#pimek", "ru"),
]

async def main():
    print("🚀 Starting batch forcelink process...")
    print(f"👤 Target Discord ID: {DISCORD_USER_ID}")
    print(f"📝 Total accounts: {len(ACCOUNTS)}\n")
    
    # Initialize
    riot_api_key = os.getenv('RIOT_API_KEY')
    if not riot_api_key:
        print("❌ RIOT_API_KEY not found in environment!")
        return
    
    riot_api = RiotAPI(riot_api_key)
    db = get_db()
    
    # Get or create user
    db_user = db.get_user_by_discord_id(DISCORD_USER_ID)
    if not db_user:
        print(f"Creating new user for Discord ID {DISCORD_USER_ID}...")
        db_user_id = db.create_user(DISCORD_USER_ID)
    else:
        db_user_id = db_user['id']
        print(f"✅ Found existing user (DB ID: {db_user_id})\n")
    
    success_count = 0
    failed_count = 0
    failed_accounts = []
    
    for riot_id, region in ACCOUNTS:
        try:
            print(f"🔄 Processing: {riot_id} ({region.upper()})")
            
            # Parse Riot ID
            if '#' not in riot_id:
                print(f"   ❌ Invalid format (no #)")
                failed_count += 1
                failed_accounts.append((riot_id, region, "Invalid format"))
                continue
            
            game_name, tagline = riot_id.split('#', 1)
            
            # Get account from Riot API
            account_data = await riot_api.get_account_by_riot_id(game_name, tagline, region)
            
            if not account_data:
                print(f"   ❌ Account not found")
                failed_count += 1
                failed_accounts.append((riot_id, region, "Account not found"))
                continue
            
            puuid = account_data['puuid']
            
            # Get summoner data
            summoner_data = await riot_api.get_summoner_by_puuid(puuid, region)
            
            if not summoner_data:
                print(f"   ❌ Could not fetch summoner data")
                failed_count += 1
                failed_accounts.append((riot_id, region, "Summoner data fetch failed"))
                continue
            
            # Add to database
            db.add_league_account(
                user_id=db_user_id,
                region=region,
                game_name=game_name,
                tagline=tagline,
                puuid=puuid,
                summoner_id=summoner_data.get('id'),
                summoner_level=summoner_data.get('summonerLevel', 1),
                verified=True
            )
            
            level = summoner_data.get('summonerLevel', '?')
            print(f"   ✅ Added (Level {level}, PUUID: {puuid[:20]}...)")
            success_count += 1
            
            # Small delay to avoid rate limits
            await asyncio.sleep(0.5)
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            failed_count += 1
            failed_accounts.append((riot_id, region, str(e)))
    
    # Summary
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    print(f"✅ Successfully linked: {success_count}/{len(ACCOUNTS)}")
    print(f"❌ Failed: {failed_count}/{len(ACCOUNTS)}")
    
    if failed_accounts:
        print("\n⚠️ Failed accounts:")
        for riot_id, region, reason in failed_accounts:
            print(f"   • {riot_id} ({region}): {reason}")
    
    print("\n🎉 Batch forcelink complete!")

if __name__ == "__main__":
    asyncio.run(main())
