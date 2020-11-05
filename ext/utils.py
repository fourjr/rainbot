from __future__ import annotations
import datetime
import random
import re
from typing import Any, Callable, Optional, Tuple, Union, TYPE_CHECKING

import discord
from discord.ext import commands
from discord.ext.commands import check

if TYPE_CHECKING:
    from bot import rainbot
    from ext.database import DBDict
    from ext.command import RainCommand, RainGroup  # noqa: F401


UNICODE_EMOJI = r'(?:\U0001f1e6[\U0001f1e8-\U0001f1ec\U0001f1ee\U0001f1f1\U0001f1f2\U0001f1f4\U0001f1f6-\U0001f1fa\U0001f1fc\U0001f1fd\U0001f1ff])|(?:\U0001f1e7[\U0001f1e6\U0001f1e7\U0001f1e9-\U0001f1ef\U0001f1f1-\U0001f1f4\U0001f1f6-\U0001f1f9\U0001f1fb\U0001f1fc\U0001f1fe\U0001f1ff])|(?:\U0001f1e8[\U0001f1e6\U0001f1e8\U0001f1e9\U0001f1eb-\U0001f1ee\U0001f1f0-\U0001f1f5\U0001f1f7\U0001f1fa-\U0001f1ff])|(?:\U0001f1e9[\U0001f1ea\U0001f1ec\U0001f1ef\U0001f1f0\U0001f1f2\U0001f1f4\U0001f1ff])|(?:\U0001f1ea[\U0001f1e6\U0001f1e8\U0001f1ea\U0001f1ec\U0001f1ed\U0001f1f7-\U0001f1fa])|(?:\U0001f1eb[\U0001f1ee-\U0001f1f0\U0001f1f2\U0001f1f4\U0001f1f7])|(?:\U0001f1ec[\U0001f1e6\U0001f1e7\U0001f1e9-\U0001f1ee\U0001f1f1-\U0001f1f3\U0001f1f5-\U0001f1fa\U0001f1fc\U0001f1fe])|(?:\U0001f1ed[\U0001f1f0\U0001f1f2\U0001f1f3\U0001f1f7\U0001f1f9\U0001f1fa])|(?:\U0001f1ee[\U0001f1e8-\U0001f1ea\U0001f1f1-\U0001f1f4\U0001f1f6-\U0001f1f9])|(?:\U0001f1ef[\U0001f1ea\U0001f1f2\U0001f1f4\U0001f1f5])|(?:\U0001f1f0[\U0001f1ea\U0001f1ec-\U0001f1ee\U0001f1f2\U0001f1f3\U0001f1f5\U0001f1f7\U0001f1fc\U0001f1fe\U0001f1ff])|(?:\U0001f1f1[\U0001f1e6-\U0001f1e8\U0001f1ee\U0001f1f0\U0001f1f7-\U0001f1fb\U0001f1fe])|(?:\U0001f1f2[\U0001f1e6\U0001f1e8-\U0001f1ed\U0001f1f0-\U0001f1ff])|(?:\U0001f1f3[\U0001f1e6\U0001f1e8\U0001f1ea-\U0001f1ec\U0001f1ee\U0001f1f1\U0001f1f4\U0001f1f5\U0001f1f7\U0001f1fa\U0001f1ff])|\U0001f1f4\U0001f1f2|(?:\U0001f1f4[\U0001f1f2])|(?:\U0001f1f5[\U0001f1e6\U0001f1ea-\U0001f1ed\U0001f1f0-\U0001f1f3\U0001f1f7-\U0001f1f9\U0001f1fc\U0001f1fe])|\U0001f1f6\U0001f1e6|(?:\U0001f1f6[\U0001f1e6])|(?:\U0001f1f7[\U0001f1ea\U0001f1f4\U0001f1f8\U0001f1fa\U0001f1fc])|(?:\U0001f1f8[\U0001f1e6-\U0001f1ea\U0001f1ec-\U0001f1f4\U0001f1f7-\U0001f1f9\U0001f1fb\U0001f1fd-\U0001f1ff])|(?:\U0001f1f9[\U0001f1e6\U0001f1e8\U0001f1e9\U0001f1eb-\U0001f1ed\U0001f1ef-\U0001f1f4\U0001f1f7\U0001f1f9\U0001f1fb\U0001f1fc\U0001f1ff])|(?:\U0001f1fa[\U0001f1e6\U0001f1ec\U0001f1f2\U0001f1f8\U0001f1fe\U0001f1ff])|(?:\U0001f1fb[\U0001f1e6\U0001f1e8\U0001f1ea\U0001f1ec\U0001f1ee\U0001f1f3\U0001f1fa])|(?:\U0001f1fc[\U0001f1eb\U0001f1f8])|\U0001f1fd\U0001f1f0|(?:\U0001f1fd[\U0001f1f0])|(?:\U0001f1fe[\U0001f1ea\U0001f1f9])|(?:\U0001f1ff[\U0001f1e6\U0001f1f2\U0001f1fc])|(?:\U0001f3f3\ufe0f\u200d\U0001f308)|(?:\U0001f441\u200d\U0001f5e8)|(?:[\U0001f468\U0001f469]\u200d\u2764\ufe0f\u200d(?:\U0001f48b\u200d)?[\U0001f468\U0001f469])|(?:(?:(?:\U0001f468\u200d[\U0001f468\U0001f469])|(?:\U0001f469\u200d\U0001f469))(?:(?:\u200d\U0001f467(?:\u200d[\U0001f467\U0001f466])?)|(?:\u200d\U0001f466\u200d\U0001f466)))|(?:(?:(?:\U0001f468\u200d\U0001f468)|(?:\U0001f469\u200d\U0001f469))\u200d\U0001f466)|(?:\U00002714\ufe0f)|(?:\U000026a0\ufe0f)|[\u2194-\u2199]|[\u23e9-\u23f3]|[\u23f8-\u23fa]|[\u25fb-\u25fe]|[\u2600-\u2604]|[\u2638-\u263a]|[\u2648-\u2653]|[\u2692-\u2694]|[\u26f0-\u26f5]|[\u26f7-\u26fa]|[\u2708-\u270d]|[\u2753-\u2755]|[\u2795-\u2797]|[\u2b05-\u2b07]|[\U0001f191-\U0001f19a]|[\U0001f1e6-\U0001f1ff]|[\U0001f232-\U0001f23a]|[\U0001f300-\U0001f321]|[\U0001f324-\U0001f393]|[\U0001f399-\U0001f39b]|[\U0001f39e-\U0001f3f0]|[\U0001f3f3-\U0001f3f5]|[\U0001f3f7-\U0001f3fa]|[\U0001f400-\U0001f4fd]|[\U0001f4ff-\U0001f53d]|[\U0001f549-\U0001f54e]|[\U0001f550-\U0001f567]|[\U0001f573-\U0001f57a]|[\U0001f58a-\U0001f58d]|[\U0001f5c2-\U0001f5c4]|[\U0001f5d1-\U0001f5d3]|[\U0001f5dc-\U0001f5de]|[\U0001f5fa-\U0001f64f]|[\U0001f680-\U0001f6c5]|[\U0001f6cb-\U0001f6d2]|[\U0001f6e0-\U0001f6e5]|[\U0001f6f3-\U0001f6f6]|[\U0001f910-\U0001f91e]|[\U0001f920-\U0001f927]|[\U0001f933-\U0001f93a]|[\U0001f93c-\U0001f93e]|[\U0001f940-\U0001f945]|[\U0001f947-\U0001f94b]|[\U0001f950-\U0001f95e]|[\U0001f980-\U0001f991]|\u00a9|\u00ae|\u203c|\u2049|\u2122|\u2139|\u21a9|\u21aa|\u231a|\u231b|\u2328|\u23cf|\u24c2|\u25aa|\u25ab|\u25b6|\u25c0|\u260e|\u2611|\u2614|\u2615|\u2618|\u261d|\u2620|\u2622|\u2623|\u2626|\u262a|\u262e|\u262f|\u2660|\u2663|\u2665|\u2666|\u2668|\u267b|\u267f|\u2696|\u2697|\u2699|\u269b|\u269c|\u26a1|\u26aa|\u26ab|\u26b0|\u26b1|\u26bd|\u26be|\u26c4|\u26c5|\u26c8|\u26ce|\u26cf|\u26d1|\u26d3|\u26d4|\u26e9|\u26ea|\u26fd|\u2702|\u2705|\u270f|\u2712|\u2716|\u271d|\u2721|\u2728|\u2733|\u2734|\u2744|\u2747|\u274c|\u274e|\u2757|\u2763|\u2764|\u27a1|\u27b0|\u27bf|\u2934|\u2935|\u2b1b|\u2b1c|\u2b50|\u2b55|\u3030|\u303d|\u3297|\u3299|\U0001f004|\U0001f0cf|\U0001f170|\U0001f171|\U0001f17e|\U0001f17f|\U0001f18e|\U0001f201|\U0001f202|\U0001f21a|\U0001f22f|\U0001f250|\U0001f251|\U0001f396|\U0001f397|\U0001f56f|\U0001f570|\U0001f587|\U0001f590|\U0001f595|\U0001f596|\U0001f5a4|\U0001f5a5|\U0001f5a8|\U0001f5b1|\U0001f5b2|\U0001f5bc|\U0001f5e1|\U0001f5e3|\U0001f5e8|\U0001f5ef|\U0001f5f3|\U0001f6e9|\U0001f6eb|\U0001f6ec|\U0001f6f0|\U0001f930|\U0001f9c0|\U0001f97a|[#|0-9]\u20e3'
UNICODE_EMOJI_REGEX = re.compile(UNICODE_EMOJI)
# Modified version of https://gist.github.com/Vexs/a8fd95377ca862ca13fe6d0f0e42737e


