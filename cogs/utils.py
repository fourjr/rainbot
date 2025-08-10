from __future__ import annotations

import inspect
import io
import os
import subprocess
import textwrap
import traceback
from contextlib import redirect_stdout
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, Union

import discord
from discord.ext import commands
from ext.command import RainCommand, RainGroup, command
from ext.paginator import Paginator
from ext.utility import get_command_level, get_perm_level, owner
import logging
from config import BOT_VERSION, get_emoji

if TYPE_CHECKING:
    from bot import rainbot


class Utility(commands.Cog):
    """General utility commands and enhanced help system"""

    def __init__(self, bot: "rainbot") -> None:
        self.bot = bot
        self.order = 4
        self.logger = logging.getLogger("rainbot.utils")

    @owner()
    @command(0, name="eval")
    async def _eval(self, ctx: commands.Context, *, body: str) -> None:
        """Evaluates python code with enhanced output"""
        self.logger.info(
            f"Owner eval invoked by {ctx.author} ({getattr(ctx.author, 'id', None)}) in {getattr(ctx.guild, 'id', None)}"
        )
        env = {
            "ctx": ctx,
            "self": self,
            "bot": self.bot,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "source": inspect.getsource,
        }

        env.update(globals())

        def cleanup_code(content):
            """Automatically removes code blocks from the code."""
            if content.startswith("```") and content.endswith("```"):
                return "\n".join(content.split("\n")[1:-1])
            return content.strip("` \n")

        body = cleanup_code(body)
        stdout = io.StringIO()
        err = out = None

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        def paginate(text: str):
            """Simple generator that paginates text."""
            last = 0
            pages = []
            for curr in range(0, len(text)):
                if curr % 1980 == 0:
                    pages.append(text[last:curr])
                    last = curr
                    appd_index = curr
            if appd_index != len(text) - 1:
                pages.append(text[last:curr])
            return list(filter(lambda a: a != "", pages))

        try:
            exec(to_compile, env)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Evaluation Error",
                description=f"```py\n{e.__class__.__name__}: {e}\n```",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        func = env["func"]
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            embed = discord.Embed(
                title="❌ Runtime Error",
                description=f"```py\n{value}{traceback.format_exc()}\n```",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    try:
                        embed = discord.Embed(
                            title="✅ Evaluation Result",
                            description=f"```py\n{value}\n```",
                            color=discord.Color.green(),
                        )
                        await ctx.send(embed=embed)
                    except:
                        paginated_text = paginate(value)
                        for page in paginated_text:
                            if page == paginated_text[-1]:
                                embed = discord.Embed(
                                    title="✅ Evaluation Result",
                                    description=f"```py\n{page}\n```",
                                    color=discord.Color.green(),
                                )
                                await ctx.send(embed=embed)
                                break
            else:
                try:
                    embed = discord.Embed(
                        title="✅ Evaluation Result",
                        description=f"```py\n{value}{ret}\n```",
                        color=discord.Color.green(),
                    )
                    await ctx.send(embed=embed)
                except:
                    paginated_text = paginate(f"{value}{ret}")
                    for page in paginated_text:
                        if page == paginated_text[-1]:
                            embed = discord.Embed(
                                title="✅ Evaluation Result",
                                description=f"```py\n{page}\n```",
                                color=discord.Color.green(),
                            )
                            await ctx.send(embed=embed)
                            break

    @owner()
    @command(0, name="exec")
    async def _exec(self, ctx: commands.Context, *, command: str) -> None:
        """Executes a shell command with enhanced output"""
        # Restrict in production unless explicitly allowed
        if not self.bot.dev_mode and os.getenv("ALLOW_EXEC_IN_PROD", "false").lower() != "true":
            await ctx.send("❌ Shell execution is disabled in production.")
            return

        self.logger.info(
            f"Owner exec invoked by {ctx.author} ({getattr(ctx.author, 'id', None)}) cmd={command!r}"
        )
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)

            embed = discord.Embed(title="🖥️ Command Execution", color=discord.Color.blue())

            if result.stdout:
                embed.add_field(
                    name="📤 Output", value=f"```\n{result.stdout[:1024]}\n```", inline=False
                )

            if result.stderr:
                embed.add_field(
                    name="⚠️ Errors", value=f"```\n{result.stderr[:1024]}\n```", inline=False
                )

            embed.add_field(name="📊 Return Code", value=f"`{result.returncode}`", inline=True)

            await ctx.send(embed=embed)

        except subprocess.TimeoutExpired:
            embed = discord.Embed(
                title="⏰ Timeout",
                description="Command execution timed out after 30 seconds.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Execution Error",
                description=f"```py\n{e}\n```",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)

    @owner()
    @command(0)
    async def update(self, ctx: commands.Context) -> None:
        """Updates the bot with enhanced feedback"""
        embed = discord.Embed(title="🔄 Updating...", color=discord.Color.blue())
        msg = await ctx.send(embed=embed)

        try:
            result = subprocess.run(["git", "pull"], capture_output=True, text=True)

            if result.returncode == 0:
                embed = discord.Embed(
                    title="✅ Update Complete",
                    description=f"```\n{result.stdout}\n```",
                    color=discord.Color.green(),
                )
                await msg.edit(embed=embed)

                # Reload extensions
                fmt = ""
                for extension in list(self.bot.extensions):
                    try:
                        await self.bot.reload_extension(extension)
                        fmt += f"✅ Reloaded {extension}\n"
                    except Exception as e:
                        fmt += f"❌ Failed to reload {extension}: {e}\n"

                if fmt:
                    embed.add_field(name="🔄 Extensions", value=f"```\n{fmt}\n```", inline=False)
                    await msg.edit(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ Update Failed",
                    description=f"```\n{result.stderr}\n```",
                    color=discord.Color.red(),
                )
                await msg.edit(embed=embed)

        except Exception as e:
            embed = discord.Embed(
                title="❌ Update Error", description=f"```py\n{e}\n```", color=discord.Color.red()
            )
            await msg.edit(embed=embed)

    async def can_run(self, ctx: commands.Context, cmd: Union[RainCommand, RainGroup]) -> bool:
        """Check if a command can be run by the user"""
        ctx.command = cmd
        can_run = True
        if cmd.checks:
            try:
                # Convert generator to list of awaitables
                checks = [predicate(ctx) for predicate in cmd.checks]
                can_run = await discord.utils.async_all(checks)
            except commands.CheckFailure:
                can_run = False
        return can_run

    async def format_cog_help(
        self, ctx: commands.Context, prefix: str, cog: commands.Cog
    ) -> Optional[discord.Embed]:
        """Enhanced cog help formatting"""
        # Get cog descriptions for better formatting
        cog_descriptions = {
            "Moderation": f"{get_emoji('moderation')} User management and moderation tools",
            "Setup": f"{get_emoji('setup')} Bot configuration and setup",
            "Detections": f"{get_emoji('detections')} Content filtering and automod",
            "Logs": f"{get_emoji('logs')} Activity logging and monitoring",
            "Roles": f"{get_emoji('roles')} Role management and automation",
            "Tags": f"{get_emoji('tags')} Custom commands and responses",
            "Giveaway": f"{get_emoji('giveaway')} Giveaway management system",
            "EventsAnnouncer": f"{get_emoji('events')} Member join/leave announcements",
        }

        cog_name = cog.__class__.__name__
        description = cog_descriptions.get(cog_name, f"📚 {cog_name}")

        em = discord.Embed(
            title=description,
            description=cog.__doc__ or "No description available",
            color=discord.Color.blue(),
        )

        commands_list = []
        # Get commands using cog.get_commands() instead of inspect.getmembers()
        for cmd in list(cog.get_commands()):
            if cmd.parent:
                continue
            if await self.can_run(ctx, cmd):
                commands_list.append(cmd)

        if commands_list:
            # Group commands by permission level
            cmd_groups = {}
            for cmd in commands_list:
                guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
                level = get_command_level(cmd, guild_config)
                if level not in cmd_groups:
                    cmd_groups[level] = []
                cmd_groups[level].append(cmd)

            for level in sorted(cmd_groups.keys()):
                cmds = cmd_groups[level]
                # Create a cleaner command list
                cmd_list = []
                for cmd in cmds:
                    cmd_desc = cmd.short_doc or "No description"
                    # Truncate long descriptions
                    if len(cmd_desc) > 50:
                        cmd_desc = cmd_desc[:47] + "..."
                    cmd_list.append(f"• `{prefix}{cmd.name}` - {cmd_desc}")

                value = "\n".join(cmd_list)
                if len(value) > 1024:
                    # Split into multiple fields if too long
                    chunks = [value[i : i + 1024] for i in range(0, len(value), 1024)]
                    for i, chunk in enumerate(chunks):
                        em.add_field(
                            name=f"{get_emoji('tools')} Level {level} Commands"
                            + (f" (Part {i+1})" if len(chunks) > 1 else ""),
                            value=chunk,
                            inline=False,
                        )
                else:
                    em.add_field(
                        name=f"{get_emoji('tools')} Level {level} Commands",
                        value=value,
                        inline=False,
                    )

        return em if em.fields else None

    async def format_command_help(
        self, ctx: commands.Context, prefix: str, cmd: Union[RainCommand, RainGroup]
    ) -> Optional[discord.Embed]:
        """Enhanced command help formatting"""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        cmd_level = get_command_level(cmd, guild_config)

        if await self.can_run(ctx, cmd) and cmd.enabled:
            if isinstance(cmd, RainCommand):
                em = discord.Embed(
                    title=f"📖 {prefix}{cmd.signature}",
                    description=f"{cmd.help}\n\n**🔐 Permission Level:** {cmd_level}",
                    color=discord.Color.blue(),
                )

                if cmd.aliases:
                    em.add_field(
                        name=f"{get_emoji('aliases')} Aliases",
                        value=f"`{', '.join(cmd.aliases)}`",
                        inline=True,
                    )

                return em

            elif isinstance(cmd, RainGroup):
                em = discord.Embed(
                    title=f"📖 {prefix}{cmd.signature}",
                    description=f"{cmd.help}\n\n**🔐 Permission Level:** {cmd_level}",
                    color=discord.Color.blue(),
                )

                subcommands = []
                for i in list(cmd.commands):
                    if await self.can_run(ctx, i):
                        subcommands.append(f"• `{i.name}` - {i.short_doc or 'No description'}")

                if subcommands:
                    em.add_field(
                        name=f"{get_emoji('subcommands')} Subcommands",
                        value="\n".join(subcommands),
                        inline=False,
                    )
                    return em

        return None

    @command(0, name="help")
    async def help_(
        self,
        ctx: commands.Context,
        *,
        command_or_cog: str = None,
        error: Union[str, Exception] = None,
    ) -> None:
        """Enhanced help command with better formatting and search"""
        if error:
            error = await commands.clean_content(escape_markdown=True).convert(ctx, str(error))
            error = f"{self.bot.error} `{error}`"

        prefix = (await self.bot.db.get_guild_config(ctx.guild.id)).prefix

        if command_or_cog:
            # Check if it's a number first
            if command_or_cog.isdigit():
                # Handle numbered category access
                await self._handle_numbered_help(ctx, command_or_cog, prefix, error)
                return

            # Search for command or cog
            cmd = self.bot.get_command(command_or_cog.lower())
            if not cmd:
                cog = self.bot.get_cog(command_or_cog.title())
                if not cog:
                    # Try fuzzy search
                    all_commands = [c.qualified_name for c in list(self.bot.commands)]
                    all_cogs = [cog.__class__.__name__ for cog in self.bot.cogs.values()]

                    # Find closest match
                    import difflib

                    cmd_matches = difflib.get_close_matches(
                        command_or_cog.lower(), all_commands, n=3
                    )
                    cog_matches = difflib.get_close_matches(command_or_cog.title(), all_cogs, n=3)

                    embed = discord.Embed(
                        title=f"{get_emoji('error')} Command/Cog Not Found",
                        description=f"Could not find `{command_or_cog}`",
                        color=discord.Color.red(),
                    )

                    if cmd_matches or cog_matches:
                        suggestions = []
                        if cmd_matches:
                            suggestions.extend([f"`{cmd}`" for cmd in cmd_matches])
                        if cog_matches:
                            suggestions.extend([f"`{cog}`" for cog in cog_matches])

                        embed.add_field(
                            name=f"{get_emoji('suggestions')} Did you mean?",
                            value=", ".join(suggestions[:5]),
                            inline=False,
                        )

                    await ctx.send(content=error, embed=embed)
                    return

                em = await self.format_cog_help(ctx, prefix, cog)
                await ctx.send(content=error, embed=em)
            else:
                em = await self.format_command_help(ctx, prefix, cmd)
                await ctx.send(content=error, embed=em)
        else:
            # Main help menu - optimized and cleaner
            embed = discord.Embed(
                title=f"{get_emoji('bot')} rainbot Help",
                description="A powerful moderation bot with automod and logging features",
                color=discord.Color.blue(),
            )

            # Get available cogs with optimized filtering
            available_cogs = []
            for cog in self.bot.cogs.values():
                if cog.__class__.__name__ != "Utility":
                    commands_list = list(cog.get_commands())
                    # Check if any commands can be run
                    can_run_commands = []
                    for cmd in commands_list:
                        can_run_commands.append(await self.can_run(ctx, cmd))
                    has_commands = any(can_run_commands)
                    if has_commands:
                        available_cogs.append(cog)

            if available_cogs:
                # Create a cleaner cog list with emojis and descriptions
                cog_descriptions = {
                    "Moderation": "🛡️ User management and moderation tools",
                    "Setup": "⚙️ Bot configuration and setup",
                    "Detections": "🔍 Content filtering and automod",
                    "Logs": "📝 Activity logging and monitoring",
                    "Roles": "🎭 Role management and automation",
                    "Tags": "🏷️ Custom commands and responses",
                    "Giveaway": "🎉 Giveaway management system",
                    "EventsAnnouncer": "📢 Member join/leave announcements",
                }

                cog_list = []
                cog_mapping = {}  # Store cog to number mapping
                for i, cog in enumerate(available_cogs, 1):
                    cog_name = cog.__class__.__name__
                    description = cog_descriptions.get(cog_name, f"📚 {cog_name}")
                    commands_list = list(cog.get_commands())
                    # Count commands that can be run
                    cmd_count = 0
                    for cmd in commands_list:
                        if await self.can_run(ctx, cmd):
                            cmd_count += 1
                    cog_list.append(f"**{i}.** {description} - **{cmd_count}** commands")
                    cog_mapping[str(i)] = cog  # Store mapping for later use

                embed.add_field(
                    name=f"{get_emoji('available')} Available Categories",
                    value="\n".join(cog_list),
                    inline=False,
                )

                # Store the mapping in the embed for later reference
                embed.add_field(
                    name=f"{get_emoji('quick_access')} Quick Access",
                    value=f"Use `{prefix}help <number>` to quickly access a category\n"
                    f"Example: `{prefix}help 1` for Moderation",
                    inline=False,
                )

            embed.add_field(
                name=f"{get_emoji('quick')} Quick Commands",
                value=f"• `{prefix}help <category>` - View category commands\n"
                f"• `{prefix}help <command>` - Detailed command help\n"
                f"• `{prefix}settings` - View server configuration\n"
                f"• `{prefix}about` - Bot information",
                inline=False,
            )

            embed.add_field(
                name=f"{get_emoji('resources')} Resources",
                value="[Support Server](https://discord.gg/zmdYe3ZVHG) • [Documentation](https://github.com/fourjr/rainbot/wiki)",
                inline=False,
            )

            embed.set_footer(
                text=f"Prefix: {prefix} | Use {prefix}help <category> for more details"
            )

            await ctx.send(content=error, embed=embed)

    async def _handle_numbered_help(
        self, ctx: commands.Context, number: str, prefix: str, error: str = None
    ) -> None:
        """Handle numbered category access for help command"""
        # Get available cogs
        available_cogs = []
        for cog in self.bot.cogs.values():
            if cog.__class__.__name__ != "Utility":
                commands_list = list(cog.get_commands())
                # Check if any commands can be run
                can_run_commands = []
                for cmd in commands_list:
                    can_run_commands.append(await self.can_run(ctx, cmd))
                has_commands = any(can_run_commands)
                if has_commands:
                    available_cogs.append(cog)

        # Check if number is valid
        number_int = int(number)
        if number_int < 1 or number_int > len(available_cogs):
            embed = discord.Embed(
                title=f"{get_emoji('error')} Invalid Category Number",
                description=f"Please choose a number between 1 and {len(available_cogs)}",
                color=discord.Color.red(),
            )
            await ctx.send(content=error, embed=embed)
            return

        # Get the cog for this number
        selected_cog = available_cogs[number_int - 1]

        # Show the cog help
        em = await self.format_cog_help(ctx, prefix, selected_cog)
        await ctx.send(content=error, embed=em)

    @command(0, name="settings")
    async def settings(self, ctx: commands.Context, category: str = None) -> None:
        """View server configuration settings

        Categories: logs, modlog, detections, punishments, roles, giveaway, general
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        prefix = guild_config.prefix

        if category:
            category = category.lower()
            await self._show_category_settings(ctx, guild_config, category, prefix)
        else:
            await self._show_all_settings(ctx, guild_config, prefix)

    async def _show_category_settings(
        self, ctx: commands.Context, config: Any, category: str, prefix: str
    ) -> None:
        """Show settings for a specific category"""
        embed = discord.Embed(
            title=f"{get_emoji('settings')} {category.title()} Settings",
            description=f"Configuration for {category}",
            color=discord.Color.blue(),
        )

        if category == "logs":
            self._add_logs_settings(embed, config)
        elif category == "modlog":
            self._add_modlog_settings(embed, config)
        elif category == "detections":
            self._add_detections_settings(embed, config)
        elif category == "punishments":
            self._add_punishments_settings(embed, config)
        elif category == "roles":
            self._add_roles_settings(embed, config)
        elif category == "giveaway":
            self._add_giveaway_settings(embed, config)
        elif category == "general":
            self._add_general_settings(embed, config)
        else:
            embed = discord.Embed(
                title=f"{get_emoji('error')} Invalid Category",
                description=f"Available categories: logs, modlog, detections, punishments, roles, giveaway, general",
                color=discord.Color.red(),
            )

        embed.set_footer(text=f"Use {prefix}settings <category> to view specific settings")
        await ctx.send(embed=embed)

    async def _show_all_settings(self, ctx: commands.Context, config: Any, prefix: str) -> None:
        """Show overview of all settings"""
        embed = discord.Embed(
            title=f"{get_emoji('settings')} Server Settings Overview",
            description="Current configuration for this server",
            color=discord.Color.blue(),
        )

        # General settings
        embed.add_field(
            name=f"{get_emoji('tools')} General",
            value=f"**Prefix:** `{config.prefix}`\n"
            f"**Mute Role:** {f'<@&{config.mute_role}>' if config.mute_role else 'Not set'}\n"
            f"**Time Offset:** {config.time_offset} hours",
            inline=True,
        )

        # Logs summary
        logs_enabled = sum(1 for log in config.logs.values() if log is not None)
        embed.add_field(
            name=f"{get_emoji('logs')} Logging",
            value=f"**Log Channels:** {logs_enabled}/11 enabled\n"
            f"**Modlog Channels:** {sum(1 for log in config.modlog.values() if log is not None)}/11 enabled",
            inline=True,
        )

        # Detections summary
        detections_enabled = sum(
            1 for det in config.detections.values() if det and det != [] and det is not None
        )
        embed.add_field(
            name=f"{get_emoji('detections')} Detections",
            value=f"**Active Filters:** {detections_enabled} enabled\n"
            f"**Custom Filters:** {len(config.detections.filters)} added\n"
            f"**Ignored Channels:** {sum(len(channels) for channels in config.ignored_channels.values())} total",
            inline=True,
        )

        # Roles summary
        embed.add_field(
            name=f"{get_emoji('roles')} Roles",
            value=f"**Auto Roles:** {len(config.autoroles)} set\n"
            f"**Self Roles:** {len(config.selfroles)} available\n"
            f"**Reaction Roles:** {len(config.reaction_roles)} configured",
            inline=True,
        )

        # Permissions summary
        embed.add_field(
            name=f"{get_emoji('permissions')} Permissions",
            value=f"**Custom Levels:** {len(config.perm_levels)} set\n"
            f"**Command Levels:** {len(config.command_levels)} customized\n"
            f"**Warn Punishments:** {len(config.warn_punishments)} configured",
            inline=True,
        )

        # Giveaway summary
        if config.giveaway.channel_id:
            embed.add_field(
                name=f"{get_emoji('giveaway')} Giveaway",
                value=f"**Channel:** <#{config.giveaway.channel_id}>\n"
                f"**Role:** {f'<@&{config.giveaway.role_id}>' if config.giveaway.role_id else 'None'}\n"
                f"**Status:** {'Ended' if config.giveaway.ended else 'Active'}",
                inline=True,
            )

        embed.add_field(
            name=f"{get_emoji('categories')} Categories",
            value="• `logs` - Logging channels\n"
            "• `modlog` - Moderation logs\n"
            "• `detections` - Content filters\n"
            "• `punishments` - Auto punishments\n"
            "• `roles` - Role management\n"
            "• `giveaway` - Giveaway settings\n"
            "• `general` - General settings",
            inline=False,
        )

        embed.set_footer(text=f"Use {prefix}settings <category> for detailed view")
        await ctx.send(embed=embed)

    def _add_logs_settings(self, embed: discord.Embed, config: Any) -> None:
        """Add logs settings to embed"""
        logs = config.logs
        enabled_logs = []
        disabled_logs = []

        for log_type, channel_id in logs.items():
            if channel_id:
                enabled_logs.append(f"• {log_type.replace('_', ' ').title()}: <#{channel_id}>")
            else:
                disabled_logs.append(f"• {log_type.replace('_', ' ').title()}")

        if enabled_logs:
            embed.add_field(
                name=f"{get_emoji('enabled')} Enabled Logs",
                value="\n".join(enabled_logs),
                inline=False,
            )
        if disabled_logs:
            embed.add_field(
                name=f"{get_emoji('disabled')} Disabled Logs",
                value="\n".join(disabled_logs),
                inline=False,
            )

    def _add_modlog_settings(self, embed: discord.Embed, config: Any) -> None:
        """Add modlog settings to embed"""
        modlogs = config.modlog
        enabled_modlogs = []
        disabled_modlogs = []

        for modlog_type, channel_id in modlogs.items():
            if channel_id:
                enabled_modlogs.append(
                    f"• {modlog_type.replace('_', ' ').title()}: <#{channel_id}>"
                )
            else:
                disabled_modlogs.append(f"• {modlog_type.replace('_', ' ').title()}")

        if enabled_modlogs:
            embed.add_field(
                name=f"{get_emoji('enabled')} Enabled Modlogs",
                value="\n".join(enabled_modlogs),
                inline=False,
            )
        if disabled_modlogs:
            embed.add_field(
                name=f"{get_emoji('disabled')} Disabled Modlogs",
                value="\n".join(disabled_modlogs),
                inline=False,
            )

    def _add_detections_settings(self, embed: discord.Embed, config: Any) -> None:
        """Add detections settings to embed"""
        detections = config.detections
        enabled_detections = []
        disabled_detections = []

        for detection_type, value in detections.items():
            if value and value != [] and value is not None:
                if isinstance(value, bool):
                    status = "Enabled" if value else "Disabled"
                elif isinstance(value, list):
                    status = f"{len(value)} items"
                else:
                    status = str(value)
                enabled_detections.append(f"• {detection_type.replace('_', ' ').title()}: {status}")
            else:
                disabled_detections.append(f"• {detection_type.replace('_', ' ').title()}")

        if enabled_detections:
            embed.add_field(
                name=f"{get_emoji('enabled')} Enabled Detections",
                value="\n".join(enabled_detections),
                inline=False,
            )
        if disabled_detections:
            embed.add_field(
                name=f"{get_emoji('disabled')} Disabled Detections",
                value="\n".join(disabled_detections),
                inline=False,
            )

        # Custom filters
        if detections.filters:
            embed.add_field(
                name=f"{get_emoji('filters')} Custom Filters",
                value=f"{len(detections.filters)} filters configured",
                inline=True,
            )
        if detections.regex_filters:
            embed.add_field(
                name=f"{get_emoji('regex')} Regex Filters",
                value=f"{len(detections.regex_filters)} filters configured",
                inline=True,
            )

    def _add_punishments_settings(self, embed: discord.Embed, config: Any) -> None:
        """Add punishments settings to embed"""
        punishments = config.detection_punishments

        for detection_type, punishment in punishments.items():
            if punishment:
                actions = []
                if punishment.get("warn", 0) > 0:
                    actions.append(f"Warn: {punishment['warn']}")
                if punishment.get("mute"):
                    actions.append(f"Mute: {punishment['mute']}")
                if punishment.get("kick"):
                    actions.append("Kick")
                if punishment.get("ban"):
                    actions.append("Ban")
                if punishment.get("delete"):
                    actions.append("Delete")

                embed.add_field(
                    name=f"{get_emoji('punishments')} {detection_type.replace('_', ' ').title()}",
                    value=", ".join(actions) if actions else "No actions",
                    inline=True,
                )

    def _add_roles_settings(self, embed: discord.Embed, config: Any) -> None:
        """Add roles settings to embed"""
        # Auto roles
        if config.autoroles:
            autoroles = [f"<@&{role_id}>" for role_id in config.autoroles]
            embed.add_field(
                name=f"{get_emoji('autoroles')} Auto Roles",
                value=", ".join(autoroles),
                inline=False,
            )

        # Self roles
        if config.selfroles:
            selfroles = [f"<@&{role_id}>" for role_id in config.selfroles]
            embed.add_field(
                name=f"{get_emoji('selfroles')} Self Roles",
                value=", ".join(selfroles),
                inline=False,
            )

        # Reaction roles
        if config.reaction_roles:
            embed.add_field(
                name=f"{get_emoji('reaction_roles')} Reaction Roles",
                value=f"{len(config.reaction_roles)} configured",
                inline=True,
            )

    def _add_giveaway_settings(self, embed: discord.Embed, config: Any) -> None:
        """Add giveaway settings to embed"""
        giveaway = config.giveaway

        if giveaway.channel_id:
            embed.add_field(
                name=f"{get_emoji('channel')} Channel",
                value=f"<#{giveaway.channel_id}>",
                inline=True,
            )
        if giveaway.role_id:
            embed.add_field(
                name=f"{get_emoji('role')} Role", value=f"<@&{giveaway.role_id}>", inline=True
            )
        if giveaway.emoji_id:
            # Display unicode emoji as-is; custom emoji as <:name:id>
            emoji_value = giveaway.emoji_id
            if isinstance(emoji_value, str) and emoji_value.isdigit():
                emoji_display = f"<:giveaway:{emoji_value}>"
            else:
                emoji_display = str(emoji_value)
            embed.add_field(
                name=f"{get_emoji('emoji')} Emoji", value=emoji_display, inline=True
            )

        embed.add_field(
            name=f"{get_emoji('status')} Status",
            value="Ended" if giveaway.ended else "Active",
            inline=True,
        )

    def _add_general_settings(self, embed: discord.Embed, config: Any) -> None:
        """Add general settings to embed"""
        embed.add_field(
            name=f"{get_emoji('prefix')} Prefix", value=f"`{config.prefix}`", inline=True
        )

        if config.mute_role:
            embed.add_field(
                name=f"{get_emoji('mute')} Mute Role", value=f"<@&{config.mute_role}>", inline=True
            )
        else:
            embed.add_field(name=f"{get_emoji('mute')} Mute Role", value="Not set", inline=True)

        embed.add_field(
            name=f"{get_emoji('offset')} Time Offset",
            value=f"{config.time_offset} hours",
            inline=True,
        )

        if config.whitelisted_guilds:
            embed.add_field(
                name=f"{get_emoji('whitelist')} Whitelisted Guilds",
                value=f"{len(config.whitelisted_guilds)} guilds",
                inline=True,
            )

    @command(0)
    async def about(self, ctx: commands.Context) -> None:
        """Enhanced about command with statistics"""
        stats = await self.bot.get_bot_stats()

        embed = discord.Embed(
            title=f"{get_emoji('bot')} About rainbot",
            description="A powerful moderation bot with automod and logging features",
            color=discord.Color.blue(),
        )

        embed.add_field(
            name=f"{get_emoji('stats')} Statistics",
            value=f"**Servers:** {stats['guilds']:,}\n"
            f"**Users:** {stats['users']:,}\n"
            f"**Commands Used:** {stats['commands_used']:,}\n"
            f"**Uptime:** {stats['uptime']}\n"
            f"**Latency:** {stats['latency']}ms",
            inline=True,
        )

        if stats["top_commands"]:
            top_cmds = "\n".join([f"• {cmd}: {count}" for cmd, count in stats["top_commands"]])
            embed.add_field(name="🔥 Top Commands", value=top_cmds, inline=True)

        embed.add_field(
            name=f"{get_emoji('link')} Links",
            value=f"[Invite Bot](https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&scope=bot&permissions=2013785334)\n"
            "[Support Server](https://discord.gg/zmdYe3ZVHG)\n"
            "[Documentation](https://github.com/fourjr/rainbot/wiki)",
            inline=False,
        )

        embed.set_footer(text=f"Made with ❤️ by the rainbot team")

        await ctx.send(embed=embed)

    @command(0)
    async def invite(self, ctx: commands.Context) -> None:
        """Get bot invite link"""
        embed = discord.Embed(
            title=f"{get_emoji('invite')} Invite rainbot",
            description="Click the link below to add rainbot to your server!",
            color=discord.Color.green(),
            url=f"https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&scope=bot&permissions=2013785334",
        )
        embed.add_field(
            name=f"{get_emoji('list')} Required Permissions",
            value="• Manage Messages\n• Kick Members\n• Ban Members\n• Manage Roles\n• View Channels\n• Send Messages\n• Embed Links\n• Attach Files\n• Read Message History\n• Use External Emojis",
            inline=False,
        )
        await ctx.send(embed=embed)

    @command(0)
    async def server(self, ctx: commands.Context) -> None:
        """Enhanced server information"""
        guild = ctx.guild

        embed = discord.Embed(
            title=f"{get_emoji('stats')} {guild.name}",
            description=guild.description or "No description",
            color=discord.Color.blue(),
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        # General info
        embed.add_field(name="👑 Owner", value=guild.owner.mention, inline=True)
        embed.add_field(name="🆔 ID", value=guild.id, inline=True)
        embed.add_field(
            name="📅 Created", value=guild.created_at.strftime("%B %d, %Y"), inline=True
        )

        # Member stats
        embed.add_field(name="👥 Members", value=f"{guild.member_count:,}", inline=True)
        embed.add_field(name="🤖 Bots", value=len([m for m in guild.members if m.bot]), inline=True)
        embed.add_field(
            name="👤 Humans", value=len([m for m in guild.members if not m.bot]), inline=True
        )

        # Channel stats
        embed.add_field(name="💬 Text Channels", value=len(guild.text_channels), inline=True)
        embed.add_field(name="🔊 Voice Channels", value=len(guild.voice_channels), inline=True)
        embed.add_field(name="📁 Categories", value=len(guild.categories), inline=True)

        # Role and emoji stats
        embed.add_field(name="🎭 Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="😀 Emojis", value=len(guild.emojis), inline=True)
        embed.add_field(name="🚀 Boost Level", value=guild.premium_tier, inline=True)

        await ctx.send(embed=embed)

    @command(0)
    async def mylevel(self, ctx: commands.Context) -> None:
        """Show user's permission level"""
        perm_level = get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))

        embed = discord.Embed(
            title=f"{get_emoji('user')} Your Permission Level", color=discord.Color.blue()
        )

        embed.add_field(
            name=f"{get_emoji('level')} Level", value=f"**{perm_level[0]}**", inline=True
        )
        embed.add_field(name=f"{get_emoji('book')} Role", value=f"**{perm_level[1]}**", inline=True)

        # Show what commands they can use
        available_commands = []
        for cmd in list(self.bot.commands):
            if await self.can_run(ctx, cmd):
                available_commands.append(cmd.qualified_name)

        if available_commands:
            embed.add_field(
                name=f"{get_emoji('commands')} Available Commands",
                value=f"You can use **{len(available_commands)}** commands",
                inline=False,
            )

        await ctx.send(embed=embed)

    @command(0)
    async def ping(self, ctx: commands.Context) -> None:
        """Enhanced ping command with detailed latency info"""
        start = datetime.utcnow()
        msg = await ctx.send(f"{get_emoji('ping')} Pinging...")
        end = datetime.utcnow()

        latency = (end - start).total_seconds() * 1000

        embed = discord.Embed(title=f"{get_emoji('ping')} Pong!", color=discord.Color.green())

        embed.add_field(
            name=f"{get_emoji('websocket')} WebSocket",
            value=f"`{self.bot.latency * 1000:.2f}ms`",
            inline=True,
        )
        embed.add_field(
            name=f"{get_emoji('message')} Message", value=f"`{latency:.2f}ms`", inline=True
        )

        # Status indicators
        if self.bot.latency < 0.1:
            status = f"{get_emoji('excellent')} Excellent"
        elif self.bot.latency < 0.3:
            status = f"{get_emoji('good')} Good"
        else:
            status = f"{get_emoji('poor')} Poor"

        embed.add_field(name=f"{get_emoji('status')} Status", value=status, inline=True)

        await msg.edit(content=None, embed=embed)

    @command(0)
    async def stats(self, ctx: commands.Context) -> None:
        """Show detailed bot statistics"""
        stats = await self.bot.get_bot_stats()

        embed = discord.Embed(
            title=f"{get_emoji('stats')} Bot Statistics", color=discord.Color.blue()
        )

        embed.add_field(
            name="🖥️ System",
            value=f"**Uptime:** {stats['uptime']}\n"
            f"**Latency:** {stats['latency']}ms\n"
            f"**Servers:** {stats['guilds']:,}\n"
            f"**Users:** {stats['users']:,}",
            inline=True,
        )

        embed.add_field(
            name="📈 Usage",
            value=f"**Commands Used:** {stats['commands_used']:,}\n"
            f"**Successful:** {stats['successful_commands']:,}\n"
            f"**Errors:** {stats['errors']:,}\n"
            f"**Success Rate:** {(stats['successful_commands'] / max(stats['commands_used'], 1) * 100):.1f}%",
            inline=True,
        )

        if stats["top_commands"]:
            top_cmds = "\n".join([f"• {cmd}: {count}" for cmd, count in stats["top_commands"]])
            embed.add_field(name="🔥 Top Commands", value=top_cmds, inline=False)

        await ctx.send(embed=embed)

    @command(0, name="serverhealth", hidden=True)
    async def serverhealth(self, ctx: commands.Context) -> None:
        """Secret command to show server health information"""
        import psutil
        import platform
        from datetime import datetime, timedelta

        # Get system information
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        # Get uptime
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time

        # Get bot uptime
        bot_uptime = (
            datetime.now() - self.bot.start_time
            if hasattr(self.bot, "start_time")
            else timedelta(0)
        )

        # Get process info
        process = psutil.Process()
        process_memory = process.memory_info().rss / 1024 / 1024  # MB

        embed = discord.Embed(
            title=f"{get_emoji('system')} Server Health",
            description="Detailed system and bot information",
            color=discord.Color.blue(),
            timestamp=datetime.now(),
        )

        # Bot Stats
        embed.add_field(
            name=f"{get_emoji('bot')} Bot Stats",
            value=f"**Version:** `{BOT_VERSION}`\n"
            f"**Clusters:** `1 / 1`\n"
            f"**Servers:** `{len(self.bot.guilds):,}`\n"
            f"**Users:** `{len(self.bot.users):,}`\n"
            f"**Ping:** `{self.bot.latency * 1000:.0f}ms`\n"
            f"**Bot Uptime:** `{str(bot_uptime).split('.')[0]}`",
            inline=True,
        )

        # Server Stats
        embed.add_field(
            name=f"{get_emoji('system')} Server Stats",
            value=f"**OS:** `{platform.system()} {platform.release()}`\n"
            f"**CPU:** `{platform.processor().split()[0]}`\n"
            f"**CPU Usage:** `{cpu_percent:.2f}%`\n"
            f"**RAM Usage:** `{memory.used / 1024 / 1024 / 1024:.2f} GB / {memory.total / 1024 / 1024 / 1024:.1f} GB`\n"
            f"**System Uptime:** `{str(uptime).split('.')[0]}`",
            inline=True,
        )

        # Process Info
        embed.add_field(
            name=f"{get_emoji('process')} Process Info",
            value=f"**Memory:** `{process_memory:.0f} MB`\n"
            f"**CPU:** `{process.cpu_percent():.2f}%`\n"
            f"**Threads:** `{process.num_threads()}`\n"
            f"**Status:** `{process.status()}`",
            inline=True,
        )

        # Disk Info
        embed.add_field(
            name=f"{get_emoji('disk')} Disk Usage",
            value=f"**Used:** `{disk.used / 1024 / 1024 / 1024:.1f} GB`\n"
            f"**Free:** `{disk.free / 1024 / 1024 / 1024:.1f} GB`\n"
            f"**Total:** `{disk.total / 1024 / 1024 / 1024:.1f} GB`\n"
            f"**Usage:** `{(disk.used / disk.total) * 100:.1f}%`",
            inline=True,
        )

        # Network Info
        try:
            network = psutil.net_io_counters()
            embed.add_field(
                name=f"{get_emoji('network')} Network",
                value=f"**Bytes Sent:** `{network.bytes_sent / 1024 / 1024:.1f} MB`\n"
                f"**Bytes Recv:** `{network.bytes_recv / 1024 / 1024:.1f} MB`\n"
                f"**Packets Sent:** `{network.packets_sent:,}`\n"
                f"**Packets Recv:** `{network.packets_recv:,}`",
                inline=True,
            )
        except:
            pass

        embed.set_footer(text="Secret command - Server health monitoring")
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_join(self, guild) -> None:
        """Enhanced guild join handling with welcome message"""
        try:
            # Find a suitable channel to send welcome message
            system_channel = guild.system_channel
            if system_channel and system_channel.permissions_for(guild.me).send_messages:
                welcome_embed = await self.bot.create_welcome_embed(guild)
                await system_channel.send(embed=welcome_embed)

            # Log to owner channel (from configured Owner Log Channel ID if available)
            channel_id = getattr(self.bot, "OWNER_LOG_CHANNEL_ID", None)
            channel = self.bot.get_channel(channel_id) if channel_id else None
            if channel:
                embed = discord.Embed(
                    title="🎉 New Server!",
                    description=f"**{guild.name}** ({guild.id})\n"
                    f"**Members:** {len(guild.members):,}\n"
                    f"**Owner:** {guild.owner}",
                    color=discord.Color.green(),
                )
                await channel.send(embed=embed)
        except Exception as e:
            self.bot.logger.error(f"Error in guild join for {guild.id}: {e}")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild) -> None:
        """Enhanced guild leave handling"""
        try:
            channel_id = getattr(self.bot, "OWNER_LOG_CHANNEL_ID", None)
            channel = self.bot.get_channel(channel_id) if channel_id else None
            if channel:
                embed = discord.Embed(
                    title="👋 Server Left",
                    description=f"**{guild.name}** ({guild.id})\n"
                    f"**Members:** {len(guild.members):,}\n"
                    f"**Owner:** {guild.owner}",
                    color=discord.Color.red(),
                )
                await channel.send(embed=embed)
        except Exception as e:
            self.bot.logger.error(f"Error in guild remove for {guild.id}: {e}")


async def setup(bot: "rainbot") -> None:
    await bot.add_cog(Utility(bot))
