from __future__ import annotations

import inspect
import io
import os
import subprocess
import textwrap
import traceback
from contextlib import redirect_stdout
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Union

import discord
from discord.ext import commands
from ext.command import RainCommand, RainGroup, command
from ext.paginator import Paginator
from ext.utility import get_command_level, get_perm_level, owner

if TYPE_CHECKING:
    from bot import rainbot


class Utility(commands.Cog):
    """General utility commands and enhanced help system"""

    def __init__(self, bot: "rainbot") -> None:
        self.bot = bot
        self.order = 4

    @owner()
    @command(0, name="eval")
    async def _eval(self, ctx: commands.Context, *, body: str) -> None:
        """Evaluates python code with enhanced output"""
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
                can_run = await discord.utils.async_all(predicate(ctx) for predicate in cmd.checks)
            except commands.CheckFailure:
                can_run = False
        return can_run

    async def format_cog_help(
        self, ctx: commands.Context, prefix: str, cog: commands.Cog
    ) -> Optional[discord.Embed]:
        """Enhanced cog help formatting"""
        em = discord.Embed(
            title=f"📚 {cog.__class__.__name__}",
            description=cog.__doc__ or "No description available",
            color=discord.Color.blue(),
        )

        commands_list = []
        for i in inspect.getmembers(
            cog, predicate=lambda x: isinstance(x, (RainCommand, RainGroup))
        ):
            if i[1].parent:
                continue
            if await self.can_run(ctx, i[1]):
                commands_list.append(i[1])

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
                value = "\n".join(
                    [f"`{prefix}{cmd.name}` - {cmd.short_doc or 'No description'}" for cmd in cmds]
                )
                if len(value) > 1024:
                    # Split into multiple fields if too long
                    chunks = [value[i : i + 1024] for i in range(0, len(value), 1024)]
                    for i, chunk in enumerate(chunks):
                        em.add_field(
                            name=f"Commands (Level {level})"
                            + (f" (Part {i+1})" if len(chunks) > 1 else ""),
                            value=chunk,
                            inline=False,
                        )
                else:
                    em.add_field(name=f"Commands (Level {level})", value=value, inline=False)

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
                    description=f"{cmd.help}\n\n**Permission Level:** {cmd_level}",
                    color=discord.Color.blue(),
                )

                if cmd.aliases:
                    em.add_field(
                        name="🔄 Aliases", value=f"`{', '.join(cmd.aliases)}`", inline=True
                    )

                return em

            elif isinstance(cmd, RainGroup):
                em = discord.Embed(
                    title=f"📖 {prefix}{cmd.signature}",
                    description=f"{cmd.help}\n\n**Permission Level:** {cmd_level}",
                    color=discord.Color.blue(),
                )

                subcommands = []
                for i in list(cmd.commands):
                    if await self.can_run(ctx, i):
                        subcommands.append(f"`{i.name}` - {i.short_doc or 'No description'}")

                if subcommands:
                    em.add_field(name="📋 Subcommands", value="\n".join(subcommands), inline=False)
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
                        title="❌ Command/Cog Not Found",
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
                            name="💡 Did you mean?", value=", ".join(suggestions[:5]), inline=False
                        )

                    await ctx.send(content=error, embed=embed)
                    return

                em = await self.format_cog_help(ctx, prefix, cog)
                await ctx.send(content=error, embed=em)
            else:
                em = await self.format_command_help(ctx, prefix, cmd)
                await ctx.send(content=error, embed=em)
        else:
            # Main help menu
            embed = discord.Embed(
                title="🤖 rainbot Help",
                description="Welcome to rainbot! Here are the available command categories:",
                color=discord.Color.blue(),
            )

            # Get available cogs
            available_cogs = []
            for cog in self.bot.cogs.values():
                if cog.__class__.__name__ != "Utility":  # Don't show utility in main help
                    commands_list = list(cog.get_commands())
                    has_commands = any(await self.can_run(ctx, cmd) for cmd in commands_list)
                    if has_commands:
                        available_cogs.append(cog)

            if available_cogs:
                cog_list = []
                for cog in available_cogs:
                    commands_list = list(cog.get_commands())
                    cmd_count = len(
                        [cmd for cmd in commands_list if await self.can_run(ctx, cmd)]
                    )
                    cog_list.append(f"📚 **{cog.__class__.__name__}** - {cmd_count} commands")

                embed.add_field(name="📋 Categories", value="\n".join(cog_list), inline=False)

            embed.add_field(
                name="🔍 Usage",
                value=f"Use `{prefix}help <category>` to see commands in a category\n"
                f"Use `{prefix}help <command>` to see detailed help for a command",
                inline=False,
            )

            embed.add_field(
                name="🔗 Quick Links",
                value="[Support Server](https://discord.gg/zmdYe3ZVHG) • [Documentation](https://github.com/fourjr/rainbot/wiki)",
                inline=False,
            )

            embed.set_footer(text=f"Prefix: {prefix} | Total Commands: {len(list(self.bot.commands))}")

            await ctx.send(content=error, embed=embed)

    @command(0)
    async def about(self, ctx: commands.Context) -> None:
        """Enhanced about command with statistics"""
        stats = await self.bot.get_bot_stats()

        embed = discord.Embed(
            title="🤖 About rainbot",
            description="A powerful moderation bot with automod and logging features",
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="📊 Statistics",
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
            name="🔗 Links",
            value="[Invite Bot](https://discord.com/oauth2/authorize?client_id=372748944448552961&scope=bot&permissions=2013785334)\n"
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
            title="🔗 Invite rainbot",
            description="Click the link below to add rainbot to your server!",
            color=discord.Color.green(),
            url="https://discord.com/oauth2/authorize?client_id=372748944448552961&scope=bot&permissions=2013785334",
        )
        embed.add_field(
            name="📋 Required Permissions",
            value="• Manage Messages\n• Kick Members\n• Ban Members\n• Manage Roles\n• View Channels\n• Send Messages\n• Embed Links\n• Attach Files\n• Read Message History\n• Use External Emojis",
            inline=False,
        )
        await ctx.send(embed=embed)

    @command(0)
    async def server(self, ctx: commands.Context) -> None:
        """Enhanced server information"""
        guild = ctx.guild

        embed = discord.Embed(
            title=f"📊 {guild.name}",
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

        embed = discord.Embed(title="👤 Your Permission Level", color=discord.Color.blue())

        embed.add_field(name="📊 Level", value=f"**{perm_level[0]}**", inline=True)
        embed.add_field(name="📝 Role", value=f"**{perm_level[1]}**", inline=True)

        # Show what commands they can use
        available_commands = []
        for cmd in list(self.bot.commands):
            if await self.can_run(ctx, cmd):
                available_commands.append(cmd.qualified_name)

        if available_commands:
            embed.add_field(
                name="🔧 Available Commands",
                value=f"You can use **{len(available_commands)}** commands",
                inline=False,
            )

        await ctx.send(embed=embed)

    @command(0)
    async def ping(self, ctx: commands.Context) -> None:
        """Enhanced ping command with detailed latency info"""
        start = datetime.utcnow()
        msg = await ctx.send("🏓 Pinging...")
        end = datetime.utcnow()

        latency = (end - start).total_seconds() * 1000

        embed = discord.Embed(title="🏓 Pong!", color=discord.Color.green())

        embed.add_field(
            name="🌐 WebSocket", value=f"`{self.bot.latency * 1000:.2f}ms`", inline=True
        )
        embed.add_field(name="💬 Message", value=f"`{latency:.2f}ms`", inline=True)

        # Status indicators
        if self.bot.latency < 0.1:
            status = "🟢 Excellent"
        elif self.bot.latency < 0.3:
            status = "🟡 Good"
        else:
            status = "🔴 Poor"

        embed.add_field(name="📊 Status", value=status, inline=True)

        await msg.edit(content=None, embed=embed)

    @command(0)
    async def stats(self, ctx: commands.Context) -> None:
        """Show detailed bot statistics"""
        stats = await self.bot.get_bot_stats()

        embed = discord.Embed(title="📊 Bot Statistics", color=discord.Color.blue())

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

    @commands.Cog.listener()
    async def on_guild_join(self, guild) -> None:
        """Enhanced guild join handling with welcome message"""
        try:
            # Find a suitable channel to send welcome message
            system_channel = guild.system_channel
            if system_channel and system_channel.permissions_for(guild.me).send_messages:
                welcome_embed = await self.bot.create_welcome_embed(guild)
                await system_channel.send(embed=welcome_embed)

            # Log to owner channel
            channel = self.bot.get_channel(733702521893289985)
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
            channel = self.bot.get_channel(733702521893289985)
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
