"""
AI Moderation Extension

Provides AI-powered content moderation using external APIs for text and image analysis.
"""

import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

import discord
import aiohttp
from discord.ext import commands

from core.bot import RainBot
from utils.decorators import has_permissions
from utils.helpers import create_embed, confirm_action
from config.config import config


class AIModerationExtension(commands.Cog, name="AI Moderation"):
    """AI-powered content moderation system"""

    VALID_CATEGORIES = [
        "harassment",
        "hate",
        "violence",
        "self-harm/instructions",
        "sexual",
        "illicit",
        "harassment/threatening",
        "self-harm",
        "self-harm/intent",
        "illicit/violent",
        "violence/graphic",
        "hate/threatening",
        "sexual/minors",
    ]

    def __init__(self, bot: RainBot):
        self.bot = bot
        self.logger = logging.getLogger("rainbot.aimoderation")
        self.api_url = config.api.moderation_api_url

        if not self.api_url:
            self.logger.warning("MODERATION_API_URL not set - AI moderation disabled")

    @commands.group(invoke_without_command=True, aliases=["aimod"])
    @has_permissions(level=5)
    async def aimoderation(self, ctx: commands.Context):
        """
        **AI Moderation Management**

        Configure and manage AI-powered content moderation.

        **Subcommands:**
        • `enable` - Enable AI moderation
        • `disable` - Disable AI moderation
        • `config` - View current configuration
        • `test` - Test AI moderation with sample content
        • `sensitivity` - Set detection sensitivity
        • `action` - Set moderation actions
        • `category` - Enable/disable specific categories
        • `setlogchannel` - Set the log channel for moderation actions
        • `removelogchannel` - Remove the log channel
        """
        if ctx.invoked_subcommand is None:
            await self._show_status(ctx)

    async def _show_status(self, ctx: commands.Context):
        """Show AI moderation status"""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        ai_config = guild_config.get("ai_moderation", {})

        embed = create_embed(
            title="🤖 AI Moderation Status", color=discord.Color.blue()
        )

        # Status
        enabled = ai_config.get("enabled", False)
        embed.add_field(
            name="Status", value="🟢 Enabled" if enabled else "🔴 Disabled", inline=True
        )

        # API Status
        api_status = "🟢 Connected" if self.api_url else "🔴 Not Configured"
        embed.add_field(name="API Status", value=api_status, inline=True)

        # Log Channel
        log_channel_id = ai_config.get("log_channel")
        if log_channel_id:
            channel = self.bot.get_channel(log_channel_id)
            log_channel_status = channel.mention if channel else "Not Found"
        else:
            log_channel_status = "Not Set"
        embed.add_field(name="Log Channel", value=log_channel_status, inline=True)

        # Features
        features = []
        if ai_config.get("text_moderation", True):
            features.append("📝 Text Analysis")
        if ai_config.get("image_moderation", True):
            features.append("🖼️ Image Analysis")

        embed.add_field(
            name="Features",
            value="\n".join(features) if features else "None",
            inline=False,
        )

        await ctx.send(embed=embed)

    @aimoderation.command(name="enable")
    @has_permissions(level=5)
    async def enable(self, ctx: commands.Context):
        """Enables the AI moderation system for the server.

        **Usage:** `{prefix}aimod enable`
        """
        if not self.api_url:
            embed = create_embed(
                title="❌ Configuration Required",
                description="AI moderation API URL is not configured. Please contact the bot administrator.",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if not await confirm_action(
            ctx, "Are you sure you want to enable AI moderation?"
        ):
            await ctx.send("Cancelled.", delete_after=20)
            return

        await self.bot.db.update_guild_config(
            ctx.guild.id,
            {
                "ai_moderation.enabled": True,
                "ai_moderation.text_moderation": True,
                "ai_moderation.image_moderation": True,
            },
        )

        embed = create_embed(
            title="✅ AI Moderation Enabled",
            description="AI-powered content moderation is now active for this server.",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @aimoderation.command(name="disable")
    @has_permissions(level=5)
    async def disable(self, ctx: commands.Context):
        """Disables the AI moderation system for the server.

        **Usage:** `{prefix}aimod disable`
        """
        if not await confirm_action(
            ctx, "Are you sure you want to disable AI moderation?"
        ):
            await ctx.send("Cancelled.", delete_after=20)
            return

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"ai_moderation.enabled": False}
        )

        embed = create_embed(
            title="🔴 AI Moderation Disabled",
            description="AI-powered content moderation has been deactivated.",
            color=discord.Color.orange(),
        )
        await ctx.send(embed=embed)

    @aimoderation.command(name="config")
    @has_permissions(level=5)
    async def config(self, ctx: commands.Context):
        """Displays the current AI moderation configuration.

        **Usage:** `{prefix}aimod config`
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        ai_config = guild_config.get("ai_moderation", {})

        embed = create_embed(
            title="⚙️ AI Moderation Configuration", color=discord.Color.blue()
        )

        # Basic settings
        embed.add_field(
            name="Enabled",
            value="✅ Yes" if ai_config.get("enabled", False) else "❌ No",
            inline=True,
        )

        embed.add_field(
            name="Text Moderation",
            value="✅ Yes" if ai_config.get("text_moderation", True) else "❌ No",
            inline=True,
        )

        embed.add_field(
            name="Image Moderation",
            value="✅ Yes" if ai_config.get("image_moderation", True) else "❌ No",
            inline=True,
        )

        # Log channel
        log_channel_id = ai_config.get("log_channel")
        if log_channel_id:
            channel = self.bot.get_channel(log_channel_id)
            log_channel_status = channel.mention if channel else "Not Found"
        else:
            log_channel_status = "Not Set"
        embed.add_field(name="Log Channel", value=log_channel_status, inline=False)

        # Categories
        categories = ai_config.get("categories", {})
        if categories:
            enabled_cats = []
            disabled_cats = []
            for cat, enabled in categories.items():
                if enabled:
                    enabled_cats.append(cat.title())
                else:
                    disabled_cats.append(cat.title())

            if enabled_cats:
                embed.add_field(
                    name="Enabled Categories",
                    value=", ".join(enabled_cats),
                    inline=False,
                )

            if disabled_cats:
                embed.add_field(
                    name="Disabled Categories",
                    value=", ".join(disabled_cats),
                    inline=False,
                )

        await ctx.send(embed=embed)

    @aimoderation.command(name="test")
    @has_permissions(level=5)
    async def test(self, ctx: commands.Context, *, content: Optional[str] = None):
        """Tests the AI moderation with sample content or an image.

        **Usage:** `{prefix}aimod test [content]`
        **Example (text):** `{prefix}aimod test This is a test message`
        **Example (image):** `{prefix}aimod test` (with an attached image)
        """
        if not self.api_url:
            embed = create_embed(
                title="❌ API Not Configured",
                description="AI moderation API URL is not configured.",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if ctx.message.attachments:
            await self._test_image_moderation(ctx, ctx.message.attachments[0])
        elif content:
            await self._test_text_moderation(ctx, content)
        else:
            embed = create_embed(
                title="❌ No Input",
                description="Please provide text or an image attachment to test.",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)

    def _add_result_fields_to_embed(self, embed: discord.Embed, result: Dict[str, Any]):
        """Adds moderation result fields to an embed."""
        embed.add_field(
            name="Decision",
            value=result.get("decision", "unknown").title(),
            inline=True,
        )

        categories = result.get("categories", [])
        if categories:
            embed.add_field(
                name="Flagged Categories",
                value=", ".join(cat.replace("/", " / ").title() for cat in categories),
                inline=True,
            )

        scores = result.get("category_scores", {})
        if scores:
            score_text = "\n".join(
                [
                    f"• {cat.replace('/', ' / ').title()}: {int(score * 100)}%"
                    for cat, score in scores.items()
                ]
            )
            embed.add_field(
                name="Confidence Scores", value=score_text, inline=False
            )

    async def _test_text_moderation(self, ctx: commands.Context, content: str):
        """Helper to test text moderation"""
        async with ctx.typing():
            try:
                result = await self._moderate_text(content)
                embed = create_embed(
                    title="🧪 AI Text Moderation Test Results", color=discord.Color.blue()
                )
                embed.add_field(
                    name="Content",
                    value=f"```{content[:1000]}{'...' if len(content) > 1000 else ''}```",
                    inline=False,
                )
                self._add_result_fields_to_embed(embed, result)
                await ctx.send(embed=embed)
            except Exception as e:
                self.logger.error(f"AI moderation text test failed: {e}")
                embed = create_embed(
                    title="❌ Test Failed",
                    description=f"Failed to test AI moderation: {str(e)}",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)

    async def _test_image_moderation(self, ctx: commands.Context, attachment: discord.Attachment):
        """Helper to test image moderation"""
        if not any(
            attachment.filename.lower().endswith(ext)
            for ext in [".png", ".jpg", ".jpeg", ".webp"]
        ):
            embed = create_embed(
                title="❌ Invalid File Type",
                description="Please attach a valid image (.png, .jpg, .jpeg, .webp).",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        async with ctx.typing():
            try:
                result = await self._moderate_image(attachment)
                embed = create_embed(
                    title="🧪 AI Image Moderation Test Results", color=discord.Color.blue()
                )
                embed.set_image(url=attachment.url)
                self._add_result_fields_to_embed(embed, result)
                await ctx.send(embed=embed)
            except Exception as e:
                self.logger.error(f"AI moderation image test failed: {e}")
                embed = create_embed(
                    title="❌ Test Failed",
                    description=f"Failed to test AI moderation: {str(e)}",
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed)

    @aimoderation.command(name="sensitivity")
    @has_permissions(level=5)
    async def sensitivity(self, ctx: commands.Context, category: str, sensitivity: int):
        """Sets the detection sensitivity for a category.

        **Usage:** `{prefix}aimoderation sensitivity <category|all> <sensitivity>`
        **Examples:**
        - `{prefix}aimoderation sensitivity hate 80`
        - `{prefix}aimoderation sensitivity all 75`
        """
        if not await confirm_action(
            ctx,
            f"Are you sure you want to set the sensitivity for `{category}` to `{sensitivity}%`?",
        ):
            await ctx.send("Cancelled.", delete_after=20)
            return

        if not 1 <= sensitivity <= 100:
            embed = create_embed(
                title="❌ Invalid Sensitivity",
                description="Sensitivity must be between 1 and 100",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        # Convert percentage to 0.0-1.0 for storage
        threshold = sensitivity / 100.0

        if category.lower() == "all":
            update_data = {}
            for cat in self.VALID_CATEGORIES:
                update_data[f"ai_moderation.thresholds.{cat}"] = threshold

            await self.bot.db.update_guild_config(ctx.guild.id, update_data)
            description = f"Set sensitivity for all categories to {sensitivity}%"
        elif category.lower() in self.VALID_CATEGORIES:
            await self.bot.db.update_guild_config(
                ctx.guild.id,
                {f"ai_moderation.thresholds.{category.lower()}": threshold},
            )
            description = f"Set {category} sensitivity to {sensitivity}%"
        else:
            embed = create_embed(
                title="❌ Invalid Category",
                description=f"Valid categories: {', '.join(self.VALID_CATEGORIES)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        embed = create_embed(
            title="✅ Sensitivity Updated",
            description=description,
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @aimoderation.command(name="category")
    @has_permissions(level=5)
    async def category(
        self,
        ctx: commands.Context,
        category: Optional[str] = None,
        enabled: Optional[bool] = None,
    ):
        """Enables or disables a specific moderation category.

        If no category is provided, it will list all available categories.

        **Usage:** `{prefix}aimoderation category [category|all] <true/false>`
        **Examples:**
        - `{prefix}aimoderation category`
        - `{prefix}aimoderation category hate true`
        - `{prefix}aimoderation category all false`
        """
        if category is None:
            embed = create_embed(
                title="🤖 Available AI Moderation Categories",
                description="Here is a list of all available categories for AI moderation.",
                color=discord.Color.blue(),
            )
            embed.add_field(
                name="Categories",
                value="\n".join([f"• `{cat}`" for cat in self.VALID_CATEGORIES]),
                inline=False,
            )
            await ctx.send(embed=embed)
            return

        if enabled is None:
            embed = create_embed(
                title="❌ Missing Argument",
                description="You must provide whether to enable or disable the category (`true` or `false`).",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        status = "enabled" if enabled else "disabled"

        if not await confirm_action(
            ctx,
            f"Are you sure you want to set the status for `{category}` to `{status}`?",
        ):
            await ctx.send("Cancelled.", delete_after=20)
            return

        if category.lower() == "all":
            update_data = {}
            for cat in self.VALID_CATEGORIES:
                update_data[f"ai_moderation.categories.{cat}"] = enabled

            await self.bot.db.update_guild_config(ctx.guild.id, update_data)
            description = f"All detection categories have been {status}"
        elif category.lower() in self.VALID_CATEGORIES:
            update_data = {f"ai_moderation.categories.{category.lower()}": enabled}
            await self.bot.db.update_guild_config(ctx.guild.id, update_data)
            description = f"{category.title()} detection {status}"
        else:
            embed = create_embed(
                title="❌ Invalid Category",
                description=f"Valid categories: {', '.join(self.VALID_CATEGORIES)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        embed = create_embed(
            title="✅ Category Updated",
            description=description,
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @aimoderation.command(name="action")
    @has_permissions(level=5)
    async def action(self, ctx: commands.Context, category: str, action: str):
        """Sets the moderation action for a category.

        **Usage:** `{prefix}aimoderation action <category|all> <action>`

        **Actions:**
        - `delete`
        - `warn`
        - `mute`
        - `kick`
        - `ban`
        - `none`

        **Examples:**
        - `{prefix}aimoderation action hate delete`
        - `{prefix}aimoderation action all warn`
        """
        valid_actions = ["delete", "warn", "mute", "kick", "ban", "none"]

        if not await confirm_action(
            ctx,
            f"Are you sure you want to set the action for `{category}` to `{action}`?",
        ):
            await ctx.send("Cancelled.", delete_after=20)
            return

        if action.lower() not in valid_actions:
            embed = create_embed(
                title="❌ Invalid Action",
                description=f"Valid actions: {', '.join(valid_actions)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if category.lower() == "all":
            update_data = {}
            for cat in self.VALID_CATEGORIES:
                update_data[f"ai_moderation.actions.{cat}"] = action.lower()

            await self.bot.db.update_guild_config(ctx.guild.id, update_data)
            description = f"Set action for all categories to {action}"
        elif category.lower() in self.VALID_CATEGORIES:
            await self.bot.db.update_guild_config(
                ctx.guild.id,
                {f"ai_moderation.actions.{category.lower()}": action.lower()},
            )
            description = f"Set {category} action to {action}"
        else:
            embed = create_embed(
                title="❌ Invalid Category",
                description=f"Valid categories: {', '.join(self.VALID_CATEGORIES)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        embed = create_embed(
            title="✅ Action Updated",
            description=description,
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @aimoderation.command(name="setlogchannel")
    @has_permissions(level=5)
    async def set_log_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """Sets the log channel for AI moderation actions.

        **Usage:** `{prefix}aimod setlogchannel <#channel>`
        """
        if not await confirm_action(
            ctx, f"Are you sure you want to set the log channel to {channel.mention}?"
        ):
            await ctx.send("Cancelled.", delete_after=20)
            return

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"ai_moderation.log_channel": channel.id}
        )

        embed = create_embed(
            title="✅ Log Channel Set",
            description=f"AI moderation logs will now be sent to {channel.mention}",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @aimoderation.command(name="removelogchannel")
    @has_permissions(level=5)
    async def remove_log_channel(self, ctx: commands.Context):
        """Removes the AI moderation log channel.

        **Usage:** `{prefix}aimod removelogchannel`
        """
        if not await confirm_action(
            ctx, "Are you sure you want to remove the log channel?"
        ):
            await ctx.send("Cancelled.", delete_after=20)
            return

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"ai_moderation.log_channel": None}
        )

        embed = create_embed(
            title="✅ Log Channel Removed",
            description="AI moderation logs will no longer be sent to a specific channel.",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    async def _moderate_text(self, content: str) -> Dict[str, Any]:
        """Moderate text content using external API"""
        if not self.api_url:
            raise ValueError("API URL not configured")

        payload = {"content": content}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_url}/moderate/text", json=payload
            ) as resp:
                if resp.status != 200:
                    raise ValueError(f"API request failed with status {resp.status}")
                return await resp.json()

    async def _moderate_image(self, attachment: discord.Attachment) -> Dict[str, Any]:
        """Moderate image content using external API"""
        if not self.api_url:
            raise ValueError("API URL not configured")

        form = aiohttp.FormData()
        form.add_field("file", await attachment.read(), filename=attachment.filename)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_url}/moderate/image", data=form
            ) as resp:
                if resp.status != 200:
                    raise ValueError(f"API request failed with status {resp.status}")
                return await resp.json()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Process messages for AI moderation"""
        if not message.guild or message.author.bot:
            return

        guild_config = await self.bot.db.get_guild_config(message.guild.id)
        ai_config = guild_config.get("ai_moderation", {})

        if not ai_config.get("enabled", False):
            return

        if not self.api_url:
            return

        try:
            # Text moderation
            if message.content and ai_config.get("text_moderation", True):
                await self._process_text_moderation(message, ai_config)

            # Image moderation
            if message.attachments and ai_config.get("image_moderation", True):
                await self._process_image_moderation(message, ai_config)

        except Exception as e:
            self.logger.error(f"AI moderation error: {e}")

    async def _process_text_moderation(self, message: discord.Message, ai_config):
        """Process text moderation"""
        try:
            result = await self._moderate_text(message.content)

            if result.get("decision") == "flag":
                await self._take_action(message, result, ai_config)

        except Exception as e:
            self.logger.error(f"Text moderation failed: {e}")

    async def _process_image_moderation(self, message: discord.Message, ai_config):
        """Process image moderation"""
        for attachment in message.attachments:
            if not any(
                attachment.filename.lower().endswith(ext)
                for ext in [".png", ".jpg", ".jpeg", ".webp"]
            ):
                continue

            try:
                result = await self._moderate_image(attachment)

                if result.get("decision") in ("block", "flag"):
                    await self._take_action(message, result, ai_config)
                    break

            except Exception as e:
                self.logger.error(f"Image moderation failed: {e}")

    async def _log_action(self, guild_id: int, embed: discord.Embed):
        guild_config = await self.bot.db.get_guild_config(guild_id)
        ai_config = guild_config.get("ai_moderation", {})
        log_channel_id = ai_config.get("log_channel")

        if log_channel_id:
            log_channel = self.bot.get_channel(log_channel_id)
            if log_channel:
                try:
                    await log_channel.send(embed=embed)
                except discord.Forbidden:
                    self.logger.warning(
                        f"Missing permissions to send log message to {log_channel_id}"
                    )
                except discord.HTTPException as e:
                    self.logger.error(f"Failed to send log message: {e}")

    async def _take_action(
        self, message: discord.Message, result: Dict[str, Any], ai_config
    ):
        """Take moderation action based on AI result"""
        categories = result.get("categories", [])
        if not categories:
            return

        enabled_categories = ai_config.get("categories", {})
        active_categories = [
            cat for cat in categories if enabled_categories.get(cat, True)
        ]

        if not active_categories:
            return

        actions = ai_config.get("actions", {})
        action = "delete"  # Default
        for category in active_categories:
            if category in actions:
                action = actions[category]
                break

        reason = f"AI moderation: {', '.join(active_categories)}"

        try:
            # Log to channel first
            log_embed = create_embed(
                title="AI Moderation Action",
                color=discord.Color.red(),
            )
            log_embed.add_field(
                name="Member",
                value=f"{message.author.mention} (`{message.author.id}`)",
                inline=False,
            )
            log_embed.add_field(name="Action Taken", value=action.title(), inline=True)
            log_embed.add_field(name="Reason", value=reason, inline=True)
            if message.content:
                log_embed.add_field(
                    name="Content",
                    value=f"```{message.content[:1000]}```",
                    inline=False,
                )

            scores = result.get("category_scores", {})
            if scores:
                score_text = "\n".join(
                    [
                        f"• {cat.title()}: {int(score * 100)}%"
                        for cat, score in scores.items()
                    ]
                )
                log_embed.add_field(
                    name="Confidence Scores", value=score_text, inline=False
                )

            log_embed.add_field(
                name="Context",
                value=f"In {message.channel.mention} | [Jump to Message]({message.jump_url})",
                inline=False,
            )
            log_embed.timestamp = datetime.utcnow()

            await self._log_action(message.guild.id, log_embed)

            if action == "none":
                return  # Only notify, take no action

            if action == "delete":
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}, your message was removed for violating our content policy.",
                    delete_after=10,
                )

            self.logger.info(
                f"AI moderation action taken: {action} for {message.author} in {message.guild}"
            )

        except Exception as e:
            self.logger.error(f"Failed to take AI moderation action: {e}")


async def setup(bot: RainBot):
    """Load the AI Moderation extension"""
    await bot.add_cog(AIModerationExtension(bot))
