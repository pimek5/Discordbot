"""Update profile_commands.py mastery section"""

with open('profile_commands.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Replace lines 483-508 (0-indexed so 482-507)
new_lines = [
    '            # Mastery statistics\n',
    '            total_champs = len(champ_stats)\n',
    '            level_10_plus = sum(1 for c in champ_stats if c[\'level\'] >= 10)\n',
    '            total_points = sum(c[\'score\'] for c in champ_stats)\n',
    '            avg_points = total_points // total_champs if total_champs > 0 else 0\n',
    '            avg_str = f"{avg_points/1000:.1f}k" if avg_points >= 1000 else f"{avg_points:,}"\n',
    '\n',
    '            mastery_lines = [\n',
    '                f"**{level_10_plus}x** Level 10+",\n',
    '                f"**{total_points:,}** Total Points",\n',
    '                f"**{avg_str}** Avg/Champ"\n',
    '            ]\n',
    '\n',
    '            embed.add_field(\n',
    '                name="Mastery Statistics",\n',
    '                value="\\n".join(mastery_lines),\n',
    '                inline=True\n',
    '            )\n',
    '\n',
    '            # Recently Played\n',
    '            if recently_played and len(recently_played) > 0:\n',
    '                recent_lines = []\n',
    '                unique_champs = []\n',
    '                for game in recently_played:\n',
    '                    champ = game[\'champion\']\n',
    '                    if champ not in unique_champs:\n',
    '                        champ_emoji = get_champion_emoji(champ)\n',
    '                        recent_lines.append(f"{champ_emoji} **{champ} - Today**")\n',
    '                        unique_champs.append(champ)\n',
    '                    if len(recent_lines) >= 3:\n',
    '                        break\n',
    '\n',
    '                embed.add_field(\n',
    '                    name="Recently Played",\n',
    '                    value="\\n".join(recent_lines) if recent_lines else "No recent games",\n',
    '                    inline=True\n',
    '                )\n',
    '            else:\n',
    '                embed.add_field(\n',
    '                    name="Recently Played",\n',
    '                    value="No recent games",\n',
    '                    inline=True\n',
    '                )\n',
    '\n',
]

# Replace the lines
lines[482:508] = new_lines

# Write back
with open('profile_commands.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("✅ Profile updated successfully!")
print(f"   - Updated Mastery Statistics (3 lines)")
print(f"   - Added Recently Played section")
