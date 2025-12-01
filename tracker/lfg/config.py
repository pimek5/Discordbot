"""
LFG Configuration
=================
Central configuration file for the LFG system.
Edit these values to customize the LFG system for your server.
"""

# ================================
#    DISCORD CONFIGURATION
# ================================

# Channel where LFG listings are posted
LFG_CHANNEL_ID = 1234567890  # TODO: Change this to your LFG channel ID

# Channel where LFG commands can be used (None = all channels)
LFG_COMMAND_CHANNEL_ID = None

# Role that can manage LFG listings (delete others' listings, etc.)
LFG_MODERATOR_ROLE_ID = None  # None = admins only


# ================================
#    LISTING CONFIGURATION
# ================================

# How long listings stay active before expiring
LISTING_EXPIRATION_HOURS = 6

# Maximum number of active listings per user
MAX_LISTINGS_PER_USER = 3

# Minimum level/age to create listings (Discord account age in days)
MIN_ACCOUNT_AGE_DAYS = 7


# ================================
#    RIOT API CONFIGURATION
# ================================

# Whether to verify Riot accounts when creating profiles
VERIFY_RIOT_ACCOUNTS = True

# Whether to auto-update ranks from Riot API
AUTO_UPDATE_RANKS = True

# How often to update ranks (in hours)
RANK_UPDATE_INTERVAL_HOURS = 24


# ================================
#    FEATURE FLAGS
# ================================

# Enable/disable specific features
FEATURES = {
    'profiles': True,           # Profile system
    'listings': True,           # Listing creation
    'applications': True,       # Application system (join button)
    'auto_cleanup': True,       # Auto-cleanup expired listings
    'rank_verification': True,  # Verify ranks through Riot API
    'champion_stats': False,    # Show top champions in profiles (TODO)
    'matchmaking': False,       # Matchmaking suggestions (TODO)
}


# ================================
#    EMBED COLORS
# ================================

COLORS = {
    'profile': 0x3498db,       # Blue
    'listing': 0x2ecc71,       # Green
    'expired': 0x95a5a6,       # Grey
    'error': 0xe74c3c,         # Red
    'success': 0x2ecc71,       # Green
    'warning': 0xf39c12,       # Orange
}


# ================================
#    RANK REQUIREMENTS
# ================================

# Minimum rank required to create listings for ranked queues
MIN_RANK_FOR_RANKED = None  # None = no restriction, or 'IRON', 'BRONZE', etc.

# Whether to allow unranked players to create ranked listings
ALLOW_UNRANKED_RANKED_LISTINGS = True


# ================================
#    NOTIFICATION SETTINGS
# ================================

# Send DM notifications to listing creators when someone applies
NOTIFY_CREATOR_ON_APPLICATION = True

# Send DM notifications to applicants when accepted/rejected
NOTIFY_APPLICANT_ON_RESPONSE = True


# ================================
#    ANTI-SPAM SETTINGS
# ================================

# Cooldown between creating listings (in minutes)
LISTING_COOLDOWN_MINUTES = 15

# Maximum listings per user per day
MAX_LISTINGS_PER_DAY = 10


# ================================
#    DATABASE SETTINGS
# ================================

# Whether to store match history for groups (for future matchmaking)
STORE_GROUP_HISTORY = True

# How long to keep expired listings in database (in days, 0 = forever)
KEEP_EXPIRED_LISTINGS_DAYS = 30


# ================================
#    VALIDATION
# ================================

def validate_config():
    """Validate configuration settings."""
    errors = []
    
    if LFG_CHANNEL_ID == 1234567890:
        errors.append("⚠️ LFG_CHANNEL_ID not configured! Set it in lfg/config.py")
    
    if LISTING_EXPIRATION_HOURS < 1:
        errors.append("❌ LISTING_EXPIRATION_HOURS must be at least 1")
    
    if MAX_LISTINGS_PER_USER < 1:
        errors.append("❌ MAX_LISTINGS_PER_USER must be at least 1")
    
    return errors


if __name__ == "__main__":
    # Test configuration
    errors = validate_config()
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  {error}")
    else:
        print("✅ Configuration valid!")
