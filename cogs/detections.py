import asyncio
import functools
import os
import re
from collections import Counter, defaultdict
from datetime import timedelta
from tempfile import NamedTemporaryFile
from typing import DefaultDict, List

import discord
import tensorflow as tf
from cachetools import LFUCache
from discord.ext import commands
from discord.ext.commands import Cog
from imagehash import average_hash
from nudenet import NudeDetector
from PIL import Image

from bot import rainbot
from ext.utils import UNICODE_EMOJI, Detection, detection


tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)


class Detections(commands.Cog):
    def __init__(self, bot: rainbot) -> None:
        self.bot = bot
        self.spam_detection: DefaultDict[str, List[int]] = defaultdict(list)
        self.repetitive_message: DefaultDict[str, Counter] = defaultdict(Counter)
        self.INVITE_REGEX = re.compile(r'((http(s|):\/\/|)(discord)(\.(gg|io|me)\/|app\.com\/invite\/)([0-z]+))')
        self.ENGLISH_REGEX = re.compile(r'[ -~]|(?:' + UNICODE_EMOJI + r')|(?:\U00002018|\U00002019|\s)|[.!?\\\-\(\)]|ツ|(?:\(╯°□°\）╯︵ ┻━┻)|(?:┬─┬ ノ\( ゜-゜ノ\))')  # U2018 and U2019 are iOS quotes

        self.nude_detector = NudeDetector()
        self.nude_graph = tf.get_default_graph()

        self.nude_image_cache: LFUCache[str, List[str]] = LFUCache(50)

        self.detections = []

        for func in self.__class__.__dict__.values():
            if isinstance(func, Detection):
                self.detections.append(func)

    @Cog.listener()
    async def on_message(self, m: discord.Message) -> None:
        if (not self.bot.dev_mode or (m.guild and m.guild.id != 733697261065994320)) or m.type != discord.MessageType.default:
            return

        for func in self.detections:
            await func.trigger(self, m)

    @detection('auto_purge_trickocord', require_user=755580145078632508, allow_bot=True)
    async def auto_purge_trickocord(self, m: discord.Message) -> None:
        print(self, m)
        if m.embeds and m.embeds[0].title == 'A trick-or-treater has stopped by!':
            await asyncio.sleep(90)
            await m.delete()

    @detection('sexually_explicit', require_attachment=True)
    async def sexually_explicit(self, m: discord.Message) -> None:
        for i in m.attachments:
            if i.filename.endswith('.png') or i.filename.endswith('.jpg') or i.filename.endswith('.jpeg'):
                with NamedTemporaryFile(mode='wb+', delete=False) as fp:
                    async with self.bot.session.get(i.url) as resp:
                        fp.write(await resp.read())
                await self.bot.loop.run_in_executor(None, functools.partial(self.get_nudenet_classifications, m, fp.name))

    @detection('mention_limit')
    async def mention_limit(self, m: discord.Message) -> None:
        mentions = []
        for i in m.mentions:
            if i not in mentions and i != m.author and not i.bot:
                mentions.append(i)

        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        if len(mentions) >= guild_config.detections.mention_limit:
            await m.delete()
            await self.invoke('warn add', m, member=m.author, reason=f'Mass mentions ({len(m.mentions)})')
            await self.bot.mute(m.author, timedelta(minutes=10), reason=f'Mass mentions ({len(m.mentions)})')

    @detection('max_lines')
    async def max_lines(self, m: discord.Message) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        if len(m.content.splitlines()) > guild_config.detections.max_lines:
            await m.delete()
            return True

    @detection('max_words')
    async def max_words(self, m: discord.Message) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        if len(m.content.split(' ')) > guild_config.detections.max_words:
            await m.delete()
            return True

    @detection('max_characters')
    async def max_characters(self, m: discord.Message) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        if len(m.content) > guild_config.detections.max_characters:
            await m.delete()
            return True

    @detection('filter', check_enabled=False)
    async def filtered_words(self, m: discord.Message) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        words = [i for i in guild_config.detections.filters if i in m.content.lower()]
        if words:
            await m.delete()
            return True

    @detection('regex_filter', check_enabled=False)
    async def regex_filter(self, m: discord.Message) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        matches = [i for i in guild_config.detections.regex_filters if re.match(i, m.content)]
        if matches:
            await m.delete()
            return True

    @detection('block_invite')
    async def block_invite(self, m: discord.Message) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        invite_match = self.INVITE_REGEX.findall(m.content)
        if invite_match:
            for i in invite_match:
                try:
                    invite = await self.bot.fetch_invite(i[-1])
                except discord.NotFound:
                    pass
                else:
                    if not (invite.guild.id == m.guild.id or str(invite.guild.id) in guild_config.whitelisted_guilds):
                        await m.delete()
                        await self.invoke('warn add', m, member=m.author, reason=f'Advertising discord server {invite.guild.name} (<{invite.url}>)')
                        await self.bot.mute(m.author, timedelta(minutes=10), reason=f'Advertising discord server {invite.guild.name} (<{invite.url}>)')

    @detection('english_only')
    async def english_only(self, m: discord.Message) -> None:
        english_text = ''.join(self.ENGLISH_REGEX.findall(m.content))
        if english_text != m.content:
            await m.delete()

    @detection('spam_detection')
    async def spam_detection(self, m: discord.Message) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        limit = guild_config.detections.spam_detection
        if len(self.spam_detection.get(str(m.author.id), [])) >= limit:
            reason = f'Exceeding spam detection ({limit} messages/5s)'
            await self.bot.mute(m.author, timedelta(minutes=10), reason=reason)
            await self.invoke('warn add', m, member=m.author, reason=reason)
            await self.invoke('purge', m, member=m.author, limit=len(self.spam_detection[str(m.author.id)]))

            try:
                del self.spam_detection[str(m.author.id)]
            except KeyError:
                pass
        else:
            self.spam_detection[str(m.author.id)].append(m.id)
            await asyncio.sleep(5)
            try:
                self.spam_detection[str(m.author.id)].remove(m.id)

                if not self.spam_detection[str(m.author.id)]:
                    del self.spam_detection[str(m.author.id)]
            except ValueError:
                pass

    @detection('repetitive_message')
    async def repetitive_message(self, m: discord.Message) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        limit = guild_config.detections.repetitive_message
        if self.get_most_common_count_repmessage(m.author.id) >= limit:
            reason = f'Repetitive message detection ({limit} identical messages/1m)'
            await self.bot.mute(m.author, timedelta(minutes=10), reason=reason)
            await self.invoke('warn add', m, member=m.author, reason=reason)
            await self.invoke('purge', m, member=m.author, limit=self.get_most_common_count_repmessage(m.author.id))

            try:
                del self.repetitive_message[str(m.author.id)]
            except KeyError:
                pass
        else:
            self.repetitive_message[str(m.author.id)][m.content] += 1
            await asyncio.sleep(60)
            try:
                self.repetitive_message[str(m.author.id)][m.content] -= 1

                if not self.repetitive_message[str(m.author.id)].values():
                    del self.repetitive_message[str(m.author.id)]
            except KeyError:
                pass

    async def invoke(self, command, message: discord.Message, **kwargs) -> None:
        ctx = await self.bot.get_context(message)
        ctx.author = message.guild.me
        await ctx.invoke(self.bot.get_command(command), **kwargs)

    def get_most_common_count_repmessage(self, id_: int) -> int:
        most_common = self.repetitive_message.get(str(id_), Counter()).most_common(1)
        if most_common:
            if most_common[0]:
                return most_common[0][1]
        return 0

    def get_nudenet_classifications(self, m, path) -> None:
        img = Image.open(path)
        image_hash = str(average_hash(img))
        img.close()

        try:
            labels = self.nude_image_cache[image_hash]
        except KeyError:
            with self.nude_graph.as_default():
                result = self.nude_detector.detect(path, min_prob=0.8)
            labels = []

            for i in result:
                labels.append(i['label'])

        os.remove(path)
        if labels:
            self.nude_image_cache[image_hash] = labels
            self.bot.loop.create_task(self.nudenet_callback(m, labels))

    async def nudenet_callback(self, m, labels) -> None:
        guild_config = await self.bot.db.get_guild_config(m.guild.id)

        for i in guild_config.detections.sexually_explicit:
            if i in labels:
                await m.delete()
                await self.bot.mute(m.author, timedelta(minutes=10), reason=f'Explicit image detection {tuple(labels)}')

                break


def setup(bot: rainbot) -> None:
    bot.add_cog(Detections(bot))
