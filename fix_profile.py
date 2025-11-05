"""Fix profile_commands.py mastery section"""

with open('profile_commands.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace mastery statistics section
old_section = '''            # Mastery statistics
            total_champs = len(champ_stats)
            level_10_plus = sum(1 for c in champ_stats if c['level'] >= 10)
            level_7_plus = sum(1 for c in champ_stats if c['level'] >= 7)
            level_5_plus = sum(1 for c in champ_stats if c['level'] >= 5)
            total_points = sum(c['score'] for c in champ_stats)
            chests_earned = sum(1 for c in champ_stats if c.get('chest_granted'))
            
            if total_points >= 1000000:
                total_str = f"{total_points/1000000:.2f}M"
            else:
                total_str = f"{total_points:,}"
            
            mastery_lines = [
                f"💎 **{level_10_plus}x** Mastery 10",
                f"⭐ **{level_7_plus}x** Mastery 7+",
                f"🌟 **{level_5_plus}x** Mastery 5+",
                f"📊 **{total_str}** total points",
                f"📦 **{chests_earned}/{total_champs}** chests"
            ]
            
            embed.add_field(
                name="Mastery Statistics",
                value="\n".join(mastery_lines),
                inline=True
            )'''

new_section = '''            # Mastery statistics
            total_champs = len(champ_stats)
            level_10_plus = sum(1 for c in champ_stats if c['level'] >= 10)
            total_points = sum(c['score'] for c in champ_stats)
            avg_points = total_points // total_champs if total_champs > 0 else 0
            
            if avg_points >= 1000:
                avg_str = f"{avg_points/1000:.1f}k"
            else:
                avg_str = f"{avg_points:,}"
            
            mastery_lines = [
                f"**{level_10_plus}x** Level 10+",
                f"**{total_points:,}** Total Points",
                f"**{avg_str}** Avg/Champ"
            ]
            
            embed.add_field(
                name="Mastery Statistics",
                value="\n".join(mastery_lines),
                inline=True
            )
            
            # Recently Played
            if recently_played and len(recently_played) > 0:
                recent_lines = []
                unique_champs = []
                for game in recently_played:
                    champ = game['champion']
                    if champ not in unique_champs:
                        champ_emoji = get_champion_emoji(champ)
                        recent_lines.append(f"{champ_emoji} **{champ} - Today**")
                        unique_champs.append(champ)
                    if len(recent_lines) >= 3:
                        break
                
                embed.add_field(
                    name="Recently Played",
                    value="\n".join(recent_lines) if recent_lines else "No recent games",
                    inline=True
                )
            else:
                embed.add_field(
                    name="Recently Played",
                    value="No recent games",
                    inline=True
                )'''

if old_section in content:
    content = content.replace(old_section, new_section)
    with open('profile_commands.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ Profile updated successfully")
else:
    print("❌ Could not find section to replace")
    print("Searching for alternative...")
    # Try without emoji
    if "level_10_plus" in content and "level_7_plus" in content:
        print("Found mastery section, checking lines...")
