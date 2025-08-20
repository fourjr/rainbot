import discord
from discord.ext import commands
from core.database import Database
from utils.decorators import has_permissions
from utils.helpers import create_embed, confirm_action, safe_send
import re


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.detection_types = [
            "max_lines",
            "max_words",
            "max_characters",
            "english_only",
            "repetitive_characters",
            "caps_message",
            "image_filters",
        ]
        self.recommended_config = {
            "enabled": True,
            "detections": {
                "max_lines": True,
                "max_words": True,
                "max_characters": True,
                "english_only": False,
                "repetitive_characters": True,
                "caps_message": True,
                "image_filters": False,
            },
            "punishments": {
                "max_lines": "delete",
                "max_words": "delete",
                "max_characters": "delete",
                "english_only": "delete",
                "repetitive_characters": "delete",
                "caps_message": "delete",
                "image_filters": "delete",
            },
            "config": {
                "max_lines": 20,
                "max_words": 300,
                "max_characters": 2000,
                "repetitive_characters_threshold": 20,
                "caps_message_percent": 70,
                "caps_message_min_length": 50,
            },
        }

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return

        guild_config = await self.db.get_guild_config(message.guild.id)
        automod_config = guild_config.get("automod", {})

        if not automod_config.get("enabled"):
            return
            
        ignored_channels = automod_config.get("ignored_channels", [])
        if message.channel.id in ignored_channels:
            return

        detections = automod_config.get("detections", {})
        config = automod_config.get("config", {})

        if detections.get("max_lines") and await self.max_lines(message, config):
            return
        if detections.get("max_words") and await self.max_words(message, config):
            return
        if detections.get("max_characters") and await self.max_characters(message, config):
            return
        if detections.get("english_only") and await self.english_only(message, config):
            return
        if detections.get("repetitive_characters") and await self.repetitive_characters(
            message, config
        ):
            return
        if detections.get("caps_message") and await self.caps_message(message, config):
            return
        if detections.get("image_filters") and await self.image_filters(message, config):
            return

    async def _handle_punishment(self, message, detection_type):
        """Handle the punishment for a detected offense"""
        guild_config = await self.db.get_guild_config(message.guild.id)
        punishments = guild_config.get("automod", {}).get("punishments", {})
        punishment = punishments.get(detection_type, "delete") # Default to delete

        if punishment == "delete":
            try:
                await message.delete()
                await safe_send(
                    message.channel,
                    f"{message.author.mention}, your message was removed due to `{detection_type}`.",
                    delete_after=10,
                )
            except discord.NotFound:
                pass
        elif punishment == "warn":
            # You would need to call the warn command from the moderation cog
            # This is a simplified example
            await safe_send(
                message.channel,
                f"{message.author.mention}, you have been warned for `{detection_type}`.",
                delete_after=10,
            )

    async def max_lines(self, message, config):
        max_lines = config.get("max_lines")
        if max_lines and len(message.content.splitlines()) > max_lines:
            await self._handle_punishment(message, "max_lines")
            return True
        return False

    async def max_words(self, message, config):
        max_words = config.get("max_words")
        if max_words and len(message.content.split()) > max_words:
            await self._handle_punishment(message, "max_words")
            return True
        return False

    async def max_characters(self, message, config):
        max_characters = config.get("max_characters")
        if max_characters and len(message.content) > max_characters:
            await self._handle_punishment(message, "max_characters")
            return True
        return False

    async def english_only(self, message, config):
        from utils.constants import UNICODE_EMOJI

        english_regex = re.compile(
            r"(?:\(╯°□°\）╯︵ ┻━┻)|[ -~]|(?:"
            + UNICODE_EMOJI
            + r")|(?:‘|’|“|”|\s)|[.!?\\\-\(\)]|ツ|¯|(?:┬─┬ ノ\( ゜-゜ノ\))"
        )
        english_text = "".join(english_regex.findall(message.content))
        if english_text != message.content:
            await self._handle_punishment(message, "english_only")
            return True
        return False

    async def repetitive_characters(self, message, config):
        threshold = config.get("repetitive_characters_threshold")
        if threshold:
            from collections import Counter

            counter = Counter(message.content)
            for char, count in counter.most_common(1):
                if count > threshold:
                    await self._handle_punishment(message, "repetitive_characters")
                    return True
        return False

    async def caps_message(self, message, config):
        percent = config.get("caps_message_percent")
        min_length = config.get("caps_message_min_length")
        if percent and min_length and len(message.content) >= min_length:
            caps = sum(1 for c in message.content if c.isupper())
            if (caps / len(message.content)) * 100 > percent:
                await self._handle_punishment(message, "caps_message")
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
                            await self._handle_punishment(message, "image_filters")
                            return True
                    except Exception as e:
                        print(e)
        return False

    @commands.group(invoke_without_command=True)
    @has_permissions(level=4)
    async def automod(self, ctx):
        embed = create_embed(
            title="🤖 Automod",
            description="Use `!automod <subcommand>` to configure automod settings.",
            color="info",
        )
        await ctx.send(embed=embed)

    @automod.command()
    @has_permissions(level=4)
    async def enable(self, ctx):
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
        valid_settings = [
            "max_lines",
            "max_words",
            "max_characters",
            "repetitive_characters_threshold",
            "caps_message_percent",
            "caps_message_min_length",
        ]
        if setting not in valid_settings:
            await safe_send(ctx, f"Invalid setting. Valid settings: {', '.join(valid_settings)}")
            return
        
        try:
            value = int(value)
        except ValueError:
            await safe_send(ctx, "Value must be a number.")
            return

        await self.db.update_guild_config(ctx.guild.id, {f"automod.config.{setting}": value})
        await safe_send(ctx, f"Set `{setting}` to `{value}`.")

    @automod.command(name="setdetection")
    @has_permissions(level=4)
    async def set_detection(self, ctx, detection_type: str, enabled: bool):
        if detection_type not in self.detection_types:
            await safe_send(ctx, f"Invalid detection type. Valid types: {', '.join(self.detection_types)}")
            return
        
        await self.db.update_guild_config(ctx.guild.id, {f"automod.detections.{detection_type}": enabled})
        status = "enabled" if enabled else "disabled"
        await safe_send(ctx, f"Detection for `{detection_type}` has been {status}.")

    @automod.command(name="setdetectionpunishments")
    @has_permissions(level=4)
    async def set_detection_punishments(self, ctx, detection_type: str, punishment: str):
        if detection_type not in self.detection_types:
            await safe_send(ctx, f"Invalid detection type. Valid types: {', '.join(self.detection_types)}")
            return
        
        valid_punishments = ["delete", "warn"]
        if punishment not in valid_punishments:
            await safe_send(ctx, f"Invalid punishment. Valid punishments: {', '.join(valid_punishments)}")
            return

        await self.db.update_guild_config(ctx.guild.id, {f"automod.punishments.{detection_type}": punishment})
        await safe_send(ctx, f"Punishment for `{detection_type}` set to `{punishment}`.")

    @automod.command(name="setrecommended")
    @has_permissions(level=4)
    async def set_recommended(self, ctx):
        confirmed = await confirm_action(
            ctx,
            "Are you sure you want to apply the recommended automod configuration?",
            "This will overwrite your current automod settings.",
        )
        if not confirmed:
            await safe_send(ctx, "Action cancelled.")
            return

        await self.db.update_guild_config(
            ctx.guild.id, {"automod": self.recommended_config}
        )
        await safe_send(ctx, "Recommended automod configuration has been applied.")

    @automod.command(name="setdetectionignore")
    @has_permissions(level=4)
    async def set_detection_ignore(self, ctx, channel: discord.TextChannel):
        config = await self.db.get_guild_config(ctx.guild.id)
        ignored_channels = config.get("automod", {}).get("ignored_channels", [])

        if channel.id in ignored_channels:
            ignored_channels.remove(channel.id)
            await self.db.update_guild_config(ctx.guild.id, {"automod.ignored_channels": ignored_channels})
            await safe_send(ctx, f"Removed {channel.mention} from the automod ignore list.")
        else:
            ignored_channels.append(channel.id)
            await self.db.update_guild_config(ctx.guild.id, {"automod.ignored_channels": ignored_channels})
            await safe_send(ctx, f"Added {channel.mention} to the automod ignore list.")


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
