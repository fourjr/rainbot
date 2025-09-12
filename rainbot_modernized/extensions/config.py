"""
Configuration extension for RainBot
"""

import json
import aiohttp
import asyncio
import discord
from discord.ext import commands

from core.bot import RainBot
from core.permissions import PermissionLevel
from utils.decorators import require_permission
from utils.helpers import create_embed, confirm_action, safe_send, status_embed
from utils.constants import EMOJIS


class Config(commands.Cog):
    """
    ⚙️ **Configuration Commands**

    Commands for managing the bot's configuration on this server.
    """

    def __init__(self, bot: RainBot):
        self.bot = bot

    @commands.command(name="importconfig")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def import_config(self, ctx: commands.Context, url: str):
        """
        **Import configuration from a JSON URL**

        **Usage:**
        `!!importconfig <url>`
        **Note:** This will overwrite all existing settings.
        """
        confirmed = await confirm_action(
            ctx,
            "Are you sure you want to import a new configuration?",
            "This will overwrite all existing server settings.",
        )
        if not confirmed:
            await safe_send(ctx, "Configuration import cancelled.")
            return

        try:
            async with self.bot.session.get(url) as resp:
                if resp.status != 200:
                    embed = status_embed(
                        title=f"{EMOJIS['error']} Download Failed",
                        description=f"Could not fetch the configuration file. Status: {resp.status}",
                        status="error",
                    )
                    await safe_send(ctx, embed=embed)
                    return

                config_data = await resp.json(content_type=None)

        except (aiohttp.ClientError, json.JSONDecodeError, asyncio.TimeoutError) as e:
            embed = status_embed(
                title=f"{EMOJIS['error']} Import Failed",
                description=f"Failed to download or parse the configuration file.\n`{e}`",
                status="error",
            )
            await safe_send(ctx, embed=embed)
            return

        if not isinstance(config_data, dict):
            embed = status_embed(
                title=f"{EMOJIS['error']} Invalid Format",
                description="The configuration file is not in the correct format (must be a JSON object).",
                status="error",
            )
            await safe_send(ctx, embed=embed)
            return

        config_data.pop("guild_id", None)
        config_data.pop("_id", None)

        await self.bot.db.delete_guild_config(ctx.guild.id)

        for key, value in config_data.items():
            await self.bot.db.update_guild_config(ctx.guild.id, {key: value})

        self.bot._prefix_cache.pop(ctx.guild.id, None)

        embed = status_embed(
            title="✅ Configuration Imported",
            description="The new configuration has been successfully imported and applied.",
            status="success",
        )
        await safe_send(ctx, embed=embed)

    @commands.command(name="resetconfig")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def reset_config(self, ctx: commands.Context):
        """
        **Reset server configuration to defaults**

        **Usage:**
        `!!resetconfig`
        """
        confirmed = await confirm_action(
            ctx,
            "Are you sure you want to reset the entire server configuration?",
            "This is irreversible and will reset all settings to their defaults.",
        )

        if not confirmed:
            await safe_send(ctx, "Configuration reset cancelled.")
            return

        await self.bot.db.delete_guild_config(ctx.guild.id)
        self.bot._prefix_cache.pop(ctx.guild.id, None)

        embed = status_embed(
            title="✅ Configuration Reset",
            description="All server settings have been reset to their defaults.",
            status="success",
        )
        await safe_send(ctx, embed=embed)

    @commands.command(name="setcommandlevel")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def set_command_level(
        self, ctx: commands.Context, command_name: str, level: str
    ):
        """
        **Changes a command's required permission level**

        **Usage:**
        `!!setcommandlevel <command> <level>`
        **Example:** `!!setcommandlevel ban SENIOR_MODERATOR`
        """
        command = self.bot.get_command(command_name.lower())
        if not command:
            embed = status_embed(
                title=f"{EMOJIS['error']} Command Not Found",
                description=f"No command named `{command_name}` was found.",
                status="error",
            )
            await safe_send(ctx, embed=embed)
            return

        level_upper = level.upper()
        if level_upper not in PermissionLevel.__members__:
            levels = ", ".join(PermissionLevel.__members__.keys())
            embed = status_embed(
                title=f"{EMOJIS['error']} Invalid Level",
                description=f"Valid levels are: {levels}",
                status="error",
            )
            await safe_send(ctx, embed=embed)
            return

        permission_level = PermissionLevel[level_upper]
        if permission_level >= PermissionLevel.SERVER_OWNER:
            embed = status_embed(
                title=f"{EMOJIS['error']} Invalid Level",
                description="You cannot set a permission level this high.",
                status="error",
            )
            await safe_send(ctx, embed=embed)
            return

        await self.bot.db.update_guild_config(
            ctx.guild.id,
            {f"command_levels.{command.qualified_name}": permission_level.value},
        )

        embed = status_embed(
            title="✅ Command Permission Updated",
            description=f"The required permission level for `{command.qualified_name}` is now **{level_upper.title()}**.",
            status="success",
        )
        await safe_send(ctx, embed=embed)

    @commands.command(name="setoffset")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def set_offset(self, ctx: commands.Context, offset: str):
        """
        **Sets the time offset from UTC**

        **Usage:**
        `!!setoffset <offset>`
        **Example:** `!!setoffset -5`
        """
        try:
            offset_val = int(offset)
            if not (-12 <= offset_val <= 14):
                raise ValueError("Offset out of range.")
        except ValueError:
            embed = status_embed(
                title=f"{EMOJIS['error']} Invalid Offset",
                description="Please provide a valid UTC offset (an integer between -12 and +14).",
                status="error",
            )
            await safe_send(ctx, embed=embed)
            return

        await self.bot.db.update_guild_config(ctx.guild.id, {"time_offset": offset_val})

        embed = status_embed(
            title="✅ Time Offset Set",
            description=f"The time offset for this server has been set to **UTC{offset_val:+}**.",
            status="success",
        )
        await safe_send(ctx, embed=embed)

    @commands.command(name="setalert")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def set_alert(self, ctx: commands.Context, *, message: str):
        """
        **Set the message DM-ed to the user upon a punishment**

        **Usage:**
        `!!setalert <message>`

        **Placeholders:**
        • `{user}` - User mention
        • `{guild}` - Server name
        • `{action}` - The moderation action (e.g., banned, muted)
        • `{reason}` - The reason for the action
        • `{duration}` - The duration of the punishment (if applicable)
        """
        await self.bot.db.update_guild_config(
            ctx.guild.id, {"punishment_alert": message}
        )

        embed = status_embed(
            title="✅ Punishment Alert Set",
            description="The custom punishment alert message has been updated.",
            status="success",
        )
        await safe_send(ctx, embed=embed)

    @commands.command(name="exportconfig")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def export_config(self, ctx: commands.Context):
        """
        **Export the server's configuration to a JSON file**

        **Usage:**
        `!!exportconfig`
        """
        async with ctx.typing():
            config_data = await self.bot.db.get_guild_config(ctx.guild.id)

            # Remove sensitive or unnecessary fields
            config_data.pop("_id", None)
            config_data.pop("guild_id", None)

            try:
                import io
                import json
                from datetime import datetime

                def json_serial(obj):
                    """JSON serializer for objects not serializable by default json code"""
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    raise TypeError(
                        f"Object of type {type(obj).__name__} is not JSON serializable"
                    )

                json_data = json.dumps(config_data, indent=4, default=json_serial)
                file_data = io.BytesIO(json_data.encode("utf-8"))

                file = discord.File(
                    file_data, filename=f"rainbot_config_{ctx.guild.id}.json"
                )

                embed = create_embed(
                    title="📄 Configuration Exported",
                    description="Here is the configuration file for this server. You can use this file to back up your settings or import them on another server.",
                    color="success",
                )
                await safe_send(ctx, embed=embed)
                await safe_send(ctx, file=file)
            except Exception as e:
                embed = status_embed(
                    title=f"{EMOJIS['error']} Export Failed",
                    description=f"An unexpected error occurred while exporting the configuration: `{e}`",
                    status="error",
                )
        await safe_send(ctx, embed=embed)

    @commands.command(name="setannouncement")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def set_announcement_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ):
        """
        **Sets the channel for bot announcements**

        **Usage:**
        `!!setannouncement <#channel>` or `!!setannouncement` to disable.
        """
        if channel:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"announcement_channel": channel.id}
            )
            embed = status_embed(
                title="✅ Announcement Channel Set",
                description=f"Bot announcements will now be sent to {channel.mention}.",
                status="success",
            )
        else:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"announcement_channel": None}
            )
            embed = status_embed(
                title="✅ Announcement Channel Disabled",
                description="Bot announcements have been disabled for this server.",
                status="success",
            )

        await safe_send(ctx, embed=embed)


async def setup(bot: RainBot):
    """Load the Config extension"""
    await bot.add_cog(Config(bot))
