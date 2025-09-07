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
        # Google Cloud Vision categories
        "vision/adult",
        "vision/violence",
        "vision/racy",
        "vision/spoof",
        "vision/medical",
    ]

    def __init__(self, bot: RainBot):
        self.bot = bot
        self.logger = logging.getLogger("rainbot.aimoderation")
        self.api_url = config.api.moderation_api_url

        if not self.api_url:
            self.logger.warning(
                "MODERATION_API_URL not set - AI moderation disabled"
            )

    @property
    def image_whitelist_collection(self):
        """Helper to get the whitelist collection from the database."""
        return self.bot.db.db["image_moderation_whitelist"]

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

    @aimoderation.command(name="debug")
    @commands.is_owner()
    async def aimod_debug(self, ctx: commands.Context):
        """(Owner Only) Shows internal bot ownership status for debugging."""
        owner_ids = self.bot.owner_ids
        author_id = ctx.author.id
        is_owner = await self.bot.is_owner(ctx.author)

        embed = create_embed(title="🐞 AIMod Owner Debug", color=discord.Color.gold())
        embed.add_field(
            name="Bot's Known Owner IDs", value=f"```\n{owner_ids}\n```", inline=False
        )
        embed.add_field(name="Your User ID", value=f"`{author_id}`", inline=False)
        embed.add_field(
            name="`is_owner()` Check Result", value=f"**{is_owner}**", inline=False
        )

        footer_text = ""
        if is_owner:
            footer_text = "✅ The bot correctly identifies you as an owner."
        else:
            footer_text = "❌ The bot does NOT identify you as an owner. Please check your .env file and restart."
        embed.set_footer(text=footer_text)

        await ctx.send(embed=embed)

    async def is_server_whitelisted(self, guild_id: int) -> bool:
        """Checks if a guild is in the image moderation whitelist."""
        return (
            await self.image_whitelist_collection.find_one({"guild_id": guild_id})
            is not None
        )

    @aimoderation.group(
        name="serverwhitelist", aliases=["swl"], invoke_without_command=True
    )
    @commands.is_owner()
    async def server_whitelist(self, ctx: commands.Context):
        """
        **Manage Image Moderation Server Whitelist (Owner Only)**

        Allows or disallows servers from using image moderation.

        **Subcommands:**
        • `add <server_id>`
        • `remove <server_id>`
        • `list`
        """
        if ctx.invoked_subcommand is None:
            await self.swl_list(ctx)

    @server_whitelist.command(name="add")
    @commands.is_owner()
    async def swl_add(self, ctx: commands.Context, guild_id: int):
        """Adds a server to the image moderation whitelist."""
        if await self.is_server_whitelisted(guild_id):
            guild = self.bot.get_guild(guild_id)
            await ctx.send(
                f"❌ Server `{guild.name if guild else guild_id}` is already whitelisted."
            )
            return

        await self.image_whitelist_collection.insert_one({"guild_id": guild_id})
        guild = self.bot.get_guild(guild_id)
        await ctx.send(
            f"✅ Added `{guild.name if guild else guild_id}` to the image moderation whitelist."
        )

    @server_whitelist.command(name="remove")
    @commands.is_owner()
    async def swl_remove(self, ctx: commands.Context, guild_id: int):
        """Removes a server from the image moderation whitelist."""
        if not await self.is_server_whitelisted(guild_id):
            guild = self.bot.get_guild(guild_id)
            await ctx.send(
                f"❌ Server `{guild.name if guild else guild_id}` is not whitelisted."
            )
            return

        await self.image_whitelist_collection.delete_one({"guild_id": guild_id})
        guild = self.bot.get_guild(guild_id)
        await ctx.send(
            f"✅ Removed `{guild.name if guild else guild_id}` from the image moderation whitelist."
        )

    @server_whitelist.command(name="list")
    @commands.is_owner()
    async def swl_list(self, ctx: commands.Context):
        """Lists all servers in the image moderation whitelist."""
        cursor = self.image_whitelist_collection.find({})

        description_lines = []
        async for server_doc in cursor:
            guild_id = server_doc["guild_id"]
            guild = self.bot.get_guild(guild_id)
            description_lines.append(
                f"• {guild.name if guild else 'Unknown Server'} (`{guild_id}`)"
            )

        if not description_lines:
            description = "No servers are currently whitelisted for image moderation."
        else:
            description = "\n".join(description_lines)

        embed = create_embed(
            title="🖼️ Image Moderation Server Whitelist",
            description=description,
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    @aimoderation.group(name="whitelist", invoke_without_command=True)
    @has_permissions(level=5)
    async def whitelist(self, ctx: commands.Context):
        """
        **Whitelist Management**

        Manage users, roles, and channels to be exempt from AI moderation.

        **Subcommands:**
        • `add <user|role|channel>`
        • `remove <user|role|channel>`
        • `list`
        """
        if ctx.invoked_subcommand is None:
            await self.list_whitelist(ctx)

    @whitelist.command(name="add")
    @has_permissions(level=5)
    async def add_to_whitelist(
        self,
        ctx: commands.Context,
        entity: discord.abc.GuildChannel | discord.Role | discord.User,
    ):
        """Adds a user, role, or channel to the AI moderation whitelist.

        **Usage:** `{prefix}aimod whitelist add <user|role|channel>`
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        whitelist = guild_config.get("ai_moderation", {}).get("whitelist", [])

        if entity.id in whitelist:
            embed = create_embed(
                title="❌ Already Whitelisted",
                description=f"{entity.mention} is already in the whitelist.",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        await self.bot.db.update_guild_config_atomic(
            ctx.guild.id, {"$push": {"ai_moderation.whitelist": entity.id}}
        )

        embed = create_embed(
            title="✅ Whitelist Updated",
            description=f"{entity.mention} has been added to the AI moderation whitelist.",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @whitelist.command(name="remove")
    @has_permissions(level=5)
    async def remove_from_whitelist(
        self,
        ctx: commands.Context,
        entity: discord.abc.GuildChannel | discord.Role | discord.User,
    ):
        """Removes a user, role, or channel from the AI moderation whitelist.

        **Usage:** `{prefix}aimod whitelist remove <user|role|channel>`
        """
        await self.bot.db.update_guild_config_atomic(
            ctx.guild.id, {"$pull": {"ai_moderation.whitelist": entity.id}}
        )

        embed = create_embed(
            title="✅ Whitelist Updated",
            description=f"{entity.mention} has been removed from the AI moderation whitelist.",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @whitelist.command(name="list")
    @has_permissions(level=5)
    async def list_whitelist(self, ctx: commands.Context):
        """Lists all whitelisted users, roles, and channels.

        **Usage:** `{prefix}aimod whitelist list`
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        whitelist_ids = guild_config.get("ai_moderation", {}).get("whitelist", [])

        if not whitelist_ids:
            embed = create_embed(
                title="ℹ️ Whitelist is Empty",
                description="No users, roles, or channels are currently whitelisted.",
                color=discord.Color.blue(),
            )
            await ctx.send(embed=embed)
            return

        users = []
        roles = []
        channels = []

        for entity_id in whitelist_ids:
            user = ctx.guild.get_member(entity_id)
            role = ctx.guild.get_role(entity_id)
            channel = ctx.guild.get_channel(entity_id)

            if user:
                users.append(user.mention)
            elif role:
                roles.append(role.mention)
            elif channel:
                channels.append(channel.mention)

        embed = create_embed(
            title="Whitelist Configuration", color=discord.Color.blue()
        )
        if users:
            embed.add_field(name="Users", value="\n".join(users), inline=False)
        if roles:
            embed.add_field(name="Roles", value="\n".join(roles), inline=False)
        if channels:
            embed.add_field(name="Channels", value="\n".join(channels), inline=False)

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

        # Whitelist
        whitelist_ids = ai_config.get("whitelist", [])
        if whitelist_ids:
            whitelisted_items = []
            for entity_id in whitelist_ids:
                user = self.bot.get_user(entity_id)
                role = ctx.guild.get_role(entity_id)
                channel = self.bot.get_channel(entity_id)
                if user:
                    whitelisted_items.append(user.mention)
                elif role:
                    whitelisted_items.append(role.mention)
                elif channel:
                    whitelisted_items.append(channel.mention)

            if whitelisted_items:
                embed.add_field(
                    name="Whitelist",
                    value=", ".join(whitelisted_items),
                    inline=False,
                )

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
            # Check if scores are binary (0/1) or percentage (0.0-1.0)
            is_binary = all(score in [0, 1] for score in scores.values())
            
            if is_binary:
                score_text = "\n".join(
                    [
                        f"• {cat.replace('/', ' / ').title()}: {'✅ Detected' if score == 1 else '❌ Not Detected'}"
                        for cat, score in scores.items()
                    ]
                )
            else:
                score_text = "\n".join(
                    [
                        f"• {cat.replace('/', ' / ').title()}: {int(score * 100)}%"
                        for cat, score in scores.items()
                    ]
                )
            embed.add_field(name="Detection Results" if is_binary else "Confidence Scores", value=score_text, inline=False)

    async def _test_text_moderation(self, ctx: commands.Context, content: str):
        """Helper to test text moderation"""
        async with ctx.typing():
            try:
                result = await self._moderate_text(content)
                embed = create_embed(
                    title="🧪 AI Text Moderation Test Results",
                    color=discord.Color.blue(),
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

    async def _test_image_moderation(
        self, ctx: commands.Context, attachment: discord.Attachment
    ):
        """Helper to test image moderation"""
        if not any(
            attachment.filename.lower().endswith(ext)
            for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]
        ):
            embed = create_embed(
                title="❌ Invalid File Type",
                description="Please attach a valid image (.png, .jpg, .jpeg, .webp, .gif).",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        async with ctx.typing():
            try:
                result = await self._moderate_image(attachment)
                embed = create_embed(
                    title="🧪 AI Image Moderation Test Results",
                    color=discord.Color.blue(),
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
                description="Below are all the categories you can configure.",
                color=discord.Color.blue(),
            )

            text_categories = []
            image_categories = []
            for cat in self.VALID_CATEGORIES:
                if cat.startswith("vision/"):
                    image_categories.append(f"• {cat.replace('vision/', '')}")
                else:
                    text_categories.append(f"• {cat}")

            if text_categories:
                embed.add_field(
                    name="📝 Text Categories",
                    value="```\n" + "\n".join(text_categories) + "\n```",
                    inline=False,
                )

            if image_categories:
                embed.add_field(
                    name="🖼️ Image Categories (Vision)",
                    value="```\n" + "\n".join(image_categories) + "\n```",
                    inline=False,
                )

            embed.set_footer(
                text="When enabling/disabling, use the full name (e.g., vision/adult)"
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
                result = await resp.json()
                self.logger.debug(f"Text moderation API response: {result}")
                return result

    async def _moderate_image(self, attachment: discord.Attachment) -> Dict[str, Any]:
        """Moderate image content using moderation API"""
        if not self.api_url:
            raise ValueError("API URL not configured")

        # Validate image type
        valid_extensions = [".png", ".jpg", ".jpeg", ".webp", ".gif"]
        if not any(
            attachment.filename.lower().endswith(ext)
            for ext in valid_extensions
        ):
            raise ValueError(f"Unsupported image type: {attachment.filename}")

        try:
            image_content = await attachment.read()
            
            # Determine proper content type based on file extension
            filename_lower = attachment.filename.lower()
            if filename_lower.endswith(('.jpg', '.jpeg')):
                content_type = 'image/jpeg'
            elif filename_lower.endswith('.png'):
                content_type = 'image/png'
            elif filename_lower.endswith('.gif'):
                content_type = 'image/gif'
            elif filename_lower.endswith('.webp'):
                content_type = 'image/webp'
            else:
                content_type = 'application/octet-stream'
            
            # Create form data for image upload - use 'file' as field name to match API docs
            data = aiohttp.FormData()
            data.add_field('file', image_content, filename=attachment.filename, content_type=content_type)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/moderate/image", data=data
                ) as resp:
                    if resp.status == 422:
                        raise ValueError(f"Invalid media type: {attachment.filename}")
                    if resp.status != 200:
                        raise ValueError(f"API request failed with status {resp.status}")
                    result = await resp.json()
                    self.logger.debug(f"Image moderation API response: {result}")
                    return result

        except Exception as e:
            self.logger.error(f"Error moderating image with API: {e}")
            raise ValueError(f"Error moderating image: {e}")

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

        # Whitelist check
        whitelist = ai_config.get("whitelist", [])
        if message.author.id in whitelist:
            return
        if message.channel.id in whitelist:
            return
        if any(role.id in whitelist for role in message.author.roles):
            return

        try:
            # Text moderation
            if message.content and ai_config.get("text_moderation", True):
                await self._process_text_moderation(message, ai_config)

            # Image moderation
            if message.attachments and ai_config.get("image_moderation", True):
                if await self.is_server_whitelisted(message.guild.id):
                    await self._process_image_moderation(message, ai_config)

        except Exception as e:
            self.logger.error(f"AI moderation error: {e}")

    async def _process_text_moderation(self, message: discord.Message, ai_config):
        """Process text moderation"""
        try:
            result = await self._moderate_text(message.content)
            scores = result.get("category_scores", {})
            thresholds = ai_config.get("thresholds", {})

            flagged_categories = [
                cat
                for cat, score in scores.items()
                if score >= thresholds.get(cat, 0.8)  # Default to 80% if not set
            ]

            if flagged_categories:
                # Update result with categories that actually crossed the threshold
                result["categories"] = flagged_categories
                await self._take_action(message, result, ai_config)

        except Exception as e:
            self.logger.error(f"Text moderation failed: {e}")

    async def _process_image_moderation(self, message: discord.Message, ai_config):
        """Process image moderation"""
        for attachment in message.attachments:
            try:
                result = await self._moderate_image(attachment)
                scores = result.get("category_scores", {})
                thresholds = ai_config.get("thresholds", {})

                flagged_categories = [
                    cat
                    for cat, score in scores.items()
                    if score >= thresholds.get(cat, 0.8)  # Default to 80% if not set
                ]

                if flagged_categories:
                    # Update result with categories that actually crossed the threshold
                    result["categories"] = flagged_categories
                    await self._take_action(
                        message, result, ai_config, attachment=attachment
                    )
                    break

            except Exception as e:
                self.logger.error(f"Image moderation failed: {e}")

    async def _log_action(
        self, guild_id: int, embed: discord.Embed, file: Optional[discord.File] = None
    ):
        guild_config = await self.bot.db.get_guild_config(guild_id)
        ai_config = guild_config.get("ai_moderation", {})
        log_channel_id = ai_config.get("log_channel")

        if log_channel_id:
            log_channel = self.bot.get_channel(log_channel_id)
            if log_channel:
                try:
                    await log_channel.send(embed=embed, file=file)
                except discord.Forbidden:
                    self.logger.warning(
                        f"Missing permissions to send log message to {log_channel_id}"
                    )
                except discord.HTTPException as e:
                    self.logger.error(f"Failed to send log message: {e}")

    async def _take_action(
        self,
        message: discord.Message,
        result: Dict[str, Any],
        ai_config,
        attachment: Optional[discord.Attachment] = None,
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
                is_binary = all(score in [0, 1] for score in scores.values())
                
                if is_binary:
                    score_text = "\n".join(
                        [
                            f"• {cat.title()}: {'✅ Detected' if score == 1 else '❌ Not Detected'}"
                            for cat, score in scores.items()
                        ]
                    )
                    field_name = "Detection Results"
                else:
                    score_text = "\n".join(
                        [
                            f"• {cat.title()}: {int(score * 100)}%"
                            for cat, score in scores.items()
                        ]
                    )
                    field_name = "Confidence Scores"
                    
                log_embed.add_field(name=field_name, value=score_text, inline=False)

            log_embed.add_field(
                name="Context",
                value=f"In {message.channel.mention} | [Jump to Message]({message.jump_url})",
                inline=False,
            )
            log_embed.timestamp = datetime.utcnow()

            log_file = None
            if attachment:
                log_file = await attachment.to_file(spoiler=True)

            await self._log_action(message.guild.id, log_embed, file=log_file)

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
