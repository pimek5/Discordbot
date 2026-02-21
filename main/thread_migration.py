"""
Thread Migration System
Migrates threads from custom-skins channel to champion-specific channels
"""

import discord
from discord import app_commands
from discord.ext import commands
import re
import logging
from typing import Optional, Dict

logger = logging.getLogger("thread_migration")

# Source channel for custom skins
CUSTOM_SKINS_CHANNEL_ID = 1279916286612078665

# Champion -> Channel ID mapping
CHAMPION_CHANNELS = {
    'Aatrox': 1269174255988510721,
    'Ahri': 1269174837168050207,
    'Akali': 1269174869745074276,
    'Akshan': 1269174891303932005,
    'Alistar': 1269174970676940830,
    'Ambessa': 1437712066382135347,
    'Amumu': 1269174913332281435,
    'Anivia': 1269174994693390426,
    'Annie': 1269175021914427415,
    'Aphelios': 1269175048036417638,
    'Ashe': 1269175073445515326,
    'Aurelion Sol': 1269175103225200661,
    'Aurora': 1269175133151690835,
    'Azir': 1269175153808506974,
    'Bard': 1269175179523784714,
    "Bel'Veth": 1269175203968188549,
    'Blitzcrank': 1269175228118990869,
    'Brand': 1269175272884928512,
    'Braum': 1269175294757961829,
    'Briar': 1269175317398945925,
    'Caitlyn': 1269175340945772585,
    'Camille': 1269175366191419413,
    'Cassiopeia': 1269175391440867389,
    "Cho'Gath": 1269175411204554752,
    'Corki': 1269175432536920086,
    'Darius': 1269175459594371184,
    'Diana': 1269175486022549586,
    'Dr. Mundo': 1269175511331110942,
    'Draven': 1269175532629786674,
    'Ekko': 1269175576674172990,
    'Elise': 1269175555131965520,
    'Evelynn': 1269175602045390901,
    'Ezreal': 1269175625000812626,
    'Fiddlesticks': 1269168441349247027,
    'Fiora': 1269169089847492688,
    'Fizz': 1269169117496344576,
    'Galio': 1269169148618080337,
    'Gangplank': 1269169172085080095,
    'Garen': 1269169192494694430,
    'Gnar': 1269169213038137367,
    'Gragas': 1269169260857397249,
    'Graves': 1269169306663518268,
    'Gwen': 1269169331045011488,
    'Hecarim': 1269169352004079667,
    'Heimerdinger': 1269169371406667846,
    'Hwei': 1269169392420257792,
    'Illaoi': 1269169416885633036,
    'Irelia': 1269169438721314889,
    'Ivern': 1269169504282476655,
    'Janna': 1269169532686172161,
    'Jarvan IV': 1269169580602036298,
    'Jax': 1269169613015613491,
    'Jayce': 1269169639741722716,
    'Jhin': 1269169663124701194,
    'Jinx': 1269169686298365952,
    "K'Sante": 1264854344604581950,
    "Kai'Sa": 1264853629089611902,
    'Kalista': 1264853780055199797,
    'Karma': 1264853809163669600,
    'Karthus': 1264853950738202676,
    'Kassadin': 1264854000105295914,
    'Katarina': 1264854032795832404,
    'Kayle': 1264854144930287647,
    'Kayn': 1264854184956526653,
    'Kennen': 1264854213771657359,
    "Kha'Zix": 1264854245040062485,
    'Kindred': 1264854275511681136,
    'Kled': 1264854296004923402,
    "Kog'Maw": 1264854319354871839,
    'LeBlanc': 1264854385306107905,
    'Lee Sin': 1264854443204284476,
    'Leona': 1264854465496748072,
    'Lillia': 1264854487080632452,
    'Lissandra': 1264854514708512850,
    'Lucian': 1264854540704944168,
    'Lulu': 1264854561189789756,
    'Lux': 1264854586468991090,
    'Malphite': 1264854611421040732,
    'Malzahar': 1264854638453325844,
    'Maokai': 1264854664525119600,
    'Master Yi': 1264854712759615528,
    'Mel': 1437711775603753000,
    'Milio': 1264854736381673504,
    'Miss Fortune': 1264854773325107211,
    'Mordekaiser': 1264854800546402394,
    'Morgana': 1264854866811944970,
    'Naafiri': 1264854892267180149,
    'Nami': 1264854983778635797,
    'Nasus': 1264854983778635797,
    'Nautilus': 1264855023108620339,
    'Neeko': 1264855051684286494,
    'Nidalee': 1264855072316067872,
    'Nilah': 1264855092754907207,
    'Nocturne': 1264855114322153503,
    'Nunu & Willump': 1264855133733519380,
    'Olaf': 1264855153216061531,
    'Orianna': 1264855177358475287,
    'Ornn': 1264855197415505962,
    'Pantheon': 1263771982701400096,
    'Poppy': 1263772244807782444,
    'Pyke': 1264185603356889121,
    'Qiyana': 1263772376370511872,
    'Quinn': 1263772457379037204,
    'Rakan': 1263772489604009984,
    'Rammus': 1263772517319839774,
    "Rek'Sai": 1263772559040712816,
    'Rell': 1263772595879284777,
    'Renata Glasc': 1263772714725019648,
    'Renekton': 1263772626158092368,
    'Rengar': 1263772663172829278,
    'Riven': 1263772739450437662,
    'Rumble': 1263772774481133680,
    'Ryze': 1263772801777795184,
    'Samira': 1263772840050823302,
    'Sejuani': 1263772885747499109,
    'Senna': 1263772920447111189,
    'Seraphine': 1263772952697110640,
    'Sett': 1263773004219940874,
    'Shaco': 1263773047328866377,
    'Shen': 1263773136692842497,
    'Shyvana': 1263773177163550771,
    'Singed': 1263773265021894696,
    'Sion': 1263773831793872946,
    'Sivir': 1263773855932092439,
    'Skarner': 1466370738037719316,
    'Smolder': 1437711329954893934,
    'Sona': 1263773885573234709,
    'Soraka': 1263773935468806205,
    'Swain': 1263773984017879153,
    'Sylas': 1263774013327409266,
    'Syndra': 1263774036325044318,
    'Tahm Kench': 1263774081543704667,
    'Taliyah': 1263774156604964990,
    'Talon': 1263774174703521844,
    'Taric': 1263774224703553546,
    'Teemo': 1263774277430280202,
    'Thresh': 1263774311127449661,
    'Tristana': 1263774356866338926,
    'Trundle': 1263774387471913013,
    'Tryndamere': 1263774418807820348,
    'Twisted Fate': 1263774455566569543,
    'Twitch': 1263774500181377075,
    'Udyr': 1263757874409111604,
    'Urgot': 1263757865680633966,
    'Varus': 1263757855668830289,
    'Vayne': 1263757844084424736,
    'Veigar': 1263757833791471688,
    "Vel'Koz": 1263757818456969256,
    'Vex': 1263757798588547153,
    'Vi': 1263757788136472618,
    'Viego': 1263757719266136064,
    'Viktor': 1263754678743863379,
    'Vladimir': 1263754710402465834,
    'Volibear': 1263754720162484244,
    'Warwick': 1263754738613096478,
    'Wukong': 1263755296296140833,
    'Xayah': 1263755281590915185,
    'Xerath': 1263755329217368124,
    'Xin Zhao': 1263755385815175168,
    'Yasuo': 1263755361383616552,
    'Yone': 1263755375493124178,
    'Yorick': 1263755428974563351,
    'Yunara': 1437711561493053450,
    'Yuumi': 1263764052824555541,
    'Zac': 1263755438462341222,
    'Zed': 1263755480568954920,
    'Zeri': 1263755489297305601,
    'Ziggs': 1263755562534043668,
    'Zilean': 1263755579932016660,
    'Zoe': 1263755550513172503,
    'Zyra': 1263755599758360637,
}


