from typing import Any, Callable

import discord
from discord.ext import commands

from ..ext.permissions import get_perm_level, get_command_level
from ..ext.errors import Underleveled


async def check_perm_level(ctx: commands.Context, *, command_level: int = None) -> bool:
    guild_config = await ctx.bot.db.get_guild_config(ctx.guild.id)

    if isinstance(ctx.author, discord.Member):
        perm_level = get_perm_level(ctx.bot, ctx.author, guild_config)[0]
    else:
        perm_level = 10

    cmd_level = command_level or get_command_level(ctx.command, guild_config)

    if not perm_level >= cmd_level:
        raise Underleveled(
            f"User's level ({perm_level}) is not enough for the command's required level ({cmd_level})"
        )
    return True


class RainCommand(commands.Command):
    """Overwrites the default Command to use permission levels,
    overwrites signature to hide aliases"""

    def __init__(self, callback: Callable, **kwargs: Any) -> None:
        super().__init__(callback, **kwargs)
        self.perm_level = kwargs.get("perm_level", 0)
        self.checks.append(check_perm_level)

    async def invoke(self, ctx):
        """Override invoke to show help when required parameters are missing"""
        try:
            await super().invoke(ctx)
        except commands.MissingRequiredArgument:
            await ctx.send_help(self)
        except commands.BadArgument as e:
            if "is a required argument that is missing" in str(e):
                await ctx.send_help(self)
            else:
                raise

    @property
    def signature(self) -> str:
        """Returns a POSIX-like signature useful for help command output."""
        result = []
        parent = self.full_parent_name
        name = self.name if not parent else parent + " " + self.name
        result.append(name)

        if self.usage:
            result.append(self.usage)
            return " ".join(result)

        params = self.clean_params
        if not params:
            return " ".join(result)

        for name, param in params.items():
            if param.default is not param.empty:
                # We don't want None or '' to trigger the [name=value] case and instead it should
                # do [name] since [name=None] or [name=] are not exactly useful for the user.
                should_print = (
                    param.default if isinstance(param.default, str) else param.default is not None
                )
                if should_print:
                    result.append("[%s=%s]" % (name, param.default))
                else:
                    result.append("[%s]" % name)
            elif param.kind == param.VAR_POSITIONAL:
                result.append("[%s...]" % name)
            else:
                result.append("<%s>" % name)

        return " ".join(result)


class RainGroup(commands.Group):
    """Overwrites the default Command to use permission levels,
    overwrites signature to hide aliases"""

    def __init__(self, *args: Any, **attrs: Any) -> None:
        super().__init__(*args, **attrs)
        self.perm_level = attrs.get("perm_level")
        if self.perm_level:
            self.checks.append(check_perm_level)

    async def invoke(self, ctx):
        """Override invoke to show formatted help when no subcommand is provided"""
        if ctx.invoked_subcommand is None:
            if ctx.subcommand_passed is not None:
                await ctx.send_help(self)
            else:
                await self.send_group_help(ctx)
        else:
            await super().invoke(ctx)

    async def send_group_help(self, ctx):
        """Send formatted help for group commands"""
        embed = discord.Embed(
            title=f"🔧 {self.name.title()} Commands",
            description=self.help or f"Commands for {self.name}",
            color=discord.Color.blue(),
        )

        if self.commands:
            commands_text = ""
            for cmd in self.commands:
                commands_text += f"`{cmd.name}` - {cmd.short_doc or 'No description'}\n"
            embed.add_field(name="📋 Available Commands", value=commands_text, inline=False)

        embed.add_field(
            name="💡 Usage",
            value=f"Use `{ctx.prefix}{self.name} <command>` to run a specific command.",
            inline=False,
        )

        await ctx.send(embed=embed)

    def command(self, *args: Any, **kwargs: Any) -> Callable:
        """Overwrites GroupMixin.command to use RainCommand"""

        def decorator(func: Callable) -> bool:
            kwargs.setdefault("parent", self)
            # Use the group's permission level if no level is provided
            level = self.perm_level if self.perm_level is not None else 0
            result = command(level, *args, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator

    @property
    def signature(self) -> str:
        """Returns a POSIX-like signature useful for help command output."""
        result = []
        parent = self.full_parent_name
        name = self.name if not parent else parent + " " + self.name
        result.append(name)

        if self.usage:
            result.append(self.usage)
            return " ".join(result)

        params = self.clean_params
        if not params:
            return " ".join(result)

        for name, param in params.items():
            if param.default is not param.empty:
                # We don't want None or '' to trigger the [name=value] case and instead it should
                # do [name] since [name=None] or [name=] are not exactly useful for the user.
                should_print = (
                    param.default if isinstance(param.default, str) else param.default is not None
                )
                if should_print:
                    result.append("[%s=%s]" % (name, param.default))
                else:
                    result.append("[%s]" % name)
            elif param.kind == param.VAR_POSITIONAL:
                result.append("[%s...]" % name)
            else:
                result.append("<%s>" % name)

        return " ".join(result)


def command(level: int, **kwargs: Any) -> Callable:
    kwargs["perm_level"] = level
    return commands.command(cls=RainCommand, **kwargs)


def group(level: int, **kwargs: Any) -> Callable:
    """Overwrites the default group to use RainGroup"""
    kwargs["perm_level"] = level
    return commands.group(cls=RainGroup, **kwargs)
