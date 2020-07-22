import asyncio
import re
from collections import defaultdict, Counter
from datetime import timedelta

import discord
from discord.ext import commands
from discord.ext.commands import Cog

from ext.utils import get_perm_level


class Detections(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam_detection = defaultdict(list)
        self.repetitive_message = defaultdict(Counter)
        self.INVITE_REGEX = re.compile(r'((http(s|):\/\/|)(discord)(\.(gg|io|me)\/|app\.com\/invite\/)([0-z]+))')
        self.ENGLISH_REGEX = re.compile(r'[ -~]|(?:(?:\U0001f1e6[\U0001f1e8-\U0001f1ec\U0001f1ee\U0001f1f1\U0001f1f2\U0001f1f4\U0001f1f6-\U0001f1fa\U0001f1fc\U0001f1fd\U0001f1ff])|(?:\U0001f1e7[\U0001f1e6\U0001f1e7\U0001f1e9-\U0001f1ef\U0001f1f1-\U0001f1f4\U0001f1f6-\U0001f1f9\U0001f1fb\U0001f1fc\U0001f1fe\U0001f1ff])|(?:\U0001f1e8[\U0001f1e6\U0001f1e8\U0001f1e9\U0001f1eb-\U0001f1ee\U0001f1f0-\U0001f1f5\U0001f1f7\U0001f1fa-\U0001f1ff])|(?:\U0001f1e9[\U0001f1ea\U0001f1ec\U0001f1ef\U0001f1f0\U0001f1f2\U0001f1f4\U0001f1ff])|(?:\U0001f1ea[\U0001f1e6\U0001f1e8\U0001f1ea\U0001f1ec\U0001f1ed\U0001f1f7-\U0001f1fa])|(?:\U0001f1eb[\U0001f1ee-\U0001f1f0\U0001f1f2\U0001f1f4\U0001f1f7])|(?:\U0001f1ec[\U0001f1e6\U0001f1e7\U0001f1e9-\U0001f1ee\U0001f1f1-\U0001f1f3\U0001f1f5-\U0001f1fa\U0001f1fc\U0001f1fe])|(?:\U0001f1ed[\U0001f1f0\U0001f1f2\U0001f1f3\U0001f1f7\U0001f1f9\U0001f1fa])|(?:\U0001f1ee[\U0001f1e8-\U0001f1ea\U0001f1f1-\U0001f1f4\U0001f1f6-\U0001f1f9])|(?:\U0001f1ef[\U0001f1ea\U0001f1f2\U0001f1f4\U0001f1f5])|(?:\U0001f1f0[\U0001f1ea\U0001f1ec-\U0001f1ee\U0001f1f2\U0001f1f3\U0001f1f5\U0001f1f7\U0001f1fc\U0001f1fe\U0001f1ff])|(?:\U0001f1f1[\U0001f1e6-\U0001f1e8\U0001f1ee\U0001f1f0\U0001f1f7-\U0001f1fb\U0001f1fe])|(?:\U0001f1f2[\U0001f1e6\U0001f1e8-\U0001f1ed\U0001f1f0-\U0001f1ff])|(?:\U0001f1f3[\U0001f1e6\U0001f1e8\U0001f1ea-\U0001f1ec\U0001f1ee\U0001f1f1\U0001f1f4\U0001f1f5\U0001f1f7\U0001f1fa\U0001f1ff])|\U0001f1f4\U0001f1f2|(?:\U0001f1f4[\U0001f1f2])|(?:\U0001f1f5[\U0001f1e6\U0001f1ea-\U0001f1ed\U0001f1f0-\U0001f1f3\U0001f1f7-\U0001f1f9\U0001f1fc\U0001f1fe])|\U0001f1f6\U0001f1e6|(?:\U0001f1f6[\U0001f1e6])|(?:\U0001f1f7[\U0001f1ea\U0001f1f4\U0001f1f8\U0001f1fa\U0001f1fc])|(?:\U0001f1f8[\U0001f1e6-\U0001f1ea\U0001f1ec-\U0001f1f4\U0001f1f7-\U0001f1f9\U0001f1fb\U0001f1fd-\U0001f1ff])|(?:\U0001f1f9[\U0001f1e6\U0001f1e8\U0001f1e9\U0001f1eb-\U0001f1ed\U0001f1ef-\U0001f1f4\U0001f1f7\U0001f1f9\U0001f1fb\U0001f1fc\U0001f1ff])|(?:\U0001f1fa[\U0001f1e6\U0001f1ec\U0001f1f2\U0001f1f8\U0001f1fe\U0001f1ff])|(?:\U0001f1fb[\U0001f1e6\U0001f1e8\U0001f1ea\U0001f1ec\U0001f1ee\U0001f1f3\U0001f1fa])|(?:\U0001f1fc[\U0001f1eb\U0001f1f8])|\U0001f1fd\U0001f1f0|(?:\U0001f1fd[\U0001f1f0])|(?:\U0001f1fe[\U0001f1ea\U0001f1f9])|(?:\U0001f1ff[\U0001f1e6\U0001f1f2\U0001f1fc])|(?:\U0001f3f3\ufe0f\u200d\U0001f308)|(?:\U0001f441\u200d\U0001f5e8)|(?:[\U0001f468\U0001f469]\u200d\u2764\ufe0f\u200d(?:\U0001f48b\u200d)?[\U0001f468\U0001f469])|(?:(?:(?:\U0001f468\u200d[\U0001f468\U0001f469])|(?:\U0001f469\u200d\U0001f469))(?:(?:\u200d\U0001f467(?:\u200d[\U0001f467\U0001f466])?)|(?:\u200d\U0001f466\u200d\U0001f466)))|(?:(?:(?:\U0001f468\u200d\U0001f468)|(?:\U0001f469\u200d\U0001f469))\u200d\U0001f466)|(?:\U00002714\ufe0f)|(?:\U000026a0\ufe0f)|[\u2194-\u2199]|[\u23e9-\u23f3]|[\u23f8-\u23fa]|[\u25fb-\u25fe]|[\u2600-\u2604]|[\u2638-\u263a]|[\u2648-\u2653]|[\u2692-\u2694]|[\u26f0-\u26f5]|[\u26f7-\u26fa]|[\u2708-\u270d]|[\u2753-\u2755]|[\u2795-\u2797]|[\u2b05-\u2b07]|[\U0001f191-\U0001f19a]|[\U0001f1e6-\U0001f1ff]|[\U0001f232-\U0001f23a]|[\U0001f300-\U0001f321]|[\U0001f324-\U0001f393]|[\U0001f399-\U0001f39b]|[\U0001f39e-\U0001f3f0]|[\U0001f3f3-\U0001f3f5]|[\U0001f3f7-\U0001f3fa]|[\U0001f400-\U0001f4fd]|[\U0001f4ff-\U0001f53d]|[\U0001f549-\U0001f54e]|[\U0001f550-\U0001f567]|[\U0001f573-\U0001f57a]|[\U0001f58a-\U0001f58d]|[\U0001f5c2-\U0001f5c4]|[\U0001f5d1-\U0001f5d3]|[\U0001f5dc-\U0001f5de]|[\U0001f5fa-\U0001f64f]|[\U0001f680-\U0001f6c5]|[\U0001f6cb-\U0001f6d2]|[\U0001f6e0-\U0001f6e5]|[\U0001f6f3-\U0001f6f6]|[\U0001f910-\U0001f91e]|[\U0001f920-\U0001f927]|[\U0001f933-\U0001f93a]|[\U0001f93c-\U0001f93e]|[\U0001f940-\U0001f945]|[\U0001f947-\U0001f94b]|[\U0001f950-\U0001f95e]|[\U0001f980-\U0001f991]|\u00a9|\u00ae|\u203c|\u2049|\u2122|\u2139|\u21a9|\u21aa|\u231a|\u231b|\u2328|\u23cf|\u24c2|\u25aa|\u25ab|\u25b6|\u25c0|\u260e|\u2611|\u2614|\u2615|\u2618|\u261d|\u2620|\u2622|\u2623|\u2626|\u262a|\u262e|\u262f|\u2660|\u2663|\u2665|\u2666|\u2668|\u267b|\u267f|\u2696|\u2697|\u2699|\u269b|\u269c|\u26a1|\u26aa|\u26ab|\u26b0|\u26b1|\u26bd|\u26be|\u26c4|\u26c5|\u26c8|\u26ce|\u26cf|\u26d1|\u26d3|\u26d4|\u26e9|\u26ea|\u26fd|\u2702|\u2705|\u270f|\u2712|\u2716|\u271d|\u2721|\u2728|\u2733|\u2734|\u2744|\u2747|\u274c|\u274e|\u2757|\u2763|\u2764|\u27a1|\u27b0|\u27bf|\u2934|\u2935|\u2b1b|\u2b1c|\u2b50|\u2b55|\u3030|\u303d|\u3297|\u3299|\U0001f004|\U0001f0cf|\U0001f170|\U0001f171|\U0001f17e|\U0001f17f|\U0001f18e|\U0001f201|\U0001f202|\U0001f21a|\U0001f22f|\U0001f250|\U0001f251|\U0001f396|\U0001f397|\U0001f56f|\U0001f570|\U0001f587|\U0001f590|\U0001f595|\U0001f596|\U0001f5a4|\U0001f5a5|\U0001f5a8|\U0001f5b1|\U0001f5b2|\U0001f5bc|\U0001f5e1|\U0001f5e3|\U0001f5e8|\U0001f5ef|\U0001f5f3|\U0001f6e9|\U0001f6eb|\U0001f6ec|\U0001f6f0|\U0001f930|\U0001f9c0|[#|0-9]\u20e3)')
    @Cog.listener()
    async def on_message(self, m):
        if not m.guild or m.type != discord.MessageType.default or m.author.bot or self.bot.dev_mode:
            return

        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        if get_perm_level(m.author, guild_config)[0] >= 5:
            return

        detection_config = guild_config.detections
        ignored_channels = guild_config.ignored_channels
        filtered_words = [i for i in detection_config.filters if i in m.content.lower()]
        invite_match = self.INVITE_REGEX.findall(m.content)
        english_text = ''.join(self.ENGLISH_REGEX.findall(m.content))

        mentions = []
        for i in m.mentions:
            if i not in mentions and i != m.author and not i.bot:
                mentions.append(i)

        warn_cmd = self.bot.get_command('warn add')
        ctx = await self.bot.get_context(m)
        ctx.author = m.guild.me
        ctx.command = warn_cmd

        if detection_config.mention_limit and len(mentions) >= detection_config.mention_limit and str(m.channel.id) not in ignored_channels.mention_limit:
            await m.delete()
            await ctx.invoke(warn_cmd, m.author, reason=f'Mass mentions ({len(m.mentions)})')
            await self.bot.mute(m.author, timedelta(minutes=10), reason=f'Mass mentions ({len(m.mentions)})')

        elif len(filtered_words) != 0 and str(m.channel.id) not in ignored_channels.filter:
            await m.delete()

        elif detection_config.block_invite and invite_match and str(m.channel.id) not in ignored_channels.block_invite:
            for i in invite_match:
                try:
                    invite = await self.bot.fetch_invite(i[-1])
                except discord.NotFound:
                    pass
                else:
                    if not (invite.guild.id == m.guild.id or str(invite.guild.id) in guild_config.whitelisted_guilds):
                        await m.delete()
                        await ctx.invoke(warn_cmd, m.author, reason=f'Advertising discord server (<{invite.url}>)')
                        await self.bot.mute(m.author, timedelta(minutes=10), reason=f'Advertising discord server (<{invite.url}>)')

        elif detection_config.english_only and english_text != m.content and str(m.channel.id) not in ignored_channels.english_only:
            await m.delete()

        elif detection_config.spam_detection and len(self.spam_detection.get(str(m.author.id), [])) >= detection_config.spam_detection and str(m.channel.id) not in ignored_channels.spam_detection:
            await ctx.invoke(warn_cmd, m.author, reason=f'Exceeding spam detection ({detection_config.spam_detection} messages/5s)')
            await self.bot.mute(m.author, timedelta(minutes=10), reason=f'Exceeding spam detection ({detection_config.spam_detection} messages/5s)')

            await m.delete()
            for i in self.spam_detection[str(m.author.id)]:
                try:
                    msg = await m.channel.fetch_message(i)
                    await msg.delete()
                except discord.NotFound:
                    pass

        elif detection_config.repetitive_message and self.get_most_common_count(m.author.id) >= detection_config.repetitive_message and str(m.channel.id) not in ignored_channels.repetitive_message:
            await ctx.invoke(warn_cmd, m.author, reason=f'Repetitive message detection ({detection_config.repetitive_message} identical messages/1m)')
            await ctx.invoke(self.bot.get_command('purge'), limit=self.get_most_common_count(m.author.id), member=m.author)
            await self.bot.mute(m.author, timedelta(minutes=10), reason=f'Repetitive message detection ({detection_config.repetitive_message} identical messages/1m)')

        if str(m.channel.id) not in ignored_channels.spam_detection:
            self.spam_detection[str(m.author.id)].append(m.id)
            await asyncio.sleep(5)
            self.spam_detection[str(m.author.id)].remove(m.id)

            if not self.spam_detection[str(m.author.id)]:
                del self.spam_detection[str(m.author.id)]

        if str(m.channel.id) not in ignored_channels.repetitive_message:
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
