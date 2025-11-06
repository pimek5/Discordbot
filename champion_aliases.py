"""
Champion name aliases for better recognition
Maps common abbreviations and nicknames to official champion names
"""

# Champion aliases dictionary - maps alias to official name
CHAMPION_ALIASES = {
    # Common abbreviations
    'asol': 'Aurelion Sol',
    'aph': 'Aphelios',
    'cait': 'Caitlyn',
    'cass': 'Cassiopeia',
    'cho': "Cho'Gath",
    'chogath': "Cho'Gath",
    'drmundo': 'Dr. Mundo',
    'mundo': 'Dr. Mundo',
    'j4': 'Jarvan IV',
    'jarvan': 'Jarvan IV',
    'jax': 'Jax',
    'kass': 'Kassadin',
    'kata': 'Katarina',
    'kayle': 'Kayle',
    'kayn': 'Kayn',
    'kennen': 'Kennen',
    'kha': "Kha'Zix",
    'khazix': "Kha'Zix",
    'kog': "Kog'Maw",
    'kogmaw': "Kog'Maw",
    'lb': 'LeBlanc',
    'leblanc': 'LeBlanc',
    'lee': 'Lee Sin',
    'leesin': 'Lee Sin',
    'liss': 'Lissandra',
    'lux': 'Lux',
    'malph': 'Malphite',
    'mf': 'Miss Fortune',
    'missfortune': 'Miss Fortune',
    'morde': 'Mordekaiser',
    'morg': 'Morgana',
    'naut': 'Nautilus',
    'nida': 'Nidalee',
    'noc': 'Nocturne',
    'nunu': 'Nunu & Willump',
    'ori': 'Orianna',
    'panth': 'Pantheon',
    'reksai': "Rek'Sai",
    'renek': 'Renekton',
    'seju': 'Sejuani',
    'shen': 'Shen',
    'shyv': 'Shyvana',
    'tf': 'Twisted Fate',
    'twistedfate': 'Twisted Fate',
    'trundle': 'Trundle',
    'trynd': 'Tryndamere',
    'trynda': 'Tryndamere',
    'tk': 'Tahm Kench',
    'tahmkench': 'Tahm Kench',
    'tahm': 'Tahm Kench',
    'tali': 'Taliyah',
    'twitch': 'Twitch',
    'udyr': 'Udyr',
    'varus': 'Varus',
    'veigar': 'Veigar',
    'velkoz': "Vel'Koz",
    'vel': "Vel'Koz",
    'vi': 'Vi',
    'vik': 'Viktor',
    'vlad': 'Vladimir',
    'voli': 'Volibear',
    'ww': 'Warwick',
    'xin': 'Xin Zhao',
    'xinzhao': 'Xin Zhao',
    'yas': 'Yasuo',
    'yone': 'Yone',
    'zac': 'Zac',
    'zed': 'Zed',
    'ziggs': 'Ziggs',
    'zilean': 'Zilean',
    'zoe': 'Zoe',
    'zyra': 'Zyra',
    
    # Multiple word champions (without spaces)
    'aurelionsol': 'Aurelion Sol',
    'jarvaniv': 'Jarvan IV',
    'leesin': 'Lee Sin',
    'masteryi': 'Master Yi',
    'missfortune': 'Miss Fortune',
    'nunuwillump': 'Nunu & Willump',
    'tahmkench': 'Tahm Kench',
    'twistedfate': 'Twisted Fate',
    'xinzhao': 'Xin Zhao',
    
    # Honorable mentions with apostrophes
    'kaisa': "Kai'Sa",
    'khazix': "Kha'Zix",
    'kogmaw': "Kog'Maw",
    'reksai': "Rek'Sai",
    'velkoz': "Vel'Koz",
    'chogath': "Cho'Gath",
    
    # Additional common typos/variations
    'reng': 'Rengar',
    'renga': 'Rengar',
    'yi': 'Master Yi',
    'akshan': 'Akshan',
    'anivia': 'Anivia',
    'annie': 'Annie',
    'azir': 'Azir',
    'bard': 'Bard',
    'blitz': 'Blitzcrank',
    'brand': 'Brand',
    'braum': 'Braum',
    'corki': 'Corki',
    'darius': 'Darius',
    'diana': 'Diana',
    'draven': 'Draven',
    'ekko': 'Ekko',
    'elise': 'Elise',
    'eve': 'Evelynn',
    'ezreal': 'Ezreal',
    'ez': 'Ezreal',
    'fiddle': 'Fiddlesticks',
    'fiora': 'Fiora',
    'fizz': 'Fizz',
    'garen': 'Garen',
    'gnar': 'Gnar',
    'gragas': 'Gragas',
    'graves': 'Graves',
    'gwen': 'Gwen',
    'hecarim': 'Hecarim',
    'hec': 'Hecarim',
    'heimer': 'Heimerdinger',
    'illaoi': 'Illaoi',
    'irelia': 'Irelia',
    'ivern': 'Ivern',
    'janna': 'Janna',
    'jhin': 'Jhin',
    'jinx': 'Jinx',
    'kalista': 'Kalista',
    'karma': 'Karma',
    'karthus': 'Karthus',
    'kindred': 'Kindred',
    'kled': 'Kled',
    'ksante': "K'Sante",
    'lillia': 'Lillia',
    'lulu': 'Lulu',
    'malz': 'Malzahar',
    'malzahar': 'Malzahar',
    'maokai': 'Maokai',
    'milio': 'Milio',
    'naafiri': 'Naafiri',
    'nami': 'Nami',
    'neeko': 'Neeko',
    'nasus': 'Nasus',
    'olaf': 'Olaf',
    'ornn': 'Ornn',
    'pike': 'Pyke',
    'qiyana': 'Qiyana',
    'quinn': 'Quinn',
    'rakan': 'Rakan',
    'rammus': 'Rammus',
    'rell': 'Rell',
    'renata': 'Renata Glasc',
    'renataglasc': 'Renata Glasc',
    'riven': 'Riven',
    'rumble': 'Rumble',
    'ryze': 'Ryze',
    'samira': 'Samira',
    'senna': 'Senna',
    'seraphine': 'Seraphine',
    'sera': 'Seraphine',
    'sett': 'Sett',
    'shaco': 'Shaco',
    'sion': 'Sion',
    'sivir': 'Sivir',
    'skarner': 'Skarner',
    'sona': 'Sona',
    'soraka': 'Soraka',
    'swain': 'Swain',
    'sylas': 'Sylas',
    'syndra': 'Syndra',
    'talon': 'Talon',
    'taric': 'Taric',
    'teemo': 'Teemo',
    'thresh': 'Thresh',
    'tristana': 'Tristana',
    'trist': 'Tristana',
    'urgot': 'Urgot',
    'vex': 'Vex',
    'vayne': 'Vayne',
    'viego': 'Viego',
    'xerath': 'Xerath',
    'xayah': 'Xayah',
    'yorick': 'Yorick',
    'yumi': 'Yuumi',
    'yuumi': 'Yuumi',
    'zeri': 'Zeri',
}

def normalize_champion_name(name: str, valid_champions: set) -> str:
    """
    Normalize champion name using aliases and fuzzy matching.
    Returns the official champion name or None if not found.
    """
    # Remove extra whitespace and convert to lowercase
    name_lower = name.strip().lower()
    
    # Check direct match (case-insensitive)
    for champion in valid_champions:
        if champion.lower() == name_lower:
            return champion
    
    # Check aliases
    if name_lower in CHAMPION_ALIASES:
        return CHAMPION_ALIASES[name_lower]
    
    # Try removing spaces/special characters
    name_clean = name_lower.replace(' ', '').replace("'", '').replace('.', '')
    
    # Check aliases again with cleaned name
    if name_clean in CHAMPION_ALIASES:
        return CHAMPION_ALIASES[name_clean]
    
    # Check if cleaned name matches any champion
    for champion in valid_champions:
        champion_clean = champion.lower().replace(' ', '').replace("'", '').replace('.', '')
        if champion_clean == name_clean:
            return champion
    
    return None