def extract_champion_from_title(title: str) -> Optional[str]:
    """Extract champion name from thread title.
    
    Looks for champion names in title (case insensitive).
    Returns the champion name if found, None otherwise.
    """
    title_lower = title.lower()
    
    # Check each champion (longest names first to avoid partial matches)
    sorted_champions = sorted(CHAMPION_CHANNELS.keys(), key=len, reverse=True)
    
    for champion in sorted_champions:
        if champion.lower() in title_lower:
            return champion
    
    return None


async def migrate_thread(thread: discord.Thread, target_channel_id: int, champion_name: str) -> bool:
    """Migrate a thread to target champion channel.
    
    Creates a new thread in target channel with:
    - Same name as original
    - Images from original thread
    - Link back to original thread
    """
    try:
        guild = thread.guild
        target_channel = guild.get_channel(target_channel_id)
        
        if not target_channel:
            logger.warning(f"Target channel {target_channel_id} not found for {champion_name}")
            return False
        
        # Get original thread messages
        messages = []
        async for message in thread.history(limit=100, oldest_first=True):
            messages.append(message)
        
        if not messages:
            logger.info(f"No messages in thread {thread.name}")
            return False
        
        # Collect images
        image_urls = []
        for msg in messages:
            for attachment in msg.attachments:
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    image_urls.append(attachment.url)
            # Check for embeds with images
            for embed in msg.embeds:
                if embed.image:
                    image_urls.append(embed.image.url)
                if embed.thumbnail:
                    image_urls.append(embed.thumbnail.url)
        
        # Create new thread in target channel
        new_thread = await target_channel.create_thread(
            name=thread.name,
            auto_archive_duration=10080,  # 7 days
            reason=f"Migrated from custom-skins by /migrate command"
        )
        
        # Post content
        content_parts = [f"📋 **Migrated from custom-skins**"]
        content_parts.append(f"🔗 Original thread: {thread.jump_url}")
        
        if image_urls:
            content_parts.append(f"\n📸 **Images from original thread:**")
            for i, url in enumerate(image_urls[:10], 1):  # Limit to 10 images
                content_parts.append(f"[Image {i}]({url})")
        
        await new_thread.send('\n'.join(content_parts))
        
        logger.info(f"✅ Migrated thread '{thread.name}' to {champion_name} channel")
        return True
    
    except Exception as e:
        logger.error(f"❌ Failed to migrate thread '{thread.name}': {e}")
        return False


class ThreadMigrationCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="migrate", description="Migrate threads from custom-skins to champion channels")
    @app_commands.checks.has_permissions(administrator=True)
    async def migrate_threads(self, interaction: discord.Interaction):
        """Scan custom-skins channel and migrate threads to champion-specific channels"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            guild = interaction.guild
            source_channel = guild.get_channel(CUSTOM_SKINS_CHANNEL_ID)
            
            if not source_channel:
                await interaction.followup.send("❌ Custom-skins channel not found!")
                return
            
            # Get all threads
            threads = []
            
            # Active threads
            for thread in source_channel.threads:
                threads.append(thread)
            
            # Archived threads
            async for thread in source_channel.archived_threads(limit=None):
                threads.append(thread)
            
            if not threads:
                await interaction.followup.send("ℹ️ No threads found in custom-skins channel.")
                return
            
            # Process threads
            migrated = 0
            skipped = 0
            errors = 0
            
            status_msg = await interaction.followup.send(f"🔄 Processing {len(threads)} threads...")
            
            for thread in threads:
                champion = extract_champion_from_title(thread.name)
                
                if not champion:
                    skipped += 1
                    logger.info(f"⏭️ Skipped '{thread.name}' - no champion found")
                    continue
                
                target_channel_id = CHAMPION_CHANNELS.get(champion)
                if not target_channel_id:
                    skipped += 1
                    logger.warning(f"⏭️ Skipped '{thread.name}' - no channel for {champion}")
                    continue
                
                success = await migrate_thread(thread, target_channel_id, champion)
                
                if success:
                    migrated += 1
                else:
                    errors += 1
                
                # Update status every 10 threads
                if (migrated + skipped + errors) % 10 == 0:
                    await status_msg.edit(content=f"🔄 Progress: {migrated} migrated, {skipped} skipped, {errors} errors...")
            
            # Final summary
            summary = (
                f"✅ **Migration Complete!**\n\n"
                f"📊 **Summary:**\n"
                f"✅ Migrated: {migrated}\n"
                f"⏭️ Skipped: {skipped}\n"
                f"❌ Errors: {errors}\n"
                f"📋 Total: {len(threads)}"
            )
            
            await status_msg.edit(content=summary)
            logger.info(f"Migration complete: {migrated}/{len(threads)} threads migrated")
        
        except Exception as e:
            logger.error(f"Migration command error: {e}")
            await interaction.followup.send(f"❌ Error during migration: {e}")


async def setup(bot: commands.Bot):
    """Setup function to add cog to bot"""
    await bot.add_cog(ThreadMigrationCommands(bot))
