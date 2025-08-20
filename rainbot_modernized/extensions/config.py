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
from utils.helpers import create_embed, confirm_action, safe_send
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
            await safe_send(ctx, "Configuration import cancelled.", ephemeral=True)
            return

        try:
            async with self.bot.session.get(url) as resp:
                if resp.status != 200:
                    embed = create_embed(
                        title=f"{EMOJIS['error']} Download Failed",
                        description=f"Could not fetch the configuration file. Status: {resp.status}",
                        color="error",
                    )
                    await safe_send(ctx, embed=embed)
                    return
                
                config_data = await resp.json(content_type=None)

        except (aiohttp.ClientError, json.JSONDecodeError, asyncio.TimeoutError) as e:
            embed = create_embed(
                title=f"{EMOJIS['error']} Import Failed",
                description=f"Failed to download or parse the configuration file.\n`{e}`",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        if not isinstance(config_data, dict):
            embed = create_embed(
                title=f"{EMOJIS['error']} Invalid Format",
                description="The configuration file is not in the correct format (must be a JSON object).",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        config_data.pop("guild_id", None)
        config_data.pop("_id", None)

        await self.bot.db.delete_guild_config(ctx.guild.id)
        
        for key, value in config_data.items():
            await self.bot.db.update_guild_config(ctx.guild.id, {key: value})
        
        self.bot._prefix_cache.pop(ctx.guild.id, None)

        embed = create_embed(
            title="✅ Configuration Imported",
            description="The new configuration has been successfully imported and applied.",
            color="success",
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
            await safe_send(ctx, "Configuration reset cancelled.", ephemeral=True)
            return

        await self.bot.db.delete_guild_config(ctx.guild.id)
        self.bot._prefix_cache.pop(ctx.guild.id, None)

        embed = create_embed(
            title="✅ Configuration Reset",
            description="All server settings have been reset to their defaults.",
            color="success",
        )
        await safe_send(ctx, embed=embed)

    @commands.command(name="setcommandlevel")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def set_command_level(self, ctx: commands.Context, command_name: str, level: str):
        """
        **Changes a command's required permission level**

        **Usage:**
        `!!setcommandlevel <command> <level>`
        **Example:** `!!setcommandlevel ban SENIOR_MODERATOR`
        """
        command = self.bot.get_command(command_name.lower())
        if not command:
            embed = create_embed(
                title=f"{EMOJIS['error']} Command Not Found",
                description=f"No command named `{command_name}` was found.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        level_upper = level.upper()
        if level_upper not in PermissionLevel.__members__:
            levels = ", ".join(PermissionLevel.__members__.keys())
            embed = create_embed(
                title=f"{EMOJIS['error']} Invalid Level",
                description=f"Valid levels are: {levels}",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        permission_level = PermissionLevel[level_upper]
        if permission_level >= PermissionLevel.SERVER_OWNER:
            embed = create_embed(
                title=f"{EMOJIS['error']} Invalid Level",
                description="You cannot set a permission level this high.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return
        
        await self.bot.db.update_guild_config(
            ctx.guild.id, {f"command_levels.{command.qualified_name}": permission_level.value}
        )

        embed = create_embed(
            title="✅ Command Permission Updated",
            description=f"The required permission level for `{command.qualified_name}` is now **{level_upper.title()}**.",
            color="success",
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
            embed = create_embed(
                title=f"{EMOJIS['error']} Invalid Offset",
                description="Please provide a valid UTC offset (an integer between -12 and +14).",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"time_offset": offset_val}
        )

        embed = create_embed(
            title="✅ Time Offset Set",
            description=f"The time offset for this server has been set to **UTC{offset_val:+}**.",
            color="success",
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

        embed = create_embed(
            title="✅ Punishment Alert Set",
            description="The custom punishment alert message has been updated.",
            color="success",
        )
        await safe_send(ctx, embed=embed)


async def setup(bot: RainBot):
    """Load the Config extension"""
    await bot.add_cog(Config(bot))
