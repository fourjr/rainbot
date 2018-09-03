from discord.ext import commands

from .utils import get_perm_level
from ext.errors import Underleveled


async def check_perm_level(ctx):
    guild_info = await ctx.guild_config()

    perm_level = get_perm_level(ctx.author, guild_info)[0]

    if not perm_level >= ctx.command.perm_level:
        raise Underleveled(f"User's level ({perm_level}) is not enough for the command's required level ({ctx.command.perm_level})")
    return True


class RainCommand(commands.Command):
    """Overwrites the default Command to use permission levels,
    overwrites signature to hide aliases"""

    def __init__(self, name, callback, **kwargs):
        super().__init__(name, callback, **kwargs)
        self.perm_level = kwargs.get('perm_level')
        if self.perm_level:
            self.checks.append(check_perm_level)

    @property
    def signature(self):
        """Returns a POSIX-like signature useful for help command output."""
        result = []
        parent = self.full_parent_name
        name = self.name if not parent else parent + ' ' + self.name
        result.append(name)

        if self.usage:
            result.append(self.usage)
            return ' '.join(result)

        params = self.clean_params
        if not params:
            return ' '.join(result)

        for name, param in params.items():
            if param.default is not param.empty:
                # We don't want None or '' to trigger the [name=value] case and instead it should
                # do [name] since [name=None] or [name=] are not exactly useful for the user.
                should_print = param.default if isinstance(param.default, str) else param.default is not None
                if should_print:
                    result.append('[%s=%s]' % (name, param.default))
                else:
                    result.append('[%s]' % name)
            elif param.kind == param.VAR_POSITIONAL:
                result.append('[%s...]' % name)
            else:
                result.append('<%s>' % name)

        return ' '.join(result)


class RainGroup(commands.Group):
    """Overwrites the default Command to use permission levels,
    overwrites signature to hide aliases"""

    def __init__(self, **attrs):
        super().__init__(**attrs)
        self.perm_level = attrs.get('perm_level')
        if self.perm_level:
            self.checks.append(check_perm_level)

    def command(self, *args, **kwargs):
        """Overwrites GroupMixin.command to use RainCommand"""
        def decorator(func):
            result = command(*args, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator

    @property
    def signature(self):
        """Returns a POSIX-like signature useful for help command output."""
        result = []
        parent = self.full_parent_name
        name = self.name if not parent else parent + ' ' + self.name
        result.append(name)

        if self.usage:
            result.append(self.usage)
            return ' '.join(result)

        params = self.clean_params
        if not params:
            return ' '.join(result)

        for name, param in params.items():
            if param.default is not param.empty:
                # We don't want None or '' to trigger the [name=value] case and instead it should
                # do [name] since [name=None] or [name=] are not exactly useful for the user.
                should_print = param.default if isinstance(param.default, str) else param.default is not None
                if should_print:
                    result.append('[%s=%s]' % (name, param.default))
                else:
                    result.append('[%s]' % name)
            elif param.kind == param.VAR_POSITIONAL:
                result.append('[%s...]' % name)
            else:
                result.append('<%s>' % name)

        return ' '.join(result)


def command(level, *args, **kwargs):
    kwargs['perm_level'] = level
    return commands.command(cls=RainCommand, *args, **kwargs)


def group(level, *args, **kwargs):
    """Overwrites the default group to use RainGroup"""
    kwargs['perm_level'] = level
    return commands.command(cls=RainGroup, *args, **kwargs)
