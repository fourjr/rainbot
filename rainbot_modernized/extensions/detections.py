import discord
from discord.ext import commands
import re
import asyncio
from collections import defaultdict, deque
from core.database import Database
from utils.helpers import create_embed, status_embed, update_nested_config
import time


class Detections(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.spam_tracker = defaultdict(lambda: deque(maxlen=5))
        self.duplicate_tracker = defaultdict(lambda: deque(maxlen=3))

        # Invite regex
        self.invite_regex = re.compile(
            r"discord(?:\.gg|app\.com\/invite)\/([a-zA-Z0-9\-]+)"
        )

        # Bad words list (basic)
        self.bad_words = {"badword1", "badword2", "spam", "toxic"}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        config = await self.db.get_guild_config(message.guild.id)
        automod = config.get("automod", {})

        # Spam detection
        if automod.get("spam", False):
            await self._check_spam(message)

        # Invite detection
        if automod.get("invites", False):
            await self._check_invites(message)

        # Bad words detection
        if automod.get("badwords", False):
            await self._check_badwords(message)

        # Mass mentions detection
        if automod.get("mass_mentions", False):
            await self._check_mass_mentions(message)

        # Caps detection
        if automod.get("caps", False):
            await self._check_caps(message)

        # Duplicate messages detection
        if automod.get("duplicates", False):
            await self._check_duplicates(message)

    async def _check_spam(self, message):
        user_id = message.author.id
        now = time.time()

        # Add message timestamp
        self.spam_tracker[user_id].append(now)

        # Check if 5 messages in 5 seconds
        if len(self.spam_tracker[user_id]) == 5:
            if now - self.spam_tracker[user_id][0] < 5:
                await self._punish_user(message, "Spam detected", "spam")

    async def _check_invites(self, message):
        if self.invite_regex.search(message.content):
            await message.delete()
            await self._punish_user(message, "Invite link detected", "invites")

    async def _check_badwords(self, message):
        content_lower = message.content.lower()
        for word in self.bad_words:
            if word in content_lower:
                await message.delete()
                await self._punish_user(
                    message, f"Bad word detected: {word}", "badwords"
                )
                break

    async def _check_mass_mentions(self, message):
        if len(message.mentions) > 5:
            await message.delete()
            await self._punish_user(message, "Mass mentions detected", "mass_mentions")

    async def _check_caps(self, message):
        if len(message.content) > 10:
            caps_ratio = sum(1 for c in message.content if c.isupper()) / len(
                message.content
            )
            if caps_ratio > 0.7:
                await message.delete()
                await self._punish_user(message, "Excessive caps detected", "caps")

    async def _check_duplicates(self, message):
        user_id = message.author.id
        content = message.content.lower()

        self.duplicate_tracker[user_id].append(content)

        if len(self.duplicate_tracker[user_id]) == 3:
            if all(msg == content for msg in self.duplicate_tracker[user_id]):
                await message.delete()
                await self._punish_user(
                    message, "Duplicate messages detected", "duplicates"
                )

    async def _punish_user(self, message, reason, detection_type):
        config = await self.db.get_guild_config(message.guild.id)
        punishment = config.get("automod_punishments", {}).get(detection_type, "warn")

        if punishment == "warn":
            await self._warn_user(message.author, message.guild, reason)
        elif punishment == "mute":
            await self._mute_user(
                message.author, message.guild, reason, 300
            )  # 5 min mute
        elif punishment == "kick":
            await message.author.kick(reason=reason)

    async def _warn_user(self, user, guild, reason):
        await self.db.add_warning(guild.id, user.id, reason)

        embed = create_embed(
            title="⚠️ Warning",
            description=f"{user.mention} has been warned for: {reason}",
            color=discord.Color.orange(),
        )

        config = await self.db.get_guild_config(guild.id)
        # Prefer unified log_channels.moderation, fallback to legacy mod_log_channel
        log_channels = config.get("log_channels", {}) or {}
        mod_log_id = log_channels.get("moderation") or config.get("mod_log_channel")
        if mod_log_id:
            channel = guild.get_channel(mod_log_id)
            if channel:
                await channel.send(embed=embed)

    async def _mute_user(self, user, guild, reason, duration):
        config = await self.db.get_guild_config(guild.id)
        # Prefer standardized key, fallback to legacy
        mute_role_id = config.get("mute_role_id") or config.get("mute_role")

        if mute_role_id:
            mute_role = guild.get_role(mute_role_id)
            if mute_role:
                await user.add_roles(mute_role, reason=reason)

                # Schedule unmute
                await asyncio.sleep(duration)
                await user.remove_roles(mute_role, reason="Auto-unmute")

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def detections(self, ctx):
        """Auto-moderation configuration"""
        config = await self.db.get_guild_config(ctx.guild.id)
        automod = config.get("automod", {})

        embed = create_embed(
            title="🛡️ Auto-moderation Status", color=discord.Color.blue()
        )

        features = {
            "spam": "Spam Detection",
            "invites": "Invite Links",
            "badwords": "Bad Words",
            "mass_mentions": "Mass Mentions",
            "caps": "Caps Lock",
            "nsfw": "NSFW Images",
            "duplicates": "Duplicate Messages",
        }

        for key, name in features.items():
            status = "✅ Enabled" if automod.get(key, False) else "❌ Disabled"
            embed.add_field(name=name, value=status, inline=True)

        await ctx.send(embed=embed)

    @detections.command()
    @commands.has_permissions(manage_guild=True)
    async def toggle(self, ctx, feature: str):
        """Toggle an auto-moderation feature"""
        valid_features = [
            "spam",
            "invites",
            "badwords",
            "mass_mentions",
            "caps",
            "nsfw",
            "duplicates",
        ]

        if feature not in valid_features:
            embed = status_embed(
                title="❌ Invalid Feature",
                description=f"Valid features: {', '.join(valid_features)}",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        config = await self.db.get_guild_config(ctx.guild.id)
        automod = config.get("automod", {})

        current_state = automod.get(feature, False)
        new_state = not current_state

        # Use nested config helper for DRY update
        await update_nested_config(self.db, ctx.guild.id, "automod", feature, new_state)

        status = "enabled" if new_state else "disabled"
        embed = status_embed(
            title="✅ Feature Updated",
            description=f"{feature.title()} detection has been {status}",
            status="success",
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Detections(bot))
