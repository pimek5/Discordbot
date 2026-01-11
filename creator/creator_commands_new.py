    # ==================== CONFIG COMMANDS ====================
    config_group = app_commands.Group(name="config", description="Configure server settings", parent=creator_group)
    
    @config_group.command(name="set-channel", description="Set notification channel for creator updates")
    @app_commands.describe(channel="Discord channel for notifications")
    async def config_set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the notification channel for this server"""
        if not has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ Only administrators can configure server settings!",
                ephemeral=True
            )
            return
        
        db = get_creator_db()
        guild_id = interaction.guild_id if interaction.guild else 0
        
        if db.set_guild_config(guild_id, notification_channel_id=channel.id):
            await interaction.response.send_message(
                f"✅ Notification channel set to {channel.mention}",
                ephemeral=True
            )
            logger.info("✅ Guild %s: notification channel set to %s", guild_id, channel.name)
        else:
            await interaction.response.send_message(
                "❌ Failed to save configuration",
                ephemeral=True
            )
    
    @config_group.command(name="set-webhook", description="Set webhook URL for external integrations")
    @app_commands.describe(webhook_url="Discord webhook URL or custom endpoint")
    async def config_set_webhook(self, interaction: discord.Interaction, webhook_url: str):
        """Set a webhook URL for receiving mod notifications"""
        if not has_admin_permissions(interaction):
            await interaction.response.send_message(
                "❌ Only administrators can configure server settings!",
                ephemeral=True
            )
            return
        
        # Basic validation
        if not (webhook_url.startswith('http://') or webhook_url.startswith('https://')):
            await interaction.response.send_message(
                "❌ Invalid webhook URL. Must start with http:// or https://",
                ephemeral=True
            )
            return
        
        db = get_creator_db()
        guild_id = interaction.guild_id if interaction.guild else 0
        
        if db.set_guild_config(guild_id, webhook_url=webhook_url):
            await interaction.response.send_message(
                f"✅ Webhook URL configured successfully",
                ephemeral=True
            )
            logger.info("✅ Guild %s: webhook URL configured", guild_id)
        else:
            await interaction.response.send_message(
                "❌ Failed to save webhook configuration",
                ephemeral=True
            )
    
    @config_group.command(name="view", description="View current server configuration")
    async def config_view(self, interaction: discord.Interaction):
        """View the current configuration for this server"""
        db = get_creator_db()
        guild_id = interaction.guild_id if interaction.guild else 0
        
        config = db.get_guild_config(guild_id)
        
        if not config:
            await interaction.response.send_message(
                "ℹ️ No configuration set yet for this server. Use `/creator config set-channel` to get started.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🔧 Server Configuration",
            color=discord.Color.blue()
        )
        
        if config.get('notification_channel_id'):
            embed.add_field(
                name="📢 Notification Channel",
                value=f"<#{config['notification_channel_id']}>",
                inline=False
            )
        else:
            embed.add_field(
                name="📢 Notification Channel",
                value="Not configured",
                inline=False
            )
        
        if config.get('webhook_url'):
            # Mask webhook URL for security
            masked_url = config['webhook_url'][:20] + "..." if len(config['webhook_url']) > 20 else config['webhook_url']
            embed.add_field(
                name="🪝 Webhook URL",
                value=f"`{masked_url}`",
                inline=False
            )
        else:
            embed.add_field(
                name="🪝 Webhook URL",
                value="Not configured",
                inline=False
            )
        
        embed.set_footer(text=f"Created: {config.get('created_at')}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # ==================== API KEY COMMANDS ====================
    api_group = app_commands.Group(name="api", description="Manage API keys", parent=creator_group)
    
    def _has_creator_role(interaction: discord.Interaction) -> bool:
        """Check if user has admin or Creator role"""
        if not interaction.guild:
            return False
        
        # Main guild check (hardcoded)
        MAIN_GUILD_ID = int(os.getenv('GUILD_ID', '0'))
        CREATOR_ROLE_ID = 1432859206142394452
        
        # Admin check
        if interaction.user.guild_permissions.administrator:
            return True
        
        # Creator role check
        creator_role = discord.utils.get(interaction.guild.roles, id=CREATOR_ROLE_ID)
        if creator_role and creator_role in interaction.user.roles:
            return True
        
        return False
    
    @api_group.command(name="generate-key", description="Generate a new API key")
    async def api_generate_key(self, interaction: discord.Interaction):
        """Generate a new API key for external integrations"""
        if not self._has_creator_role(interaction):
            await interaction.response.send_message(
                "❌ Only administrators and Creator role members can generate API keys!",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            db = get_creator_db()
            guild_id = interaction.guild_id if interaction.guild else 0
            user_id = interaction.user.id
            
            key, key_info = db.create_api_key(guild_id, user_id)
            
            if not key:
                await interaction.followup.send(
                    "❌ Failed to generate API key",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="🔑 API Key Generated",
                description="⚠️ **Save this key securely. You won't be able to see it again!**",
                color=discord.Color.green()
            )
            embed.add_field(
                name="📋 Your API Key",
                value=f"```{key}```",
                inline=False
            )
            embed.add_field(
                name="🏷️ Key Prefix",
                value=f"`{key_info['prefix']}`",
                inline=True
            )
            embed.add_field(
                name="⏰ Created",
                value=key_info['created_at'],
                inline=True
            )
            embed.add_field(
                name="💡 Usage",
                value="Include this key in the `Authorization: Bearer <key>` header when making API requests.",
                inline=False
            )
            embed.set_footer(text="⚠️ Treat this key like a password — do not share it!")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info("✅ API key generated for user %s in guild %s", user_id, guild_id)
        
        except Exception as e:
            logger.error("❌ Error generating API key: %s", e)
            await interaction.followup.send(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )
    
    @api_group.command(name="list-keys", description="List your API keys")
    async def api_list_keys(self, interaction: discord.Interaction):
        """List all your active API keys"""
        if not self._has_creator_role(interaction):
            await interaction.response.send_message(
                "❌ Only administrators and Creator role members can view API keys!",
                ephemeral=True
            )
            return
        
        db = get_creator_db()
        guild_id = interaction.guild_id if interaction.guild else 0
        user_id = interaction.user.id
        
        keys = db.get_api_keys(guild_id, user_id)
        
        if not keys:
            await interaction.response.send_message(
                "ℹ️ You don't have any active API keys yet. Use `/creator api generate-key` to create one.",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="🔑 Your API Keys",
            color=discord.Color.blue()
        )
        
        for key in keys:
            created = key.get('created_at', 'Unknown')
            last_used = key.get('last_used', 'Never')
            prefix = key.get('key_prefix', 'N/A')
            
            embed.add_field(
                name=f"Key #{key['id']}",
                value=f"**Prefix:** `{prefix}`\n**Created:** {created}\n**Last Used:** {last_used}",
                inline=False
            )
        
        embed.set_footer(text=f"Total: {len(keys)} key(s)")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @api_group.command(name="revoke-key", description="Revoke an API key")
    @app_commands.describe(key_id="The ID of the key to revoke")
    async def api_revoke_key(self, interaction: discord.Interaction, key_id: int):
        """Revoke an API key by ID"""
        if not self._has_creator_role(interaction):
            await interaction.response.send_message(
                "❌ Only administrators and Creator role members can revoke API keys!",
                ephemeral=True
            )
            return
        
        db = get_creator_db()
        
        if db.revoke_api_key(key_id):
            await interaction.response.send_message(
                f"✅ API key #{key_id} has been revoked.",
                ephemeral=True
            )
            logger.info("✅ API key %d revoked by user %s", key_id, interaction.user.id)
        else:
            await interaction.response.send_message(
                f"❌ Failed to revoke API key #{key_id}",
                ephemeral=True
            )
