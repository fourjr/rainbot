"""Command decorators for permission checking"""

import discord
from discord.ext import commands
from typing import Callable, Any
from enum import IntEnum

from core.permissions import PermissionLevel


def require_permission(level: PermissionLevel):
    """Decorator to require a specific permission level

    Now respects per-command overrides stored in the guild configuration under
    `command_levels.{qualified_name}`. If an override exists, it will be used
    instead of the static decorator level.
    """

    def decorator(func: Callable) -> Callable:
        async def predicate(ctx: commands.Context) -> bool:
            # Bot owners bypass all checks
            owner_ids = getattr(ctx.bot, "owner_ids", set())
            if ctx.author.id in owner_ids:
                return True

            # Determine required level, allowing per-command override from DB
            required_level_value = int(level)
            try:
                if getattr(ctx.bot, "db", None) and ctx.guild is not None:
                    config = await ctx.bot.db.get_guild_config(ctx.guild.id)
                    overrides = config.get("command_levels", {}) or {}
                    override_val = overrides.get(ctx.command.qualified_name)
                    if override_val is not None:
                        required_level_value = int(override_val)
            except Exception:
                # Fail open to static level if DB lookup fails
                required_level_value = int(level)

            # Get user's permission level from bot's permission manager
            if hasattr(ctx.bot, "permissions") and ctx.bot.permissions:
                user_level = await ctx.bot.permissions.get_user_level(
                    ctx.guild, ctx.author
                )
            else:
                user_level = await get_user_permission_level(ctx)

            if user_level < required_level_value:
                # Build friendly name for required level if possible
                try:
                    req_name = PermissionLevel(required_level_value).name
                except ValueError:
                    req_name = str(required_level_value)
                raise commands.CheckFailure(f"Required permission level: {req_name}")

            return True

        # Keep a hint of the default level on the function for introspection
        func.__permission_level__ = level
        return commands.check(predicate)(func)

    return decorator


def has_permissions(level: int = None, **perms):
    """Decorator to check permissions - supports both level and Discord permissions"""

    def decorator(func: Callable) -> Callable:
        if level is not None:
            # Use permission level check (respects per-command overrides)
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
