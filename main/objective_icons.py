"""
Objective Icons Management
Downloads and manages icons for dragons, baron, herald, and other objectives
"""

# DDragon objective icons
DDRAGON_VERSION = "14.23.1"
OBJECTIVE_BASE = f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default"

# Objective icon URLs from Community Dragon (better quality than DDragon)
OBJECTIVE_ICONS = {
    # Dragons
    'dragon_chemtech': f"{OBJECTIVE_BASE}/assets/maps/particles/map11/dragon_souls/chemtech_dragonsoul_buff.png",
    'dragon_hextech': f"{OBJECTIVE_BASE}/assets/maps/particles/map11/dragon_souls/hextech_dragonsoul_buff.png",
    'dragon_infernal': f"{OBJECTIVE_BASE}/assets/maps/particles/map11/dragon_souls/infernal_dragonsoul_buff.png",
    'dragon_mountain': f"{OBJECTIVE_BASE}/assets/maps/particles/map11/dragon_souls/mountain_dragonsoul_buff.png",
    'dragon_ocean': f"{OBJECTIVE_BASE}/assets/maps/particles/map11/dragon_souls/ocean_dragonsoul_buff.png",
    'dragon_cloud': f"{OBJECTIVE_BASE}/assets/maps/particles/map11/dragon_souls/cloud_dragonsoul_buff.png",
    'dragon_elder': f"{OBJECTIVE_BASE}/assets/maps/particles/map11/dragon_souls/elder_dragonsoul_buff.png",
    
    # Epic monsters
    'baron': f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/assets/maps/particles/map11/baron_buff.png",
    'herald': f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/assets/maps/particles/map11/riftherald_buff.png",
    
    # Neutral objectives
    'tower': f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/assets/maps/particles/map11/turret_icon.png",
    'inhibitor': f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/assets/maps/particles/map11/inhibitor_icon.png",
    
    # Jungle camps (from DDragon)
    'blue_buff': f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}/img/sprite/spell0.png",  # Placeholder
    'red_buff': f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}/img/sprite/spell0.png",  # Placeholder
    'gromp': f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}/img/sprite/spell0.png",  # Placeholder
    'krugs': f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}/img/sprite/spell0.png",  # Placeholder
    'wolves': f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}/img/sprite/spell0.png",  # Placeholder
    'raptors': f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}/img/sprite/spell0.png",  # Placeholder
    
    # Minions
    'minion': f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/assets/characters/sruap_minionmelee/hud/icons2d/sruap_minionmelee_square.png",
    'cannon': f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/assets/characters/sruap_minionsiege/hud/icons2d/sruap_minionsiege_square.png",
}

# Emoji-based icons (fallback)
OBJECTIVE_EMOJIS = {
    'dragon_chemtech': '🟢',
    'dragon_hextech': '🔷',
    'dragon_infernal': '🔥',
    'dragon_mountain': '⛰️',
    'dragon_ocean': '🌊',
    'dragon_cloud': '☁️',
    'dragon_elder': '👑',
    'baron': '👹',
    'herald': '👁️',
    'tower': '🗼',
    'inhibitor': '🏛️',
    'blue_buff': '🔵',
    'red_buff': '🔴',
    'gromp': '🐸',
    'krugs': '🪨',
    'wolves': '🐺',
    'raptors': '🦅',
    'minion': '⚔️',
    'cannon': '🎯',
    'kills': '💀',
    'gold': '💰',
    'damage': '⚡',
    'vision': '👁️',
    'cs': '🗡️',
}


def get_objective_icon(objective_type: str) -> str:
    """Get objective icon URL"""
    return OBJECTIVE_ICONS.get(objective_type.lower(), '')


def get_objective_emoji(objective_type: str) -> str:
    """Get objective emoji (fallback)"""
    return OBJECTIVE_EMOJIS.get(objective_type.lower(), '❓')
