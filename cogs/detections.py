import asyncio
import functools
import io
import os
import re
from collections import Counter, defaultdict
from tempfile import NamedTemporaryFile
from typing import DefaultDict, List

import discord
import aiohttp
from cachetools import LFUCache
from discord.ext import commands
from discord.ext.commands import Cog
from imagehash import average_hash
from PIL import Image, UnidentifiedImageError
import logging
import openai

from bot import rainbot
from ext.utility import UNICODE_EMOJI, Detection, detection, MessageWrapper


# Removed TensorFlow dependency


class Detections(commands.Cog):
    def __init__(self, bot: rainbot) -> None:
        self.bot = bot
        self.logger = logging.getLogger("rainbot.detections")
        self.spam_detection: DefaultDict[str, List[float]] = defaultdict(list)
        self.repetitive_message: DefaultDict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        self.INVITE_REGEX = re.compile(
            r"((http(s|):\/\/|)(discord)(\.(gg|io|me)\/|app\.com\/invite\/)([0-z]+))"
        )
        self.ENGLISH_REGEX = re.compile(
            r"(?:\(╯°□°\）╯︵ ┻━┻)|[ -~]|(?:"
            + UNICODE_EMOJI
            + r")|(?:‘|’|“|”|\s)|[.!?\\\-\(\)]|ツ|¯|(?:┬─┬ ノ\( ゜-゜ノ\))"
        )

        try:
            self.nude_detector = None  # Will use free API instead
        except Exception as e:
            if hasattr(self.bot, "logger"):
                self.bot.logger.warning(f"Failed to initialize NSFW detector: {e}")
            self.nude_detector = None

        self.nude_image_cache: LFUCache[str, List[str]] = LFUCache(50)

        self.detections = []

        for func in self.__class__.__dict__.values():
            if isinstance(func, Detection):
                self.detections.append(func)

    @Cog.listener()
    async def on_message(self, m: MessageWrapper) -> None:
        if self.bot.dev_mode:
            dev_guild_id = getattr(self.bot, "dev_guild_id", None)
            if dev_guild_id and m.guild and m.guild.id != dev_guild_id:
                return
        if (
            self.bot.dev_mode
            and getattr(self.bot, "dev_guild_id", None)
            and (m.guild and m.guild.id != getattr(self.bot, "dev_guild_id", None))
        ) or m.type != discord.MessageType.default or not m.guild:
            return

        guild_config = await self.bot.db.get_guild_config(m.guild.id)
        for func in self.detections:
            await func.trigger(self, m, guild_config)

    @detection("sexually_explicit", require_attachment=True)
    async def sexually_explicit(self, m: MessageWrapper, guild_config) -> None:
        if not guild_config.detections.sexually_explicit:
            return

        for i in m.attachments:
            if (
                i.filename.endswith(".png")
                or i.filename.endswith(".jpg")
                or i.filename.endswith(".jpeg")
            ):
                await self.get_openai_classifications(m, guild_config, i.url)

    @detection("mention_limit")
    async def mention_limit(self, m: MessageWrapper, guild_config) -> None:
        mentions = []
        for i in m.mentions:
            if i not in mentions and i != m.author and not i.bot:
                mentions.append(i)

        if len(mentions) >= guild_config.detections.mention_limit:
            await m.detection.punish(self.bot, m, guild_config, reason=f"Mass mentions ({len(m.mentions)})")

    @detection("max_lines")
    async def max_lines(self, m: MessageWrapper, guild_config) -> None:
        if len(m.content.splitlines()) > guild_config.detections.max_lines:
            await m.detection.punish(self.bot, m, guild_config)

    @detection("max_words")
    async def max_words(self, m: MessageWrapper, guild_config) -> None:
        if len(m.content.split(" ")) > guild_config.detections.max_words:
            await m.detection.punish(self.bot, m, guild_config)

    @detection("max_characters")
    async def max_characters(self, m: MessageWrapper, guild_config) -> None:
        if len(m.content) > guild_config.detections.max_characters:
            await m.detection.punish(self.bot, m, guild_config)

    @detection("filters")
    async def filtered_words(self, m: MessageWrapper, guild_config) -> None:
        words = [i for i in guild_config.detections.filters if i in m.content.lower()]
        if words:
            await m.detection.punish(self.bot, m, guild_config, reason=f"Sent a filtered word: {words[0]}")

    @detection("regex_filters")
    async def regex_filter(self, m: MessageWrapper, guild_config) -> None:
        matches = [i for i in guild_config.detections.regex_filters if re.search(i, m.content)]
        if matches:
            await m.detection.punish(self.bot, m, guild_config, reason="Sent a filtered message.")

    @detection("image_filters", require_attachment=True)
    async def image_filters(self, m: MessageWrapper, guild_config) -> None:
        for i in m.attachments:
            stream = io.BytesIO()
            await i.save(stream)
            try:
                img = Image.open(stream)
            except UnidentifiedImageError:
                pass
            else:
                image_hash = str(average_hash(img))
                img.close()

                if image_hash in guild_config.detections.image_filters:
                    await m.detection.punish(self.bot, m, guild_config, reason="Sent a filtered image")
                    break

    @detection("block_invite")
    async def block_invite(self, m: MessageWrapper, guild_config) -> None:
        invite_match = self.INVITE_REGEX.findall(m.content)
        if invite_match:
            for i in invite_match:
                try:
                    invite = await self.bot.fetch_invite(i[-1])
                except discord.NotFound:
                    pass
                else:
                    if not (
                        invite.guild.id == m.guild.id
                        or str(invite.guild.id) in guild_config.whitelisted_guilds
                    ):
                        await m.detection.punish(
                            self.bot,
                            m,
                            guild_config,
                            reason=f"Advertising discord server `{invite.guild.name}` (<{invite.url}>)",
                        )

    @detection("english_only")
    async def english_only(self, m: MessageWrapper, guild_config) -> None:
        english_text = "".join(self.ENGLISH_REGEX.findall(m.content))
        if english_text != m.content:
            await m.detection.punish(self.bot, m, guild_config)

    @detection("spam_detection")
    async def spam_detection(self, m: MessageWrapper, guild_config) -> None:
        now = m.created_at.timestamp()
        self.spam_detection[str(m.author.id)].append(now)
        # Remove messages older than 5 seconds
        self.spam_detection[str(m.author.id)] = [t for t in self.spam_detection[str(m.author.id)] if now - t < 5]

        limit = guild_config.detections.spam_detection
        if len(self.spam_detection[str(m.author.id)]) >= limit:
            reason = f"Exceeding spam detection ({limit} messages/5s)"
            await m.detection.punish(
                self.bot, m, guild_config, reason=reason, purge_limit=len(self.spam_detection[str(m.author.id)])
            )
            # Clear after punishment
            self.spam_detection[str(m.author.id)].clear()


    @detection("repetitive_message")
    async def repetitive_message(self, m: MessageWrapper, guild_config) -> None:
        now = m.created_at.timestamp()
        author_messages = self.repetitive_message[str(m.author.id)]
        
        # Add current message timestamp
        author_messages[m.content].append(now)

        # Clean up old messages
        for content, timestamps in list(author_messages.items()):
            author_messages[content] = [t for t in timestamps if now - t < 60]
            if not author_messages[content]:
                del author_messages[content]

        limit = guild_config.detections.repetitive_message
        
        current_message_count = len(author_messages.get(m.content, []))

        if current_message_count >= limit:
            reason = f"Repetitive message detection ({limit} identical messages/1m)"
            await m.detection.punish(
                self.bot,
                m,
                guild_config,
                reason=reason,
                purge_limit=current_message_count,
            )
            # Clear after punishment
            if m.content in author_messages:
                del author_messages[m.content]

    @detection("repetitive_characters")
    async def repetitive_characters(self, m: MessageWrapper, guild_config) -> None:
        limit = guild_config.detections.repetitive_characters

        counter = Counter(m.content)
        for c, n in counter.most_common(None):
            if n > limit:
                reason = f"Repetitive character detection ({n} > {limit} of {c} in message)"
                await m.detection.punish(self.bot, m, guild_config, reason=reason)
                break

    @detection("caps_message", check_enabled=False)
    async def caps_message(self, m: MessageWrapper, guild_config) -> None:
        percent = guild_config.detections.caps_message_percent
        min_words = guild_config.detections.caps_message_min_words

        if all((percent, min_words)):
            # this is the check enabled
            english_text = "".join(self.ENGLISH_REGEX.findall(m.content))
            if (
                english_text
                and len(m.content.split(" ")) >= min_words
                and (len([i for i in english_text if i.upper() == i]) / len(english_text))
                >= percent
            ):
                await m.detection.punish(self.bot, m, guild_config)

    def get_most_common_count_repmessage(self, id_: int) -> int:
        author_messages = self.repetitive_message.get(str(id_), {})
        if not author_messages:
            return 0
        
        most_common_count = 0
        for content, timestamps in author_messages.items():
            if len(timestamps) > most_common_count:
                most_common_count = len(timestamps)
        return most_common_count

    async def get_openai_classifications(self, m, guild_config, url) -> None:
        """Use OpenAI's Moderation API for NSFW detection"""
        try:
            response = await self.bot.loop.run_in_executor(
                self.bot.executor,
                lambda: openai.Moderation.create(input=url)
            )
            if response['results'][0]['flagged']:
                await self.openai_callback(m, guild_config, response['results'][0]['categories'])
        except Exception as e:
            self.logger.error(f"Error calling OpenAI Image Moderation API: {e}")

    @detection("ai_moderation")
    async def ai_moderation(self, m: MessageWrapper, guild_config) -> None:
        """Use OpenAI's Moderation API for text moderation"""
        if not guild_config.detections.ai_moderation:
            return
        
        try:
            response = await self.bot.loop.run_in_executor(
                self.bot.executor,
                lambda: openai.Moderation.create(input=m.content)
            )
            if response['results'][0]['flagged']:
                flagged_categories = [k for k, v in response['results'][0]['categories'].items() if v]
                reason = f"AI moderation triggered for: {', '.join(flagged_categories)}"
                await m.detection.punish(self.bot, m, guild_config, reason=reason)
        except Exception as e:
            self.logger.error(f"Error calling OpenAI Moderation API: {e}")

    async def openai_callback(self, m, guild_config, categories) -> None:
        flagged_categories = [k for k, v in categories.items() if v]
        reason = f"Potentially inappropriate image detected for: {', '.join(flagged_categories)}"
        await m.detection.punish(
            self.bot, m, guild_config, reason=reason
        )


async def setup(bot: rainbot) -> None:
    await bot.add_cog(Detections(bot))
