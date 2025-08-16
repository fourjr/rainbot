import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import traceback
from datetime import datetime, timedelta
from time import time
from typing import Any, Dict, List, Optional, Union

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler

from ext import errors
from ext.database import DatabaseManager
from ext.errors import Underleveled
from ext.utility import format_timedelta, tryint
import config

# Initialize Rich console for better logging
console = Console()


class rainbot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True  # Enable message content intent for slash commands

        super().__init__(
            command_prefix=None,
            max_messages=10000,
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
            help_command=None,  # We'll use our custom help command
        )

        # Emoji constants
        self.accept = "✅"
        self.deny = "❌"
        self.loading = "⏳"
        self.success = "✅"
        self.error = "❌"
        self.warning = "⚠️"

        # Reporting channels (from env/config)
        self.ERROR_CHANNEL_ID = self._parse_int_env("error_channel_id")
        self.GUILD_JOIN_CHANNEL_ID = self._parse_int_env("guild_join_channel_id")
        self.GUILD_REMOVE_CHANNEL_ID = self._parse_int_env("guild_remove_channel_id")
        self.OWNER_LOG_CHANNEL_ID = self._parse_int_env("owner_log_channel_id")

        # Optional dev-only guild gate (for local testing)
        self.dev_guild_id = self._parse_int_env("dev_guild_id")

        self.dev_mode = os.name == "nt"
        self.session: Optional[aiohttp.ClientSession] = None
        self.start_time = datetime.utcnow()

        # Set up enhanced logging
        self.setup_logging()

        # Database and configuration
        self.db = None  # Will be initialized in setup_hook
        self.owners = self._parse_owner_ids(os.getenv("owners", ""))

        # Bot statistics
        self.command_usage = {}
        self.error_count = 0
        self.successful_commands = 0
        self._startup_announced = False

    def setup_logging(self) -> None:
        """Set up enhanced logging with Rich formatting"""
        self.logger = logging.getLogger("rainbot")

        if self.dev_mode:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

        # Use Rich handler for better console output
        rich_handler = RichHandler(
            console=console, show_time=True, show_path=False, markup=True, rich_tracebacks=True
        )
        rich_handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(rich_handler)

        # Also add rotating file handler for production
        if not self.dev_mode:
            try:
                log_file = config.LOGGING.get("file", "rainbot.log")
                max_bytes = int(config.LOGGING.get("max_size", 10 * 1024 * 1024))
                backup_count = int(config.LOGGING.get("backup_count", 5))
                file_handler = RotatingFileHandler(
                    log_file, maxBytes=max_bytes, backupCount=backup_count
                )
                file_handler.setFormatter(
                    logging.Formatter(
                        config.LOGGING.get(
                            "format", "%(asctime)s:%(levelname)s:%(name)s: %(message)s"
                        )
                    )
                )
                self.logger.addHandler(file_handler)
            except Exception as e:
                # Fallback to basic file handler if rotation fails
                file_handler = logging.FileHandler("rainbot.log")
                file_handler.setFormatter(
                    logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
                )
                self.logger.addHandler(file_handler)

    @staticmethod
    def _parse_int_env(var_name: str) -> Optional[int]:
        value = os.getenv(var_name)
        if value is None or value == "":
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _parse_owner_ids(self, owners_raw: str) -> List[int]:
        owners: List[int] = []
        for token in owners_raw.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                owners.append(int(token))
            except ValueError:
                # Ignore invalid IDs but log once bot logger is ready
                pass
        return owners

    async def _resolve_channel(
        self, channel_id: Optional[int]
    ) -> Optional[discord.abc.Messageable]:
        if not channel_id:
            return None
        try:
            channel = self.get_channel(channel_id)
            if channel is None:
                channel = await self.fetch_channel(channel_id)
            return channel  # type: ignore[return-value]
        except Exception as e:
            self.logger.debug(f"Failed to resolve channel {channel_id}: {e}")
            return None

    async def setup_hook(self) -> None:
        """Async setup hook for discord.py 2.x"""
        self.logger.info("🚀 Starting rainbot setup...")

        # Initialize database
        mongo_uri = os.getenv("mongo")
        if not mongo_uri:
            self.logger.error("MongoDB connection string (mongo) not configured in environment.")
            raise RuntimeError("Missing required environment variable: mongo")
        self.db = DatabaseManager(mongo_uri, loop=self.loop)
        self.db.start_change_listener()

        # Load extensions
        await self.load_extensions()

        # Setup background tasks
        if not self.dev_mode:
            await self.setup_unmutes()
            await self.setup_unbans()

        self.logger.info("✅ Setup complete!")

    async def load_extensions(self) -> None:
        """Load all extensions with better error handling"""
        extensions_loaded = 0
        extensions_failed = 0

        for file in os.listdir("cogs"):
            if file.endswith(".py"):
                if self.dev_mode and file in ("logs.py",):
                    continue

                extension_name = f'cogs.{file.replace(".py", "")}'

                try:
                    await self.load_extension(extension_name)
                    self.logger.info(f"✅ Loaded {file}")
                    extensions_loaded += 1
                except Exception as e:
                    self.logger.error(f"❌ Failed to load {file}: {e}")
                    extensions_failed += 1

        self.logger.info(f"📊 Extensions: {extensions_loaded} loaded, {extensions_failed} failed")

    async def on_message(self, message: discord.Message) -> None:
        """Enhanced message handling with statistics"""
        if not message.author.bot and message.guild:
            # Optional dev-only guild gate for local testing
            if self.dev_mode and self.dev_guild_id and message.guild.id != self.dev_guild_id:
                return
            ctx = await self.get_context(message)
            if ctx.command:
                # Track command usage
                cmd_name = ctx.command.qualified_name
                self.command_usage[cmd_name] = self.command_usage.get(cmd_name, 0) + 1

                # Add loading reaction for better UX
                try:
                    await message.add_reaction(self.loading)
                except discord.Forbidden:
                    pass

                # If user invoked a bare command without required args, show help instead
                try:
                    await self.invoke(ctx)
                except commands.MissingRequiredArgument:
                    try:
                        await ctx.invoke(
                            self.get_command("help"), command_or_cog=ctx.command.qualified_name
                        )
                    except Exception:
                        pass

                # Remove loading reaction and add success reaction
                try:
                    await message.remove_reaction(self.loading, self.user)
                    await message.add_reaction(self.success)
                except (discord.Forbidden, discord.NotFound):
                    pass

    async def get_prefix(self, message: discord.Message) -> Union[str, List[str]]:
        """Get command prefix with fallback"""
        if self.dev_mode:
            return ["./", "!"]

        try:
            guild_config = await self.db.get_guild_config(message.guild.id)
            return commands.when_mentioned_or(guild_config.prefix)(self, message)
        except Exception:
            # Fallback to default prefix
            return commands.when_mentioned_or("!")(self, message)

    async def on_connect(self) -> None:
        """Enhanced connection handling"""
        self.session = aiohttp.ClientSession()
        self.logger.info("🔗 Connected to Discord")

    async def on_ready(self) -> None:
        """Enhanced ready event with statistics"""
        self.logger.info(f"🎉 {self.user} is ready!")
        self.logger.info(f"📊 Serving {len(self.guilds)} guilds with {len(self.users)} users")

        if self.dev_mode:
            self.logger.info("🐛 Debug mode active - Prefix: ./")

        # Set bot status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} servers | {self.command_prefix or '!'}help",
        )
        await self.change_presence(activity=activity)

        # Resolve configured channels and log results
        err = await self._resolve_channel(self.ERROR_CHANNEL_ID)
        join = await self._resolve_channel(self.GUILD_JOIN_CHANNEL_ID)
        leave = await self._resolve_channel(self.GUILD_REMOVE_CHANNEL_ID)
        self.logger.info(
            f"Channels: error={'ok' if err else 'missing'} join={'ok' if join else 'missing'} leave={'ok' if leave else 'missing'}"
        )

        # One-off startup connectivity check messages
        if not self._startup_announced:
            now = int(datetime.utcnow().timestamp())
            try:
                if err:
                    await err.send(f"✅ Startup connectivity check at <t:{now}:T>")
                if join:
                    await join.send(f"✅ Startup connectivity check at <t:{now}:T>")
                if leave:
                    await leave.send(f"✅ Startup connectivity check at <t:{now}:T>")
            except Exception as e:
                self.logger.debug(f"Failed to send startup test messages: {e}")
            self._startup_announced = True

    async def on_command_error(self, ctx: commands.Context, e: Exception) -> None:
        """Enhanced error handling with user-friendly messages"""
        e = getattr(e, "original", e)

        # Track errors
        self.error_count += 1

        # Remove loading reaction and add error reaction
        try:
            await ctx.message.remove_reaction(self.loading, self.user)
            await ctx.message.add_reaction(self.error)
        except (discord.Forbidden, discord.NotFound):
            pass

        # Don't silently ignore Underleveled so we can show a helpful message
        ignored = (
            commands.CommandNotFound,
            commands.CheckFailure,
            commands.BadArgument,
        )

        if isinstance(e, ignored) and not self.dev_mode:
            return

        # Create user-friendly error messages
        if isinstance(e, commands.UserInputError):
            # Try to provide more helpful info for missing/invalid arguments
            usage = f"{ctx.prefix}{ctx.command.signature}"
            # If it's a missing required argument, highlight what's missing
            missing = None
            if isinstance(e, commands.MissingRequiredArgument):
                missing = f"Missing required argument: `{e.param.name}`."
            elif isinstance(e, commands.BadArgument):
                missing = (
                    f"Invalid value for argument: `{e.param.name if hasattr(e, 'param') else ''}`."
                )
            else:
                missing = str(e)

            embed = discord.Embed(
                title="❌ Invalid Command Usage",
                description=f"{missing}\n\n**Usage:**\n`{usage}`",
                color=discord.Color.red(),
            )
            # Optionally, show help text if available
            if ctx.command.help:
                embed.add_field(name="Help", value=ctx.command.help, inline=False)
            from ext.safe_send import safe_send

            await safe_send(ctx, embed=embed)

        elif isinstance(e, commands.MissingPermissions):
            perms = ", ".join(
                [f"`{perm.replace('_', ' ').title()}`" for perm in e.missing_permissions]
            )
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description=f"You are missing the following permission(s) to run this command: {perms}",
                color=discord.Color.red(),
            )
            from ext.safe_send import safe_send

            await safe_send(ctx, embed=embed)

        elif isinstance(e, commands.BotMissingPermissions):
            perms = ", ".join(
                [f"`{perm.replace('_', ' ').title()}`" for perm in e.missing_permissions]
            )
            embed = discord.Embed(
                title="❌ Bot Missing Permissions",
                description=f"I am missing the following permission(s) to run this command: {perms}",
                color=discord.Color.red(),
            )
            from ext.safe_send import safe_send

            await safe_send(ctx, embed=embed)

        elif isinstance(e, Underleveled):
            embed = discord.Embed(
                title="❌ Insufficient Permission Level",
                description="You do not have the required permission level to use this command.",
                color=discord.Color.red(),
            )
            # Optionally, show required level if available
            if hasattr(ctx.command, "perm_level"):
                embed.add_field(
                    name="Required Level",
                    value=f"{getattr(ctx.command, 'perm_level', 'Unknown')}",
                    inline=True,
                )
            from ext.safe_send import safe_send

            await safe_send(ctx, embed=embed)

        elif isinstance(e, discord.Forbidden):
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="I don't have the required permissions to perform this action.",
                color=discord.Color.red(),
            )
            from ext.safe_send import safe_send

            await safe_send(ctx, embed=embed)

        elif isinstance(e, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="⏰ Command on Cooldown",
                description=f"Please wait {e.retry_after:.2f} seconds before using this command again.",
                color=discord.Color.orange(),
            )
            from ext.safe_send import safe_send

            await safe_send(ctx, embed=embed)

        else:
            # Log detailed error for debugging
            self.logger.error(f"Error in {ctx.command}: {e}")
            if self.dev_mode:
                from ext.safe_send import safe_send

                await safe_send(ctx, content=f"```py\n{type(e).__name__}: {e}\n```")
            else:
                embed = discord.Embed(
                    title="❌ An error occurred",
                    description="Something went wrong. Please try again or contact support.",
                    color=discord.Color.red(),
                )
                from ext.safe_send import safe_send

                await safe_send(ctx, embed=embed)

        # Always report to error channel
        try:
            if not self.ERROR_CHANNEL_ID:
                return
            error_channel = await self._resolve_channel(self.ERROR_CHANNEL_ID)
            if not error_channel:
                return
            embed = discord.Embed(
                title="⚠️ Command Error",
                color=discord.Color.red(),
                timestamp=datetime.utcnow(),
            )
            embed.add_field(name="Guild", value=f"{ctx.guild.name} ({ctx.guild.id})", inline=False)
            embed.add_field(
                name="Channel", value=f"#{ctx.channel} ({ctx.channel.id})", inline=False
            )
            embed.add_field(name="User", value=f"{ctx.author} ({ctx.author.id})", inline=False)
            embed.add_field(
                name="Command",
                value=f"{ctx.command.qualified_name if ctx.command else 'Unknown'}",
                inline=False,
            )
            embed.add_field(name="Error", value=f"{type(e).__name__}: {e}", inline=False)
            from ext.safe_send import safe_send

            await safe_send(error_channel, embed=embed)
        except Exception as send_err:
            # Avoid recursive failures
            self.logger.debug(f"Failed to send error report: {send_err}")

    async def on_error(self, event_method: str, /, *args, **kwargs) -> None:  # type: ignore[override]
        # Fallback handler for unexpected errors in listeners
        tb = traceback.format_exc()
        self.logger.error(f"Unhandled error in {event_method}:\n{tb}")
        try:
            if not self.ERROR_CHANNEL_ID:
                return
            error_channel = await self._resolve_channel(self.ERROR_CHANNEL_ID)
            if not error_channel:
                return
            embed = discord.Embed(
                title="🔥 Unhandled Error",
                description=f"Event: `{event_method}`",
                color=discord.Color.red(),
                timestamp=datetime.utcnow(),
            )
            embed.add_field(
                name="Traceback",
                value=(tb if len(tb) < 1900 else tb[-1900:]),
                inline=False,
            )
            await error_channel.send(embed=embed)
        except Exception as e:
            self.logger.debug(f"Failed to send unhandled error: {e}")

    async def on_guild_join(self, guild: discord.Guild) -> None:
        # Prepare embed with server info
        try:
            owner = guild.owner or (await guild.fetch_owner())
        except Exception:
            owner = None

        humans = sum(1 for m in guild.members if not m.bot) if guild.members else None
        bots = sum(1 for m in guild.members if m.bot) if guild.members else None
        embed = discord.Embed(
            title="✅ Joined Server",
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Name", value=f"{guild.name}", inline=True)
        embed.add_field(name="ID", value=f"{guild.id}", inline=True)
        if owner:
            embed.add_field(name="Owner", value=f"{owner} ({owner.id})", inline=False)
        embed.add_field(name="Members", value=f"{guild.member_count}", inline=True)
        if humans is not None and bots is not None:
            embed.add_field(name="Humans/Bots", value=f"{humans}/{bots}", inline=True)
        # Use Discord local timestamp tag for client-local display
        embed.add_field(
            name="Created",
            value=f"<t:{int(guild.created_at.timestamp())}:F>",
            inline=False,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        try:
            dest = await self._resolve_channel(self.GUILD_JOIN_CHANNEL_ID)
            if dest:
                await dest.send(embed=embed)
            else:
                self.logger.debug("Join channel not resolved; skipping announce")
        except Exception as e:
            self.logger.debug(f"Failed to send join announce: {e}")

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        # Prepare embed with server info on leave
        try:
            owner = guild.owner or None
        except Exception:
            owner = None
        embed = discord.Embed(
            title="❌ Left Server",
            color=discord.Color.red(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Name", value=f"{guild.name}", inline=True)
        embed.add_field(name="ID", value=f"{guild.id}", inline=True)
        if owner:
            embed.add_field(
                name="Owner", value=f"{owner} ({getattr(owner, 'id', 'N/A')})", inline=False
            )
        embed.add_field(
            name="Members", value=f"{getattr(guild, 'member_count', 'N/A')}", inline=True
        )
        embed.add_field(
            name="Created",
            value=f"<t:{int(guild.created_at.timestamp())}:F>",
            inline=False,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        try:
            dest = await self._resolve_channel(self.GUILD_REMOVE_CHANNEL_ID)
            if dest:
                await dest.send(embed=embed)
            else:
                self.logger.debug("Leave channel not resolved; skipping announce")
        except Exception as e:
            self.logger.debug(f"Failed to send leave announce: {e}")

    async def setup_unmutes(self) -> None:
        """Setup unmute tasks with better error handling"""
        try:
            data = self.db.coll.find({"mutes": {"$exists": True, "$ne": []}})
            count = 0
            async for d in data:
                for m in d["mutes"]:
                    self.loop.create_task(
                        self.unmute(int(d["guild_id"]), int(m["member"]), m["time"])
                    )
                    count += 1
            self.logger.info(f"🔓 Setup {count} unmute tasks")
        except Exception as e:
            self.logger.error(f"Failed to setup unmutes: {e}")

    async def setup_unbans(self) -> None:
        """Setup unban tasks with better error handling"""
        try:
            data = self.db.coll.find({"tempbans": {"$exists": True, "$ne": []}})
            count = 0
            async for d in data:
                for m in d["tempbans"]:
                    self.loop.create_task(
                        self.unban(int(d["guild_id"]), int(m["member"]), m["time"])
                    )
                    count += 1
            self.logger.info(f"🔓 Setup {count} unban tasks")
        except Exception as e:
            self.logger.error(f"Failed to setup unbans: {e}")

    async def on_member_join(self, m: discord.Member) -> None:
        """Enhanced member join handling"""
        if not self.dev_mode:
            try:
                guild_config = await self.db.get_guild_config(m.guild.id)
                mutes = guild_config.mutes
                user_mute = None

                for mute in mutes:
                    if mute["member"] == str(m.id):
                        user_mute = mute

                if user_mute:
                    await self.mute(
                        m.guild.me, m, user_mute["time"] - time(), "Mute evasion", modify_db=False
                    )
            except Exception as e:
                self.logger.error(f"Error during member join mute evasion for {m.id}: {e}")

    async def mute(
        self,
        actor: discord.Member,
        member: discord.Member,
        delta: timedelta,
        reason: str,
        modify_db: bool = True,
    ) -> None:
        """Mutes a ``member`` for ``delta``"""
        guild_config = await self.db.get_guild_config(member.guild.id)
        mute_role = discord.utils.get(member.guild.roles, id=int(guild_config.mute_role or 0))
        if not mute_role:
            # mute role
            mute_role = discord.utils.get(member.guild.roles, name="Muted")
            if not mute_role:
                # existing mute role not found, let's create one
                mute_role = await member.guild.create_role(
                    name="Muted",
                    color=discord.Color(0x818689),
                    reason="Attempted to mute user but role did not exist",
                )
                for tc in member.guild.text_channels:
                    try:
                        await tc.set_permissions(
                            mute_role,
                            send_messages=False,
                            reason="Attempted to mute user but role did not exist",
                        )
                    except discord.Forbidden:
                        pass
                for vc in member.guild.voice_channels:
                    try:
                        await vc.set_permissions(
                            mute_role,
                            speak=False,
                            reason="Attempted to mute user but role did not exist",
                        )
                    except discord.Forbidden:
                        pass

            await self.db.update_guild_config(
                member.guild.id, {"$set": {"mute_role": str(mute_role.id)}}
            )
        await member.add_roles(mute_role)

        # mute complete, log it
        log_channel: discord.TextChannel = self.get_channel(tryint(guild_config.modlog.member_mute))
        if log_channel:
            # Use Discord local time tag; still honor guild time_offset
            current_time = datetime.utcnow() + timedelta(hours=guild_config.time_offset)
            current_time_fmt = f"<t:{int(current_time.timestamp())}:T>"

            await log_channel.send(
                f"{current_time_fmt} {actor} has muted {member} ({member.id}), reason: {reason} for {format_timedelta(delta)}"
            )

        if delta:
            duration = delta.total_seconds()
            # log complete, save to DB
            if duration is not None:
                duration += time()
                if modify_db:
                    await self.db.update_guild_config(
                        member.guild.id,
                        {"$push": {"mutes": {"member": str(member.id), "time": duration}}},
                    )
                self.loop.create_task(self.unmute(member.guild.id, member.id, duration))

    async def unmute(
        self, guild_id: int, member_id: int, duration: Optional[float], reason: str = "Auto"
    ) -> None:
        await self.wait_until_ready()
        if duration is not None:
            await asyncio.sleep(duration - time())

        try:
            member = self.get_guild(guild_id).get_member(member_id)
            member.guild.id
        except AttributeError:
            member = None

        if member:
            guild_config = await self.db.get_guild_config(guild_id)
            mute_role: Optional[discord.Role] = discord.utils.get(
                member.guild.roles, id=int(guild_config.mute_role)
            )
            log_channel: Optional[discord.TextChannel] = self.get_channel(
                tryint(guild_config.modlog.member_unmute)
            )

            current_time = datetime.utcnow() + timedelta(hours=guild_config.time_offset)
            current_time_fmt = f"<t:{int(current_time.timestamp())}:T>"

            if member:
                if mute_role in member.roles:
                    await member.remove_roles(mute_role)
                    if log_channel:
                        await log_channel.send(
                            f"{current_time_fmt} {member} ({member.id}) has been unmuted. Reason: {reason}"
                        )
            else:
                if log_channel:
                    await log_channel.send(
                        f"{current_time_fmt} Tried to unmute {member} ({member.id}), member not in server"
                    )

        # set db
        pull: Dict[str, Any] = {"$pull": {"mutes": {"member": str(member_id)}}}
        if duration is not None:
            pull["$pull"]["mutes"]["time"] = duration
        await self.db.update_guild_config(guild_id, pull)

    async def unban(
        self, guild_id: int, member_id: int, duration: Optional[float], reason: str = "Auto"
    ) -> None:
        """Enhanced unban with better error handling"""
        await self.wait_until_ready()
        if duration is not None:
            await asyncio.sleep(duration - time())

        guild = self.get_guild(guild_id)

        if guild:
            try:
                guild_config = await self.db.get_guild_config(guild_id)
                log_channel: Optional[discord.TextChannel] = self.get_channel(
                    tryint(guild_config.modlog.member_unban)
                )

                current_time = datetime.utcnow() + timedelta(hours=guild_config.time_offset)
                current_time_fmt = f"<t:{int(current_time.timestamp())}:T>"

                try:
                    await guild.unban(discord.Object(member_id), reason=reason)
                except discord.NotFound:
                    pass
                else:
                    if log_channel:
                        user = self.get_user(member_id)
                        name = getattr(user, "name", "(no name)")
                        await log_channel.send(
                            f"{current_time_fmt} {name} ({member_id}) has been unbanned. Reason: {reason}"
                        )

                # Update database
                pull: Dict[str, Any] = {"$pull": {"tempbans": {"member": str(member_id)}}}
                if duration is not None:
                    pull["$pull"]["tempbans"]["time"] = duration
                await self.db.update_guild_config(guild_id, pull)

            except Exception as e:
                self.logger.error(f"Error during unban for {member_id}: {e}")

    async def get_bot_stats(self) -> Dict[str, Any]:
        """Get comprehensive bot statistics"""
        uptime = datetime.utcnow() - self.start_time

        return {
            "uptime": str(uptime).split(".")[0],
            "guilds": len(self.guilds),
            "users": len(self.users),
            "commands_used": sum(self.command_usage.values()),
            "errors": self.error_count,
            "successful_commands": self.successful_commands,
            "latency": round(self.latency * 1000, 2),
            "top_commands": sorted(self.command_usage.items(), key=lambda x: x[1], reverse=True)[
                :5
            ],
        }

    async def create_welcome_embed(self, guild: discord.Guild) -> discord.Embed:
        """Create a welcome embed for new guilds"""
        embed = discord.Embed(
            title="🎉 Thanks for adding rainbot!",
            description="I'm a powerful moderation bot with automod and logging features.",
            color=discord.Color.green(),
        )

        embed.add_field(
            name="🚀 Quick Start",
            value="1. Set up your prefix: `!setprefix <prefix>`\n"
            "2. Configure moderation: `!setup`\n"
            "3. Get help: `!help`",
            inline=False,
        )

        embed.add_field(
            name="📊 Features",
            value="• Auto-moderation\n• Manual moderation\n• Logging system\n• Custom commands\n• Permission levels",
            inline=False,
        )

        embed.add_field(
            name="🔗 Links",
            value="[Support Server](https://discord.gg/zmdYe3ZVHG) • [Documentation](https://github.com/fourjr/rainbot/wiki)",
            inline=False,
        )

        embed.set_footer(text=f"Guild ID: {guild.id}")
        return embed


if __name__ == "__main__":
    load_dotenv()

    async def main():
        """Enhanced main function with better error handling"""
        bot = rainbot()

        try:
            console.print("[bold green]🚀 Starting rainbot...[/bold green]")
            token = os.getenv("token")
            if not token:
                console.print(
                    "[bold red]❌ Discord token not configured in environment (.env token)[/bold red]"
                )
                bot.logger.error("Missing Discord token")
                return
            await bot.start(token)
        except discord.LoginFailure:
            console.print("[bold red]❌ Invalid token provided![/bold red]")
            bot.logger.error("Invalid token")
        except KeyboardInterrupt:
            console.print("[bold yellow]⚠️ Shutting down...[/bold yellow]")
            await bot.close()
        except Exception as e:
            console.print(f"[bold red]❌ Fatal error: {e}[/bold red]")
            bot.logger.error("Fatal exception")
            traceback.print_exc(file=sys.stderr)
        finally:
            if bot.session:
                await bot.session.close()
            console.print("[bold green]✅ Shutdown complete![/bold green]")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("[bold yellow]⚠️ Forced shutdown![/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]❌ Critical error: {e}[/bold red]")
        sys.exit(1)
