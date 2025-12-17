"""
Objective Icons Management
Downloads and manages icons for dragons, baron, herald, and other objectives
Also provides URLs for items, summoner spells, runes, and other game assets from Data Dragon
"""

# DDragon version
DDRAGON_VERSION = "14.23.1"
CDRAGON_BASE = "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default"
DDRAGON_BASE = f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VERSION}"

# Objective icon URLs from Community Dragon (better quality than DDragon)
OBJECTIVE_ICONS = {
    # Dragons
    'dragon_chemtech': f"{CDRAGON_BASE}/assets/maps/particles/map11/dragon_souls/chemtech_dragonsoul_buff.png",
    'dragon_hextech': f"{CDRAGON_BASE}/assets/maps/particles/map11/dragon_souls/hextech_dragonsoul_buff.png",
    'dragon_infernal': f"{CDRAGON_BASE}/assets/maps/particles/map11/dragon_souls/infernal_dragonsoul_buff.png",
    'dragon_mountain': f"{CDRAGON_BASE}/assets/maps/particles/map11/dragon_souls/mountain_dragonsoul_buff.png",
    'dragon_ocean': f"{CDRAGON_BASE}/assets/maps/particles/map11/dragon_souls/ocean_dragonsoul_buff.png",
    'dragon_cloud': f"{CDRAGON_BASE}/assets/maps/particles/map11/dragon_souls/cloud_dragonsoul_buff.png",
    'dragon_elder': f"{CDRAGON_BASE}/assets/maps/particles/map11/dragon_souls/elder_dragonsoul_buff.png",
    
    # Epic monsters
    'baron': f"{CDRAGON_BASE}/assets/maps/particles/map11/baron_buff.png",
    'herald': f"{CDRAGON_BASE}/assets/maps/particles/map11/riftherald_buff.png",
    
    # Neutral objectives
    'tower': f"{CDRAGON_BASE}/assets/maps/particles/map11/turret_icon.png",
    'inhibitor': f"{CDRAGON_BASE}/assets/maps/particles/map11/inhibitor_icon.png",
    
    # Stats icons
    'kills': f"{CDRAGON_BASE}/assets/perks/styles/resolve/conditioning/conditioning.png",
    'gold': f"{DDRAGON_BASE}/img/item/1001.png",  # Boots of Speed as gold icon
    'damage': f"{CDRAGON_BASE}/assets/perks/styles/domination/electrocute/electrocute.png",
    'vision': f"{DDRAGON_BASE}/img/item/3340.png",  # Stealth Ward
    'cs': f"{CDRAGON_BASE}/assets/characters/sruap_minionmelee/hud/icons2d/sruap_minionmelee_square.png",
    
    # Jungle camps
    'blue_buff': f"{CDRAGON_BASE}/assets/characters/sru_blue/hud/icons2d/sru_blue_square.png",
    'red_buff': f"{CDRAGON_BASE}/assets/characters/sru_red/hud/icons2d/sru_red_square.png",
    'gromp': f"{CDRAGON_BASE}/assets/characters/sru_gromp/hud/icons2d/sru_gromp_square.png",
    'krugs': f"{CDRAGON_BASE}/assets/characters/sru_krug/hud/icons2d/sru_krug_square.png",
    'wolves': f"{CDRAGON_BASE}/assets/characters/sru_murkwolf/hud/icons2d/sru_murkwolf_square.png",
    'raptors': f"{CDRAGON_BASE}/assets/characters/sru_razorbeak/hud/icons2d/sru_razorbeak_square.png",
    
    # Minions
    'minion': f"{CDRAGON_BASE}/assets/characters/sruap_minionmelee/hud/icons2d/sruap_minionmelee_square.png",
    'cannon': f"{CDRAGON_BASE}/assets/characters/sruap_minionsiege/hud/icons2d/sruap_minionsiege_square.png",
}

# Emoji-based icons (fallback when icons can't be used in embed text)
# These are high-quality Unicode emoji alternatives
OBJECTIVE_EMOJIS = {
    # Dragons - use distinctive emoji
    'dragon_chemtech': '🟢',
    'dragon_hextech': '🔷',
    'dragon_infernal': '🔥',
    'dragon_mountain': '⛰️',
    'dragon_ocean': '🌊',
    'dragon_cloud': '☁️',
    'dragon_elder': '👑',
    
    # Epic monsters
    'baron': '👹',
    'herald': '👁️',
    
    # Structures
    'tower': '🗼',
    'inhibitor': '🏛️',
    
    # Jungle camps
    'blue_buff': '🔵',
    'red_buff': '🔴',
    'gromp': '🐸',
    'krugs': '🪨',
    'wolves': '🐺',
    'raptors': '🦅',
    
    # Minions
    'minion': '⚔️',
    'cannon': '🎯',
    
    # Stats - better visual emoji
    'kills': '💀',
    'gold': '💰',
    'damage': '⚡',
    'vision': '👁️',
    'cs': '🗡️',
    
    # Additional useful emoji
    'win': '🟢',
    'loss': '🔴',
    'victory': '🏆',
    'defeat': '💔',
    'kda': '⚔️',
    'rank': '📊',
    'level': '⬆️',
    'champion': '🦸',
}


def get_objective_icon(objective_type: str) -> str:
    """Get objective icon URL"""
    return OBJECTIVE_ICONS.get(objective_type.lower(), '')