__all__ = ('get_perm_level', 'format_timedelta')


def get_perm_level(member: discord.Member, guild_config: 'DBDict') -> Tuple[int, Union[str, discord.Role, None]]:
    # User is not in server
    if not getattr(member, 'guild_permissions', None):
        return (0, None)

    highest_role: Union[str, discord.Role, None] = None

    if member.guild_permissions.administrator:
        perm_level = 15
        highest_role = 'Administrator'
    elif member.guild_permissions.manage_guild:
        perm_level = 10
        highest_role = 'Manage Server'
    else:
        perm_level = 0
        highest_role = None

        perm_levels = [int(i.role_id) for i in guild_config.perm_levels]
        for i in reversed(member.roles):
            if i.id in perm_levels:
                new_perm_level = guild_config.perm_levels.get_kv('role_id', str(i.id)).level
                if new_perm_level > perm_level:
                    perm_level = new_perm_level
                    highest_role = i

    return (perm_level, highest_role)


def get_command_level(cmd: Union['RainCommand', 'RainGroup'], guild_config: 'DBDict') -> int:
    name = cmd.qualified_name.replace(' ', '_')

    try:
        perm_level = guild_config.command_levels.get_kv('command', name).level
    except IndexError:
        perm_level = cmd.perm_level

    return perm_level


