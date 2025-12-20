"""
Generate 5-emoji sequences for each champion based on ability keywords
"""
import json

# Keyword to emoji mapping
EMOJI_MAP = {
    # Damage types
    'fire': '🔥',
    'flame': '🔥',
    'burn': '🔥',
    'ice': '❄️',
    'frost': '❄️',
    'frozen': '❄️',
    'freeze': '❄️',
    'cold': '❄️',
    'lightning': '⚡',
    'thunder': '⚡',
    'electric': '⚡',
    'shock': '⚡',
    'water': '💧',
    'wave': '🌊',
    'ocean': '🌊',
    'sea': '🌊',
    'wind': '🌪️',
    'tornado': '🌪️',
    'poison': '☠️',
    'toxic': '☠️',
    'venom': '☠️',
    'shadow': '🌑',
    'dark': '🌑',
    'darkness': '🌑',
    'void': '🌑',
    'light': '✨',
    'holy': '✨',
    'divine': '✨',
    'blood': '🩸',
    'bleed': '🩸',
    
    # Weapons
    'sword': '⚔️',
    'blade': '⚔️',
    'axe': '🪓',
    'hammer': '🔨',
    'bow': '🏹',
    'arrow': '🏹',
    'gun': '🔫',
    'cannon': '💥',
    'bomb': '💣',
    'grenade': '💣',
    'dagger': '🗡️',
    'knife': '🗡️',
    'spear': '🔱',
    'shield': '🛡️',
    
    # Magic
    'magic': '🔮',
    'mage': '🔮',
    'spell': '🔮',
    'arcane': '🔮',
    'crystal': '💎',
    'gem': '💎',
    'star': '⭐',
    'moon': '🌙',
    'sun': '☀️',
    
    # Nature
    'nature': '🌿',
    'plant': '🌿',
    'tree': '🌳',
    'forest': '🌲',
    'flower': '🌸',
    'rose': '🌹',
    'thorn': '🌹',
    
    # Animals
    'dragon': '🐉',
    'wolf': '🐺',
    'bear': '🐻',
    'lion': '🦁',
    'tiger': '🐯',
    'eagle': '🦅',
    'bird': '🦅',
    'spider': '🕷️',
    'scorpion': '🦂',
    'snake': '🐍',
    'bat': '🦇',
    'crow': '🦉',
    'fox': '🦊',
    'cat': '🐈',
    'shark': '🦈',
    'kraken': '🐙',
    
    # Combat actions
    'dash': '💨',
    'jump': '🦘',
    'leap': '🦘',
    'slash': '⚔️',
    'strike': '💥',
    'punch': '👊',
    'kick': '🦵',
    'throw': '🤾',
    'spin': '🌀',
    'charge': '⚡',
    'explode': '💥',
    'explosion': '💥',
    'stun': '💫',
    'slow': '🐌',
    'root': '🌿',
    'trap': '🪤',
    'invisible': '👻',
    'stealth': '👤',
    'hide': '👤',
    
    # Support/Utility
    'heal': '💚',
    'health': '💚',
    'life': '💚',
    'shield': '🛡️',
    'protect': '🛡️',
    'armor': '🛡️',
    'speed': '💨',
    'fast': '💨',
    'slow': '🐌',
    'buff': '📈',
    'enhance': '📈',
    
    # Music/Sound
    'music': '🎵',
    'song': '🎵',
    'sound': '🔊',
    'scream': '🔊',
    'shout': '🔊',
    
    # Death/Undead
    'death': '💀',
    'dead': '💀',
    'skull': '💀',
    'undead': '💀',
    'ghost': '👻',
    'soul': '👻',
    
    # Time/Space
    'time': '⏰',
    'clock': '⏰',
    'portal': '🌀',
    'teleport': '🌀',
    
    # Technology
    'tech': '⚙️',
    'machine': '⚙️',
    'robot': '🤖',
    'mech': '🤖',
    'laser': '🔴',
    'rocket': '🚀',
    
    # Elements/Weather
    'storm': '⛈️',
    'rain': '🌧️',
    'cloud': '☁️',
    'meteor': '☄️',
    'comet': '☄️',
}

