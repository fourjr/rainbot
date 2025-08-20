import discord
from discord.ext import commands
from core.database import Database
from utils.decorators import has_permissions
from utils.helpers import create_embed
import re


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return

        guild_config = await self.db.get_guild_config(message.guild.id)
        automod_config = guild_config.get("automod", {})

        if not automod_config.get("enabled"):
            return

        if await self.max_lines(message, automod_config):
            return
        if await self.max_words(message, automod_config):
            return
        if await self.max_characters(message, automod_config):
            return
        if await self.english_only(message, automod_config):
            return
        if await self.repetitive_characters(message, automod_config):
            return
        if await self.caps_message(message, automod_config):
            return
        if await self.image_filters(message, automod_config):
            return

    async def max_lines(self, message, config):
        max_lines = config.get("max_lines")
        if max_lines and len(message.content.splitlines()) > max_lines:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention}, your message exceeded the maximum number of lines.",
                delete_after=5,
            )
            return True
        return False

    async def max_words(self, message, config):
        max_words = config.get("max_words")
        if max_words and len(message.content.split()) > max_words:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention}, your message exceeded the maximum number of words.",
                delete_after=5,
            )
            return True
        return False

    async def max_characters(self, message, config):
        max_characters = config.get("max_characters")
        if max_characters and len(message.content) > max_characters:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention}, your message exceeded the maximum number of characters.",
                delete_after=5,
            )
            return True
        return False

    async def english_only(self, message, config):
        if config.get("english_only"):
            from utils.constants import UNICODE_EMOJI

            english_regex = re.compile(
                r"(?:\(╯°□°\）╯︵ ┻━┻)|[ -~]|(?:"
                + UNICODE_EMOJI
                + r")|(?:‘|’|“|”|\s)|[.!?\\\-\(\)]|ツ|¯|(?:┬─┬ ノ\( ゜-゜ノ\))"
            )
            english_text = "".join(english_regex.findall(message.content))
            if english_text != message.content:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}, please speak English.", delete_after=5
                )
                return True
        return False

    async def repetitive_characters(self, message, config):
        repetitive_characters_threshold = config.get("repetitive_characters_threshold")
        if repetitive_characters_threshold:
            from collections import Counter

            counter = Counter(message.content)
            for char, count in counter.most_common(1):
                if count > repetitive_characters_threshold:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention}, your message contains too many repetitive characters.",
                        delete_after=5,
                    )
                    return True
        return False

    async def caps_message(self, message, config):
        caps_message_percent = config.get("caps_message_percent")
        caps_message_min_length = config.get("caps_message_min_length")
        if (
            caps_message_percent
            and caps_message_min_length
            and len(message.content) >= caps_message_min_length
        ):
            caps = sum(1 for c in message.content if c.isupper())
            if (caps / len(message.content)) * 100 > caps_message_percent:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}, your message contains too many capital letters.",
                    delete_after=5,
                )
                return True
        return False

    async def image_filters(self, message, config):
        if config.get("image_filters") and message.attachments:
            import io
            from PIL import Image
            import imagehash

            for attachment in message.attachments:
                if attachment.content_type.startswith("image/"):
                    try:
                        image_bytes = await attachment.read()
                        image = Image.open(io.BytesIO(image_bytes))
                        image_hash = str(imagehash.average_hash(image))
                        if image_hash in config.get("image_filters", []):
                            await message.delete()
                            await message.channel.send(
                                f"{message.author.mention}, your message contains a filtered image.",
                                delete_after=5,
                            )
                            return True
                    except Exception as e:
                        print(e)
        return False

    @commands.group(invoke_without_command=True)
    @has_permissions(level=4)
    async def automod(self, ctx):
        f"""Configure automatic moderation filters and settings
        
        **Usage:** `{ctx.prefix}automod <subcommand>`
        **Examples:**
        • `{ctx.prefix}automod enable` (turn on automod)
        • `{ctx.prefix}automod disable` (turn off automod)
        • `{ctx.prefix}automod config max_lines 10`
        • `{ctx.prefix}automod config caps_message_percent 70`
        
        Automatically moderates spam, caps, repetitive text, and more.
        """
        embed = create_embed(
            title="🤖 Automod",
            description="Use `!automod <subcommand>` to configure automod settings.",
            color="info",
        )
        await ctx.send(embed=embed)

    @automod.command()
    @has_permissions(level=4)
    async def enable(self, ctx):
        """Turn on automatic moderation for the server"""
        await self.db.update_guild_config(ctx.guild.id, {"automod.enabled": True})
        embed = create_embed(
            title="✅ Automod Enabled",
            description="Automod is now active.",
            color="success",
        )
        await ctx.send(embed=embed)

    @automod.command()
    @has_permissions(level=4)
    async def disable(self, ctx):
        """Turn off automatic moderation for the server"""
        await self.db.update_guild_config(ctx.guild.id, {"automod.enabled": False})
        embed = create_embed(
            title="🔴 Automod Disabled",
            description="Automod is now inactive.",
            color="warning",
        )
        await ctx.send(embed=embed)

    @automod.command()
    @has_permissions(level=4)
    async def config(self, ctx, setting: str, value: str):
        f"""Modify specific automod settings like limits and thresholds
        
        **Usage:** `{ctx.prefix}automod config <setting> <value>`
        **Available Settings:**
        • `max_lines` - Maximum lines per message
        • `max_words` - Maximum words per message
        • `max_characters` - Maximum characters per message
        • `caps_message_percent` - Max % of caps (0-100)
        • `repetitive_characters_threshold` - Max repeated chars
        
        **Examples:** `{ctx.prefix}automod config max_lines 5`
        """
        valid_settings = [
            "max_lines",
            "max_words",
            "max_characters",
            "english_only",
            "repetitive_characters_threshold",
            "caps_message_percent",
            "caps_message_min_length",
            "image_filters",
        ]

        if setting not in valid_settings:
            embed = create_embed(
                title="❌ Invalid Setting",
                description=f"Valid settings are: {', '.join(valid_settings)}",
                color="error",
            )
            await ctx.send(embed=embed)
            return

        if setting == "image_filters":
            # For image_filters, we expect a list of hashes
            # For simplicity, we'll just take a space-separated string of hashes
            value = value.split()
        elif setting == "english_only":
            value = value.lower() in ["true", "yes", "1"]
        else:
            try:
                value = int(value)
            except ValueError:
                embed = create_embed(
                    title="❌ Invalid Value",
                    description="Value must be a number for this setting.",
                    color="error",
                )
                await ctx.send(embed=embed)
                return

        await self.db.update_guild_config(ctx.guild.id, {f"automod.{setting}": value})
        embed = create_embed(
            title="✅ Setting Updated",
            description=f"Automod setting `{setting}` has been updated to `{value}`.",
            color="success",
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
