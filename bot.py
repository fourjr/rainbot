import asyncio
import logging
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

        self.dev_mode = os.name == "nt"
        self.session: Optional[aiohttp.ClientSession] = None
        self.start_time = datetime.utcnow()

        # Set up enhanced logging
        self.setup_logging()

        # Database and configuration
        self.db = None  # Will be initialized in setup_hook
        self.owners = list(map(int, os.getenv("owners", "").split(",")))

        # Bot statistics
        self.command_usage = {}
        self.error_count = 0
        self.successful_commands = 0

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

        # Also add file handler for production
        if not self.dev_mode:
            file_handler = logging.FileHandler("rainbot.log")
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
            )
            self.logger.addHandler(file_handler)

    async def setup_hook(self) -> None:
        """Async setup hook for discord.py 2.x"""
        self.logger.info("🚀 Starting rainbot setup...")

        # Initialize database
        self.db = DatabaseManager(os.environ["mongo"], loop=self.loop)
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
        if message.author.bot or not message.guild:
            return

        ctx = await self.get_context(message)
        if not ctx.command:
            return  # Early return if no command is found

        cmd_name = ctx.command.qualified_name
        self.command_usage[cmd_name] = self.command_usage.get(cmd_name, 0) + 1

        # Check if the bot has permission to add reactions
        if message.channel.permissions_for(message.guild.me).add_reactions:
            try:
                await message.add_reaction(self.loading)
            except discord.Forbidden:
                self.logger.warning("Missing permissions to add reactions.")

        try:
            await self.invoke(ctx)

            # Add success reaction if the command succeeds
            if message.channel.permissions_for(message.guild.me).add_reactions:
                try:
                    await message.remove_reaction(self.loading, self.user)
                    await message.add_reaction(self.success)
                except discord.Forbidden:
                    self.logger.warning("Missing permissions to modify reactions.")
        except Exception as e:
            # Log the error with traceback
            self.logger.error(f"Error in command {cmd_name}: {e}\n{traceback.format_exc()}")

            # Add error reaction if the bot has permission
            if message.channel.permissions_for(message.guild.me).add_reactions:
                try:
                    await message.remove_reaction(self.loading, self.user)
                    await message.add_reaction(self.error)
                except discord.Forbidden:
                    self.logger.warning("Missing permissions to modify reactions.")

            # Avoid re-raising the error unless in development mode
            if self.dev_mode:
                raise

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
            type=discord.ActivityType.watching, name=f"{len(self.guilds)} servers | !!help"
        )
        await self.change_presence(activity=activity)

    async def on_command_error(self, ctx: commands.Context, e: Exception) -> None:
        """Enhanced error handling with user-friendly messages"""
        e = getattr(e, "original", e)

        # Track errors
        self.error_count += 1

        # Remove loading reaction and add error reaction
        try:
            await ctx.message.remove_reaction(self.loading, self.user)
            await ctx.message.add_reaction(self.error)
        except discord.Forbidden:
            pass

        ignored = (
            commands.CommandNotFound,
            commands.CheckFailure,
            commands.BadArgument,
            Underleveled,
        )

        if isinstance(e, ignored) and not self.dev_mode:
            return

        # Create user-friendly error messages
        if isinstance(e, commands.UserInputError):
            embed = discord.Embed(
                title="❌ Invalid Input", description=str(e), color=discord.Color.red()
            )
            embed.add_field(
                name="Usage",
                value=f"`{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`",
            )
            await ctx.send(embed=embed)

        elif isinstance(e, discord.Forbidden):
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="I don't have the required permissions to perform this action.",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)

        elif isinstance(e, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="⏰ Command on Cooldown",
                description=f"Please wait {e.retry_after:.2f} seconds before using this command again.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)

        else:
            # Log detailed error for debugging
            self.logger.error(f"Error in {ctx.command}: {e}")
            if self.dev_mode:
                await ctx.send(f"```py\n{type(e).__name__}: {e}\n```")
            else:
                embed = discord.Embed(
                    title="❌ An error occurred",
                    description="Something went wrong. Please try again or contact support.",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)

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
            current_time = datetime.utcnow()

            offset = guild_config.time_offset
            current_time += timedelta(hours=offset)
            current_time_fmt = current_time.strftime("%H:%M:%S")

            await log_channel.send(
                f"`{current_time_fmt}` {actor} has muted {member} ({member.id}), reason: {reason} for {format_timedelta(delta)}"
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

            current_time = datetime.utcnow()

            offset = guild_config.time_offset
            current_time += timedelta(hours=offset)
            current_time_fmt = current_time.strftime("%H:%M:%S")

            if member:
                if mute_role in member.roles:
                    await member.remove_roles(mute_role)
                    if log_channel:
                        await log_channel.send(
                            f"`{current_time_fmt}` {member} ({member.id}) has been unmuted. Reason: {reason}"
                        )
            else:
                if log_channel:
                    await log_channel.send(
                        f"`{current_time_fmt}` Tried to unmute {member} ({member.id}), member not in server"
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

                current_time = datetime.utcnow()
                offset = guild_config.time_offset
                current_time += timedelta(hours=offset)
                current_time_fmt = current_time.strftime("%H:%M:%S")

                try:
                    await guild.unban(discord.Object(member_id), reason=reason)
                except discord.NotFound:
                    pass
                else:
                    if log_channel:
                        user = self.get_user(member_id)
                        name = getattr(user, "name", "(no name)")
                        await log_channel.send(
                            f"`{current_time_fmt}` {name} ({member_id}) has been unbanned. Reason: {reason}"
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
            await bot.start(os.getenv("token"))
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
# Inside the on_message method...

async def on_message(self, message: discord.Message) -> None:
    """Enhanced message handling with statistics"""
    if message.author.bot or not message.guild:
        return

    ctx = await self.get_context(message)
    if not ctx.command:
        return  # Early return if no command is found

    cmd_name = ctx.command.qualified_name
    self.command_usage[cmd_name] = self.command_usage.get(cmd_name, 0) + 1

    # Check if the bot has permission to add reactions
    if message.channel.permissions_for(message.guild.me).add_reactions:
        try:
            await message.add_reaction(self.loading)
        except discord.Forbidden:
            self.logger.warning("Missing permissions to add reactions.")

    try:
        await self.invoke(ctx)

        # Add success reaction if the command succeeds
        if message.channel.permissions_for(message.guild.me).add_reactions:
            try:
                await message.remove_reaction(self.loading, self.user)
                await message.add_reaction(self.success)
            except discord.Forbidden:
                self.logger.warning("Missing permissions to modify reactions.")
    except Exception as e:
        # Log the error with traceback
        self.logger.error(f"Error in command {cmd_name}: {e}\n{traceback.format_exc()}")

        # Add error reaction if the bot has permission
        if message.channel.permissions_for(message.guild.me).add_reactions:
            try:
                await message.remove_reaction(self.loading, self.user)
                await message.add_reaction(self.error)
            except discord.Forbidden:
                self.logger.warning("Missing permissions to modify reactions.")

        # Avoid re-raising the error unless in development mode
        if self.dev_mode:
            raise