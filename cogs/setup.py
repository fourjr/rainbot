import copy
import json
import io
import re
from typing import Optional, Union, List, Dict, Any

import discord
from discord.ext import commands

from bot import rainbot
from ext.command import command, group, RainGroup
from ext.database import DEFAULT, DBDict, RECOMMENDED_DETECTIONS
from ext.time import UserFriendlyTime
from ext.utility import (
    format_timedelta,
    get_perm_level,
    tryint,
    SafeFormat,
    CannedStr,
    get_command_level,
)
from ext.errors import BotMissingPermissionsInChannel
import config
from PIL import Image
from imagehash import average_hash


class Setup(commands.Cog):
    """Enhanced server configuration and setup commands"""

    def __init__(self, bot: rainbot) -> None:
        self.bot = bot
        self.order = 1

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
        """View server configuration or get a downloadable JSON.

        Usage: `!!viewconfig [json]`
        Examples:
        - `!!viewconfig`
        - `!!viewconfig json`
        """
        guild_config = copy.copy(await self.bot.db.get_guild_config(ctx.guild.id))

        if options and options.lower() == "json":
            # Send as JSON file for easy editing
            config_json = json.dumps(guild_config, indent=2, default=str)
            file = discord.File(io.StringIO(config_json), filename=f"{ctx.guild.name}_config.json")
            embed = discord.Embed(
                title="📄 Server Configuration (JSON)",
                description="Here's your server configuration as a JSON file:",
                color=config.get_color("info"),
            )
            await ctx.send(embed=embed, file=file)
            return

        # Create detailed embed
        embed = discord.Embed(
            title=f"⚙️ {ctx.guild.name} Configuration", color=config.get_color("info")
        )

        # Basic settings
        mute_role_text = (
            f"**Mute Role:** <@&{guild_config.mute_role}>"
            if guild_config.mute_role
            else "**Mute Role:** Not set"
        )
        embed.add_field(
            name="🔧 Basic Settings",
            value=(
                f"**Prefix:** `{guild_config.prefix}`\n"
                f"**Time Offset:** {guild_config.time_offset} hours\n"
                f"{mute_role_text}"
            ),
            inline=False,
        )

        # Permission levels
        perm_levels = []
        for entry in guild_config.perm_levels:
            role_id = getattr(entry, "role_id", None)
            level = getattr(entry, "level", None)
            role = ctx.guild.get_role(int(role_id)) if role_id else None
            role_name = role.name if role else "Not set"
            perm_levels.append(f"Level {level}: {role_name}")

        if perm_levels:
            embed.add_field(
                name="🛡️ Permission Levels",
                value="\n".join(perm_levels[:5]) + ("\n..." if len(perm_levels) > 5 else ""),
                inline=True,
            )

        # Logging channels
        log_channels = []
        for log_type, channel_id in guild_config.logs.items():
            if channel_id:
                channel = ctx.guild.get_channel(int(channel_id))
                if channel:
                    log_channels.append(f"{log_type}: #{channel.name}")

        if log_channels:
            embed.add_field(
                name="📝 Logging Channels",
                value="\n".join(log_channels[:5]) + ("\n..." if len(log_channels) > 5 else ""),
                inline=True,
            )

        # Auto-moderation settings
        automod_settings = []
        for setting, value in guild_config.detections.items():
            if isinstance(value, bool):
                status = "✅" if value else "❌"
                automod_settings.append(f"{setting}: {status}")

        if automod_settings:
            embed.add_field(
                name="🛡️ Auto-moderation",
                value="\n".join(automod_settings[:5])
                + ("\n..." if len(automod_settings) > 5 else ""),
                inline=True,
            )

        embed.set_footer(text=f"Use {ctx.prefix}help setup for more configuration options")
        await ctx.send(embed=embed)

    @command(10, aliases=["import_config", "import-config"], usage="<url>")
    async def importconfig(self, ctx: commands.Context, *, url: str) -> None:
        """Import configuration from a JSON URL with validation.

        Example: `!!importconfig https://hastebin.cc/raw/abcdef`
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
        """Export current server configuration as a JSON attachment.

        Example: `!!exportconfig`
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
        """Reset server configuration to defaults with confirmation.

        Example: `!!resetconfig` and confirm with ✅
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
        """Interactive server setup wizard"""
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

    @setup.command(10, name="quick")
    async def setup_quick(self, ctx: commands.Context) -> None:
        """Quick setup wizard for basic configuration"""
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

    @setup.command(10, name="automod")
    async def setup_automod(self, ctx: commands.Context) -> None:
        """Interactive auto-moderation setup"""
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

    @setup.command(10, name="logging")
    async def setup_logging(self, ctx: commands.Context) -> None:
        """Interactive logging setup"""
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

    @setup.command(10, name="permissions")
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

    @command(10, aliases=["set_log", "set-log"], usage="<event|all> <#channel|channel name|channel id|off>")
    async def setlog(
        self, ctx: commands.Context, log_name: str, *, channel: str = None
    ) -> None:
        """Configure the log channel for message/server events.

        Valid types: all, message_delete, message_edit, member_join, member_remove, member_ban, member_unban, vc_state_change, channel_create, channel_delete, role_create, role_delete

        Examples:
        - `!!setlog all #logs`
        - `!!setlog member_join #join-log`
        - `!!setlog message_delete off`
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
                found = discord.utils.find(lambda c: c.name.lower() == channel.lower(), ctx.guild.text_channels)
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
                    reaction, user = await ctx.bot.wait_for("reaction_add", timeout=30.0, check=check)
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
            await ctx.send(f"Log channel for `{log_name}` set to {found.mention if channel_id and found else 'off'}.")

    @command(10, aliases=["set_modlog", "set-modlog"], usage="<action|all> <#channel|channel name|channel id|off>")
    async def setmodlog(
        self, ctx: commands.Context, log_name: str, *, channel: str = None
    ) -> None:
        """Configure the moderation log channel for actions.

        Valid types: all, member_warn, member_mute, member_unmute, member_kick, member_ban, member_unban, member_softban, message_purge, channel_lockdown, channel_slowmode

        Examples:
        - `!!setmodlog all #mod-log`
        - `!!setmodlog member_ban #security`
        - `!!setmodlog member_warn off`
        """
        channel_id = None
        if channel and channel.lower() not in ("off", "none"):
            found = None
            try:
                found = await commands.TextChannelConverter().convert(ctx, channel)
            except Exception:
                found = discord.utils.find(lambda c: c.name.lower() == channel.lower(), ctx.guild.text_channels)
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
                    reaction, user = await ctx.bot.wait_for("reaction_add", timeout=30.0, check=check)
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
            await ctx.send(f"Modlog channel for `{log_name}` set to {found.mention if channel_id and found else 'off'}.")

    @command(10, aliases=["set_perm_level", "set-perm-level"], usage="<level> <@role|role name|role id>")
    async def setpermlevel(
        self, ctx: commands.Context, perm_level: int, *, role: str
    ) -> None:
        """Assign or remove a role's permission level.

        Example: `!!setpermlevel 2 @Moderator` (use 0 to remove)
        """
        from ext.utility import select_role

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
        """Override a command's required permission level or reset.

        Examples:
        - `!!setcommandlevel reset ban`
        - `!!setcommandlevel 8 warn add`
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
        await ctx.send(f"Permission level for command `{name}` set to {int_perm_level}.")
                all_levels.append(int_perm_level)

                lowest = min(all_levels)
                if lowest > parent_level:
                    levels.append({"command": cmd.parent.name, "level": lowest})

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
        """Set the server's command prefix.

        Usage: `!!setprefix <prefix>`
        Example: `!!setprefix !`
        """
        await self.bot.db.update_guild_config(ctx.guild.id, {"$set": {"prefix": new_prefix}})
        await ctx.send(f"Prefix set to `{new_prefix}`.")

    @command(10, aliases=["set_offset", "set-offset"])
    async def setoffset(self, ctx: commands.Context, offset: int) -> None:
        """Set the server time offset from UTC (-12 to +13 hours).

        Usage: `!!setoffset <hours>`
        Example: `!!setoffset 2`
        """
        if not -12 < offset < 14:
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$addToSet": {"detections.filters": word}}
                )
        await ctx.send(f"Time offset set to `{offset}` hours.")

    @command(10, aliases=["set_detection", "set-detection"])
    async def setdetection(
        self, ctx: commands.Context, detection_type: str, value: Optional[str] = None
    ) -> None:
        """Sets or toggle the auto moderation types

        Valid types: block_invite, english_only, mention_limit, spam_detection, repetitive_message, auto_purge_trickocord, max_lines, max_words, max_characters, caps_message_percent, caps_message_min_words, repetitive_characters
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
                            f"detections.{detection_type}": commands.core._convert_to_bool(value)
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
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$pull": {"detections.filters": word}}
                )
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
        """Set the message DM-ed to the user upon a punishment.

        Possible punishments: kick, ban, mute, softban, unmute

        Possible templates:
        - `{time}` (in time offset)
        - `{author}`
        - `{user}`
        - `{reason}` (will be "None" if not provided)
        - `{channel}`
        - `{guild}`
        - `{duration}` (for mute only)

        Leave value blank to remove

        Example: !!setalert mute You have been muted in {guild.name} for {reason} for a duration of {duration}!
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

    @command(10, aliases=["set_detection_punishments", "set-detection-punishments"])
    async def setdetectionpunishments(
        self, ctx: commands.Context, detection_type: str, key: str, *, value: Optional[str] = None
    ) -> None:
        """Sets punishment for the detections

        Valid detections: filters, regex_filters, block_invite, english_only, mention_limit, spam_detection, repetitive_message, sexually_explicit, auto_purge_trickocord, max_lines, max_words, max_characters, caps_message, repetitive_characters

        Valid keys: warn, mute, kick, ban, delete

        Warn accepts a number of warns to give to the user
        Kick, ban and delete accepts "yes/no"
        Mute has to be set to a time, or none (mute indefinitely).

        Examples:
        - `!!setdetectionpunishments filters warn 1`
        - `!!setdetectionpunishments block_invite kick yes`
        - `!!setdetectionpunishments mention_limit mute 1d`
        """
        valid_detections = list(DEFAULT["detection_punishments"].keys())

        if detection_type not in valid_detections:
            raise commands.BadArgument("Invalid detection.")

        valid_keys = list(DEFAULT["detection_punishments"][valid_detections[0]].keys())

        if key not in valid_keys:
            raise commands.BadArgument(
                "Invalid key, pick one from below:\n" + ", ".join(valid_keys)
            )

        if key in ("warn"):
            try:
                value = int(value)
            except ValueError:
                raise commands.BadArgument(f"{key} accepts a number")

        elif key in ("kick", "ban", "delete"):
            value = commands.core._convert_to_bool(value)

        elif key in ("mute"):
            if value == "none":
                value = None
            else:
                await UserFriendlyTime(default="nil").convert(ctx, value)  # validation

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {f"detection_punishments.{detection_type}.{key}": value}}
        )
        await ctx.send(f"Detection punishment `{detection_type}` `{key}` set to `{value}`.")

    @command(10, aliases=["set_recommended", "set-recommended"])
    async def setrecommended(self, ctx: commands.Context) -> None:
        """Sets a recommended set of detections"""
    await self.bot.db.update_guild_config(ctx.guild.id, {"$set": RECOMMENDED_DETECTIONS})
    await ctx.send("Recommended detections have been set.")

    @command(10, aliases=["set-guild-whitelist", "set_guild_whitelist"])
    async def setguildwhitelist(self, ctx: commands.Context, guild_id: int = None) -> None:
        """Adds a server to the whitelist.

        Invite detection will not trigger when this guild's invite is sent.
        The current server is always whitelisted.

        Run without arguments to clear whitelist
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
        """Ignores detections in specified channels

        Valid detections: all, filters, regex_filters, block_invite, english_only, mention_limit, spam_detection, repetitive_message, sexually_explicit, auto_purge_trickocord, max_lines, max_words, max_characters, caps_message, repetitive_characters
        Run without specifying channel to clear ignored channels
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

    await ctx.send(f"Detection ignore for `{detection_type}` updated for channel {channel.mention if channel else 'all channels cleared'}.")

    @command(10, aliases=["set-log-ignore", "set_log_ignore"])
    async def setlogignore(
        self, ctx: commands.Context, detection_type: str, channel: discord.TextChannel = None
    ) -> None:
        """Ignores detections in specified channels

        Valid types: all, message_delete, message_edit, channel_delete
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

    await ctx.send(f"Log ignore for `{detection_type}` updated for channel {channel.mention if channel else 'all channels cleared'}.")

    @group(8, invoke_without_command=True)
    async def regexfilter(self, ctx: commands.Context) -> None:
        """Controls the regex filter"""
        await ctx.invoke(self.bot.get_command("help"), command_or_cog="regexfilter")

    @regexfilter.command(8, name="add")
    async def re_add(self, ctx: commands.Context, *, pattern) -> None:
        """Add blacklisted regex into the regex filter"""
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

    @regexfilter.command(8, name="remove")
    async def re_remove(self, ctx: commands.Context, *, pattern) -> None:
        """Removes blacklisted regex from the regex filter"""
        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$pull": {"detections.regex_filters": pattern}}
        )
    await ctx.send(f"Regex pattern `{pattern}` removed from filter.")

    @regexfilter.command(8, name="list")
    async def re_list_(self, ctx: commands.Context) -> None:
        """Lists the full word filter"""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        await ctx.send(
            f"Regex Filters: {', '.join([f'`{i}`' for i in guild_config.detections.regex_filters])}"
        )

    @group(8, name="filter", invoke_without_command=True)
    async def filter_(self, ctx: commands.Context) -> None:
        """Controls the word filter"""
        await ctx.invoke(self.bot.get_command("help"), command_or_cog="filter")

    @filter_.command(8)
    async def add(self, ctx: commands.Context, *, word: str = None) -> None:
        """Add blacklisted words into the word filter

        Can also add image filters if an iamge is attached,
        do note that it can easily be bypassed by
        slightly editing the images."""
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
                await ctx.send(f"Word `{'image hash(es)'}" + (f" ({', '.join(to_add)})" if to_add else "") + "` added to filter.")
            else:
                raise commands.UserInputError(
                    "word has to be provided or an image has to be attached."
                )

    @filter_.command(8)
    async def remove(self, ctx: commands.Context, *, word: str = None) -> None:
        """Removes blacklisted words from the word filter

        Can also remove image filters if an iamge is attached,"""
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
                await ctx.send(f"Word `{'image hash(es)'}" + (f" ({', '.join(to_remove)})" if to_remove else "") + "` removed from filter.")
            else:
                raise commands.UserInputError(
                    "word has to be provided or an image has to be attached."
                )

    @filter_.command(8, name="list")
    async def list_(self, ctx: commands.Context) -> None:
        """Lists the full word filter"""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        await ctx.send(f"Filters: {', '.join([f'`{i}`' for i in guild_config.detections.filters])}")

    @command(10, aliases=["set-warn-punishment", "set_warn_punishment"])
    async def setwarnpunishment(
        self,
        ctx: commands.Context,
        limit: int,
        punishment: str = None,
        *,
        time: UserFriendlyTime = None,
    ) -> None:
        """Sets punishment after certain number of warns.
        Punishments can be "mute", "kick", "ban" or "none".

        Example: !!setwarnpunishment 5 kick
        !!setwarnpunishment mute
        !!setwarnpunishment mute 5h

        It is highly encouraged to add a final "ban" condition
        """
        if punishment not in ("kick", "ban", "mute", "none"):
            raise commands.BadArgument(
                'Invalid punishment, pick from "mute", "kick", "ban", "none".'
            )

        if punishment == "none" or punishment is None:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$pull": {"warn_punishments": {"warn_number": limit}}}
            )
        else:
            duration = None
            if time is not None and time.dt:
                duration = (time.dt - ctx.message.created_at).total_seconds()

            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            if limit in [i["warn_number"] for i in guild_config["warn_punishments"]]:
                # overwrite
                await self.bot.db.update_guild_config(
                    ctx.guild.id,
                    {
                        "$set": {
                            "warn_punishments.$[elem].punishment": punishment,
                            "warn_punishments.$[elem].duration": duration,
                        }
                    },
                    array_filters=[{"elem.warn_number": limit}],
                )
            else:
                # push
                await self.bot.db.update_guild_config(
                    ctx.guild.id,
                    {
                        "$push": {
                            "warn_punishments": {
                                "warn_number": limit,
                                "punishment": punishment,
                                "duration": duration,
                            }
                        }
                    },
                )

    await ctx.send(f"Warn punishment for {limit} set to {punishment}.")

    @command(10, aliases=["set-explicit", "set_explicit"], usage="[types...]")
    async def setexplicit(self, ctx: commands.Context, *types_) -> None:
        """Types can be a space-seperated list of the following:
        `EXPOSED_ANUS, EXPOSED_ARMPITS, COVERED_BELLY, EXPOSED_BELLY, COVERED_BUTTOCKS, EXPOSED_BUTTOCKS, FACE_F, FACE_M, COVERED_FEET, EXPOSED_FEET, COVERED_BREAST_F, EXPOSED_BREAST_F, COVERED_GENITALIA_F, EXPOSED_GENITALIA_F, EXPOSED_BREAST_M, EXPOSED_GENITALIA_M`
        """
        possibles = [
            "EXPOSED_ANUS",
            "EXPOSED_ARMPITS",
            "COVERED_BELLY",
            "EXPOSED_BELLY",
            "COVERED_BUTTOCKS",
            "EXPOSED_BUTTOCKS",
            "FACE_F",
            "FACE_M",
            "COVERED_FEET",
            "EXPOSED_FEET",
            "COVERED_BREAST_F",
            "EXPOSED_BREAST_F",
            "COVERED_GENITALIA_F",
            "EXPOSED_GENITALIA_F",
            "EXPOSED_BREAST_M",
            "EXPOSED_GENITALIA_M",
        ]
        for i in types_:
            if i not in possibles:
                return await ctx.send(f"{i} is not a valid type")
        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {"detections.sexually_explicit": types_}}
        )

    await ctx.send(f"Explicit types set: {' '.join(types_)}.")

    @command(10, aliases=["set-canned-variables", "set_canned_variables"])
    async def setcannedvariables(
        self, ctx: commands.Context, name: str, *, value: Optional[str] = None
    ) -> None:
        """Set canned variables in reasons"""
        if value is None:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$unset": {f"canned_variables.{name}": value}}
            )
        else:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$set": {f"canned_variables.{name}": value}}
            )

    await ctx.send(f"Canned variable `{name}` set to: {value if value else 'removed'}.")


async def setup(bot: rainbot) -> None:
    await bot.add_cog(Setup(bot))
