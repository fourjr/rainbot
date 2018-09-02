import asyncio
from collections import defaultdict

import discord

from ext.utils import get_perm_level


class Detections:
    def __init__(self, bot):
        self.bot = bot
        self.messages = defaultdict(int)

    async def on_message(self, m):
        if not m.guild or m.type != discord.MessageType.default or m.author.bot:
            return

        guild_config = await self.bot.mongo.config.guilds.find_one({'guild_id': str(m.guild.id)}) or {}
        if get_perm_level(m.author, guild_config)[0] >= 5:
            return

        guild_config = guild_config.get('detections', {})
        filtered_words = {i: i in m.content.lower() for i in guild_config.get('filters', [])}
        invite_links = ['discord.gg/', 'discordapp.com/invite/', 'discord.io/']
        links = {i: i in m.content for i in invite_links}

        mentions = []
        for i in m.mentions:
            if i not in mentions and i != m.author:  # and not i.bot:
                mentions.append(i)

        if guild_config.get('mention_limit') and len(mentions) >= guild_config.get('mention_limit'):
            await m.delete()
            await self.bot.mute(m.author, 60 * 10, reason=f'Mass mentions ({len(m.mentions)})')

        elif any(filtered_words.values()):
            await m.delete()
            await self.bot.mute(m.author, 60 * 10, reason=f'Use of filtered words ({", ".join(i for i in filtered_words.keys() if filtered_words[i])})')

        elif guild_config.get('block_invite') and any(links.values()):
            await m.delete()
            await self.bot.mute(m.author, 60 * 10, reason=f'Advertising discord server ({len([i for i in links.keys() if links[i]])})')

        elif guild_config.get('spam_detection') and self.messages.get(str(m.author.id), 0) >= guild_config.get('spam_detection'):
            await m.delete()
            await self.bot.mute(m.author, 60 * 10, reason=f'Exceeding spam detection ({guild_config.get("spam_detection")} messages/5s)')

        self.messages[str(m.author.id)] += 1
        await asyncio.sleep(5)
        self.messages[str(m.author.id)] -= 1


def setup(bot):
    bot.add_cog(Detections(bot))
