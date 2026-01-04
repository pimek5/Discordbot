"""
Migrate verified players from leaguepedia_scraper.py to database
Run once to populate hexbet_verified_players table
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tracker_database import TrackerDatabase
from HEXBET.leaguepedia_scraper import PRO_ACCOUNTS, STREAMER_ACCOUNTS
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('migration')

def migrate_to_database():
    """Migrate all verified players to database"""
    db = TrackerDatabase()
    
    # Migrate pro players
    logger.info("Migrating PRO players...")
    for riot_id, info in PRO_ACCOUNTS.items():
        try:
            player_name = info.get('name', riot_id.split('#')[0].title())
            team = info.get('team')
            
            db.add_verified_player(
                riot_id=riot_id,
                player_name=player_name,
                player_type='pro',
                team=team,
                platform=None,
                lolpros_url=f"https://lolpros.gg/player/{riot_id.split('#')[0].lower()}",
                leaguepedia_url=f"https://lol.fandom.com/wiki/{player_name.replace(' ', '_')}" if player_name else None
            )
            logger.info(f"✅ Added PRO: {player_name} ({riot_id})")
        except Exception as e:
            logger.error(f"❌ Failed to add {riot_id}: {e}")
    
    # Migrate streamers
    logger.info("Migrating STREAMER accounts...")
    for riot_id, info in STREAMER_ACCOUNTS.items():
        try:
            player_name = info.get('name', riot_id.split('#')[0].title())
            platform = info.get('platform', 'Twitch')
            
            db.add_verified_player(
                riot_id=riot_id,
                player_name=player_name,
                player_type='streamer',
                team=None,
                platform=platform,
                lolpros_url=f"https://lolpros.gg/player/{riot_id.split('#')[0].lower()}",
                leaguepedia_url=f"https://lol.fandom.com/wiki/{player_name.replace(' ', '_')}" if player_name else None
            )
            logger.info(f"✅ Added STREAMER: {player_name} ({riot_id})")
        except Exception as e:
            logger.error(f"❌ Failed to add {riot_id}: {e}")
    
    # Get total counts
    all_players = db.get_all_verified_players()
    pros = [p for p in all_players if p['player_type'] == 'pro']
    streamers = [p for p in all_players if p['player_type'] == 'streamer']
    
    logger.info(f"\n✅ Migration complete!")
    logger.info(f"📊 Total verified players: {len(all_players)}")
    logger.info(f"   - PRO: {len(pros)}")
    logger.info(f"   - STREAMER: {len(streamers)}")

if __name__ == '__main__':
    migrate_to_database()
