"""
Modern bot implementation with enhanced error handling and features
"""

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import discord
from discord.ext import commands
import aiohttp

from config.config import config
from utils.constants import COLORS, EMOJIS
from .database import Database
from .permissions import PermissionManager
from utils.helpers import format_duration


class RainBot(commands.Bot):
    """
    Modern Discord bot with enhanced features and error handling
    """

    def __init__(self):
        # Configure intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.guild_messages = True
        intents.guild_reactions = True

        super().__init__(
            command_prefix=self._get_prefix,
            intents=intents,
            help_command=None,  # We'll implement our own
            case_insensitive=True,
            strip_after_prefix=True,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, users=True, roles=False, replied_user=True
            ),
            max_messages=config.bot.max_messages,
            owner_ids=set(config.owner_ids) if config.owner_ids else None,
        )

        # Disable slash command syncing
        self.tree.sync = lambda guild=None: None

        # Core components
        self.db: Optional[Database] = None
        self.permissions: Optional[PermissionManager] = None
        self.session: Optional[aiohttp.ClientSession] = None

        # Bot state
        self.start_time = datetime.now(timezone.utc)
        self.logger = logging.getLogger("rainbot.core")

        # Statistics
        self.command_stats: Dict[str, int] = {}
        self.error_count = 0
        self.successful_commands = 0

        # Cache
        self._prefix_cache: Dict[int, str] = {}

    async def setup_hook(self):
        """Initialize bot components"""
        self.logger.info("Starting bot setup...")

        # Initialize database
        self.logger.info("Connecting to database...")
        self.db = Database()
        await self.db.connect()
        self.logger.info("✅ Database connection successful")

        # Initialize permissions
        self.permissions = PermissionManager(self.db)

        # Create HTTP session
        self.session = aiohttp.ClientSession()

        # Load extensions
        await self._load_extensions()

        self.logger.info("Bot setup completed successfully")

    async def _load_extensions(self):
        """Load all bot extensions"""
        import os

        extensions_dir = "extensions"
        loaded = 0
        failed = 0

        for filename in os.listdir(extensions_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                extension = f"{extensions_dir}.{filename[:-3]}"
                try:
                    await self.load_extension(extension)
                    self.logger.info(f"Loaded extension: {extension}")
                    loaded += 1
                except Exception as e:
                    self.logger.error(f"Failed to load {extension}: {e}")
                    failed += 1

        self.logger.info(f"Extensions loaded: {loaded}, failed: {failed}")

    async def _get_prefix(self, bot, message: discord.Message) -> List[str]:
        """Get command prefix for a guild"""
        if not message.guild:
            return [config.bot.default_prefix]

        # Check cache first
        if message.guild.id in self._prefix_cache:
            prefix = self._prefix_cache[message.guild.id]
        else:
            # Get from database
            guild_config = await self.db.get_guild_config(message.guild.id)
            prefix = guild_config.get("prefix", config.bot.default_prefix)
            self._prefix_cache[message.guild.id] = prefix

        return commands.when_mentioned_or(prefix)(bot, message)

    async def on_ready(self):
        """Bot ready event"""
        self.logger.info(f"Bot ready! Logged in as {self.user}")
        self.logger.info(
            f"Serving {len(self.guilds)} guilds with {len(self.users)} users"
        )

        # Set status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} servers | {config.bot.default_prefix}help",
        )
        await self.change_presence(activity=activity)

        # Send startup notification
        if config.channels.owner_log_channel:
            channel = self.get_channel(config.channels.owner_log_channel)
            if channel:
                embed = discord.Embed(
                    title=f"{EMOJIS['success']} Bot Started",
                    description=f"Successfully started and ready to serve!",
                    color=COLORS["success"],
                    timestamp=datetime.now(timezone.utc),
                )
                embed.add_field(name="Guilds", value=len(self.guilds), inline=True)
                embed.add_field(name="Users", value=len(self.users), inline=True)
                embed.add_field(
                    name="Latency", value=f"{self.latency*1000:.0f}ms", inline=True
                )

                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass

    async def on_guild_join(self, guild: discord.Guild):
        """Handle guild join"""
        self.logger.info(f"Joined guild: {guild.name} ({guild.id})")

        # Clear prefix cache for this guild
        self._prefix_cache.pop(guild.id, None)

        # Send welcome message to system channel
        if (
            guild.system_channel
            and guild.system_channel.permissions_for(guild.me).send_messages
        ):
            embed = await self._create_welcome_embed(guild)
            try:
                await guild.system_channel.send(embed=embed)
            except discord.HTTPException:
                pass

        # Log to owner channel
        if config.channels.guild_join_channel:
            channel = self.get_channel(config.channels.guild_join_channel)
            if channel:
                embed = discord.Embed(
                    title=f"{EMOJIS['success']} Joined Guild",
                    color=COLORS["success"],
                    timestamp=datetime.now(timezone.utc),
                )
                embed.add_field(name="Name", value=guild.name, inline=True)
                embed.add_field(name="ID", value=guild.id, inline=True)
                embed.add_field(name="Members", value=guild.member_count, inline=True)
                embed.add_field(name="Owner", value=str(guild.owner), inline=True)

                if guild.icon:
                    embed.set_thumbnail(url=guild.icon.url)

                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass

    async def on_guild_remove(self, guild: discord.Guild):
        """Handle guild leave"""
        self.logger.info(f"Left guild: {guild.name} ({guild.id})")

        # Clear caches
        self._prefix_cache.pop(guild.id, None)

        # Log to owner channel
        if config.channels.guild_leave_channel:
            channel = self.get_channel(config.channels.guild_leave_channel)
            if channel:
                embed = discord.Embed(
                    title=f"{EMOJIS['error']} Left Guild",
                    color=COLORS["error"],
                    timestamp=datetime.now(timezone.utc),
                )
                embed.add_field(name="Name", value=guild.name, inline=True)
                embed.add_field(name="ID", value=guild.id, inline=True)
                embed.add_field(name="Members", value=guild.member_count, inline=True)

                try:
                    await channel.send(embed=embed)
                except discord.HTTPException:
                    pass

    async def on_command(self, ctx: commands.Context):
        """Handle command invocation"""
        command_name = ctx.command.qualified_name
        self.command_stats[command_name] = self.command_stats.get(command_name, 0) + 1

        self.logger.debug(
            f"Command invoked: {command_name} by {ctx.author} in {ctx.guild}"
        )

    async def on_command_completion(self, ctx: commands.Context):
        """Handle successful command completion"""
        self.successful_commands += 1

        # Add success reaction
        try:
            await ctx.message.add_reaction(EMOJIS["success"])
        except discord.HTTPException:
            pass

    async def mute(
        self,
        guild_id: int,
        user_id: int,
        duration: Optional[int] = None,
        reason: str = "No reason",
    ):
        """Mute a user"""
        guild = self.get_guild(guild_id)
        if not guild:
            return

        member = guild.get_member(user_id)
        if not member:
            return

        # Get or create mute role
        mute_role = discord.utils.get(guild.roles, name="Muted")
        if not mute_role:
            mute_role = await guild.create_role(
                name="Muted",
                color=discord.Color.greyple(),
                reason="Auto-created mute role",
            )

            # Set permissions for all channels
            for channel in guild.channels:
                try:
                    if isinstance(channel, discord.TextChannel):
                        await channel.set_permissions(mute_role, send_messages=False)
                    elif isinstance(channel, discord.VoiceChannel):
                        await channel.set_permissions(mute_role, speak=False)
                except discord.Forbidden:
                    pass

        # Add mute role
        await member.add_roles(mute_role, reason=reason)

        # Schedule unmute if duration provided
        if duration:
            await asyncio.sleep(duration)
            await self.unmute(guild_id, user_id, "Auto unmute")

    async def unmute(self, guild_id: int, user_id: int, reason: str = "No reason"):
        """Unmute a user"""
        guild = self.get_guild(guild_id)
        if not guild:
            return

        member = guild.get_member(user_id)
        if not member:
            return

        mute_role = discord.utils.get(guild.roles, name="Muted")
        if mute_role and mute_role in member.roles:
            await member.remove_roles(mute_role, reason=reason)

    async def ban(
        self,
        guild_id: int,
        user_id: int,
        duration: Optional[int] = None,
        reason: str = "No reason",
    ):
        """Ban a user"""
        guild = self.get_guild(guild_id)
        if not guild:
            return

        user = self.get_user(user_id) or await self.fetch_user(user_id)
        if not user:
            return

        await guild.ban(user, reason=reason, delete_message_days=1)

        # Schedule unban if duration provided
        if duration:
            await asyncio.sleep(duration)
            await self.unban(guild_id, user_id, "Auto unban")

    async def unban(self, guild_id: int, user_id: int, reason: str = "No reason"):
        """Unban a user"""
        guild = self.get_guild(guild_id)
        if not guild:
            return

        user = self.get_user(user_id) or await self.fetch_user(user_id)
        if not user:
            return

        try:
            await guild.unban(user, reason=reason)
        except discord.NotFound:
            pass  # User not banned

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Enhanced error handling"""
        self.error_count += 1

        # Add error reaction
        try:
            await ctx.message.add_reaction(EMOJIS["error"])
        except discord.HTTPException:
            pass

        # Get original error
        error = getattr(error, "original", error)

        # Handle specific error types
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands

        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title=f"{EMOJIS['error']} Missing Required Argument",
                description=f"Missing required argument: `{error.param.name}`",
                color=COLORS["error"],
            )
            embed.add_field(
                name="Usage",
                value=f"`{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`",
                inline=False,
            )
            await ctx.send(embed=embed, ephemeral=True)

        elif isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title=f"{EMOJIS['error']} Invalid Argument",
                description=str(error),
                color=COLORS["error"],
            )
            await ctx.send(embed=embed, ephemeral=True)

        elif isinstance(error, commands.MissingPermissions):
            perms = ", ".join(error.missing_permissions)
            embed = discord.Embed(
                title=f"{EMOJIS['error']} Missing Permissions",
                description=f"You need the following permissions: {perms}",
                color=COLORS["error"],
            )
            await ctx.send(embed=embed, ephemeral=True)

        elif isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(error.missing_permissions)
            embed = discord.Embed(
                title=f"{EMOJIS['error']} Bot Missing Permissions",
                description=f"I need the following permissions: {perms}",
                color=COLORS["error"],
            )
            await ctx.send(embed=embed, ephemeral=True)

        elif isinstance(error, commands.CheckFailure):
            embed = discord.Embed(
                title=f"{EMOJIS['error']} Check Failed",
                description="You don't have permission to use this command.",
                color=COLORS["error"],
            )
            await ctx.send(embed=embed, ephemeral=True)

        elif isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title=f"{EMOJIS['warning']} Command on Cooldown",
                description=f"Try again in {format_duration(error.retry_after)}",
                color=COLORS["warning"],
            )
            await ctx.send(embed=embed, ephemeral=True)

        elif isinstance(error, discord.Forbidden):
            embed = discord.Embed(
                title=f"{EMOJIS['error']} Permission Denied",
                description="I don't have permission to perform this action",
                color=COLORS["error"],
            )
            await ctx.send(embed=embed, ephemeral=True)

        elif isinstance(error, discord.HTTPException) and error.status == 429:
            # Rate limit error - log but don't show to user
            self.logger.warning(f"Rate limited: {error}")
            return

        else:
            # Log unexpected errors
            self.logger.error(f"Unexpected error in {ctx.command}: {error}")
            self.logger.error(traceback.format_exc())

            # Send generic error message
            embed = discord.Embed(
                title=f"{EMOJIS['error']} An Error Occurred",
                description="An unexpected error occurred. Please try again later.",
                color=COLORS["error"],
            )

            if config.is_development:
                embed.add_field(
                    name="Debug Info",
                    value=f"```py\n{type(error).__name__}: {error}\n```",
                    inline=False,
                )

            await ctx.send(embed=embed, ephemeral=True)

            # Report to error channel
            await self._report_error(ctx, error)

    async def _report_error(self, ctx: commands.Context, error: Exception):
        """Report error to error channel"""
        if not config.channels.error_channel:
            return

        channel = self.get_channel(config.channels.error_channel)
        if not channel:
            return

        embed = discord.Embed(
            title=f"{EMOJIS['error']} Command Error",
            color=COLORS["error"],
            timestamp=datetime.now(timezone.utc),
        )

        embed.add_field(name="Command", value=ctx.command.qualified_name, inline=True)
        embed.add_field(
            name="User", value=f"{ctx.author} ({ctx.author.id})", inline=True
        )
        embed.add_field(
            name="Guild", value=f"{ctx.guild.name} ({ctx.guild.id})", inline=True
        )
        embed.add_field(name="Channel", value=f"#{ctx.channel.name}", inline=True)

        error_text = f"{type(error).__name__}: {error}"
        if len(error_text) > 1024:
            error_text = error_text[:1021] + "..."

        embed.add_field(name="Error", value=f"```py\n{error_text}\n```", inline=False)

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    async def _create_welcome_embed(self, guild: discord.Guild) -> discord.Embed:
        """Create welcome embed for new guilds"""
        embed = discord.Embed(
            title=f"{EMOJIS['success']} Thanks for adding RainBot!",
            description="A modern Discord moderation bot with powerful features",
            color=COLORS["primary"],
        )

        embed.add_field(
            name=f"{EMOJIS['settings']} Quick Setup",
            value=f"• Use `!!setup` to configure the bot\n"
            f"• Use `!!help` to see all commands\n"
            f"• Use `!!config` to view settings",
            inline=False,
        )

        embed.add_field(
            name=f"{EMOJIS['moderation']} Features",
            value="• Advanced moderation tools\n"
            "• Intelligent auto-moderation\n"
            "• Comprehensive logging\n"
            "• Custom commands & tags\n"
            "• Reaction roles & giveaways",
            inline=False,
        )

        embed.add_field(
            name=f"{EMOJIS['help']} Support",
            value="[Support Server](https://discord.gg/support) • "
            "[Documentation](https://docs.rainbot.gg) • "
            "[GitHub](https://github.com/rainbot/rainbot)",
            inline=False,
        )

        embed.set_footer(text=f"Guild ID: {guild.id}")
        return embed

    async def get_stats(self) -> Dict[str, Any]:
        """Get bot statistics"""
        uptime = datetime.now(timezone.utc) - self.start_time

        return {
            "guilds": len(self.guilds),
            "users": len(self.users),
            "uptime": uptime,
            "commands_used": sum(self.command_stats.values()),
            "successful_commands": self.successful_commands,
            "errors": self.error_count,
            "latency": round(self.latency * 1000, 2),
            "top_commands": sorted(
                self.command_stats.items(), key=lambda x: x[1], reverse=True
            )[:5],
        }

    async def close(self):
        """Clean shutdown"""
        self.logger.info("Shutting down bot...")

        if self.session:
            await self.session.close()

        if self.db:
            await self.db.close()

        await super().close()
        self.logger.info("Bot shutdown complete")
