"""
Background Worker for Orianna Bot
Updates all users' mastery and ranked stats periodically
"""

import os
import asyncio
import logging
from datetime import datetime

from database import initialize_database, get_db
from riot_api import RiotAPI, load_champion_data

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('worker')

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
RIOT_API_KEY = os.getenv('RIOT_API_KEY')

# Initialize
db = None
riot_api = None

async def update_user_mastery(user_id: int, account: dict):
    """Update mastery data for a single user account"""
    try:
        # Get current mastery from Riot API
        new_mastery = await riot_api.get_champion_mastery(
            account['puuid'], 
            account['region'], 
            200
        )
        
        if not new_mastery:
            logger.warning(f"Failed to get mastery for user {user_id}")
            return
        
        # Get old mastery from database
        old_mastery = {
            stat['champion_id']: stat 
            for stat in db.get_user_champion_stats(user_id)
        }
        
        updates = 0
        deltas_recorded = 0
        
        for champ in new_mastery:
            champ_id = champ['championId']
            new_points = champ['championPoints']
            new_level = champ['championLevel']
            
            # Update champion stats
            db.update_champion_mastery(
                user_id,
                champ_id,
                new_points,
                new_level,
                champ.get('chestGranted', False),
                champ.get('tokensEarned', 0),
                champ.get('lastPlayTime')
            )
            updates += 1
            
            # Check for point changes (record delta)
            if champ_id in old_mastery:
                old_points = old_mastery[champ_id]['score']
                delta = new_points - old_points
                
                # Only record if there's a change
                if delta > 0:
                    db.add_mastery_delta(user_id, champ_id, delta, new_points)
                    deltas_recorded += 1
            else:
                # New champion - record initial value as delta
                if new_points > 0:
                    db.add_mastery_delta(user_id, champ_id, new_points, new_points)
                    deltas_recorded += 1
        
        logger.info(f"✅ Updated {updates} champions for user {user_id} ({deltas_recorded} deltas)")
        
    except Exception as e:
        logger.error(f"❌ Error updating user {user_id}: {e}")

async def update_user_ranks(user_id: int, account: dict):
    """Update ranked stats for a single user account"""
    try:
        # Get summoner data
        summoner_data = await riot_api.get_summoner_by_puuid(
            account['puuid'],
            account['region']
        )
        
        if not summoner_data:
            return
        
        # Get ranked stats
        ranked_stats = await riot_api.get_ranked_stats(
            summoner_data['id'],
            account['region']
        )
        
        if not ranked_stats:
            return
        
        for queue in ranked_stats:
            db.update_ranked_stats(
                user_id,
                queue['queueType'],
                queue.get('tier', 'UNRANKED'),
                queue.get('rank', ''),
                queue.get('leaguePoints', 0),
                queue.get('wins', 0),
                queue.get('losses', 0),
                queue.get('hotStreak', False),
                queue.get('veteran', False),
                queue.get('freshBlood', False)
            )
        
        logger.info(f"✅ Updated ranks for user {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Error updating ranks for user {user_id}: {e}")

async def update_all_users():
    """Update all users in the database"""
    try:
        logger.info("🔄 Starting update cycle...")
        
        # Get all users with accounts
        users = db.get_all_users_with_accounts()
        
        logger.info(f"📊 Found {len(users)} accounts to update")
        
        for i, user_data in enumerate(users):
            try:
                logger.info(f"Updating {i+1}/{len(users)}: User {user_data['user_id']}")
                
                # Update mastery
                await update_user_mastery(user_data['user_id'], user_data)
                
                # Update ranks
                await update_user_ranks(user_data['user_id'], user_data)
                
                # Rate limit protection - wait between users
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"❌ Error updating user {user_data['user_id']}: {e}")
                continue
        
        logger.info("✅ Update cycle completed!")
        
    except Exception as e:
        logger.error(f"❌ Error in update cycle: {e}")

async def worker_loop():
    """Main worker loop - updates every hour"""
    logger.info("🚀 Worker started!")
    
    # Initial delay to let bot start first
    await asyncio.sleep(60)
    
    while True:
        try:
            await update_all_users()
            
            # Wait 1 hour before next update
            logger.info("⏰ Sleeping for 1 hour...")
            await asyncio.sleep(3600)
            
        except Exception as e:
            logger.error(f"❌ Critical error in worker loop: {e}")
            # Wait before retry
            await asyncio.sleep(300)  # 5 minutes

async def main():
    """Initialize and start worker"""
    global db, riot_api
    
    logger.info("🔧 Initializing worker...")
    
    # Initialize database
    db = initialize_database(DATABASE_URL)
    logger.info("✅ Database connected")
    
    # Initialize Riot API
    riot_api = RiotAPI(RIOT_API_KEY)
    await load_champion_data()
    logger.info("✅ Riot API initialized")
    
    # Start worker loop
    await worker_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Worker stopped by user")
    except Exception as e:
        logger.error(f"❌ Worker crashed: {e}")