def lower(argument: str) -> str:
    return str(argument).lower()


def owner() -> Callable:
    def predicate(ctx: commands.Context) -> bool:
        return ctx.author.id in ctx.bot.owners
    return check(predicate)


def random_color() -> int:
    return random.randint(0, 0xfffff)


def format_timedelta(delta: datetime.timedelta, *, assume_forever: bool=True) -> str:
    if not delta:
        if assume_forever:
            return 'forever'
        else:
            return '0 seconds'

    minutes, seconds = divmod(int(delta.total_seconds()), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    months, days = divmod(days, 30)
    years, months = divmod(months, 12)

    fmt = ''
    if seconds:
        fmt = f'{seconds} seconds ' + fmt
    if minutes:
        fmt = f'{minutes} minutes ' + fmt
    if hours:
        fmt = f'{hours} hours ' + fmt
    if days:
        fmt = f'{days} days ' + fmt
    if months:
        fmt = f'{months} months ' + fmt
    if years:
        fmt = f'{years} years ' + fmt

    return fmt.strip()


def tryint(x: str) -> Union[str, int]:
    try:
        return int(x)
    except ValueError:
        return x


class EmojiOrUnicode(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> Union[discord.Emoji, UnicodeEmoji]:
        try:
            return await commands.EmojiConverter().convert(ctx, argument)
        except commands.BadArgument:
            if isinstance(argument, str):
                if UNICODE_EMOJI_REGEX.match(argument):
                    return UnicodeEmoji(argument)
                else:
                    raise commands.BadArgument('Invalid emoji provided')


class UnicodeEmoji:
    def __init__(self, id: str) -> None:
        self.id = id


class SafeFormat(dict):
    def __init__(self, **kw: Any) -> None:
        self.__dict = kw

    def __getitem__(self, name: str) -> Any:
        return self.__dict.get(name, SafeString('{%s}' % name))


class SafeString(str):
    def __getattr__(self, name: str) -> Optional[str]:
        try:
            return getattr(self, name)
        except AttributeError:
            return SafeString('%s.%s}' % (self[:-1], name))


def apply_vars(bot: 'rainbot', tag: str, message: discord.Message) -> str:
    return tag.format(**SafeFormat(
        invoked=message,
        guild=message.guild,
        channel=message.channel,
        bot=bot.user,
    ))


class Detection:
    def __init__(self, func: Callable, **attrs: Union[bool, str]):
        self.callback = func
        self.name = attrs.pop('name')
        self.check_enabled = attrs.pop('check_enabled', True)
        self.require_user = attrs.pop('require_user', None)
        self.allow_bot = attrs.pop('allow_bot', False)
        self.require_prod = attrs.pop('require_prod', True)
        self.require_guild = attrs.pop('require_guild', True)
        self.require_attachment = attrs.pop('require_attachment', False)

        self.__cog_detection__ = True

    async def check_constraints(self, bot: rainbot, message: discord.Message) -> bool:
        if self.require_guild and not message.guild:
            return False

        if message.guild:
            guild_config = await bot.db.get_guild_config(message.guild.id)

            if self.check_enabled and not guild_config.detections[self.name]:
                return False

            if str(message.channel.id) in guild_config.ignored_channels[self.name]:
                return False

            if not bot.dev_mode and str(message.channel.id) in guild_config.ignored_channels_in_prod:
                return False

            if get_perm_level(message.author, guild_config)[0] >= 5:
                return False

        if self.require_user and message.author.id != self.require_user:
            return False

        if not self.allow_bot and message.author.bot:
            return False

        if self.require_prod and bot.dev_mode:
            return False

        if self.require_attachment and not message.attachments:
            return False

        return True

    async def trigger(self, cog: commands.Cog, message: discord.Message) -> Any:
        if await self.check_constraints(cog.bot, message):
            return await self.callback(cog, message)


def detection(name: str, **attrs: bool) -> Callable:
    def decorator(func: Callable) -> Detection:
        return Detection(func, name=name, **attrs)
    return decorator
