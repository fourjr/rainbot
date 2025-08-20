"""Custom converters for command arguments"""

import discord
from discord.ext import commands
from datetime import timedelta


class EmojiOrUnicode(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        try:
            return await commands.EmojiConverter().convert(ctx, argument)
        except commands.BadArgument:
            return argument


from discord.ext import commands
from typing import Union


class MemberOrID(commands.IDConverter):
    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> Union[discord.Member, discord.User]:
        try:
            return await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            try:
                return await ctx.bot.fetch_user(int(argument))
            except (ValueError, TypeError):
                raise commands.BadArgument(f"Member {argument} not found")


class MemberOrUser(commands.Converter):
    """Converter that tries to get a Member, falls back to User"""

    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> Union[discord.Member, discord.User]:
        try:
            # Try member converter first
            return await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            try:
                # Fall back to user converter
                return await commands.UserConverter().convert(ctx, argument)
            except commands.BadArgument:
                # Try to fetch user by ID
                try:
                    user_id = int(argument)
                    return await ctx.bot.fetch_user(user_id)
                except (ValueError, discord.NotFound):
                    raise commands.BadArgument(f"Member or user '{argument}' not found")


class Duration(commands.Converter):
    """Converter for time durations like '1h', '30m', '2d'"""

    async def convert(self, ctx: commands.Context, argument: str) -> timedelta:
        """Convert duration string to timedelta"""
        import re

        # Parse duration string
        pattern = r"(\d+)([smhdw])"
        matches = re.findall(pattern, argument.lower())

        if not matches:
            raise commands.BadArgument(
                "Invalid duration format. Use format like: 1h, 30m, 2d"
            )

        total_seconds = 0
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}

        for amount, unit in matches:
            total_seconds += int(amount) * multipliers[unit]

        return timedelta(seconds=total_seconds)
