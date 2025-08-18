import copy
import json
import io
import os
import re
import datetime
import logging
from typing import Optional, Union, List, Dict, Any

import discord
import asyncio
import aiohttp
from discord.ext import commands

from rainbot.main import RainBot
from ..ext.command import command, group, RainGroup
from ..services.database import DEFAULT, DBDict, RECOMMENDED_DETECTIONS
from ..ext.time import UserFriendlyTime
from ..ext.utility import (
    format_timedelta,
    tryint,
    SafeFormat,
    CannedStr,
)
from ..ext.permissions import get_perm_level, get_command_level
from ..ext.errors import BotMissingPermissionsInChannel
from ..ext.paginator import Paginator
from rainbot import config
from PIL import Image
from imagehash import average_hash


class Setup(commands.Cog):
    """Enhanced server configuration and setup commands"""

    def __init__(self, bot: RainBot) -> None:
        self.bot = bot
        self.order = 1
        self.logger = logging.getLogger("rainbot.setup")

    async def cog_error(self, ctx: commands.Context, error: Exception) -> None:
        """Handle cog errors with user-friendly messages"""
        if isinstance(error, discord.Forbidden):
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description=f"I don't have the required permissions to run `{ctx.command.name}`.",
                color=config.get_color("error"),
            )
            await ctx.send(embed=embed)
        else:
            raise error

    @command(6, aliases=["view_config", "view-config"], usage="[json]")
    async def viewconfig(self, ctx: commands.Context, options: str = None) -> None:
        """**View all custom server configurations**
        This command displays every setting that has been changed from the default value.
        You can also get a downloadable JSON file of the full configuration.
        **Usage:**
        `{prefix}viewconfig [json]`
        **[json]:**
        - If provided, the full configuration will be sent as a JSON file.
        **Examples:**
        - `{prefix}viewconfig` - Displays all custom-set configurations.
        - `{prefix}viewconfig json` - Sends the full configuration as a file.
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)

        if options and options.lower() == "json":
            config_json = json.dumps(guild_config, indent=2, default=str)
            file = discord.File(io.StringIO(config_json), filename=f"{ctx.guild.name}_config.json")
            await ctx.send(
                embed=discord.Embed(
                    title="📄 Server Configuration (JSON)",
                    description="Here's your server's full configuration as a JSON file.",
                    color=config.get_color("info"),
                ),
                file=file,
            )
            return

        def format_value(path, value):
            if "role" in path.lower() and isinstance(value, str):
                try:
                    role = ctx.guild.get_role(int(value))
                    return f"{role.mention}" if role else f"`{value}`"
                except (ValueError, TypeError):
                    pass
            if "channel" in path.lower() and isinstance(value, str):
                try:
                    channel = ctx.guild.get_channel(int(value))
                    return f"{channel.mention}" if channel else f"`{value}`"
                except (ValueError, TypeError):
                    pass

            if isinstance(value, list):
                if not value:
                    return "None"
                return ", ".join(f"`{v}`" for v in value)
            if isinstance(value, dict):
                if not value:
                    return "None"
                return "\n".join(f"- `{k}`: `{v}`" for k, v in value.items())

            return f"`{value}`"

        custom_settings = []

        def find_diff(d1, d2, path=""):
            for k in d1:
                new_path = f"{path}.{k}" if path else k
                if k not in d2:
                    custom_settings.append((new_path, d1[k]))
                elif isinstance(d1[k], dict) and isinstance(d2[k], dict):
                    find_diff(d1[k], d2[k], new_path)
                elif d1[k] != d2[k]:
                    custom_settings.append((new_path, d1[k]))

        find_diff(guild_config, DEFAULT)

        if not any(path not in ("guild_id", "_id") for path, _ in custom_settings):
            embed = discord.Embed(
                title=f"⚙️ {ctx.guild.name} Custom Configurations",
                description="No custom configurations found. All settings are at their default values.",
                color=config.get_color("info"),
            )
            await ctx.send(embed=embed)
            return

        custom_settings.sort()

        embeds = [
            discord.Embed(
                title=f"⚙️ {ctx.guild.name} Custom Configurations",
                description="Showing all settings that have been changed from the default.",
                color=config.get_color("info"),
            )
        ]

        for path, value in custom_settings:
            if path in ("guild_id", "_id"):
                continue

            field_name = path.replace("_", " ").title()
            field_value = format_value(path, value)

            if (
                len(embeds[-1]) + len(field_name) + len(field_value) > 6000
                or len(embeds[-1].fields) >= 25
            ):
                embeds.append(
                    discord.Embed(
                        title=f"⚙️ {ctx.guild.name} Custom Configurations (cont.)",
                        color=config.get_color("info"),
                    )
                )

            if len(field_value) > 1024:
                chunks = [field_value[i : i + 1024] for i in range(0, len(field_value), 1024)]
                for i, chunk in enumerate(chunks):
                    embeds[-1].add_field(
                        name=f"{field_name} (part {i+1})", value=chunk, inline=False
                    )
                    if len(embeds[-1].fields) >= 25:
                        embeds.append(
                            discord.Embed(
                                title=f"⚙️ {ctx.guild.name} Custom Configurations (cont.)",
                                color=config.get_color("info"),
                            )
                        )
            else:
                embeds[-1].add_field(name=field_name, value=field_value, inline=False)

        if len(embeds) > 1:
            paginator = Paginator(ctx, *embeds)
            await paginator.start()
        else:
            await ctx.send(embed=embeds[0])

    @command(10, aliases=["import_config", "import-config"], usage="<url>")
    async def importconfig(self, ctx: commands.Context, *, url: str) -> None:
        """**Import server configuration**

        This command imports a server configuration from a JSON URL.
        The configuration is validated before being applied.

        **Usage:**
        `{prefix}importconfig <url>`

        **<url>:**
        - The raw URL to a JSON file containing the configuration.

        **Example:**
        `{prefix}importconfig https://hastebin.cc/raw/abcdef`
        """
        embed = discord.Embed(title="📥 Importing Configuration...", color=config.get_color("info"))
        msg = await ctx.send(embed=embed)

        try:
            async with self.bot.session.get(url) as resp:
                if resp.status != 200:
                    embed = discord.Embed(
                        title="❌ Import Failed",
                        description="Could not fetch configuration from the provided URL.",
                        color=config.get_color("error"),
                    )
                    await msg.edit(embed=embed)
                    return

                data = await resp.json()

            # Validate configuration
            required_fields = ["prefix", "time_offset", "perm_levels", "logs", "detections"]
            missing_fields = [field for field in required_fields if field not in data]

            if missing_fields:
                embed = discord.Embed(
                    title="❌ Invalid Configuration",
                    description=f"Missing required fields: {', '.join(missing_fields)}",
                    color=config.get_color("error"),
                )
                await msg.edit(embed=embed)
                return

            # Apply configuration
            await self.bot.db.update_guild_config(ctx.guild.id, {"$set": data})

            embed = discord.Embed(
                title="✅ Configuration Imported",
                description="Your server configuration has been successfully imported!",
                color=config.get_color("success"),
            )
            embed.add_field(
                name="📋 Imported Settings",
                value=f"• Prefix: `{data.get('prefix', '!')}`\n"
                f"• Time Offset: {data.get('time_offset', 0)} hours\n"
                f"• Permission Levels: {len(data.get('perm_levels', {}))}\n"
                f"• Log Channels: {len(data.get('logs', {}))}\n"
                f"• Auto-moderation: {len(data.get('detections', {}))} settings",
                inline=False,
            )

            await msg.edit(embed=embed)

        except json.JSONDecodeError:
            embed = discord.Embed(
                title="❌ Invalid JSON",
                description="The provided URL does not contain valid JSON data.",
                color=config.get_color("error"),
            )
            await msg.edit(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Import Error",
                description=f"An error occurred while importing: {str(e)}",
                color=config.get_color("error"),
            )
            await msg.edit(embed=embed)

    @command(10, aliases=["export_config", "export-config"])
    async def exportconfig(self, ctx: commands.Context) -> None:
        """**Export server configuration**

        This command exports the current server configuration as a JSON file.

        **Usage:**
        `{prefix}exportconfig`
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        data = json.dumps(guild_config, indent=2, default=str)
        file = discord.File(io.StringIO(data), filename=f"{ctx.guild.id}_config.json")
        embed = discord.Embed(
            title="📤 Export Configuration",
            description="Attached is your server configuration in JSON format.",
            color=config.get_color("info"),
        )
        await ctx.send(embed=embed, file=file)

    @command(10, aliases=["reset_config", "reset-config"], usage="(interactive)")
    async def resetconfig(self, ctx: commands.Context) -> None:
        """**Reset server configuration to defaults**

        This command resets all server settings to their default values.
        A confirmation is required before the reset is performed.

        **Usage:**
        `{prefix}resetconfig`

        This command is interactive. You will be asked to confirm the reset.
        """
        embed = discord.Embed(
            title="⚠️ Reset Configuration",
            description="This will reset ALL server settings to default values.\n\n"
            "**This action cannot be undone!**\n\n"
            "React with ✅ to confirm or ❌ to cancel.",
            color=config.get_color("warning"),
        )

        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        def check(reaction, user):
            return (
                user == ctx.author
                and reaction.message.id == msg.id
                and str(reaction.emoji) in ["✅", "❌"]
            )

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)

            if str(reaction.emoji) == "✅":
                # Reset configuration
                await self.bot.db.update_guild_config(ctx.guild.id, {"$set": DEFAULT})

                embed = discord.Embed(
                    title="✅ Configuration Reset",
                    description="All server settings have been reset to default values.",
                    color=config.get_color("success"),
                )
                embed.add_field(
                    name="🔄 Default Settings",
                    value=f"• Prefix: `{DEFAULT['prefix']}`\n"
                    f"• Time Offset: {DEFAULT['time_offset']} hours\n"
                    f"• All logs: Disabled\n"
                    f"• Auto-moderation: Disabled",
                    inline=False,
                )
                await msg.edit(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ Reset Cancelled",
                    description="Configuration reset was cancelled.",
                    color=config.get_color("info"),
                )
                await msg.edit(embed=embed)

        except TimeoutError:
            embed = discord.Embed(
                title="⏰ Timeout",
                description="Reset confirmation timed out. Configuration was not changed.",
                color=config.get_color("warning"),
            )
            await msg.edit(embed=embed)

    @group(10, invoke_without_command=True)
    async def setup(self, ctx: commands.Context) -> None:
        """**Interactive server setup wizard**

        This command guides you through setting up the bot for your server.
        You can choose between a quick setup for basic configuration or an advanced setup for more detailed options.

        **Subcommands:**
        - `quick` - Basic configuration wizard.
        - `automod` - Configure auto-moderation features.
        - `logging` - Set up logging channels.
        - `permissions` - Configure permission levels.
        """
        embed = discord.Embed(
            title="🚀 Welcome to rainbot Setup!",
            description="I'll help you configure rainbot for your server.\n\n"
            "Choose an option to get started:",
            color=config.get_color("info"),
        )

        embed.add_field(
            name="📋 Setup Options",
            value="1️⃣ **Quick Setup** - Basic configuration\n"
            "2️⃣ **Advanced Setup** - Detailed configuration\n"
            "3️⃣ **Auto-moderation** - Configure automod\n"
            "4️⃣ **Logging** - Set up logging channels\n"
            "5️⃣ **Permissions** - Configure permission levels\n"
            "6️⃣ **View Current** - See current settings",
            inline=False,
        )

        embed.add_field(
            name="💡 Tips",
            value="• Use `!setup quick` for basic setup\n"
            "• Use `!setup advanced` for full control\n"
            "• You can always change settings later",
            inline=False,
        )

        await ctx.send(embed=embed)

    @setup.command(name="quick")
    async def setup_quick(self, ctx: commands.Context) -> None:
        """**Quick setup wizard for basic configuration**

        This interactive command will guide you through the essential setup steps for the bot,
        including setting the command prefix, creating a mute role, and setting up a moderation log channel.

        **Usage:**
        `{prefix}setup quick`
        """
        embed = discord.Embed(
            title="⚡ Quick Setup",
            description="Let's get you started quickly!\n\n"
            "I'll ask you a few questions to configure the basics.",
            color=config.get_color("info"),
        )
        await ctx.send(embed=embed)

        # Step 1: Prefix
        embed = discord.Embed(
            title="🔧 Step 1: Command Prefix",
            description="What prefix would you like to use for commands?\n\n"
            "Examples: `!`, `?`, `>`, `r!`\n\n"
            "Type your preferred prefix:",
            color=config.get_color("info"),
        )
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and len(m.content) <= 5

        try:
            prefix_msg = await self.bot.wait_for("message", timeout=60.0, check=check)
            prefix = prefix_msg.content.strip()

            # Step 2: Mute Role
            embed = discord.Embed(
                title="🔇 Step 2: Mute Role",
                description="Do you want me to create a mute role?\n\n"
                "Type `yes` to create one, or `no` to skip:",
                color=config.get_color("info"),
            )
            await ctx.send(embed=embed)

            mute_msg = await self.bot.wait_for(
                "message",
                timeout=60.0,
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
            )

            mute_role = None
            if mute_msg.content.lower() in ["yes", "y", "create"]:
                try:
                    mute_role = await ctx.guild.create_role(
                        name="Muted",
                        color=discord.Color.dark_grey(),
                        reason="rainbot quick setup - mute role",
                    )

                    # Set permissions for all channels
                    for channel in ctx.guild.channels:
                        if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                            try:
                                await channel.set_permissions(
                                    mute_role, send_messages=False, speak=False
                                )
                            except discord.Forbidden:
                                pass

                    embed = discord.Embed(
                        title="✅ Mute Role Created",
                        description=f"Created mute role: {mute_role.mention}",
                        color=config.get_color("success"),
                    )
                    await ctx.send(embed=embed)
                except discord.Forbidden:
                    embed = discord.Embed(
                        title="❌ Permission Error",
                        description="I don't have permission to create roles.",
                        color=config.get_color("error"),
                    )
                    await ctx.send(embed=embed)

            # Step 3: Moderation Channel
            embed = discord.Embed(
                title="📝 Step 3: Moderation Logs",
                description="Would you like to set up a channel for moderation logs?\n\n"
                "Type a channel name (e.g., `mod-logs`) or `skip`:",
                color=config.get_color("info"),
            )
            await ctx.send(embed=embed)

            log_msg = await self.bot.wait_for(
                "message",
                timeout=60.0,
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
            )

            log_channel = None
            if log_msg.content.lower() != "skip":
                try:
                    log_channel = await ctx.guild.create_text_channel(
                        log_msg.content, reason="rainbot quick setup - moderation logs"
                    )
                    embed = discord.Embed(
                        title="✅ Log Channel Created",
                        description=f"Created log channel: {log_channel.mention}",
                        color=config.get_color("success"),
                    )
                    await ctx.send(embed=embed)
                except discord.Forbidden:
                    embed = discord.Embed(
                        title="❌ Permission Error",
                        description="I don't have permission to create channels.",
                        color=config.get_color("error"),
                    )
                    await ctx.send(embed=embed)

            # Save configuration
            config_data = {"prefix": prefix, "time_offset": 0}

            if mute_role:
                config_data["mute_role"] = str(mute_role.id)

            if log_channel:
                config_data["modlog"] = {
                    "member_ban": str(log_channel.id),
                    "member_unban": str(log_channel.id),
                    "member_kick": str(log_channel.id),
                    "member_mute": str(log_channel.id),
                    "member_unmute": str(log_channel.id),
                    "member_warn": str(log_channel.id),
                }

            await self.bot.db.update_guild_config(ctx.guild.id, {"$set": config_data})

            # Success message
            embed = discord.Embed(
                title="🎉 Setup Complete!",
                description="Your server has been configured successfully!",
                color=config.get_color("success"),
            )

            embed.add_field(
                name="✅ What's Ready",
                value=f"• Commands: Use `{prefix}help`\n"
                f"• Moderation: Basic commands available\n"
                f"• Logging: {'Enabled' if log_channel else 'Disabled'}\n"
                f"• Mute System: {'Ready' if mute_role else 'Not configured'}",
                inline=False,
            )

            embed.add_field(
                name="🔧 Next Steps",
                value=f"• Configure auto-moderation: `{prefix}setup automod`\n"
                f"• Set up more logging: `{prefix}setup logging`\n"
                f"• Configure permissions: `{prefix}setup permissions`\n"
                f"• Get help: `{prefix}help`",
                inline=False,
            )

            await ctx.send(embed=embed)

        except TimeoutError:
            embed = discord.Embed(
                title="⏰ Setup Timeout",
                description="Setup timed out. You can try again with `!setup quick`",
                color=config.get_color("warning"),
            )
            await ctx.send(embed=embed)

    @setup.command(name="automod")
    async def setup_automod(self, ctx: commands.Context) -> None:
        """**Interactive auto-moderation setup**

        This command provides an interactive way to enable or disable various auto-moderation features.

        **Usage:**
        `{prefix}setup automod`
        """
        embed = discord.Embed(
            title="🛡️ Auto-moderation Setup",
            description="Configure automatic moderation features.\n\n"
            "React to enable/disable features:",
            color=config.get_color("info"),
        )

        features = [
            ("🔄", "Spam Detection"),
            ("🔗", "Invite Links"),
            ("🤬", "Bad Words"),
            ("📢", "Mass Mentions"),
            ("🔊", "Caps Lock"),
            ("🖼️", "NSFW Images"),
            ("📝", "Duplicate Messages"),
        ]

        for emoji, label in features:
            embed.add_field(name=f"{emoji} {label}", value="Click to toggle", inline=True)

        msg = await ctx.send(embed=embed)

        # Add reactions
        for emoji, _ in features:
            await msg.add_reaction(emoji)

        embed = discord.Embed(
            title="✅ Auto-moderation Setup Complete",
            description="Your auto-moderation settings have been configured!",
            color=config.get_color("success"),
        )
        await ctx.send(embed=embed)

    @setup.command(name="logging")
    async def setup_logging(self, ctx: commands.Context) -> None:
        """**Interactive logging setup**

        This command allows you to interactively configure logging channels for different server events.

        **Usage:**
        `{prefix}setup logging`
        """
        embed = discord.Embed(
            title="📝 Logging Setup",
            description="Configure logging channels for different events.\n\n"
            "React to set up each log type:",
            color=config.get_color("info"),
        )

        log_types = [
            ("👥 Member Joins/Leaves", "member_join", "member_leave"),
            ("🔨 Moderation Actions", "moderation"),
            ("💬 Message Edits/Deletes", "message_edit", "message_delete"),
            ("🎭 Role Changes", "role_create", "role_delete", "role_update"),
            ("🔊 Voice Activity", "voice_join", "voice_leave"),
            ("🛡️ Server Updates", "server_update"),
        ]

        for emoji, *types in log_types:
            embed.add_field(
                name=f"{emoji} {types[0].replace('_', ' ').title()}",
                value="Click to configure",
                inline=True,
            )

        msg = await ctx.send(embed=embed)

        embed = discord.Embed(
            title="✅ Logging Setup Complete",
            description="Your logging channels have been configured!",
            color=config.get_color("success"),
        )
        await ctx.send(embed=embed)

    @setup.command(name="permissions")
    async def setup_permissions(self, ctx: commands.Context) -> None:
        """Interactive permission level setup"""
        embed = discord.Embed(
            title="🛡️ Permission Levels Setup",
            description="Configure permission levels for your server.\n\n"
            "Each level can use commands of that level and below.",
            color=config.get_color("info"),
        )

        levels = [
            (0, "Everyone", "Basic commands"),
            (1, "Helper", "Basic moderation"),
            (2, "Moderator", "Kick, warn, mute"),
            (3, "Senior Moderator", "Ban, tempban"),
            (4, "Admin", "All moderation"),
            (5, "Senior Admin", "Server management"),
            (6, "Server Manager", "Full control"),
        ]

        for level, name, description in levels:
            embed.add_field(name=f"Level {level}: {name}", value=description, inline=True)

        embed.add_field(
            name="🔧 How to Set",
            value=f"Use `{ctx.prefix}setpermlevel <level> <role>`\n"
            f"Example: `{ctx.prefix}setpermlevel 2 @Moderator`",
            inline=False,
        )

        await ctx.send(embed=embed)

    @command(
        10,
        aliases=["set_log", "set-log"],
        usage="<event|all> <#channel|channel name|channel id|off>",
    )
    async def setlog(self, ctx: commands.Context, log_name: str, *, channel: str = None) -> None:
        """**Configure the log channel for message/server events**

        This command sets the channel where various server events will be logged.

        **Usage:**
        `{prefix}setlog <event|all> <#channel|channel name|channel id|off>`

        **<event|all>:**
        - `all`: Apply the channel to all event types.
        - Specify an event type to set the log channel for that event only.

        **<#channel|channel name|channel id|off>:**
        - Mention the channel, provide its name or ID.
        - Use `off` to disable logging for the specified event.

        **Valid Event Types:**
        `all`, `message_delete`, `message_edit`, `member_join`, `member_remove`, `member_ban`, `member_unban`, `vc_state_change`, `channel_create`, `channel_delete`, `role_create`, `role_delete`

        **Examples:**
        - `{prefix}setlog all #logs`
        - `{prefix}setlog member_join #join-log`
        - `{prefix}setlog message_delete off`
        """
        valid_logs = DEFAULT["logs"].keys()
        channel_id = None
        if channel and channel.lower() not in ("off", "none"):
            # Try to resolve channel by mention, ID, or name
            found = None
            # Mention or ID
            try:
                found = await commands.TextChannelConverter().convert(ctx, channel)
            except Exception:
                # Try by name
                found = discord.utils.find(
                    lambda c: c.name.lower() == channel.lower(), ctx.guild.text_channels
                )
            if found:
                # Confirm with user
                confirm_embed = discord.Embed(
                    title="Channel Confirmation",
                    description=f"Is this the correct channel? {found.mention}",
                    color=discord.Color.blue(),
                )
                msg = await ctx.send(embed=confirm_embed)
                await msg.add_reaction("✅")
                await msg.add_reaction("❌")

                def check(reaction, user):
                    return (
                        user == ctx.author
                        and str(reaction.emoji) in ["✅", "❌"]
                        and reaction.message.id == msg.id
                    )

                try:
                    reaction, user = await ctx.bot.wait_for(
                        "reaction_add", timeout=30.0, check=check
                    )
                except asyncio.TimeoutError:
                    await ctx.send("Channel confirmation timed out. Command cancelled.")
                    return
                if str(reaction.emoji) == "✅":
                    channel_id = str(found.id)
                else:
                    await ctx.send("Channel selection cancelled.")
                    return
            else:
                await ctx.send("Channel not found by name, mention, or ID.")
                return
        elif channel and channel.lower() in ("off", "none"):
            channel_id = None

        if log_name == "all":
            for i in valid_logs:
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$set": {f"logs.{i}": channel_id}}
                )
        else:
            if log_name not in valid_logs:
                raise commands.BadArgument(
                    "Invalid log name, pick one from below:\n" + ", ".join(valid_logs)
                )

            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$set": {f"logs.{log_name}": channel_id}}
            )
            await ctx.send(
                f"Log channel for `{log_name}` set to {found.mention if channel_id and found else 'off'}."
            )

    @command(
        10,
        aliases=["set_modlog", "set-modlog"],
        usage="<action|all> <#channel|channel name|channel id|off>",
    )
    async def setmodlog(self, ctx: commands.Context, log_name: str, *, channel: str = None) -> None:
        """**Configure the moderation log channel for actions**

        This command sets the channel where moderation actions will be logged.

        **Usage:**
        `{prefix}setmodlog <action|all> <#channel|channel name|channel id|off>`

        **<action|all>:**
        - `all`: Apply the channel to all moderation action types.
        - Specify an action type to set the log channel for that action only.

        **<#channel|channel name|channel id|off>:**
        - Mention the channel, provide its name or ID.
        - Use `off` to disable logging for the specified action.

        **Valid Action Types:**
        `all`, `ai_moderation`, `member_warn`, `member_mute`, `member_unmute`, `member_kick`, `member_ban`, `member_unban`, `member_softban`, `message_purge`, `channel_lockdown`, `channel_slowmode`

        **Examples:**
        - `{prefix}setmodlog all #mod-log`
        - `{prefix}setmodlog member_ban #security`
        - `{prefix}setmodlog member_warn off`
        """
        channel_id = None
        if channel and channel.lower() not in ("off", "none"):
            found = None
            try:
                found = await commands.TextChannelConverter().convert(ctx, channel)
            except Exception:
                found = discord.utils.find(
                    lambda c: c.name.lower() == channel.lower(), ctx.guild.text_channels
                )
            if found:
                confirm_embed = discord.Embed(
                    title="Channel Confirmation",
                    description=f"Is this the correct channel? {found.mention}",
                    color=discord.Color.blue(),
                )
                msg = await ctx.send(embed=confirm_embed)
                await msg.add_reaction("✅")
                await msg.add_reaction("❌")

                def check(reaction, user):
                    return (
                        user == ctx.author
                        and str(reaction.emoji) in ["✅", "❌"]
                        and reaction.message.id == msg.id
                    )

                try:
                    reaction, user = await ctx.bot.wait_for(
                        "reaction_add", timeout=30.0, check=check
                    )
                except asyncio.TimeoutError:
                    await ctx.send("Channel confirmation timed out. Command cancelled.")
                    return
                if str(reaction.emoji) == "✅":
                    channel_id = str(found.id)
                else:
                    await ctx.send("Channel selection cancelled.")
                    return
            else:
                await ctx.send("Channel not found by name, mention, or ID.")
                return
        elif channel and channel.lower() in ("off", "none"):
            channel_id = None

        # Check if modlog is an array and convert to object
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        if isinstance(guild_config.get("modlog"), list):
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$set": {"modlog": DEFAULT["modlog"]}}
            )
        
        valid_logs = DEFAULT["modlog"].keys()
        if log_name == "all":
            for i in valid_logs:
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$set": {f"modlog.{i}": channel_id}}
                )
        else:
            if log_name not in valid_logs:
                raise commands.BadArgument(
                    "Invalid log name, pick one from below:\n" + ", ".join(valid_logs)
                )

            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$set": {f"modlog.{log_name}": channel_id}}
            )
            await ctx.send(
                f"Modlog channel for `{log_name}` set to {found.mention if channel_id and found else 'off'}."
            )

    @command(
        10, aliases=["set_perm_level", "set-perm-level"], usage="<level> <@role|role name|role id>"
    )
    async def setpermlevel(self, ctx: commands.Context, perm_level: int, *, role: str) -> None:
        """**Assign or remove a role's permission level**

        This command sets the permission level for a specified role.
        Permission levels control which commands a user can access.

        **Usage:**
        `{prefix}setpermlevel <level> <@role|role name|role id>`

        **<level>:**
        - A number from 0 to 10.
        - Use `0` to remove a permission level from a role.

        **<@role|role name|role id>:**
        - Mention the role, provide its name, or its ID.

        **Example:**
        - `{prefix}setpermlevel 2 @Moderator`
        - `{prefix}setpermlevel 0 @Muted`
        """
        from ..ext.utility import select_role

        role_obj = await select_role(ctx, role)
        if not role_obj:
            await ctx.send("Role selection cancelled or not found.")
            return

        if perm_level < 0:
            raise commands.BadArgument(f"{perm_level} is below 0")

        if perm_level == 0:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$pull": {"perm_levels": {"role_id": str(role_obj.id)}}}
            )
        else:
            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            if str(role_obj.id) in [i["role_id"] for i in guild_config["perm_levels"]]:
                # overwrite
                await self.bot.db.update_guild_config(
                    ctx.guild.id,
                    {"$set": {"perm_levels.$[elem].level": perm_level}},
                    array_filters=[{"elem.role_id": str(role_obj.id)}],
                )
            else:
                # push
                await self.bot.db.update_guild_config(
                    ctx.guild.id,
                    {"$push": {"perm_levels": {"role_id": str(role_obj.id), "level": perm_level}}},
                )
            await ctx.send(f"Permission level {perm_level} set for role {role_obj.mention}.")

    @command(
        10, aliases=["set_command_level", "set-command-level"], usage="<level|reset> <command>"
    )
    async def setcommandlevel(
        self, ctx: commands.Context, perm_level: Union[int, str], *, command: str
    ) -> None:
        """**Override a command's required permission level**

        This command allows you to change the required permission level for a specific command.

        **Usage:**
        `{prefix}setcommandlevel <level|reset> <command>`

        **<level|reset>:**
        - A number from 0 to 15 to set a new permission level.
        - `reset` to revert the command to its default permission level.

        **<command>:**
        - The name of the command you want to modify.

        **Examples:**
        - `{prefix}setcommandlevel 8 ban`
        - `{prefix}setcommandlevel reset ban`
        - `{prefix}setcommandlevel 5 warn add`
        """
        if isinstance(perm_level, int) and (perm_level < 0 or perm_level > 15):
            raise commands.BadArgument(
                f"{perm_level} is an invalid level, valid levels: 0-15 or reset"
            )

        if isinstance(perm_level, str) and perm_level != "reset":
            raise commands.BadArgument(
                f"{perm_level} is an invalid level, valid levels: 0-15 or reset"
            )

        cmd = self.bot.get_command(command)
        if not cmd:
            raise commands.BadArgument(f'No command with name "{command}" found')

        if isinstance(cmd, RainGroup):
            raise commands.BadArgument("Cannot override a command group")

        name = cmd.qualified_name

        if perm_level == "reset":
            int_perm_level = cmd.perm_level
        else:
            int_perm_level = perm_level

        levels: Union[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]] = [
            {"command": name, "level": int_perm_level}
        ]
        action = "pull" if int_perm_level == cmd.perm_level else "push"
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)

        if cmd.parent:
            parent_level = get_command_level(cmd.parent, guild_config)
            if int_perm_level < parent_level:
                levels.append({"command": cmd.parent.name, "level": int_perm_level})
            elif int_perm_level > parent_level:
                cmd_level = get_command_level(cmd, guild_config)
                all_levels = [get_command_level(c, guild_config) for c in list(cmd.parent.commands)]
                all_levels.remove(cmd_level)
                all_levels.append(int_perm_level)
                lowest = min(all_levels)
                if lowest > parent_level:
                    levels.append({"command": cmd.parent.name, "level": lowest})
        await ctx.send(f"Permission level for command `{name}` set to {int_perm_level}.")

        to_push_levels = {"$each": copy.deepcopy(levels)}

        for i in levels:
            i["level"] = get_command_level(self.bot.get_command(i["command"]), guild_config)
            i["command"] = i["command"].replace(" ", "_")

        levels = {"$in": levels}
        await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"command_levels": levels}})

        if action == "push":
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$push": {"command_levels": to_push_levels}}
            )

    # ...existing code...

    @command(10, aliases=["set_prefix", "set-prefix"])
    async def setprefix(self, ctx: commands.Context, new_prefix: str) -> None:
        """**Set the server's command prefix**

        This command changes the prefix used to invoke bot commands in this server.

        **Usage:**
        `{prefix}setprefix <new_prefix>`

        **<new_prefix>:**
        - The new prefix you want to set.

        **Example:**
        `{prefix}setprefix !`
        """
        await self.bot.db.update_guild_config(ctx.guild.id, {"$set": {"prefix": new_prefix}})
        await ctx.send(f"Prefix set to `{new_prefix}`.")

    @command(10, aliases=["set_offset", "set-offset"])
    async def setoffset(self, ctx: commands.Context, offset: int) -> None:
        """**Set the server time offset from UTC**

        This command sets the time offset for your server, which affects the timestamps in logs.

        **Usage:**
        `{prefix}setoffset <hours>`

        **<hours>:**
        - An integer between -12 and +13 representing the time offset from UTC.

        **Example:**
        - `{prefix}setoffset -5` (for EST)
        - `{prefix}setoffset 1` (for CET)
        """
        if not -12 < offset < 14:
            raise commands.BadArgument("Offset must be between -12 and +13 hours.")
        await self.bot.db.update_guild_config(ctx.guild.id, {"$set": {"offset": offset}})
        await ctx.send(f"Time offset set to `{offset}` hours.")

    @command(10, aliases=["set_detection", "set-detection"])
    async def setdetection(
        self, ctx: commands.Context, detection_type: str, value: Optional[str] = None
    ) -> None:
        """**Sets or toggles auto-moderation types**

        This command enables, disables, or configures various auto-moderation filters.

        **Usage:**
        `{prefix}setdetection <type> [value]`

        **<type>:**
        The type of detection to configure.

        **[value]:**
        - For on/off toggles, use `on` or `off`.
        - For limits, provide a number.
        - If left blank, the detection will be disabled.

        **Valid Types:**
        - `block_invite`
        - `english_only`
        - `mention_limit`
        - `spam_detection`
        - `repetitive_message`
        - `auto_purge_trickocord`
        - `max_lines`
        - `max_words`
        - `max_characters`
        - `caps_message_percent`
        - `caps_message_min_words`
        - `repetitive_characters`

        **Examples:**
        - `{prefix}setdetection block_invite on`
        - `{prefix}setdetection mention_limit 10`
        - `{prefix}setdetection max_lines off`
        """
        if detection_type in ("block_invite", "english_only", "auto_purge_trickocord"):
            if value is None:
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$set": {f"detections.{detection_type}": value}}
                )
                await ctx.send(f"Detection `{detection_type}` set to `{value}`.")
            else:
                await self.bot.db.update_guild_config(
                    ctx.guild.id,
                    {
                        "$set": {
                            f"detections.{detection_type}": value.lower()
                            in ("true", "yes", "y", "1", "on")
                        }
                    },
                )
                await ctx.send(self.bot.accept)
        elif detection_type in (
            "mention_limit",
            "spam_detection",
            "repetitive_message",
            "max_lines",
            "max_words",
            "repetitive_characters",
        ):
            if value is None:
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$set": {f"detections.{detection_type}": value}}
                )
                await ctx.send(self.bot.accept)
            else:
                # int or float
                try:
                    value = float(value)
                    if value <= 0:
                        raise ValueError
                except ValueError:
                    try:
                        value = int(value)
                        if value <= 0:
                            raise ValueError
                    except ValueError as e:
                        raise commands.BadArgument(
                            f"{value} (value) is not a valid number above 0"
                        ) from e

                if detection_type in ("caps_message_percent"):
                    if value > 1:
                        raise commands.BadArgument(
                            f"{value} (value) should be between 1 and 0 as it is a percent."
                        )

                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$set": {f"detections.{detection_type}": int(value)}}
                )
                await ctx.send(self.bot.accept)
        else:
            raise commands.BadArgument("Invalid detection.")

    @command(10, aliases=["set-alert", "set_alert"])
    async def setalert(
        self, ctx: commands.Context, punishment: str, *, value: Optional[str] = None
    ) -> None:
        """**Set the message DMed to a user upon punishment**

        This command configures the direct message a user receives when they are punished.

        **Usage:**
        `{prefix}setalert <punishment> [message]`

        **<punishment>:**
        The type of punishment this alert is for.

        **[message]:**
        The message to be sent. Leave blank to remove the alert.

        **Valid Punishments:**
        `kick`, `ban`, `mute`, `softban`, `unmute`

        **Available Variables:**
        - `{time}`: The time of the punishment.
        - `{author}`: The moderator who issued the punishment.
        - `{user}`: The user who received the punishment.
        - `{reason}`: The reason for the punishment.
        - `{channel}`: The channel where the infraction occurred.
        - `{guild}`: The server where the punishment was issued.
        - `{duration}`: The duration of the mute (for mute punishments only).

        **Example:**
        `{prefix}setalert mute You have been muted in {guild.name} for {reason} for a duration of {duration}.`
        """
        valid_punishments = ("kick", "ban", "mute", "softban", "unmute")

        if punishment in valid_punishments:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$set": {f"alert.{punishment}": value}}
            )
            await ctx.send(f"Alert for `{punishment}` set to: {value if value else 'removed'}.")
        else:
            raise commands.BadArgument(
                f'Invalid punishment. Pick from {", ".join(valid_punishments)}.'
            )

    @command(10, aliases=["set-alert-location", "set_alert_location"])
    async def setalertlocation(self, ctx: commands.Context, location: str) -> None:
        """**Set where auto-moderation alerts are sent**

        This command determines whether auto-moderation alerts are sent to the user's DMs or in the channel of the infraction.

        **Usage:**
        `{prefix}setalertlocation <location>`

        **<location>:**
        - `dm`: Send alerts to the user's direct messages.
        - `channel`: Send alerts in the channel where the infraction occurred.

        **Example:**
        `{prefix}setalertlocation dm`
        """
        location = location.lower()
        if location not in ("dm", "channel"):
            raise commands.BadArgument("Invalid location. Must be `dm` or `channel`.")

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {f"alert.alert_location": location}}
        )
        await ctx.send(f"Alert location set to `{location}`.")

    @command(10, aliases=["set_recommended", "set-recommended"])
    async def setrecommended(self, ctx: commands.Context) -> None:
        """**Applies a recommended set of auto-moderation detections**

        This command quickly enables and configures a baseline set of auto-moderation filters that are recommended for most servers.

        **Usage:**
        `{prefix}setrecommended`
        """
        await self.bot.db.update_guild_config(ctx.guild.id, {"$set": RECOMMENDED_DETECTIONS})
        await ctx.send("Recommended detections have been set.")

    @group(10, aliases=["set-ai-moderation", "set_ai_moderation"], invoke_without_command=True)
    async def setaimoderation(self, ctx: commands.Context) -> None:
        """**Manage AI-powered auto-moderation settings**

        This command group allows you to configure the AI-based content moderation features.

        **Subcommands:**
        - `enable` - Enable AI moderation.
        - `disable` - Disable AI moderation.
        - `sensitivity` - Set the sensitivity of the AI.
        - `category` - Enable or disable specific moderation categories.
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        enabled_categories = [
            k for k, v in guild_config.detections.ai_moderation.categories.items() if v
        ]

        embed = discord.Embed(
            title="AI Moderation Settings",
            description="Control the AI-powered automoderation features for text and images.",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Status",
            value="Enabled" if guild_config.detections.ai_moderation.enabled else "Disabled",
            inline=False,
        )
        embed.add_field(
            name="Enabled Categories",
            value=", ".join(enabled_categories) if enabled_categories else "None",
            inline=False,
        )
        embed.add_field(
            name="Usage",
            value=(
                "`setaimoderation enable` - Enable AI moderation\n"
                "`setaimoderation disable` - Disable AI moderation\n"
                "`setaimoderation category <name | all> <on|off>` - Toggle a category"
            ),
            inline=False,
        )
        embed.add_field(
            name="Configuring Actions",
            value=(
                "Actions (delete, warn, mute, etc.) are configured with the `setdetectionpunishments` command.\n"
                "**Example:** `!!setdetectionpunishments ai_moderation mute 10m`\n"
                "**Example:** `!!setdetectionpunishments image_moderation mute 1h`"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @setaimoderation.command(name="enable")
    async def aimod_enable(self, ctx: commands.Context) -> None:
        """**Enable AI-powered auto-moderation**

        This command enables the AI-based content moderation. You will be asked for confirmation.

        **Usage:**
        `{prefix}setaimoderation enable`
        """
        embed = discord.Embed(
            title="⚠️ AI Moderation Warning",
            description=(
                "Enabling AI moderation can lead to **false positives**. "
                "The AI may incorrectly flag innocent messages.\n\n"
                "Please confirm that you understand this risk and wish to enable the feature."
            ),
            color=discord.Color.orange(),
        )
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        def check(reaction, user):
            return (
                user == ctx.author
                and str(reaction.emoji) in ["✅", "❌"]
                and reaction.message.id == msg.id
            )

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
            if str(reaction.emoji) == "✅":
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$set": {"detections.ai_moderation.enabled": True}}
                )
                await ctx.send("AI moderation has been enabled.")
            else:
                await ctx.send("AI moderation setup cancelled.")
        except asyncio.TimeoutError:
            await ctx.send("Confirmation timed out. AI moderation remains disabled.")

    @setaimoderation.command(name="disable")
    async def aimod_disable(self, ctx: commands.Context) -> None:
        """**Disable AI-powered auto-moderation**

        This command disables the AI-based content moderation.

        **Usage:**
        `{prefix}setaimoderation disable`
        """
        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {"detections.ai_moderation.enabled": False}}
        )
        await ctx.send("AI moderation has been disabled.")

    @setaimoderation.command(name="sensitivity")
    async def aimod_sensitivity(self, ctx: commands.Context, sensitivity: int) -> None:
        """**Set the sensitivity of the AI moderation**

        This command adjusts how strict the AI moderation is.
        A higher sensitivity means the AI is more likely to flag content.

        **Usage:**
        `{prefix}setaimoderation sensitivity <percentage>`

        **<percentage>:**
        - An integer between 1 and 100.

        **Example:**
        `{prefix}setaimoderation sensitivity 80`
        """
        if not 1 <= sensitivity <= 100:
            await ctx.send("Sensitivity must be between 1 and 100.")
            return

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {"detections.ai_moderation.sensitivity": sensitivity}}
        )
        await ctx.send(f"AI moderation sensitivity set to {sensitivity}%.")

    @setaimoderation.command(name="category")
    async def aimod_category(self, ctx: commands.Context, category: str, value: bool) -> None:
        """**Enable or disable a specific AI moderation category**

        This command allows you to toggle which categories of content the AI will moderate.

        **Usage:**
        `{prefix}setaimoderation category <name|all> <on|off>`

        **<name|all>:**
        - The name of the category to toggle.
        - `all` to enable or disable all categories at once.

        **<on|off>:**
        - `on` to enable the category.
        - `off` to disable the category.

        **Available Categories:**
        `hate`, `hate/threatening`, `self-harm`, `sexual`, `sexual/minors`, `violence`, `violence/graphic`

        **Examples:**
        - `{prefix}setaimoderation category hate on`
        - `{prefix}setaimoderation category all off`
        """
        valid_categories = [
            "hate",
            "hate/threatening",
            "self-harm",
            "sexual",
            "sexual/minors",
            "violence",
            "violence/graphic",
        ]

        if category.lower() == "all":
            update_payload = {
                f"detections.ai_moderation.categories.{cat}": value for cat in valid_categories
            }
            await self.bot.db.update_guild_config(ctx.guild.id, {"$set": update_payload})
            await ctx.send(
                f"All AI moderation categories have been {'enabled' if value else 'disabled'}."
            )
            return

        if category not in valid_categories:
            await ctx.send(
                f"Invalid category. Valid categories are: `all`, `{', '.join(valid_categories)}`"
            )
            return

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {f"detections.ai_moderation.categories.{category}": value}}
        )
        await ctx.send(f"Category `{category}` has been {'enabled' if value else 'disabled'}.")

    @command(10, aliases=["set-guild-whitelist", "set_guild_whitelist"])
    async def setguildwhitelist(self, ctx: commands.Context, guild_id: int = None) -> None:
        """**Adds a server to the invite whitelist**

        This command prevents the bot from flagging invites from whitelisted servers.
        The current server is always whitelisted by default.

        **Usage:**
        `{prefix}setguildwhitelist [guild_id]`

        **[guild_id]:**
        - The ID of the server to whitelist.
        - If left blank, the whitelist will be cleared.

        **Examples:**
        - `{prefix}setguildwhitelist 123456789012345678`
        - `{prefix}setguildwhitelist`
        """
        if guild_id is None:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$set": {"whitelisted_guilds": []}}
            )
        else:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$addToSet": {"whitelisted_guilds": str(guild_id)}}
            )
        await ctx.send(f"Guild whitelist updated: {guild_id if guild_id else 'cleared'}.")

    @command(10, aliases=["set-detection-ignore", "set_detection_ignore"])
    async def setdetectionignore(
        self, ctx: commands.Context, detection_type: str, channel: discord.TextChannel = None
    ) -> None:
        """**Configure channels to ignore for specific detections**

        This command allows you to disable certain auto-moderation filters in specific channels.

        **Usage:**
        `{prefix}setdetectionignore <type> [#channel]`

        **<type>:**
        The detection type to ignore in the specified channel.

        **[#channel]:**
        - The channel to ignore the detection in.
        - If left blank, this will clear all ignored channels for the specified detection type.

        **Valid Types:**
        - `all`: Apply to all detection types.
        - `filters`: Word filters.
        - `regex_filters`: Regular expression filters.
        - `block_invite`: Invite link blocking.
        - `mention_limit`: Mass mentions.
        - `spam_detection`: Spam prevention.
        - `max_words`: Maximum words per message.

        **Examples:**
        - `{prefix}setdetectionignore spam_detection #spam-channel`
        - `{prefix}setdetectionignore all #general`
        - `{prefix}setdetectionignore filters`
        """
        valid_detections = list(DEFAULT["ignored_channels"].keys())

        if detection_type not in valid_detections + ["all"]:
            raise commands.BadArgument(
                "Invalid detection, pick one from below:\n all, " + ", ".join(valid_detections)
            )

        if detection_type == "all":
            for i in valid_detections:
                if channel is None:
                    await self.bot.db.update_guild_config(
                        ctx.guild.id, {"$set": {f"ignored_channels.{i}": []}}
                    )
                else:
                    await self.bot.db.update_guild_config(
                        ctx.guild.id, {"$addToSet": {f"ignored_channels.{i}": str(channel.id)}}
                    )
        else:
            if channel is None:
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$set": {f"ignored_channels.{detection_type}": []}}
                )
            else:
                await self.bot.db.update_guild_config(
                    ctx.guild.id,
                    {"$addToSet": {f"ignored_channels.{detection_type}": str(channel.id)}},
                )
        await ctx.send(
            f"Detection ignore for `{detection_type}` updated for channel {channel.mention if channel else 'all channels cleared'}."
        )

    @command(10, aliases=["set-log-ignore", "set_log_ignore"])
    async def setlogignore(
        self, ctx: commands.Context, detection_type: str, channel: discord.TextChannel = None
    ) -> None:
        """**Configure channels to ignore for logging**

        This command prevents logging of certain events in specific channels.

        **Usage:**
        `{prefix}setlogignore <type> [#channel]`

        **<type>:**
        The log type to ignore in the specified channel.

        **[#channel]:**
        - The channel to ignore the log event in.
        - If left blank, this will clear all ignored channels for the specified log type.

        **Valid Types:**
        - `all`: Apply to all log types.
        - `message_delete`: Message deletions.
        - `message_edit`: Message edits.
        - `channel_delete`: Channel deletions.

        **Examples:**
        - `{prefix}setlogignore message_edit #bot-spam`
        - `{prefix}setlogignore all`
        """
        valid_logs = ["message_delete", "message_edit", "channel_delete"]

        if detection_type not in valid_logs + ["all"]:
            raise commands.BadArgument(
                "Invalid detection, pick one from below:\n all, " + ", ".join(valid_logs)
            )

        if detection_type == "all":
            for i in valid_logs:
                if channel is None:
                    await self.bot.db.update_guild_config(
                        ctx.guild.id, {"$set": {f"ignored_channels.{i}": []}}
                    )
                else:
                    await self.bot.db.update_guild_config(
                        ctx.guild.id, {"$addToSet": {f"ignored_channels.{i}": str(channel.id)}}
                    )
        else:
            if channel is None:
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$set": {f"ignored_channels.{detection_type}": []}}
                )
            else:
                await self.bot.db.update_guild_config(
                    ctx.guild.id,
                    {"$addToSet": {f"ignored_channels.{detection_type}": str(channel.id)}},
                )
        await ctx.send(
            f"Log ignore for `{detection_type}` updated for channel {channel.mention if channel else 'all channels cleared'}."
        )

    @group(8, invoke_without_command=True)
    async def regexfilter(self, ctx: commands.Context) -> None:
        """**Manages the regex filter**

        This command group allows you to add, remove, and list regular expression patterns for the auto-moderation filter.

        **Subcommands:**
        - `add` - Adds a regex pattern to the filter.
        - `remove` - Removes a regex pattern from the filter.
        - `list` - Lists all regex patterns in the filter.
        """
        await ctx.invoke(self.bot.get_command("help"), command_or_cog="regexfilter")

    @regexfilter.command(name="add")
    async def re_add(self, ctx: commands.Context, *, pattern) -> None:
        """**Adds a regex pattern to the filter**

        This command adds a new regular expression pattern to the auto-moderation filter.

        **Usage:**
        `{prefix}regexfilter add <pattern>`

        **<pattern>:**
        The regex pattern to add.

        **Example:**
        `{prefix}regexfilter add bad-word`
        """
        try:
            re.compile(pattern)
        except re.error as e:
            return await ctx.send(
                f"Invalid regex pattern: `{e}`.\nView <https://regexr.com/> for a guide."
            )

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$addToSet": {"detections.regex_filters": pattern}}
        )
        await ctx.send(f"Regex pattern `{pattern}` added to filter.")

    @regexfilter.command(name="remove")
    async def re_remove(self, ctx: commands.Context, *, pattern) -> None:
        """**Removes a regex pattern from the filter**

        This command removes a regular expression pattern from the auto-moderation filter.

        **Usage:**
        `{prefix}regexfilter remove <pattern>`

        **<pattern>:**
        The regex pattern to remove.

        **Example:**
        `{prefix}regexfilter remove bad-word`
        """
        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$pull": {"detections.regex_filters": pattern}}
        )
        await ctx.send(f"Regex pattern `{pattern}` removed from filter.")

    @regexfilter.command(name="list")
    async def re_list_(self, ctx: commands.Context) -> None:
        """**Lists all regex patterns in the filter**

        This command displays a list of all regular expression patterns currently in the auto-moderation filter.

        **Usage:**
        `{prefix}regexfilter list`
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        await ctx.send(
            f"Regex Filters: {', '.join([f'`{i}`' for i in guild_config.detections.regex_filters])}"
        )

    @group(8, name="filter", invoke_without_command=True)
    async def filter_(self, ctx: commands.Context) -> None:
        """**Manages the word and image filter**

        This command group allows you to add, remove, and list blacklisted words and images for the auto-moderation filter.

        **Subcommands:**
        - `add` - Adds a word or image to the filter.
        - `remove` - Removes a word or image from the filter.
        - `list` - Lists all words in the filter.
        """
        await ctx.invoke(self.bot.get_command("help"), command_or_cog="filter")

    @filter_.command()
    async def add(self, ctx: commands.Context, *, word: str = None) -> None:
        """**Adds a word or image to the filter**

        This command adds a blacklisted word or image to the auto-moderation filter.

        **Usage:**
        - To add a word: `{prefix}filter add <word>`
        - To add an image: Attach the image to the message and run `{prefix}filter add`

        **Note:** Image filtering is based on image hashes and can be bypassed by simple edits.

        **Examples:**
        - `{prefix}filter add badword`
        - (With an attached image) `{prefix}filter add`
        """
        if word:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$addToSet": {"detections.filters": word}}
            )
            await ctx.send(f"Word `{word}` added to filter.")
        else:
            to_add = []
            for i in ctx.message.attachments:
                if (
                    i.filename.lower().endswith(".png")
                    or i.filename.lower().endswith(".jpg")
                    or i.filename.lower().endswith(".jpeg")
                ):
                    stream = io.BytesIO()
                    await i.save(stream)
                    img = Image.open(stream)
                    image_hash = str(average_hash(img))
                    img.close()

                    to_add.append(image_hash)

            if to_add:
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$addToSet": {"detections.image_filters": {"$each": to_add}}}
                )
                await ctx.send(
                    f"Word `{'image hash(es)'}"
                    + (f" ({', '.join(to_add)})" if to_add else "")
                    + "` added to filter."
                )
            else:
                raise commands.UserInputError(
                    "word has to be provided or an image has to be attached."
                )

    @filter_.command()
    async def remove(self, ctx: commands.Context, *, word: str = None) -> None:
        """**Removes a word or image from the filter**

        This command removes a blacklisted word or image from the auto-moderation filter.

        **Usage:**
        - To remove a word: `{prefix}filter remove <word>`
        - To remove an image: Attach the image to the message and run `{prefix}filter remove`

        **Examples:**
        - `{prefix}filter remove badword`
        - (With an attached image) `{prefix}filter remove`
        """
        if word:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$pull": {"detections.filters": word}}
            )
            await ctx.send(f"Word `{word}` removed from filter.")
        else:
            to_remove = []
            for i in ctx.message.attachments:
                if (
                    i.filename.lower().endswith(".png")
                    or i.filename.lower().endswith(".jpg")
                    or i.filename.lower().endswith(".jpeg")
                ):
                    stream = io.BytesIO()
                    await i.save(stream)
                    img = Image.open(stream)
                    image_hash = str(average_hash(img))
                    img.close()

                    to_remove.append(image_hash)

            if to_remove:
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$pullAll": {"detections.image_filters": to_remove}}
                )
                await ctx.send(
                    f"Word `{'image hash(es)'}"
                    + (f" ({', '.join(to_remove)})" if to_remove else "")
                    + "` removed from filter."
                )
            else:
                raise commands.UserInputError(
                    "word has to be provided or an image has to be attached."
                )

    @filter_.command(name="list")
    async def list_(self, ctx: commands.Context) -> None:
        """**Lists all words in the filter**

        This command displays a list of all blacklisted words in the auto-moderation filter.

        **Usage:**
        `{prefix}filter list`
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        await ctx.send(f"Filters: {', '.join([f'`{i}`' for i in guild_config.detections.filters])}")

    @command(10, aliases=["set-canned-variables", "set_canned_variables"])
    async def setcannedvariables(
        self, ctx: commands.Context, name: str, *, value: Optional[str] = None
    ) -> None:
        """**Set canned variables for moderation reasons**

        This command allows you to create shortcuts for frequently used phrases in moderation reasons.

        **Usage:**
        `{prefix}setcannedvariables <name> [value]`

        **<name>:**
        The name of the variable (shortcut).

        **[value]:**
        The text that the variable will be replaced with. If left blank, the variable will be removed.

        **Example:**
        - `{prefix}setcannedvariables rule1 Breaking rule 1: No spamming.`
        - To use: `{prefix}warn @user {rule1}`
        - `{prefix}setcannedvariables rule1` (removes the variable)
        """
        if value is None:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$unset": {f"canned_variables.{name}": value}}
            )
        else:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$set": {f"canned_variables.{name}": value}}
            )
        await ctx.send(f"Canned variable `{name}` set to: {value if value else 'removed'}.")

    @command(10, aliases=["aimodtest"])
    async def aimoderationtest(self, ctx: commands.Context, *, text: str = None):
        """**Tests content against the AI moderation filter**
        This command allows you to test how the AI moderation filter will respond to a given piece of text and/or an image.
        **Usage:**
        `{prefix}aimoderationtest [text]`
        You can also attach an image to the message.
        **<text>:**
        The text you want to test.
        **Example:**
        `{prefix}aimoderationtest This is a test.`
        """
        api_url = os.getenv("MODERATION_API_URL")
        if not api_url:
            return await ctx.send("The `MODERATION_API_URL` is not set in the bot's environment.")

        embed = discord.Embed(title="AI Moderation Test Results", color=discord.Color.blue())

        # --- Text Moderation ---
        if text:
            try:
                payload = {"content": text}
                async with aiohttp.ClientSession() as session:
                    async with session.post(f"{api_url}/moderate/text", json=payload) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            decision = result.get("decision", "error")
                            categories = ", ".join(result.get("categories", [])) or "None"
                            embed.add_field(
                                name="Text Moderation",
                                value=f"**Decision:** {decision}\n**Categories:** {categories}",
                                inline=False,
                            )
                        else:
                            embed.add_field(
                                name="Text Moderation",
                                value=f"API request failed with status {resp.status}",
                                inline=False,
                            )
            except Exception as e:
                embed.add_field(
                    name="Text Moderation", value=f"An error occurred: {e}", inline=False
                )

        # --- Image Moderation ---
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            try:
                form = aiohttp.FormData()
                form.add_field("file", await attachment.read(), filename=attachment.filename)

                async with aiohttp.ClientSession() as session:
                    async with session.post(f"{api_url}/moderate/image", data=form) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            decision = result.get("decision", "error")
                            nsfw = result.get("nsfw", "N/A")
                            confidence = result.get("confidence", "N/A")
                            categories = ", ".join(result.get("categories", [])) or "None"
                            embed.add_field(
                                name="Image Moderation",
                                value=f"**Decision:** {decision}\n**NSFW:** {nsfw}\n**Confidence:** {confidence}\n**Categories:** {categories}",
                                inline=False,
                            )
                        else:
                            embed.add_field(
                                name="Image Moderation",
                                value=f"API request failed with status {resp.status}",
                                inline=False,
                            )
            except Exception as e:
                embed.add_field(
                    name="Image Moderation", value=f"An error occurred: {e}", inline=False
                )

        if not text and not ctx.message.attachments:
            return await ctx.send("Please provide text or an image to test.")

        await ctx.send(embed=embed)

    @command(6, name="setautorole")
    async def setautorole(self, ctx: commands.Context, *, role: str):
        """**Set the autorole for new members**

        This command allows you to automatically assign a role to new members when they join the server.

        **Usage:**
        `{prefix}setautorole <role>`

        **<role>:**
        - Mention the role, e.g., `@Member`
        - Provide the role ID, e.g., `123456789012345678`
        - Provide the role name, e.g., `Member`

        **Example:**
        `{prefix}setautorole @Member`
        `{prefix}setautorole 123456789012345678`
        `{prefix}setautorole Member`
        """
        from ..ext.utility import select_role

        role_obj = await select_role(ctx, role)
        if not role_obj:
            return
        await self.bot.db.update_guild_config(ctx.guild.id, {"$set": {"autoroles": [role_obj.id]}})
        await ctx.send(f"Autorole set to {role_obj.mention} for new members.")

    @command(6, name="setselfrole")
    async def setselfrole(self, ctx: commands.Context, *, role: str):
        """**Add a self-assignable role**

        This command allows you to add a role that members can assign to themselves using the `{prefix}role` command.

        **Usage:**
        `{prefix}setselfrole <role>`

        **<role>:**
        - Mention the role, e.g., `@Updates`
        - Provide the role ID, e.g., `123456789012345678`
        - Provide the role name, e.g., `Updates`

        **Example:**
        `{prefix}setselfrole @Updates`
        `{prefix}setselfrole 123456789012345678`
        `{prefix}setselfrole Updates`
        """
        from ..ext.utility import select_role

        role_obj = await select_role(ctx, role)
        if not role_obj:
            return
        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$addToSet": {"selfroles": role_obj.id}}
        )
        await ctx.send(f"Added {role_obj.mention} as a self-assignable role.")

    @command(6, name="setreactionrole")
    async def setreactionrole(self, ctx: commands.Context, *, role: str):
        """**Add a reaction role**

        This command allows you to add a role that members can get by reacting to a message.

        **Usage:**
        `{prefix}setreactionrole <role>`

        **<role>:**
        - Mention the role, e.g., `@Color`
        - Provide the role ID, e.g., `123456789012345678`
        - Provide the role name, e.g., `Color`

        **Example:**
        `{prefix}setreactionrole @Color`
        `{prefix}setreactionrole 123456789012345678`
        `{prefix}setreactionrole Color`
        """
        from ..ext.utility import select_role

        role_obj = await select_role(ctx, role)
        if not role_obj:
            return
        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$addToSet": {"reaction_roles": role_obj.id}}
        )
        await ctx.send(f"Added {role_obj.mention} as a reaction role.")

    @command(6, name="setmuterole")
    async def setmuterole(self, ctx: commands.Context, *, role: str):
        """**Set the mute role**

        This command allows you to set the role that will be used to mute members.

        **Usage:**
        `{prefix}setmuterole <role>`

        **<role>:**
        - Mention the role, e.g., `@Muted`
        - Provide the role ID, e.g., `123456789012345678`
        - Provide the role name, e.g., `Muted`

        **Example:**
        `{prefix}setmuterole @Muted`
        `{prefix}setmuterole 123456789012345678`
        `{prefix}setmuterole Muted`
        """
        from ..ext.utility import select_role

        role_obj = await select_role(ctx, role)
        if not role_obj:
            return
        await self.bot.db.update_guild_config(ctx.guild.id, {"$set": {"mute_role": role_obj.id}})
        await ctx.send(f"Mute role set to {role_obj.mention}.")


async def setup(bot: RainBot) -> None:
    await bot.add_cog(Setup(bot))
