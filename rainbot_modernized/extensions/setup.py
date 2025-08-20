import discord
from discord.ext import commands
from core.database import Database
from utils.decorators import require_permission, PermissionLevel
from utils.helpers import create_embed
import asyncio


class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.group(invoke_without_command=True)
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def setup(self, ctx):
        f"""Configure bot settings with interactive setup wizards
        
        **Usage:** `{ctx.prefix}setup [option]`
        **Available Options:**
        • `{ctx.prefix}setup quick` - Basic configuration
        • `{ctx.prefix}setup automod` - Auto-moderation settings
        • `{ctx.prefix}setup logging` - Logging channels
        
        Run without options to see the interactive menu.
        """
        embed = create_embed(
            title="🛠️ Rainbot Setup",
            description="Choose a setup option:",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="📋 Quick Setup",
            value=f"`{ctx.prefix}setup quick` - Basic configuration",
            inline=False,
        )
        embed.add_field(
            name="🔧 Auto-moderation",
            value=f"`{ctx.prefix}setup automod` - Configure automod",
            inline=False,
        )
        embed.add_field(
            name="📝 Logging",
            value=f"`{ctx.prefix}setup logging` - Set up logging",
            inline=False,
        )
        embed.add_field(
            name="🔒 Permissions",
            value=f"`{ctx.prefix}setup permissions` - Configure perms",
            inline=False,
        )
        embed.add_field(
            name="👀 View Config",
            value=f"`{ctx.prefix}viewconfig` - Current settings",
            inline=False,
        )
        await ctx.send(embed=embed)

    @setup.command()
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def quick(self, ctx):
        f"""Run a quick setup to configure basic bot settings
        
        **Usage:** `{ctx.prefix}setup quick`
        **What it sets up:**
        • Command prefix
        • Mute role (creates if needed)
        • Moderation log channel
        • Basic logging settings
        
        Perfect for getting started quickly with essential features.
        """
        embed = create_embed(
            title="🚀 Quick Setup",
            description="Let's get started!",
            color=discord.Color.green(),
        )
        msg = await ctx.send(embed=embed)

        # Prefix setup
        embed.description = "What prefix would you like? (e.g., !, ?, >, r!)"
        await msg.edit(embed=embed)

        try:
            prefix_msg = await self.bot.wait_for(
                "message",
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                timeout=60,
            )
            prefix = prefix_msg.content.strip()
            await self.db.update_guild_config(ctx.guild.id, {"prefix": prefix})
        except asyncio.TimeoutError:
            from config.config import config

            prefix = config.bot.default_prefix

        # Mute role setup
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if not mute_role:
            mute_role = await ctx.guild.create_role(name="Muted", reason="Setup wizard")
            for channel in ctx.guild.channels:
                await channel.set_permissions(
                    mute_role, send_messages=False, speak=False
                )

        await self.db.update_guild_config(ctx.guild.id, {"mute_role": mute_role.id})

        # Mod log channel
        mod_log = await ctx.guild.create_text_channel("mod-logs", reason="Setup wizard")
        await self.db.update_guild_config(ctx.guild.id, {"mod_log_channel": mod_log.id})

        embed = create_embed(
            title="✅ Quick Setup Complete!",
            description=f"Prefix: `{prefix}`\nMute Role: {mute_role.mention}\nMod Logs: {mod_log.mention}",
            color=discord.Color.green(),
        )
        await msg.edit(embed=embed)

    @setup.command()
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def automod(self, ctx):
        f"""Configure automatic moderation features and filters
        
        **Usage:** `{ctx.prefix}setup automod`
        **Features you can toggle:**
        • Spam detection
        • Invite link blocking
        • Bad word filtering
        • Mass mention protection
        • Caps lock detection
        • NSFW image detection
        • Duplicate message prevention
        
        Interactive menu with emoji reactions to toggle features.
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        automod = config.get("automod", {})

        options = {
            "🔄": ("spam", "Spam Detection"),
            "🔗": ("invites", "Invite Links"),
            "🤬": ("badwords", "Bad Words"),
            "📢": ("mass_mentions", "Mass Mentions"),
            "🔊": ("caps", "Caps Lock"),
            "🖼️": ("nsfw", "NSFW Images"),
            "📝": ("duplicates", "Duplicate Messages"),
        }

        embed = create_embed(
            title="🛡️ Auto-moderation Setup", color=discord.Color.orange()
        )
        for emoji, (key, name) in options.items():
            status = "✅ Enabled" if automod.get(key, False) else "❌ Disabled"
            embed.add_field(name=f"{emoji} {name}", value=status, inline=True)

        embed.set_footer(text="React to toggle features")
        msg = await ctx.send(embed=embed)

        for emoji in options:
            await msg.add_reaction(emoji)

    @setup.command()
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def logging(self, ctx):
        """Set up logging channels for different server events"""
        embed = create_embed(
            title="📝 Logging Setup",
            description="Set up logging channels for different events",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Commands",
            value=f"`{ctx.prefix}setup logging mod` - Moderation logs\n`{ctx.prefix}setup logging member` - Member logs\n`{ctx.prefix}setup logging message` - Message logs",
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.command()
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def viewconfig(self, ctx):
        f"""Display the current bot configuration for this server
        
        **Usage:** `{ctx.prefix}viewconfig`
        **Shows:**
        • Command prefix
        • Mute role
        • Log channels
        • Auto-moderation settings
        • Permission levels
        
        Use this to review your current settings.
        """
        config = await self.db.get_guild_config(ctx.guild.id)

        embed = create_embed(title="⚙️ Server Configuration", color=discord.Color.blue())
        from config.config import config as bot_config

        embed.add_field(
            name="Prefix",
            value=config.get("prefix", bot_config.bot.default_prefix),
            inline=True,
        )

        mute_role_id = config.get("mute_role")
        mute_role = ctx.guild.get_role(mute_role_id) if mute_role_id else None
        embed.add_field(
            name="Mute Role",
            value=mute_role.mention if mute_role else "Not set",
            inline=True,
        )

        mod_log_id = config.get("mod_log_channel")
        mod_log = ctx.guild.get_channel(mod_log_id) if mod_log_id else None
        embed.add_field(
            name="Mod Logs",
            value=mod_log.mention if mod_log else "Not set",
            inline=True,
        )

        await ctx.send(embed=embed)

    @commands.command()
    @require_permission(PermissionLevel.SERVER_MANAGER)
    async def resetconfig(self, ctx):
        f"""Reset all bot settings to default values for this server
        
        **Usage:** `{ctx.prefix}resetconfig`
        **⚠️ Warning:** This will reset:
        • All configuration settings
        • Auto-moderation settings
        • Log channel assignments
        • Permission level assignments
        
        This action cannot be undone!
        """
        await self.db.reset_guild_config(ctx.guild.id)
        embed = create_embed(
            title="🔄 Configuration Reset",
            description="All settings have been reset to defaults",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Setup(bot))
