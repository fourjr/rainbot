import asyncio
import re
from collections import defaultdict, Counter
from datetime import timedelta

import discord
from discord.ext import commands
from discord.ext.commands import Cog

from ext.context import RainContext
from ext.utils import get_perm_level


class Detections(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam_detection = defaultdict(list)
        self.repetitive_message = defaultdict(Counter)
        self.INVITE_REGEX = re.compile(r'((http(s|):\/\/|)(discord)(\.(gg|io|me)\/|app\.com\/invite\/)([0-z]+))')

    @Cog.listener()
    async def on_message(self, m):
        if not m.guild or m.type != discord.MessageType.default or m.author.bot or self.bot.dev_mode:
            return

        guild_config = await self.bot.mongo.rainbot.guilds.find_one({'guild_id': str(m.guild.id)}) or {}
        if get_perm_level(m.author, guild_config)[0] >= 5:
            return

        detection_config = guild_config.get('detections', {})
        filtered_words = [i for i in detection_config.get('filters', []) if i in m.content.lower()]
        invite_match = self.INVITE_REGEX.findall(m.content)

        mentions = []
        for i in m.mentions:
            if i not in mentions and i != m.author and not i.bot:
                mentions.append(i)

        warn_cmd = self.bot.get_command('warn add')
        ctx = await self.bot.get_context(m, cls=RainContext)
        ctx.author = m.guild.me
        ctx.command = warn_cmd

        if detection_config.get('mention_limit') and len(mentions) >= detection_config.get('mention_limit'):
            await m.delete()
            await ctx.invoke(warn_cmd, m.author, reason=f'Mass mentions ({len(m.mentions)})')
            await self.bot.mute(m.author, timedelta(minutes=10), reason=f'Mass mentions ({len(m.mentions)})')

        elif len(filtered_words) != 0:
            await m.delete()

        elif detection_config.get('block_invite') and invite_match:
            for i in invite_match:
                try:
                    invite = await self.bot.fetch_invite(i[-1])
                except discord.NotFound:
                    pass
                else:
                    if not (invite.guild.id == m.guild.id or str(invite.guild.id) in guild_config.get('whitelisted_guilds', [])):
                        await m.delete()
                        await ctx.invoke(warn_cmd, m.author, reason=f'Advertising discord server (<{invite.url}>)')
                        await self.bot.mute(m.author, timedelta(minutes=10), reason=f'Advertising discord server (<{invite.url}>)')

        elif detection_config.get('spam_detection') and len(self.spam_detection.get(str(m.author.id), [])) >= detection_config.get('spam_detection'):
            await ctx.invoke(warn_cmd, m.author, reason=f'Exceeding spam detection ({detection_config.get("spam_detection")} messages/5s)')
            await self.bot.mute(m.author, timedelta(minutes=10), reason=f'Exceeding spam detection ({detection_config.get("spam_detection")} messages/5s)')

            await m.delete()
            for i in self.spam_detection[str(m.author.id)]:
                try:
                    msg = await m.channel.fetch_message(i)
                    await msg.delete()
                except discord.NotFound:
                    pass

        elif detection_config.get('repetitive_message') and self.get_most_common_count(m.author.id) >= detection_config.get("repetitive_message"):
            await ctx.invoke(warn_cmd, m.author, reason=f'Repetitive message detection ({detection_config.get("repetitive_message")} identical messages/1m)')
            await ctx.invoke(self.bot.get_command('purge'), limit=self.get_most_common_count(m.author.id), member=m.author)
            await self.bot.mute(m.author, timedelta(minutes=10), reason=f'Repetitive message detection ({detection_config.get("repetitive_message")} identical messages/1m)')

        self.spam_detection[str(m.author.id)].append(m.id)
        await asyncio.sleep(5)
        self.spam_detection[str(m.author.id)].remove(m.id)

        if not self.spam_detection[str(m.author.id)]:
            del self.spam_detection[str(m.author.id)]

        self.repetitive_message[str(m.author.id)][m.content] += 1
        await asyncio.sleep(60)
        self.repetitive_message[str(m.author.id)][m.content] -= 1

        if not self.repetitive_message[str(m.author.id)].values():
            del self.repetitive_message[str(m.author.id)]

    def get_most_common_count(self, id):
        most_common = self.repetitive_message.get(str(id), Counter()).most_common(1)
        if most_common:
            if most_common[0]:
                return most_common[0][1]
        return 0


def setup(bot):
    bot.add_cog(Detections(bot))
