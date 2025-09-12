import discord
from discord.ext import commands
from core.database import Database
from utils.decorators import require_permission, PermissionLevel
from utils.helpers import (
    create_embed,
    update_nested_config,
    remove_nested_config,
    status_embed,
)
from utils.paginator import Paginator
import asyncio


class Setup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.group(invoke_without_command=True)
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def setup(self, ctx):
        """
        Guides you through setting up the bot on your server.

        **Subcommands:**
        - `quick`: Run a quick setup wizard
        - `automod`: Configure auto-moderation options
        - `permissions`: Configure role permission levels (see `help setup permissions`)
        - `logging`: Configure logging channels (see `help setup logging`)
        - `viewconfig`: View current server configuration

        Use `!!help setup <subcommand>` for more details on each.
        """
        embed = create_embed(
            title="🛠️ Rainbot Setup",
            description="Choose a setup option:",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="📋 Quick Setup",
            value=f"`{ctx.prefix}setup quick` - Basic configuration",
            inline=False,
        )
        embed.add_field(
            name="🔧 Auto-moderation",
            value=f"`{ctx.prefix}setup automod` - Configure automod",
            inline=False,
        )
        embed.add_field(
            name="📝 Logging",
            value=f"`{ctx.prefix}setup logging` - Set up logging",
            inline=False,
        )
        embed.add_field(
            name="🔒 Permissions",
            value=f"`{ctx.prefix}setup permissions` - Configure perms",
            inline=False,
        )
        embed.add_field(
            name="👀 View Config",
            value=f"`{ctx.prefix}viewconfig` - Current settings",
            inline=False,
        )
        await ctx.send(embed=embed)

    @setup.command()
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def quick(self, ctx):
        """Runs a quick setup for the bot's essential features.

        **Usage:** `{prefix}setup quick`

        Configures the command prefix, mute role, and moderation log channel.
        """
        embed = create_embed(
            title="🚀 Quick Setup",
            description="Let's get started!",
            color=discord.Color.green(),
        )
        msg = await ctx.send(embed=embed)

        # Prefix setup
        embed.description = "What prefix would you like? (e.g., !, ?, >, r!)"
        await msg.edit(embed=embed)

        try:
            prefix_msg = await self.bot.wait_for(
                "message",
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                timeout=60,
            )
            prefix = prefix_msg.content.strip()
            await self.db.update_guild_config(ctx.guild.id, {"prefix": prefix})
        except asyncio.TimeoutError:
            from config.config import config

            prefix = config.bot.default_prefix

        # Mute role setup
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if not mute_role:
            mute_role = await ctx.guild.create_role(name="Muted", reason="Setup wizard")
            for channel in ctx.guild.channels:
                await channel.set_permissions(
                    mute_role, send_messages=False, speak=False
                )

        # Store under standardized key used across the bot
        await self.db.update_guild_config(ctx.guild.id, {"mute_role_id": mute_role.id})

        # Mod log channel (legacy key for older features)
        mod_log = await ctx.guild.create_text_channel("mod-logs", reason="Setup wizard")
        await self.db.update_guild_config(ctx.guild.id, {"mod_log_channel": mod_log.id})

        # Unified log_channels.moderation for the Logs cog
        await update_nested_config(
            self.db, ctx.guild.id, "log_channels", "moderation", mod_log.id
        )

        embed = create_embed(
            title="✅ Quick Setup Complete!",
            description=f"Prefix: `{prefix}`\nMute Role: {mute_role.mention}\nMod Logs: {mod_log.mention}",
            color=discord.Color.green(),
        )
        await msg.edit(embed=embed)

    @setup.command()
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def automod(self, ctx):
        # Load current automod settings
        config = await self.db.get_guild_config(ctx.guild.id)
        automod = config.get("automod", {})

        options = {
            "🔄": ("spam", "Spam Detection"),
            "🔗": ("invites", "Invite Links"),
            "🤬": ("badwords", "Bad Words"),
            "📢": ("mass_mentions", "Mass Mentions"),
            "🔊": ("caps", "Caps Lock"),
            "🖼️": ("nsfw", "NSFW Images"),
            "📝": ("duplicates", "Duplicate Messages"),
        }

        embed = create_embed(
            title="🛡️ Auto-moderation Setup", color=discord.Color.orange()
        )
        for emoji, (key, name) in options.items():
            status = "✅ Enabled" if automod.get(key, False) else "❌ Disabled"
            embed.add_field(name=f"{emoji} {name}", value=status, inline=True)

        embed.set_footer(text="React to toggle features")
        msg = await ctx.send(embed=embed)

        for emoji in options:
            await msg.add_reaction(emoji)

    @setup.group(name="permissions", invoke_without_command=True)
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def setup_permissions(self, ctx):
        """
        Configure role permission levels for your server.

        Use subcommands:
        - `set @Role <LEVEL>`: Set a role's permission level
        - `clear @Role`: Remove a role's permission level
        """
        config = await self.db.get_guild_config(ctx.guild.id)
        permission_roles = config.get("permission_roles", {})
        embed = create_embed(
            title="🔒 Permissions Setup",
            description=(
                "Assign permission levels to roles.\n\n"
                "Commands:\n"
                f"`{ctx.prefix}setup permissions set @Role <LEVEL>` — Set a role's level\n"
                f"`{ctx.prefix}setup permissions clear @Role` — Remove a role's level\n\n"
                "Levels: EVERYONE, TRUSTED, HELPER, MODERATOR, SENIOR_MODERATOR, ADMINISTRATOR, SENIOR_ADMINISTRATOR, SERVER_MANAGER"
            ),
            color=discord.Color.blue(),
        )
        if permission_roles:
            lines = []
            for role_id, lvl in permission_roles.items():
                role = ctx.guild.get_role(int(role_id))
                name = role.mention if role else f"Role {role_id}"
                try:
                    lvl_name = PermissionLevel(int(lvl)).name
                except Exception:
                    lvl_name = str(lvl)
                lines.append(f"• {name}: {lvl_name}")
            embed.add_field(
                name="Current Mappings", value="\n".join(lines)[:1024], inline=False
            )
        else:
            embed.add_field(name="Current Mappings", value="None", inline=False)
        await ctx.send(embed=embed)

    @setup_permissions.command(name="set")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def setup_permissions_set(self, ctx, role: discord.Role, level: str):
        level_upper = level.upper()
        if level_upper not in PermissionLevel.__members__:
            levels = ", ".join(PermissionLevel.__members__.keys())
            embed = status_embed(
                title="❌ Invalid Level",
                description=f"Valid levels: {levels}",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        permission_level = PermissionLevel[level_upper]
        if permission_level >= PermissionLevel.SERVER_OWNER:
            embed = status_embed(
                title="❌ Invalid Level",
                description="You cannot assign a permission level this high.",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        await update_nested_config(
            self.db,
            ctx.guild.id,
            "permission_roles",
            str(role.id),
            permission_level.value,
        )
        embed = status_embed(
            title="✅ Permission Set",
            description=f"The permission level for {role.mention} has been set to **{level_upper.title()}**.",
            status="success",
        )
        await ctx.send(embed=embed)

    @setup_permissions.command(name="clear")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def setup_permissions_clear(self, ctx, role: discord.Role):
        config = await self.db.get_guild_config(ctx.guild.id)
        permission_roles = config.get("permission_roles", {})
        if str(role.id) in permission_roles:
            await remove_nested_config(
                self.db, ctx.guild.id, "permission_roles", str(role.id)
            )
            embed = status_embed(
                title="✅ Permission Cleared",
                description=f"Removed permission level mapping for {role.mention}.",
                status="success",
            )
        else:
            embed = status_embed(
                title="ℹ️ Not Mapped",
                description=f"{role.mention} does not have a custom permission level set.",
                status="info",
            )
        await ctx.send(embed=embed)

    @setup.group(name="logging", invoke_without_command=True)
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def setup_logging(self, ctx):
        """
        Configure logging channels for different events.

        Use subcommands:
        - `mod [#channel]`: Set moderation log channel
        - `member [#channel]`: Set member log channel
        - `message [#channel]`: Set message edit/delete log channel
        """
        embed = create_embed(
            title="📝 Logging Setup",
            description="Set up logging channels for different events",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Commands",
            value=(
                f"`{ctx.prefix}setup logging mod [#channel]` - Moderation logs\n"
                f"`{ctx.prefix}setup logging member [#channel]` - Member logs\n"
                f"`{ctx.prefix}setup logging message [#channel]` - Message logs (edits & deletes)"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @setup_logging.command(name="mod")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def setup_logging_mod(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await update_nested_config(
            self.db, ctx.guild.id, "log_channels", "moderation", channel.id
        )
        embed = status_embed(
            title="✅ Moderation Log Set",
            description=f"Moderation logs will be sent to {channel.mention}",
            status="success",
        )
        await ctx.send(embed=embed)

    @setup_logging.command(name="member")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def setup_logging_member(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await update_nested_config(
            self.db, ctx.guild.id, "log_channels", "member", channel.id
        )
        embed = status_embed(
            title="✅ Member Log Set",
            description=f"Member logs will be sent to {channel.mention}",
            status="success",
        )
        await ctx.send(embed=embed)

    @setup_logging.command(name="message")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def setup_logging_message(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await update_nested_config(
            self.db, ctx.guild.id, "log_channels", "message_edit", channel.id
        )
        await update_nested_config(
            self.db, ctx.guild.id, "log_channels", "message_delete", channel.id
        )
        embed = status_embed(
            title="✅ Message Log Set",
            description=f"Message edit/delete logs will be sent to {channel.mention}",
            status="success",
        )
        await ctx.send(embed=embed)

    @setup.command(name="viewconfig")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def setup_viewconfig(self, ctx):
        """
        View the current server configuration and all changes made (paginated).
        """
        # Always show the current config as the first page
        config = await self.db.get_guild_config(ctx.guild.id)
        from config.config import config as bot_config

        embed = create_embed(title="⚙️ Server Configuration", color=discord.Color.blue())
        embed.add_field(
            name="Prefix",
            value=config.get("prefix", bot_config.bot.default_prefix),
            inline=True,
        )
        mute_role_id = config.get("mute_role_id") or config.get("mute_role")
        mute_role = ctx.guild.get_role(mute_role_id) if mute_role_id else None
        embed.add_field(
            name="Mute Role",
            value=mute_role.mention if mute_role else "Not set",
            inline=True,
        )
        log_channels = config.get("log_channels", {})
        mod_channel = (
            ctx.guild.get_channel(log_channels.get("moderation"))
            if log_channels.get("moderation")
            else None
        )
        if not mod_channel:
            legacy_mod = config.get("mod_log_channel")
            mod_channel = ctx.guild.get_channel(legacy_mod) if legacy_mod else None
        embed.add_field(
            name="Moderation Logs",
            value=mod_channel.mention if mod_channel else "Not set",
            inline=True,
        )
        member_channel = (
            ctx.guild.get_channel(log_channels.get("member"))
            if log_channels.get("member")
            else None
        )
        embed.add_field(
            name="Member Logs",
            value=member_channel.mention if member_channel else "Not set",
            inline=True,
        )
        msg_edit = (
            ctx.guild.get_channel(log_channels.get("message_edit"))
            if log_channels.get("message_edit")
            else None
        )
        msg_delete = (
            ctx.guild.get_channel(log_channels.get("message_delete"))
            if log_channels.get("message_delete")
            else None
        )
        if msg_edit and msg_delete and msg_edit.id == msg_delete.id:
            msg_value = msg_edit.mention
        elif msg_edit or msg_delete:
            parts = []
            if msg_edit:
                parts.append(f"Edits: {msg_edit.mention}")
            if msg_delete:
                parts.append(f"Deletes: {msg_delete.mention}")
            msg_value = ", ".join(parts)
        else:
            msg_value = "Not set"
        embed.add_field(name="Message Logs", value=msg_value, inline=True)

        pages = [embed]

        # Fetch config change history from the database (assumes a config_history collection exists)
        history_cursor = self.db.db.config_history.find(
            {"guild_id": ctx.guild.id}
        ).sort("timestamp", -1)
        history = await history_cursor.to_list(length=100)

        for entry in history:
            user = entry.get("changed_by", "Unknown")
            timestamp = entry.get("timestamp")
            if timestamp:
                from datetime import datetime

                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp)
                    except Exception:
                        pass
                elif hasattr(timestamp, "isoformat"):
                    timestamp = timestamp.isoformat()
            changes = entry.get("changes", {})
            if isinstance(changes, dict):
                changes_str = "\n".join(f"**{k}**: {v}" for k, v in changes.items())
            else:
                changes_str = str(changes)
            hist_embed = create_embed(
                title="⚙️ Config Change",
                description=f"**Changed by:** {user}\n**At:** {timestamp}",
                color=discord.Color.blue(),
            )
            hist_embed.add_field(
                name="Changes", value=changes_str or "No details", inline=False
            )
            pages.append(hist_embed)

        paginator = Paginator(ctx, pages, per_page=1)
        await paginator.start()


async def setup(bot):
    await bot.add_cog(Setup(bot))
