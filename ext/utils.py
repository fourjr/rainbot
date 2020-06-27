import random
from discord.ext.commands import check


def get_perm_level(member, guild_info):
    # User is not in server
    if not getattr(member, 'guild_permissions', None):
        return (0, None)

    if member.guild_permissions.administrator:
        perm_level = 15
        highest_role = 'Administrator'
    else:
        perm_level = 0
        highest_role = None

        for i in reversed(member.roles):
            if str(i.id) in guild_info.get('perm_levels', {}).keys():
                if guild_info['perm_levels'][str(i.id)] > perm_level:
                    perm_level = guild_info['perm_levels'][str(i.id)]
                    highest_role = i

    return (perm_level, highest_role)


def lower(argument):
    return str(argument).lower()


def owner():
    def predicate(ctx):
        return ctx.author.id in [180314310298304512, 281821029490229251, 369848495546433537]
    return check(predicate)


def random_color():
    return random.randint(0, 0xfffff)


def format_timedelta(delta):
    if not delta:
        return 'forever'

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


async def in_bot_channel(ctx):
    guild_info = await ctx.bot.mongo.rainbot.guilds.find_one({'guild_id': str(ctx.guild.id)}) or {}
    bot_channel = guild_info.get('in_bot_channel', [])

    if bot_channel:
        return str(ctx.channel.id) in bot_channel
    return True
