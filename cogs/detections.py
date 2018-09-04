import asyncio
import re
from collections import defaultdict

import discord

from ext.utils import get_perm_level


class Detections:
    def __init__(self, bot):
        self.bot = bot
        self.messages = defaultdict(list)

    async def on_message(self, m):
        if not m.guild or m.type != discord.MessageType.default or m.author.bot:  # or self.bot.dev_mode:
            return

        guild_config = await self.bot.mongo.config.guilds.find_one({'guild_id': str(m.guild.id)}) or {}
        if get_perm_level(m.author, guild_config)[0] >= 5:
            return

        detection_config = guild_config.get('detections', {})
        filtered_words = {i: i in m.content.lower() for i in detection_config.get('filters', [])}
        invite_regex = r'((http(s|):\/\/|)(discord)(\.(gg|io|me)\/|app\.com\/invite\/)([0-z]+))'
        invite_match = re.findall(invite_regex, m.content)

        mentions = []
        for i in m.mentions:
            if i not in mentions and i != m.author:  # and not i.bot:
                mentions.append(i)

        if detection_config.get('mention_limit') and len(mentions) >= detection_config.get('mention_limit'):
            await m.delete()
            await self.bot.mute(m.author, 60 * 10, reason=f'Mass mentions ({len(m.mentions)})')

        elif any(filtered_words.values()):
            await m.delete()

        elif detection_config.get('block_invite') and invite_match is not None:
            for i in invite_match:
                try:
                    invite = await self.bot.get_invite(i[-1])
                except discord.NotFound:
                    pass
                else:
                    if not (invite.guild.id == m.guild.id or str(invite.guild.id) in guild_config.get('whitelisted_guilds', [])):
                        await m.delete()
                        await self.bot.mute(m.author, 60 * 10, reason=f'Advertising discord server (<{invite.url}>)')

        elif detection_config.get('spam_detection') and len(self.messages.get(str(m.author.id), [])) >= detection_config.get('spam_detection'):
            await m.delete()
            for i in self.messages[str(m.author.id)]:
                try:
                    msg = await m.channel.get_message(i)
                    await msg.delete()
                except discord.NotFound:
                    pass
            await self.bot.mute(m.author, 60 * 10, reason=f'Exceeding spam detection ({detection_config.get("spam_detection")} messages/5s)')

        self.messages[str(m.author.id)].append(m.id)
        await asyncio.sleep(5)
        self.messages[str(m.author.id)].remove(m.id)


def setup(bot):
    bot.add_cog(Detections(bot))