# Champion-specific overrides (for champions with unique themes)
CHAMPION_OVERRIDES = {
    'Yasuo': '⚔️💨🌊⛈️🗡️',
    'Zed': '🌑⚔️💀🗡️👤',
    'Ahri': '🦊💜✨💕🔮',
    'Lux': '✨💫⭐☀️🔮',
    'Brand': '🔥💥🔥☄️🔥',
    'Annie': '🔥🧸🔥💥👧',
    'Nasus': '🐕💀⏰📚🔱',
    'Renekton': '🐊⚔️🩸💥😡',
    'Anivia': '🦅❄️🥚💎🌨️',
    'Ashe': '🏹❄️👑🦅💙',
    'Jinx': '💥🔫💣🎪😜',
    'Vi': '👊💥⚙️🔴💪',
    'Ekko': '⏰⚡💎🌀🦘',
    'Fizz': '🐟🔱🌊💧🦈',
    'Jhin': '🔫🎭🌹4️⃣💀',
    'Karthus': '💀🎵👻🔮💜',
    'Katarina': '🗡️⚔️💥🌀🩸',
    'Kayn': '⚔️🌑💀👹🦇',
    'Kennen': '⚡🐭💨💥🌩️',
    'KhaZix': '🦗💜🗡️👤🦗',
    'KogMaw': '🐛💚💥🦠🤢',
    'LeBlanc': '🔮✨👤💜🎭',
    'LeeSin': '👊🐉💥🦶⚡',
    'Leona': '☀️🛡️⚔️✨👑',
    'Lissandra': '❄️👑💜🌑🧊',
    'Lucian': '🔫✨💥⚡🩸',
    'Lulu': '✨🦄💜🌸🎩',
    'Malphite': '🗿💥🛡️⛰️💪',
    'Malzahar': '💜🌑🦟👁️🔮',
    'Maokai': '🌳🌿💚🌲👣',
    'MasterYi': '⚔️💨💥🧘⚡',
    'MissFortune': '🔫💰🩸💋⚓',
    'Mordekaiser': '⚔️💀👻💚🔨',
    'Morgana': '🌑⛓️💜👻🔮',
    'Nami': '🌊💧🐟✨💙',
    'Nautilus': '⚓🌊🔱💙🛡️',
    'Neeko': '🦎🌺💚✨🌸',
    'Nidalee': '🐆🔱🌿💚🦁',
    'Nocturne': '🌑👻💀⚔️👁️',
    'Nunu': '❄️🐻💙⛄🦷',
    'Olaf': '🪓🩸💪⚡🍺',
    'Orianna': '⚙️💙🤖⚽🔮',
    'Ornn': '🔨🐏🔥⛰️⚒️',
    'Pantheon': '🔱⚔️✨🛡️⛰️',
    'Poppy': '🔨💙🛡️💪⭐',
    'Pyke': '🗡️🩸🌊👻⚓',
    'Qiyana': '💎🌿🌊🔥👑',
    'Quinn': '🦅🏹💙⚔️👁️',
    'Rakan': '💚🦚🎭✨💚',
    'Rammus': '🦔🛡️💥⚡💪',
    'RekSai': '🦈💜🗡️⛰️👁️',
    'Rell': '⚔️⚙️💪🛡️👊',
    'Renata': '⚗️💜💰🧪💊',
    'Rengar': '🦁🗡️💥🌿👁️',
    'Riven': '⚔️💚💥🛡️⚡',
    'Rumble': '🤖🔥⚙️💪🔧',
    'Ryze': '🔮💙📜⚡🔵',
    'Sejuani': '🐗❄️🔱💙⚔️',
    'Senna': '🔫👻💚🌑✨',
    'Seraphine': '🎵✨💗🎤💫',
    'Sett': '👊💪🩸💥💛',
    'Shaco': '🃏🗡️👻🎪💀',
    'Shen': '🗡️💜👤🛡️👻',
    'Shyvana': '🐉🔥⚔️💜💪',
    'Singed': '⚗️☠️💚🧪💀',
    'Sion': '⚔️💀🩸💪👻',
    'Sivir': '⚔️💛⭐💰🔵',
    'Skarner': '🦂💎💜🔱⚡',
    'Sona': '🎵💙✨🎶💫',
    'Soraka': '⭐💚🦄✨🌙',
    'Swain': '🦅🔴⚔️👁️💀',
    'Sylas': '⛓️💪⚔️🔮🩸',
    'Syndra': '🔮💜⚽💎⚡',
    'TahmKench': '🐸💚👅🎩🌊',
    'Taliyah': '🗿💎🌍⛰️🌀',
    'Talon': '🗡️💥🌑🩸⚔️',
    'Taric': '💎✨💜🛡️⭐',
    'Teemo': '🍄💀💚🏹👁️',
    'Thresh': '⛓️💚🔦👻💀',
    'Tristana': '🔫💥🦘💛🚀',
    'Trundle': '🔨❄️🦷💪🐻',
    'Tryndamere': '⚔️🩸💪😡💥',
    'TwistedFate': '🃏🎴💛⭐🎲',
    'Twitch': '🐀☠️🏹💜💉',
    'Udyr': '🐻🐯🦅🐢💪',
    'Urgot': '⚙️🔫💚🦀💀',
    'Varus': '🏹💜🩸⚡💔',
    'Vayne': '🏹💥🌑⚔️💪',
    'Veigar': '🔮💜⭐💥🎩',
    'VelKoz': '👁️💜⚡🦑🔮',
    'Vex': '🌑👻💜😔✨',
    'Vi': '👊💥⚙️💪🔴',
    'Viego': '⚔️💚👑💀💔',
    'Viktor': '⚙️💜🔮⚡🤖',
    'Vladimir': '🩸💉💜🦇👻',
    'Volibear': '🐻⚡❄️💙⛈️',
    'Warwick': '🐺🩸💉💪🌙',
    'Wukong': '🐵⚔️💛👑💥',
    'Xayah': '🦚💜🗡️⚡💔',
    'Xerath': '⚡🔮💙⚡☄️',
    'XinZhao': '🔱⚔️💪🐉💥',
    'Yasuo': '⚔️💨🌊⛈️🗡️',
    'Yone': '⚔️👻💨🌸🗡️',
    'Yorick': '💀⚔️👻💚⚰️',
    'Yuumi': '😺💜✨📖💚',
    'Zac': '💚💪🦠💥🤸',
    'Zed': '🌑⚔️💀🗡️👤',
    'Zeri': '⚡💚🔫💥💨',
    'Ziggs': '💣💥🔥🤪🧨',
    'Zilean': '⏰💙⚡👴🔮',
    'Zoe': '✨💤⭐💜🌙',
    'Zyra': '🌿🌸🌹💚🌺',
}

