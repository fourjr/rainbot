import asyncio
import functools
import re
import os
from cachetools import LFUCache
from collections import defaultdict, Counter
from datetime import timedelta
from tempfile import NamedTemporaryFile

import discord
import tensorflow as tf
from discord.ext import commands
from discord.ext.commands import Cog
from imagehash import average_hash
from nudenet import NudeDetector
from PIL import Image

from ext.utils import UNICODE_EMOJI, get_perm_level
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)


class Detections(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam_detection = defaultdict(list)
        self.repetitive_message = defaultdict(Counter)
        self.INVITE_REGEX = re.compile(r'((http(s|):\/\/|)(discord)(\.(gg|io|me)\/|app\.com\/invite\/)([0-z]+))')
        self.ENGLISH_REGEX = re.compile(r'[ -~]|(?:' + UNICODE_EMOJI + r')|(?:\U00002018|\U00002019|\s)|[.!?\\\-\(\)]|ツ|(?:\(╯°□°\）╯︵ ┻━┻)|(?:┬─┬ ノ\( ゜-゜ノ\))')  # U2018 and U2019 are iOS quotes

        self.nude_detector = NudeDetector()
        self.nude_graph = tf.get_default_graph()

        self.nude_image_cache = LFUCache(50)

    @Cog.listener()
    async def on_message(self, m):
        if not m.guild or m.type != discord.MessageType.default or self.bot.dev_mode:
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

        # bots
        if detection_config.auto_purge_trickocord and m.author.id == 755580145078632508 and m.embeds and m.embeds[0].title == 'A trick-or-treater has stopped by!':
            await asyncio.sleep(90)
            await m.delete()

        if m.author.bot:
            return

        # images
        if guild_config.detections.sexually_explicit:
            for i in m.attachments:
                if i.filename.endswith('.png') or i.filename.endswith('.jpg') or i.filename.endswith('.jpeg'):
                    with NamedTemporaryFile(mode='wb+', delete=False) as fp:
                        async with self.bot.session.get(i.url) as resp:
                            fp.write(await resp.read())
                    await self.bot.loop.run_in_executor(None, functools.partial(self.get_nudenet_classifications, m, fp.name))

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

    def get_nudenet_classifications(self, m, path):
        img = Image.open(path)
        image_hash = str(average_hash(img))
        img.close()

        try:
            labels = self.nude_image_cache[image_hash]
        except KeyError:
            with self.nude_graph.as_default():
                result = self.nude_detector.detect(path)
            labels = []

            for i in result:
                labels.append(i['label'])

        os.remove(path)
        if labels:
            self.nude_image_cache[image_hash] = labels
            self.bot.loop.create_task(self.nudenet_callback(m, labels))

    async def nudenet_callback(self, m, labels):
        guild_config = await self.bot.db.get_guild_config(m.guild.id)

        for i in guild_config.detections.sexually_explicit:
            if i in labels:
                await m.delete()
                await self.bot.mute(m.author, timedelta(minutes=10), reason=f'Explicit image detection {tuple(labels)}')

                break


def setup(bot):
    bot.add_cog(Detections(bot))
