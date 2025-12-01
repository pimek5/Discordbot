"""
LFG Configuration
=================
Central configuration file for the LFG system.
Edit these values to customize the LFG system for your server.
"""

# ================================
#    DISCORD CONFIGURATION
# ================================

# Channel where LFG profile list is displayed (with pagination)
LFG_PROFILES_CHANNEL_ID = 1445191553948717106

# Channel where LFG listings are posted (individual posts)
LFG_LISTINGS_CHANNEL_ID = 1445191553948717106  # Can be same or different

# Channel where LFG commands can be used (None = all channels)
LFG_COMMAND_CHANNEL_ID = None

# Role that can manage LFG listings (delete others' listings, etc.)
LFG_MODERATOR_ROLE_ID = None  # None = admins only

# Number of profiles per page in the profile list
PROFILES_PER_PAGE = 10


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
#    CUSTOM EMOJIS
# ================================

# Role emojis
ROLE_EMOJIS = {
    'TOP': '<:role_Toplane:1442837878257221716>',
    'JUNGLE': '<:role_Jungle:1442837824150831137>',
    'MIDDLE': '<:role_Midlane:1442837968564912250>',
    'BOTTOM': '<:role_Bottom:1442838024479182929>',
    'UTILITY': '<:role_Support:1442837923367223460>',
    'SUPPORT': '<:role_Support:1442837923367223460>',  # Alias
}

# Rank emojis
RANK_EMOJIS = {
    'IRON': '<:rank_Iron:1441318450797744138>',
    'BRONZE': '<:rank_Bronze:1441318441741975592>',
    'SILVER': '<:rank_Silver:1441318462071898132>',
    'GOLD': '<:rank_Gold:1441318447697887283>',
    'PLATINUM': '<:rank_Platinum:1441318460415152168>',
    'EMERALD': '<:rank_Emerald:1441318446175355052>',
    'DIAMOND': '<:rank_Diamond:1441318445084835941>',
    'MASTER': '<:rank_Master:1441318458943078410>',
    'GRANDMASTER': '<:rank_Grandmaster:1441318449447178272>',
    'CHALLENGER': '<:rank_Challenger:1441318443130294322>',
    'UNRANKED': '<:rank_Unranked:1445196807133986947>',
}