def generate_emoji_from_champion(champion_data):
    """Generate 5 emojis based on champion name, title, tags, and abilities"""
    champion_name = champion_data['name']
    
    # Check for override first
    if champion_name in CHAMPION_OVERRIDES:
        return CHAMPION_OVERRIDES[champion_name]
    
    found_emojis = []
    
    # Combine all text sources for analysis
    search_texts = []
    
    # 1. Champion title (often describes appearance/theme)
    title = champion_data.get('title', '').lower()
    search_texts.append(title)
    
    # 2. Champion name (some names are descriptive)
    name_lower = champion_name.lower()
    search_texts.append(name_lower)
    
    # 3. Tags (Fighter, Mage, etc.)
    tags = champion_data.get('tags', [])
    search_texts.append(' '.join([t.lower() for t in tags]))
    
    # 4. Ability description
    if 'ability' in champion_data:
        ability_text = champion_data['ability'].get('name', '') + ' ' + champion_data['ability'].get('description', '')
        search_texts.append(ability_text.lower())
    
    # Combined search text
    combined_text = ' '.join(search_texts)
    
    # Priority 1: Look for animal/creature keywords (from title/name)
    animal_keywords = {
        'fox': '🦊', 'wolf': '🐺', 'bear': '🐻', 'lion': '🦁', 'tiger': '🐯',
        'dragon': '🐉', 'spider': '🕷️', 'scorpion': '🦂', 'snake': '🐍', 'serpent': '🐍',
        'bat': '🦇', 'crow': '🦉', 'bird': '🦅', 'eagle': '🦅', 'hawk': '🦅',
        'cat': '🐈', 'shark': '🦈', 'fish': '🐟', 'kraken': '🐙',
        'monkey': '🐵', 'ape': '🦍', 'boar': '🐗', 'ram': '🐏', 'goat': '🐐'
    }
    
    for keyword, emoji in animal_keywords.items():
        if keyword in combined_text and emoji not in found_emojis:
            found_emojis.append(emoji)
            if len(found_emojis) >= 5:
                return ''.join(found_emojis[:5])
    
    # Priority 2: Role-based emojis
    role_emojis = {
        'marksman': '🏹',
        'assassin': '🗡️',
        'mage': '🔮',
        'tank': '🛡️',
        'support': '💚',
        'fighter': '⚔️'
    }
    
    for tag in tags:
        tag_lower = tag.lower()
        if tag_lower in role_emojis:
            emoji = role_emojis[tag_lower]
            if emoji not in found_emojis:
                found_emojis.append(emoji)
    
    # Priority 3: Search for all keywords in EMOJI_MAP
    # Sort by keyword length (longer = more specific)
    sorted_keywords = sorted(EMOJI_MAP.items(), key=lambda x: len(x[0]), reverse=True)
    
    for keyword, emoji in sorted_keywords:
        if keyword in combined_text:
            if emoji not in found_emojis:
                found_emojis.append(emoji)
                if len(found_emojis) >= 5:
                    return ''.join(found_emojis[:5])
    
    # Priority 4: Generic fallbacks based on tags
    tag_fallbacks = {
        'Marksman': ['🏹', '🔫', '💥', '🎯', '⚡'],
        'Assassin': ['🗡️', '🌑', '💀', '⚔️', '💥'],
        'Mage': ['🔮', '✨', '⚡', '💫', '🌟'],
        'Tank': ['🛡️', '💪', '⛰️', '🗿', '💥'],
        'Support': ['💚', '✨', '🛡️', '💙', '🌟'],
        'Fighter': ['⚔️', '💥', '💪', '🗡️', '🔨']
    }
    
    for tag in tags:
        if tag in tag_fallbacks:
            for emoji in tag_fallbacks[tag]:
                if emoji not in found_emojis:
                    found_emojis.append(emoji)
                    if len(found_emojis) >= 5:
                        return ''.join(found_emojis[:5])
    
    # Priority 5: Ultimate fallback
    ultimate_fallback = ['⚔️', '💥', '✨', '🔮', '💪']
    for emoji in ultimate_fallback:
        if emoji not in found_emojis:
            found_emojis.append(emoji)
            if len(found_emojis) >= 5:
                break
    
    return ''.join(found_emojis[:5])

def main():
    print("Loading loldle_extended_data.json...")
    with open('loldle_extended_data.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Found {len(data)} champions")
    
    updated_count = 0
    
    for champ_key, champion in data.items():
        name = champion['name']
        
        # Generate emoji sequence using full champion data
        emoji_seq = generate_emoji_from_champion(champion)
        
        # Update champion data
        old_emoji = champion.get('emoji', '')
        champion['emoji'] = emoji_seq
        
        if old_emoji != emoji_seq:
            updated_count += 1
            # Show what influenced the choice
            title = champion.get('title', '')
            tags = ', '.join(champion.get('tags', []))
            print(f"Updated {name} ({title})")
            print(f"  Tags: {tags}")
            print(f"  Old: '{old_emoji}' -> New: '{emoji_seq}'")
    
    # Save updated data
    with open('loldle_extended_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\nDone! Updated {updated_count} champions")
    print(f"All champions now have 5-emoji sequences based on appearance + abilities")

if __name__ == '__main__':
    main()
