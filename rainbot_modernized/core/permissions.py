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

    def __init__(self, db):
        self.db = db

    async def get_user_level(self, guild: discord.Guild, user: discord.Member) -> int:
        """Get the permission level for a user"""
        # Bot owners have maximum permissions
        if user.id in [188363246695219201, 95280508384063488, 231595246213922828]:
            return PermissionLevel.BOT_OWNER

        # Server owner has server manager permissions
        if user.id == guild.owner_id:
            return PermissionLevel.SERVER_OWNER

        # Check role-based permissions
        config = await self.db.get_guild_config(guild.id)
        permission_roles = config.get("permission_roles", {})

        highest_level = PermissionLevel.EVERYONE

        for role in user.roles:
            role_level = permission_roles.get(str(role.id), 0)
            if role_level > highest_level:
                highest_level = role_level

        return highest_level

    async def has_permission(
        self, guild: discord.Guild, user: discord.Member, required_level: int
    ) -> bool:
        """Check if user has required permission level"""
        user_level = await self.get_user_level(guild, user)
        return user_level >= required_level
