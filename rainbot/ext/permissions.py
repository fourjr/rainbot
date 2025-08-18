from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

import discord

if TYPE_CHECKING:
    from rainbot.core.bot import rainbot
    from rainbot.services.database import DBDict
    from .command import RainCommand, RainGroup  # noqa: F41


def get_perm_level(bot: "rainbot", member: discord.Member, guild_config: DBDict) -> Tuple[int, str]:
    if member.id in bot.owners:
        return 10, "Bot Owner"

    if hasattr(member, "guild") and member.id == member.guild.owner_id:
        return 9, "Server Owner"

    # Check if member is a discord.Member (has roles) or just discord.User
    if hasattr(member, "roles"):
        for perm_level in guild_config.perm_levels:
            if discord.utils.get(member.roles, id=int(perm_level["role_id"])):
                return int(perm_level["level"]), f"Level {perm_level['level']}"

    return 0, "Default"


def get_command_level(command: RainCommand, guild_config: DBDict) -> int:
    if command.qualified_name in guild_config.command_levels:
        return guild_config.command_levels[command.qualified_name]

    return command.perm_level