# Champion emojis (mapping champion IDs to custom emojis)
CHAMPION_EMOJIS = {
    1: '<:champ_Annie:1441318429272309810>',
    2: '<:champ_Olaf:1441318583769759785>',
    3: '<:champ_Galio:1441318469772509260>',
    4: '<:champ_TwistedFate:1441318648861167667>',
    5: '<:champ_XinZhao:1441318674366464060>',
    6: '<:champ_Urgot:1441318653491413013>',
    7: '<:champ_Leblanc:1441318528568524820>',
    8: '<:champ_Vladimir:1441318666401615894>',
    9: '<:champ_Fiddlesticks:1441318465762889738>',
    10: '<:champ_Kayle:1441318509039718400>',
    11: '<:champ_MasterYi:1441318560029872149>',
    12: '<:champ_Alistar:1441318424054861895>',
    13: '<:champ_Ryze:1441318608050589829>',
    14: '<:champ_Sion:1441318622554488852>',
    15: '<:champ_Sivir:1441318624307581008>',
    16: '<:champ_Soraka:1441318630133600266>',
    17: '<:champ_Teemo:1441318640585539625>',
    18: '<:champ_Tristana:1441318643282612306>',
    19: '<:champ_Warwick:1441318668968525854>',
    20: '<:champ_Nunu:1441318582112747550>',
    21: '<:champ_MissFortune:1441318565520081037>',
    22: '<:champ_Ashe:1441318432103731210>',
    23: '<:champ_Tryndamere:1441318646851829780>',
    24: '<:champ_Jax:1441318492757561434>',
    25: '<:champ_Morgana:1441318568544305152>',
    26: '<:champ_Zilean:1441318693207408671>',
    27: '<:champ_Singed:1441318620826304595>',
    28: '<:champ_Evelynn:1441318462806036500>',
    29: '<:champ_Twitch:1441318650240958576>',
    30: '<:champ_Karthus:1441318505088815204>',
    31: '<:champ_Chogath:1441318451489800274>',
    32: '<:champ_Amumu:1441318426688884736>',
    33: '<:champ_Rammus:1441318596855726210>',
    34: '<:champ_Anivia:1441318428114812979>',
    35: '<:champ_Shaco:1441318616225153034>',
    36: '<:champ_DrMundo:1441318458238177360>',
    37: '<:champ_Sona:1441318628975706212>',
    38: '<:champ_Kassadin:1441318506275536999>',
    39: '<:champ_Irelia:1441318485388034151>',
    40: '<:champ_Janna:1441318488873373706>',
    41: '<:champ_Gangplank:1441318470959763548>',
    42: '<:champ_Corki:1441318452827783260>',
    43: '<:champ_Karma:1441318503603900558>',
    44: '<:champ_Taric:1441318639419654255>',
    45: '<:champ_Veigar:1441318657744703538>',
    48: '<:champ_Trundle:1441318644532514887>',
    50: '<:champ_Swain:1441318631287033916>',
    51: '<:champ_Caitlyn:1441318446758494299>',
    53: '<:champ_Blitzcrank:1441318440546603028>',
    54: '<:champ_Malphite:1441318556137422948>',
    55: '<:champ_Katarina:1441318507605266585>',
    56: '<:champ_Nocturne:1441318580246286366>',
    57: '<:champ_Maokai:1441318558738026548>',
    58: '<:champ_Renekton:1441318602618961942>',
    59: '<:champ_JarvanIV:1441318491046019103>',
    60: '<:champ_Elise:1441318461325316167>',
    61: '<:champ_Orianna:1441318585141301340>',
    62: '<:champ_Wukong:1441318670440726600>',
    63: '<:champ_Brand:1441318442568515615>',
    64: '<:champ_LeeSin:1441318532649320459>',
    67: '<:champ_Vayne:1441318656490475635>',
    68: '<:champ_Rumble:1441318606938833067>',
    69: '<:champ_Cassiopeia:1441318450130845757>',
    72: '<:champ_Skarner:1441318626136428615>',
    74: '<:champ_Heimerdinger:1441318481424420905>',
    75: '<:champ_Nasus:1441318572126371943>',
    76: '<:champ_Nidalee:1441318576299573309>',
    77: '<:champ_Udyr:1441318652128268401>',
    78: '<:champ_Poppy:1441318588271832431>',
    79: '<:champ_Gragas:1441318475262988350>',
    80: '<:champ_Pantheon:1441318589548277748>',
    81: '<:champ_Ezreal:1441318464219385949>',
    82: '<:champ_Mordekaiser:1441318566908657704>',
    83: '<:champ_Yorick:1441318679236317255>',
    84: '<:champ_Akali:1441318420392968213>',
    85: '<:champ_Kennen:1441318512051093586>',
    86: '<:champ_Garen:1441318472628961320>',
    89: '<:champ_Leona:1441318547254022174>',
    90: '<:champ_Malzahar:1441318557647503391>',
    91: '<:champ_Talon:1441318638199115839>',
    92: '<:champ_Riven:1441318605630210058>',
    96: '<:champ_KogMaw:1441318525909078036>',
    98: '<:champ_Shen:1441318617806274630>',
    99: '<:champ_Lux:1441318553973424231>',
    101: '<:champ_Xerath:1441318673171091466>',
    102: '<:champ_Shyvana:1441318619710750741>',
    103: '<:champ_Ahri:1441318418795069440>',
    104: '<:champ_Graves:1441318476873596938>',
    105: '<:champ_Fizz:1441318468489318410>',
    106: '<:champ_Volibear:1441318667764633690>',
    107: '<:champ_Rengar:1441318604099424256>',
    110: '<:champ_Varus:1441318654749708318>',
    111: '<:champ_Nautilus:1441318573254381640>',
    112: '<:champ_Viktor:1441318665248313394>',
    113: '<:champ_Sejuani:1441318610537676810>',
    114: '<:champ_Fiora:1441318467125907537>',
    115: '<:champ_Ziggs:1441318691483680899>',
    117: '<:champ_Lulu:1441318552614338702>',
    119: '<:champ_Draven:1441318457026023455>',
    120: '<:champ_Hecarim:1441318480103346258>',
    121: '<:champ_Khazix:1441318513980477480>',
    122: '<:champ_Darius:1441318454236807168>',
    126: '<:champ_Jayce:1441318494309318818>',
    127: '<:champ_Lissandra:1441318550072721469>',
    131: '<:champ_Diana:1441318455470067812>',
    133: '<:champ_Quinn:1441318593806602322>',
    134: '<:champ_Syndra:1441318633975316602>',
    136: '<:champ_AurelionSol:1441318433391116408>',
    141: '<:champ_Kayn:1441318510335627295>',
    142: '<:champ_Zoe:1441318695354896467>',
    143: '<:champ_Zyra:1441318697074561054>',
    145: '<:champ_Kaisa:1441318500772872222>',
    147: '<:champ_Seraphine:1441318613465436231>',
    150: '<:champ_Gnar:1441318473807565062>',
    154: '<:champ_Zac:1441318684332130396>',
    157: '<:champ_Yasuo:1441318675583078411>',
    161: '<:champ_Velkoz:1441318659166310420>',
    163: '<:champ_Taliyah:1441318636458348545>',
    164: '<:champ_Camille:1441318448876486667>',
    166: '<:champ_Akshan:1441318422742040616>',
    200: '<:champ_Belveth:1441318438847905815>',
    201: '<:champ_Braum:1441318444178870312>',
    202: '<:champ_Jhin:1441318496238702613>',
    203: '<:champ_Kindred:1441318516484603977>',
    221: '<:champ_Zeri:1441318689478545469>',
    222: '<:champ_Jinx:1441318498549760020>',
    223: '<:champ_TahmKench:1441318635309105162>',
    233: '<:champ_Briar:1441318445550403634>',
    234: '<:champ_Viego:1441318663419465883>',
    235: '<:champ_Senna:1441318612072927263>',
    236: '<:champ_Lucian:1441318551297196123>',
    238: '<:champ_Zed:1441318686890786846>',
    240: '<:champ_Kled:1441318524529147964>',
    245: '<:champ_Ekko:1441318459093946470>',
    246: '<:champ_Qiyana:1441318592326144011>',
    254: '<:champ_Vi:1441318662048055296>',
    266: '<:champ_Aatrox:1441318416375091240>',
    267: '<:champ_Nami:1441318570972676096>',
    268: '<:champ_Azir:1441318435781873684>',
    350: '<:champ_Yuumi:1441318682516258926>',
    360: '<:champ_Samira:1441318609296162867>',
    412: '<:champ_Thresh:1441318641814470687>',
    420: '<:champ_Illaoi:1441318484159107212>',
    421: '<:champ_RekSai:1441318598206427210>',
    427: '<:champ_Ivern:1441318486553923635>',
    429: '<:champ_Kalista:1441318502118985749>',
    432: '<:champ_Bard:1441318437476634675>',
    497: '<:champ_Rakan:1441318595442245694>',
    498: '<:champ_Xayah:1441318671829045279>',
    516: '<:champ_Ornn:1441318586248462336>',
    517: '<:champ_Sylas:1441318632830271630>',
    518: '<:champ_Neeko:1441318574860796006>',
    523: '<:champ_Aphelios:1441318430706761830>',
    526: '<:champ_Rell:1441318599808651275>',
    555: '<:champ_Pyke:1441318590157426729>',
    711: '<:champ_Vex:1441318660642963466>',
    777: '<:champ_Yone:1441318677143355412>',
    875: '<:champ_Sett:1441318614987964427>',
    876: '<:champ_Lillia:1441318548352930012>',
    887: '<:champ_Gwen:1441318478379225168>',
    888: '<:champ_RenataGlask:1441318601016737792>',
    893: '<:champ_Ambessa:1441318425283792937>',
    895: '<:champ_Naafiri:1441318569789882449>',
    897: '<:champ_KSante:1441318527314296965>',
    901: '<:champ_Smolder:1441318627797106750>',
    902: '<:champ_Milio:1441318563792158830>',
    910: '<:champ_Hwei:1441318482980376576>',
    950: '<:champ_Mel:1441318562504642650>',
    999: '<:champ_Zaahen:1442809688042508420>',
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
    
    if LFG_PROFILES_CHANNEL_ID == 1445191553948717106:
        pass  # This is the correct channel ID
    
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
