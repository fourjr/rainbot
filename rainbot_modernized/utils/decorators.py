"""Command decorators for permission checking"""

import discord
from discord.ext import commands
from typing import Callable, Any
from enum import IntEnum


class PermissionLevel(IntEnum):
    EVERYONE = 0
    HELPER = 1
    MODERATOR = 2
    SENIOR_MODERATOR = 3
    ADMINISTRATOR = 4
    SENIOR_ADMINISTRATOR = 5
    SERVER_MANAGER = 6
    SERVER_OWNER = 7
    BOT_DEVELOPER = 8
    BOT_OWNER = 9
    SYSTEM = 10


def require_permission(level: PermissionLevel):
    """Decorator to require a specific permission level"""

    def decorator(func: Callable) -> Callable:
        async def predicate(ctx: commands.Context) -> bool:
            # Bot owners bypass all checks
            owner_ids = getattr(ctx.bot, "owner_ids", set())
            if ctx.author.id in owner_ids:
                return True

            # Get user's permission level from bot's permission manager
            if hasattr(ctx.bot, "permissions") and ctx.bot.permissions:
                user_level = await ctx.bot.permissions.get_user_level(
                    ctx.guild, ctx.author
                )
            else:
                user_level = await get_user_permission_level(ctx)

            if user_level < level:
                raise commands.CheckFailure(f"Required permission level: {level.name}")

            return True

        func.__permission_level__ = level
        return commands.check(predicate)(func)

    return decorator


def has_permissions(level: int = None, **perms):
    """Decorator to check permissions - supports both level and Discord permissions"""

    def decorator(func: Callable) -> Callable:
        if level is not None:
            # Use permission level check
            return require_permission(PermissionLevel(level))(func)
        else:
            # Use Discord permissions check
            return commands.has_permissions(**perms)(func)

    return decorator


async def get_user_permission_level(ctx: commands.Context) -> int:
    """Get user's permission level based on roles and server position"""
    if not isinstance(ctx.author, discord.Member):
        return PermissionLevel.EVERYONE

    # Server owner
    if ctx.author == ctx.guild.owner:
        return PermissionLevel.SERVER_OWNER

    # Check for administrator permission
    if ctx.author.guild_permissions.administrator:
        return PermissionLevel.ADMINISTRATOR

    # Check for moderation permissions
    if ctx.author.guild_permissions.ban_members:
        return PermissionLevel.SENIOR_MODERATOR

    if ctx.author.guild_permissions.kick_members:
        return PermissionLevel.MODERATOR

    if ctx.author.guild_permissions.manage_messages:
        return PermissionLevel.HELPER

    return PermissionLevel.EVERYONE
