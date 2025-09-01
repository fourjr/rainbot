from enum import IntEnum
from typing import Dict, Any, Optional
import discord
from discord.ext import commands


class PermissionLevel(IntEnum):
    """Permission levels for commands"""

    EVERYONE = 0
    TRUSTED = 1
    HELPER = 2
    MODERATOR = 3
    SENIOR_MODERATOR = 4
    ADMINISTRATOR = 5
    SENIOR_ADMINISTRATOR = 6
    SERVER_MANAGER = 7
    SERVER_OWNER = 8
    BOT_ADMIN = 9
    BOT_OWNER = 10


class PermissionManager:
    """Manages permission levels for users"""

    def __init__(self, db, bot):
        self.db = db
        self.bot = bot

    async def get_user_level(self, guild: discord.Guild, user: discord.Member) -> int:
        """Get the permission level for a user, combining custom roles and Discord permissions."""
        # Bot owners have maximum permissions
        if user.id in self.bot.owner_ids:
            return PermissionLevel.BOT_OWNER

        # Server owner
        if user.id == guild.owner_id:
            return PermissionLevel.SERVER_OWNER

        # Start with base level
        highest_level = PermissionLevel.EVERYONE

        # 1. Check custom permission roles from DB
        config = await self.db.get_guild_config(guild.id)
        permission_roles = config.get("permission_roles", {})
        for role in user.roles:
            role_level = permission_roles.get(str(role.id), 0)
            if role_level > highest_level:
                highest_level = PermissionLevel(role_level)

        # 2. Check built-in Discord permissions and assign a corresponding level
        discord_perms_level = PermissionLevel.EVERYONE
        if user.guild_permissions.administrator:
            discord_perms_level = PermissionLevel.ADMINISTRATOR
        elif user.guild_permissions.ban_members:
            discord_perms_level = PermissionLevel.SENIOR_MODERATOR
        elif user.guild_permissions.kick_members:
            discord_perms_level = PermissionLevel.MODERATOR
        elif user.guild_permissions.manage_messages:
            discord_perms_level = PermissionLevel.HELPER

        # Return the highest of the two
        return max(highest_level, discord_perms_level)

    async def has_permission(
        self, guild: discord.Guild, user: discord.Member, required_level: int
    ) -> bool:
        """Check if user has required permission level"""
        user_level = await self.get_user_level(guild, user)
        return user_level >= required_level