def get_objective_emoji(objective_type: str) -> str:
    """Get objective emoji (fallback)"""
    return OBJECTIVE_EMOJIS.get(objective_type.lower(), '❓')


def get_objective_display(objective_type: str) -> dict:
    """Get both icon URL and emoji for an objective
    
    Returns:
        dict with 'icon' (URL) and 'emoji' (str) keys
        
    Example:
        display = get_objective_display('baron')
        # {'icon': 'https://...baron_buff.png', 'emoji': '👹'}
        
        # Use in embed:
        embed.set_thumbnail(url=display['icon'])
        embed.add_field(name=f"{display['emoji']} Baron", value="Stats...")
    """
    return {
        'icon': get_objective_icon(objective_type),
        'emoji': get_objective_emoji(objective_type)
    }


# ==================== ADDITIONAL ASSET FUNCTIONS ====================

def get_item_icon(item_id: int) -> str:
    """Get item icon URL from Data Dragon"""
    return f"{DDRAGON_BASE}/img/item/{item_id}.png"


# Common item IDs for quick reference
COMMON_ITEMS = {
    'boots': 1001,
    'ward': 3340,
    'control_ward': 2055,
    'infinity_edge': 3031,
    'rabadon': 3089,
    'zhonyas': 3157,
    'guardian_angel': 3026,
    'Trinity_force': 3078,
    'blade_of_ruined_king': 3153,
}


def get_common_item_icon(item_name: str) -> str:
    """Get icon for commonly used items by name
    
    Args:
        item_name: Name like 'boots', 'ward', 'zhonyas', etc.
        
    Returns:
        URL to item icon
    """
    item_id = COMMON_ITEMS.get(item_name.lower())
    if item_id:
        return get_item_icon(item_id)
    return ''


def get_summoner_spell_icon(spell_name: str) -> str:
    """Get summoner spell icon URL from Data Dragon
    
    Args:
        spell_name: Name like 'Flash', 'Ignite', 'Teleport', etc.
    """
    # Map common spell names to their file names
    spell_map = {
        'flash': 'SummonerFlash',
        'ignite': 'SummonerDot',
        'teleport': 'SummonerTeleport',
        'heal': 'SummonerHeal',
        'barrier': 'SummonerBarrier',
        'exhaust': 'SummonerExhaust',
        'cleanse': 'SummonerBoost',
        'ghost': 'SummonerHaste',
        'smite': 'SummonerSmite',
        'clarity': 'SummonerMana',
        'mark': 'SummonerSnowball',
        'snowball': 'SummonerSnowball',
    }
    
    spell_file = spell_map.get(spell_name.lower(), spell_name)
    return f"{DDRAGON_BASE}/img/spell/{spell_file}.png"


def get_rune_icon(rune_id: int) -> str:
    """Get rune icon URL from Community Dragon
    
    Common rune IDs:
    - 8000s: Precision
    - 8100s: Domination
    - 8200s: Sorcery
    - 8300s: Resolve
    - 8400s: Inspiration
    """
    return f"{CDRAGON_BASE}/v1/perk-images/styles/{rune_id}.png"


def get_position_icon(position: str) -> str:
    """Get position/role icon URL
    
    Args:
        position: 'top', 'jungle', 'mid', 'adc', 'support'
    """
    position_map = {
        'top': 'top',
        'jungle': 'jungle',
        'mid': 'middle',
        'middle': 'middle',
        'adc': 'bottom',
        'bottom': 'bottom',
        'support': 'utility',
        'utility': 'utility',
    }
    
    pos = position_map.get(position.lower(), position.lower())
    return f"{CDRAGON_BASE}/assets/ranked-positions/position_{pos}.png"


def get_ranked_emblem(tier: str, division: str = '') -> str:
    """Get ranked tier emblem URL
    
    Args:
        tier: 'iron', 'bronze', 'silver', 'gold', 'platinum', 'emerald', 'diamond', 'master', 'grandmaster', 'challenger'
        division: 'I', 'II', 'III', 'IV' (not needed for master+)
    """
    tier_lower = tier.lower()
    
    # Master+ don't have divisions
    if tier_lower in ['master', 'grandmaster', 'challenger']:
        return f"{CDRAGON_BASE}/assets/ranked-emblems/emblem-{tier_lower}.png"
    
    # For other tiers with divisions
    return f"{CDRAGON_BASE}/assets/ranked-emblems/emblem-{tier_lower}.png"


def get_champion_splash(champion_name: str, skin_num: int = 0) -> str:
    """Get champion splash art URL
    
    Args:
        champion_name: Champion name like 'Ahri', 'MasterYi', etc.
        skin_num: Skin number (0 = default)
    """
    return f"{DDRAGON_BASE}/img/champion/splash/{champion_name}_{skin_num}.jpg"


def get_champion_loading(champion_name: str, skin_num: int = 0) -> str:
    """Get champion loading screen art URL
    
    Args:
        champion_name: Champion name like 'Ahri', 'MasterYi', etc.
        skin_num: Skin number (0 = default)
    """
    return f"{DDRAGON_BASE}/img/champion/loading/{champion_name}_{skin_num}.jpg"


def get_ability_icon(champion_name: str, ability: str) -> str:
    """Get ability icon URL
    
    Args:
        champion_name: Champion name like 'Ahri', 'Yasuo'
        ability: 'Q', 'W', 'E', 'R', or 'P' for passive
    """
    # This would need champion spell data mapping
    # For now return a placeholder
    return f"{DDRAGON_BASE}/img/champion/{champion_name}.png"
