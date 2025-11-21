"""
Permission helpers for admin commands
"""

import discord

# Admin role ID
ADMIN_ROLE_ID = 318104006385729538


def has_admin_permissions(interaction: discord.Interaction) -> bool:
    """Check if user has admin permissions (Administrator permission OR specific admin role)"""
    if not interaction.guild:
        return False
    
    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        return False
    
    # Check for Administrator permission
    if member.guild_permissions.administrator:
        return True
    
    # Check for specific admin role
    return any(role.id == ADMIN_ROLE_ID for role in member.roles)
