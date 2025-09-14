"""
Modern moderation extension with enhanced features and user experience
"""

import asyncio
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Union

import discord
from discord.ext import commands

from utils.constants import COLORS, EMOJIS
from core.permissions import PermissionLevel
from utils.decorators import require_permission
from utils.converters import MemberOrUser, MemberOrID, Duration
from utils.helpers import (
    create_embed,
    safe_send,
    format_duration,
    confirm_action,
    parse_time,
)
from utils.paginator import Paginator
from utils.constants import EMOJIS
from core.logging import ModLogger


class Moderation(commands.Cog):
    """
    🛡️ **Moderation Commands**

    Comprehensive moderation tools for server management including warnings,
    mutes, kicks, bans, and advanced punishment systems.
    """

    def __init__(self, bot):
        self.bot = bot
        self.logger = ModLogger()

    # --- Internal helpers for modlog case handling ---
    def _normalize_case_id(self, guild_id: int, case: Union[int, str]) -> str:
        """Return the full case_id string in format '<guild_id>-<n>'.

        Accepts either a numeric case number (42) or a full case id string
        ('<guild_id>-42'). If a numeric string like '42' is provided, it will
        be normalized to '<guild_id>-42'. If a full id is provided, it's
        returned as-is.
        """
        # Numeric (int) or numeric string -> compose full id
        if isinstance(case, int) or (isinstance(case, str) and case.isdigit()):
            return f"{guild_id}-{int(case)}"

        # Already a string; if it looks like a full id, return as-is
        if isinstance(case, str) and "-" in case:
            return case

        # Fallback: stringify
        return str(case)

    def _format_case_embed(self, ctx: commands.Context, log: dict) -> discord.Embed:
        """Create a rich embed for a single moderation log case."""
        user = self.bot.get_user(log.get("user_id"))
        moderator = self.bot.get_user(log.get("moderator_id"))

        user_display = user.mention if user else f"<@{log.get('user_id')}>"
        mod_display = (
            moderator.mention if moderator else f"<@{log.get('moderator_id')}>"
        )

        # Timestamp handling
        ts = log.get("timestamp")
        ts_unix = int(ts.timestamp()) if isinstance(ts, datetime) else None

        embed = create_embed(
            title=f"🗂️ Case {str(log.get('case_id')).split('-')[-1]}",
            color="info",
        )

        embed.add_field(name="Case ID", value=str(log.get("case_id")), inline=False)
        embed.add_field(
            name="Action",
            value=str(log.get("action", "")).title() or "Unknown",
            inline=True,
        )
        embed.add_field(
            name="Active",
            value="Yes" if log.get("active", False) else "No",
            inline=True,
        )

        if ts_unix:
            embed.add_field(name="When", value=f"<t:{ts_unix}:F>", inline=True)

        embed.add_field(name="User", value=user_display, inline=False)
        embed.add_field(name="Moderator", value=mod_display, inline=False)

        reason = log.get("reason") or "No reason provided"
        embed.add_field(name="Reason", value=reason, inline=False)

        duration = log.get("duration")
        if duration:
            try:
                embed.add_field(
                    name="Duration",
                    value=format_duration(timedelta(seconds=int(duration))),
                    inline=True,
                )
            except Exception:
                embed.add_field(
                    name="Duration", value=f"{duration} seconds", inline=True
                )

        if not log.get("active") and log.get("completed_at"):
            comp = log["completed_at"]
            comp_unix = int(comp.timestamp()) if isinstance(comp, datetime) else None
            if comp_unix:
                embed.add_field(
                    name="Completed", value=f"<t:{comp_unix}:F>", inline=True
                )

        return embed

    @commands.command(name="setprefix")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def set_prefix(self, ctx: commands.Context, *, prefix: str):
        """Sets the bot's command prefix for this server.

        **Usage:** `{prefix}setprefix <new_prefix>`
        **Example:** `{prefix}setprefix !`

        Changes the prefix used to invoke bot commands on this server.
        """
        if len(prefix) > 5:
            embed = create_embed(
                title="❌ Prefix Too Long",
                description="Prefix cannot be longer than 5 characters.",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        await self.bot.db.update_guild_config(ctx.guild.id, {"prefix": prefix})
        self.bot._prefix_cache[ctx.guild.id] = prefix  # Update cache

        embed = create_embed(
            title="✅ Prefix Updated",
            description=f"My prefix on this server is now `{prefix}`",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="setmuterole")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def set_mute_role(self, ctx: commands.Context, role: discord.Role):
        """Sets an existing role as the mute role for this server.

        **Usage:** `{prefix}setmuterole <role>`
        **Example:** `{prefix}setmuterole @Muted`

        The bot will attempt to configure permissions for this role automatically.
        """
        if role >= ctx.guild.me.top_role:
            embed = create_embed(
                title=f"{EMOJIS['error']} Permission Error",
                description=f"I cannot manage the role '{role.name}'. Please make sure my role is higher than the mute role in the role hierarchy.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        await self.bot.db.update_guild_config(ctx.guild.id, {"mute_role_id": role.id})

        failed_channels = 0
        async with ctx.typing():
            for channel in ctx.guild.channels:
                try:
                    if isinstance(channel, discord.TextChannel):
                        await channel.set_permissions(
                            role,
                            send_messages=False,
                            add_reactions=False,
                            send_messages_in_threads=False,
                            create_public_threads=False,
                            create_private_threads=False,
                        )
                    elif isinstance(channel, discord.VoiceChannel):
                        await channel.set_permissions(
                            role,
                            speak=False,
                            stream=False,
                        )
                except discord.Forbidden:
                    failed_channels += 1
                except discord.HTTPException:
                    failed_channels += 1

        description = f"The mute role has been set to {role.mention}."
        if failed_channels > 0:
            description += f"\\n\\n{EMOJIS['warning']} I failed to configure permissions for this role in {failed_channels} channels. Please check my permissions."

        embed = create_embed(
            title="✅ Mute Role Set",
            description=description,
            color="success",
        )
        await safe_send(ctx, embed=embed)

    @commands.command(name="warn")
    @require_permission(PermissionLevel.MODERATOR)
    async def warn_user(
        self,
        ctx: commands.Context,
        user: MemberOrUser,
        *,
        reason: str = "No reason provided",
    ):
        """Issues a formal warning to a user.

        **Usage:** `{prefix}warn <user> [reason]`
        **Examples:**
        - `{prefix}warn @user Spamming in chat`
        - `{prefix}warn 123456789 Breaking server rules`

        Warnings are logged and can trigger automatic punishments.
        """
        # Check if user can be moderated
        if isinstance(user, discord.Member):
            if not await self._can_moderate(ctx, user):
                return

        # Add warning to database
        case_id = await self.bot.db.add_moderation_log(
            guild_id=ctx.guild.id,
            user_id=user.id,
            moderator_id=ctx.author.id,
            action="warn",
            reason=reason,
        )

        # Send DM to user
        await self._notify_user(user, "warned", reason, ctx.guild)

        # Create response embed
        embed = create_embed(
            title=f"{EMOJIS['warn']} User Warned",
            description=f"**User:** {user.mention if hasattr(user, 'mention') else user}\n"
            f"**Reason:** {reason}\n"
            f"**Case ID:** {case_id}",
            color="warning",
            timestamp=True,
        )

        await safe_send(ctx, embed=embed)

        # Log the action
        self.logger.moderation_action(
            "warn", user.id, ctx.author.id, ctx.guild.id, reason
        )

        # Check for automatic punishments
        await self._check_auto_punishment(ctx, user, "warn")

    @commands.command(name="mute")
    @require_permission(PermissionLevel.HELPER)
    async def mute_user(
        self,
        ctx: commands.Context,
        user: MemberOrUser,
        duration: Optional[Duration] = None,
        *,
        reason: str = "No reason provided",
    ):
        """Mutes a user, preventing them from speaking or sending messages.

        **Usage:** `{prefix}mute <user> [duration] [reason]`
        **Examples:**
        - `{prefix}mute @user 1h Spamming`
        - `{prefix}mute @user 30m Excessive caps`
        - `{prefix}mute @user Inappropriate behavior` (permanent)

        Duration formats: `30s`, `5m`, `2h`, `1d`, `1w`.
        """
        # Ensure user is a member if they're in the server
        if isinstance(user, discord.Member):
            member = user
            if not await self._can_moderate(ctx, member):
                return
        else:
            member = ctx.guild.get_member(user.id)
            if not member:
                embed = create_embed(
                    title=f"{EMOJIS['error']} User Not Found",
                    description="User is not in this server and cannot be muted.",
                    color="error",
                )
                await safe_send(ctx, embed=embed)
                return

        # Get or create mute role
        mute_role = await self._get_mute_role(ctx.guild)
        if not mute_role:
            embed = create_embed(
                title=f"{EMOJIS['error']} Mute Role Error",
                description="Could not create or find mute role. Please check my permissions.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        # Apply mute role
        try:
            await member.add_roles(mute_role, reason=f"Muted by {ctx.author}: {reason}")
        except discord.Forbidden:
            embed = create_embed(
                title=f"{EMOJIS['error']} Permission Error",
                description="I don't have permission to manage this user's roles.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        # Calculate end time
        end_time = None
        if duration:
            end_time = datetime.now(timezone.utc) + duration

        # Add to database
        case_id = await self.bot.db.add_moderation_log(
            guild_id=ctx.guild.id,
            user_id=member.id,
            moderator_id=ctx.author.id,
            action="mute",
            reason=reason,
            duration=int(duration.total_seconds()) if duration else None,
        )

        # Schedule unmute if temporary
        if duration:
            asyncio.create_task(
                self._schedule_unmute(ctx.guild.id, member.id, duration)
            )

        # Send DM to user
        duration_text = (
            f" for {format_duration(duration)}" if duration else " indefinitely"
        )
        await self._notify_user(member, f"muted{duration_text}", reason, ctx.guild)

        # Create response embed
        duration_display = format_duration(duration) if duration else "Permanent"
        embed = create_embed(
            title=f"{EMOJIS['mute']} User Muted",
            description=f"**User:** {member.mention}\n"
            f"**Duration:** {duration_display}\n"
            f"**Reason:** {reason}\n"
            f"**Case ID:** {case_id}",
            color="warning",
            timestamp=True,
        )

        if end_time:
            embed.add_field(
                name="Expires", value=f"<t:{int(end_time.timestamp())}:F>", inline=False
            )

        await safe_send(ctx, embed=embed)

        # Log the action
        self.logger.moderation_action(
            "mute", member.id, ctx.author.id, ctx.guild.id, reason
        )

    @commands.command(name="unmute")
    @require_permission(PermissionLevel.HELPER)
    async def unmute_user(
        self,
        ctx: commands.Context,
        user: MemberOrUser,
        *,
        reason: str = "No reason provided",
    ):
        """Unmutes a user, allowing them to speak and send messages again.

        **Usage:** `{prefix}unmute <user> [reason]`
        **Examples:**
        - `{prefix}unmute @user Appeal accepted`
        - `{prefix}unmute 123456789 Time served`
        """
        # Get member object
        if isinstance(user, discord.Member):
            member = user
        else:
            member = ctx.guild.get_member(user.id)
            if not member:
                embed = create_embed(
                    title=f"{EMOJIS['error']} User Not Found",
                    description="User is not in this server.",
                    color="error",
                )
                await safe_send(ctx, embed=embed)
                return

        # Get mute role
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        mute_role_id = guild_config.get("mute_role_id")

        if not mute_role_id:
            embed = create_embed(
                title=f"{EMOJIS['error']} No Mute Role",
                description="No mute role is configured for this server.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        mute_role = ctx.guild.get_role(mute_role_id)
        if not mute_role:
            embed = create_embed(
                title=f"{EMOJIS['error']} Mute Role Not Found",
                description="The configured mute role no longer exists.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        # Check if user is muted
        if mute_role not in member.roles:
            embed = create_embed(
                title=f"{EMOJIS['error']} User Not Muted",
                description="This user is not currently muted.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        # Remove mute role
        try:
            await member.remove_roles(
                mute_role, reason=f"Unmuted by {ctx.author}: {reason}"
            )
        except discord.Forbidden:
            embed = create_embed(
                title=f"{EMOJIS['error']} Permission Error",
                description="I don't have permission to manage this user's roles.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        # Add to database
        case_id = await self.bot.db.add_moderation_log(
            guild_id=ctx.guild.id,
            user_id=member.id,
            moderator_id=ctx.author.id,
            action="unmute",
            reason=reason,
        )

        # Deactivate active mute punishments
        active_mutes = await self.bot.db.get_active_punishments(
            ctx.guild.id, "mute", member.id
        )
        for mute in active_mutes:
            await self.bot.db.deactivate_punishment(mute["case_id"])

        # Send DM to user
        await self._notify_user(member, "unmuted", reason, ctx.guild)

        # Create response embed
        embed = create_embed(
            title=f"{EMOJIS['success']} User Unmuted",
            description=f"**User:** {member.mention}\n"
            f"**Reason:** {reason}\n"
            f"**Case ID:** {case_id}",
            color="success",
            timestamp=True,
        )

        await safe_send(ctx, embed=embed)

        # Log the action
        self.logger.moderation_action(
            "unmute", member.id, ctx.author.id, ctx.guild.id, reason
        )

    @commands.command(name="kick")
    @require_permission(PermissionLevel.MODERATOR)
    async def kick_user(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ):
        """Kicks a member from the server. They can rejoin with an invite.

        **Usage:** `{prefix}kick <member> [reason]`
        **Examples:**
        - `{prefix}kick @member Violating server rules`
        - `{prefix}kick @member Inappropriate behavior`
        """
        if not await self._can_moderate(ctx, member):
            return

        # Confirm action
        confirmed = await confirm_action(
            ctx,
            f"Are you sure you want to kick {member.mention}?\n"
            f"**Reason:** {reason}\n\n"
            f"They will be able to rejoin with an invite link.",
        )

        if not confirmed:
            embed = create_embed(
                title=f"{EMOJIS['error']} Action Cancelled",
                description="Kick action was cancelled.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        # Send DM before kicking
        await self._notify_user(member, "kicked", reason, ctx.guild)

        # Perform kick
        try:
            await member.kick(reason=f"Kicked by {ctx.author}: {reason}")
        except discord.Forbidden:
            embed = create_embed(
                title=f"{EMOJIS['error']} Permission Error",
                description="I don't have permission to kick this member.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        # Add to database
        case_id = await self.bot.db.add_moderation_log(
            guild_id=ctx.guild.id,
            user_id=member.id,
            moderator_id=ctx.author.id,
            action="kick",
            reason=reason,
        )

        # Create response embed
        embed = create_embed(
            title=f"{EMOJIS['kick']} Member Kicked",
            description=f"**Member:** {member} ({member.id})\n"
            f"**Reason:** {reason}\n"
            f"**Case ID:** {case_id}",
            color="warning",
            timestamp=True,
        )

        await safe_send(ctx, embed=embed)

        # Log the action
        self.logger.moderation_action(
            "kick", member.id, ctx.author.id, ctx.guild.id, reason
        )

    @commands.command(name="ban")
    @require_permission(PermissionLevel.SENIOR_MODERATOR)
    async def ban_user(
        self,
        ctx: commands.Context,
        user: MemberOrUser,
        duration: Optional[Duration] = None,
        delete_days: Optional[int] = 1,
        *,
        reason: str = "No reason provided",
    ):
        """Bans a user from the server, permanently or temporarily.

        **Usage:** `{prefix}ban <user> [duration] [delete_days] [reason]`
        **Examples:**
        - `{prefix}ban @user Serious rule violation` (permanent)
        - `{prefix}ban @user 7d Temporary ban for harassment`
        - `{prefix}ban @user 1w 3` (deletes 3 days of messages)
        """
        # Validate delete_days
        if delete_days is not None and not (0 <= delete_days <= 7):
            embed = create_embed(
                title=f"{EMOJIS['error']} Invalid Parameter",
                description="Delete days must be between 0 and 7.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        # Check if user can be moderated (if they're in the server)
        if isinstance(user, discord.Member):
            if not await self._can_moderate(ctx, user):
                return

        # Check if user is already banned
        try:
            ban_entry = await ctx.guild.fetch_ban(user)
            embed = create_embed(
                title=f"{EMOJIS['error']} Already Banned",
                description=f"User {user} is already banned from this server.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return
        except discord.NotFound:
            pass  # User is not banned, continue

        # Confirm action
        duration_text = (
            f" for {format_duration(duration)}" if duration else " permanently"
        )
        confirmed = await confirm_action(
            ctx,
            f"Are you sure you want to ban {user}{duration_text}?\n"
            f"**Reason:** {reason}\n"
            f"**Message deletion:** {delete_days} day(s)\n\n"
            f"This action cannot be easily undone.",
        )

        if not confirmed:
            embed = create_embed(
                title=f"{EMOJIS['error']} Action Cancelled",
                description="Ban action was cancelled.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        # Send DM before banning
        duration_text = (
            f" for {format_duration(duration)}" if duration else " permanently"
        )
        await self._notify_user(user, f"banned{duration_text}", reason, ctx.guild)

        # Perform ban
        try:
            await ctx.guild.ban(
                user,
                reason=f"Banned by {ctx.author}: {reason}",
                delete_message_days=delete_days or 1,
            )
        except discord.Forbidden:
            embed = create_embed(
                title=f"{EMOJIS['error']} Permission Error",
                description="I don't have permission to ban this user.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        # Add to database
        case_id = await self.bot.db.add_moderation_log(
            guild_id=ctx.guild.id,
            user_id=user.id,
            moderator_id=ctx.author.id,
            action="ban",
            reason=reason,
            duration=int(duration.total_seconds()) if duration else None,
        )

        # Schedule unban if temporary
        if duration:
            asyncio.create_task(self._schedule_unban(ctx.guild.id, user.id, duration))

        # Create response embed
        duration_display = format_duration(duration) if duration else "Permanent"
        embed = create_embed(
            title=f"{EMOJIS['ban']} User Banned",
            description=f"**User:** {user}\n"
            f"**Duration:** {duration_display}\n"
            f"**Reason:** {reason}\n"
            f"**Case ID:** {case_id}",
            color="error",
            timestamp=True,
        )

        if duration:
            end_time = datetime.now(timezone.utc) + duration
            embed.add_field(
                name="Expires", value=f"<t:{int(end_time.timestamp())}:F>", inline=False
            )

        await safe_send(ctx, embed=embed)

        # Log the action
        self.logger.moderation_action(
            "ban", user.id, ctx.author.id, ctx.guild.id, reason
        )

    async def _can_moderate(
        self, ctx: commands.Context, target: discord.Member
    ) -> bool:
        """Check if the moderator can moderate the target user"""
        # Can't moderate yourself
        if target == ctx.author:
            embed = create_embed(
                title=f"{EMOJIS['error']} Invalid Target",
                description="You cannot moderate yourself.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return False

        # Can't moderate the bot
        if target == ctx.guild.me:
            embed = create_embed(
                title=f"{EMOJIS['error']} Invalid Target",
                description="I cannot moderate myself.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return False

        # Can't moderate server owner
        if target == ctx.guild.owner:
            embed = create_embed(
                title=f"{EMOJIS['error']} Invalid Target",
                description="Cannot moderate the server owner.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return False

        # Check role hierarchy
        if target.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            embed = create_embed(
                title=f"{EMOJIS['error']} Insufficient Permissions",
                description="You cannot moderate someone with a higher or equal role.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return False

        # Check bot's role hierarchy
        if target.top_role >= ctx.guild.me.top_role:
            embed = create_embed(
                title=f"{EMOJIS['error']} Bot Insufficient Permissions",
                description="I cannot moderate someone with a higher or equal role than me.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return False

        return True

    async def _get_mute_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        """Get or create the mute role for a guild"""
        guild_config = await self.bot.db.get_guild_config(guild.id)
        mute_role_id = guild_config.get("mute_role_id")

        # Try to get existing role
        if mute_role_id:
            mute_role = guild.get_role(mute_role_id)
            if mute_role:
                return mute_role

        # Create new mute role
        try:
            mute_role = await guild.create_role(
                name="Muted",
                color=discord.Color.dark_grey(),
                reason="Auto-created mute role",
            )

            # Set permissions for all channels
            for channel in guild.channels:
                try:
                    if isinstance(channel, discord.TextChannel):
                        await channel.set_permissions(
                            mute_role,
                            send_messages=False,
                            add_reactions=False,
                            create_public_threads=False,
                            create_private_threads=False,
                            send_messages_in_threads=False,
                        )
                    elif isinstance(channel, discord.VoiceChannel):
                        await channel.set_permissions(
                            mute_role, speak=False, stream=False
                        )
                except discord.Forbidden:
                    continue

            # Save to database
            await self.bot.db.update_guild_config(
                guild.id, {"mute_role_id": mute_role.id}
            )

            return mute_role

        except discord.Forbidden:
            return None

    async def _notify_user(
        self,
        user: Union[discord.Member, discord.User],
        action: str,
        reason: str,
        guild: discord.Guild,
    ):
        """Send a DM notification to a user about moderation action"""
        try:
            embed = create_embed(
                title=f"{EMOJIS['warning']} Moderation Action",
                description=f"You have been **{action}** in **{guild.name}**",
                color="warning",
            )

            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Server", value=guild.name, inline=True)
            embed.add_field(
                name="Time",
                value=f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>",
                inline=True,
            )

            await user.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass  # User has DMs disabled or other error

    async def _schedule_unmute(self, guild_id: int, user_id: int, duration: timedelta):
        """Schedule an automatic unmute"""
        await asyncio.sleep(duration.total_seconds())

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        member = guild.get_member(user_id)
        if not member:
            return

        # Get mute role
        guild_config = await self.bot.db.get_guild_config(guild_id)
        mute_role_id = guild_config.get("mute_role_id")

        if not mute_role_id:
            return

        mute_role = guild.get_role(mute_role_id)
        if not mute_role or mute_role not in member.roles:
            return

        # Remove mute role
        try:
            await member.remove_roles(
                mute_role, reason="Automatic unmute - duration expired"
            )

            # Add to database
            await self.bot.db.add_moderation_log(
                guild_id=guild_id,
                user_id=user_id,
                moderator_id=self.bot.user.id,
                action="unmute",
                reason="Automatic unmute - duration expired",
            )

            # Notify user
            await self._notify_user(
                member, "automatically unmuted", "Duration expired", guild
            )

        except discord.Forbidden:
            pass

    async def _schedule_unban(self, guild_id: int, user_id: int, duration: timedelta):
        """Schedule an automatic unban"""
        await asyncio.sleep(duration.total_seconds())

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        # Check if user is still banned
        try:
            await guild.fetch_ban(discord.Object(user_id))
        except discord.NotFound:
            return  # User is not banned

        # Unban user
        try:
            user = await self.bot.fetch_user(user_id)
            await guild.unban(user, reason="Automatic unban - duration expired")

            # Add to database
            await self.bot.db.add_moderation_log(
                guild_id=guild_id,
                user_id=user_id,
                moderator_id=self.bot.user.id,
                action="unban",
                reason="Automatic unban - duration expired",
            )

            # Notify user
            await self._notify_user(
                user, "automatically unbanned", "Duration expired", guild
            )

        except (discord.Forbidden, discord.NotFound):
            pass

    @commands.command(name="unban")
    @require_permission(PermissionLevel.SENIOR_MODERATOR)
    async def unban_user(
        self,
        ctx: commands.Context,
        user: MemberOrUser,
        *,
        reason: str = "No reason provided",
    ):
        """Unbans a user, allowing them to rejoin the server.

        **Usage:** `{prefix}unban <user_id> [reason]`
        **Examples:**
        - `{prefix}unban 123456789 Appeal accepted`
        - `{prefix}unban 987654321 Ban period expired`
        """
        try:
            await ctx.guild.fetch_ban(user)
        except discord.NotFound:
            embed = create_embed(
                title=f"{EMOJIS['error']} User Not Banned",
                description=f"User {user} is not banned from this server.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        try:
            await ctx.guild.unban(user, reason=f"Unbanned by {ctx.author}: {reason}")
        except discord.Forbidden:
            embed = create_embed(
                title=f"{EMOJIS['error']} Permission Error",
                description="I don't have permission to unban users.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        case_id = await self.bot.db.add_moderation_log(
            guild_id=ctx.guild.id,
            user_id=user.id,
            moderator_id=ctx.author.id,
            action="unban",
            reason=reason,
        )

        embed = create_embed(
            title=f"{EMOJIS['success']} User Unbanned",
            description=f"**User:** {user}\n**Reason:** {reason}\n**Case ID:** {case_id}",
            color="success",
            timestamp=True,
        )
        await safe_send(ctx, embed=embed)

    @commands.group(invoke_without_command=True)
    @require_permission(PermissionLevel.MODERATOR)
    async def modlogs(self, ctx: commands.Context, target: str = None):
        """View moderation logs: server-wide, for a user, or a specific case.

        Usage:
        - `{prefix}modlogs` → recent server logs
        - `{prefix}modlogs @user` → logs for a user
        - `{prefix}modlogs <user_id>` → logs for a user by ID
        - `{prefix}modlogs <case_number>` → view a specific case (e.g., `modlogs 4`)
        - `{prefix}modlogs <guild_id>-<case_number>` → view a specific case by full ID
        """
        if ctx.invoked_subcommand is not None:
            return

        # No argument: show recent guild logs
        if not target:
            await self._show_guild_modlogs(ctx)
            return

        # If numeric and short (< 17 digits), treat as case number; if full id with '-', treat as case
        if (target.isdigit() and len(target) < 17) or (
            "-" in target and all(p.isdigit() for p in target.split("-", 1))
        ):
            full_id = self._normalize_case_id(ctx.guild.id, target)
            log = await self.bot.db.get_moderation_log(ctx.guild.id, full_id)
            if not log:
                embed = create_embed(
                    title=f"{EMOJIS['error']} Case Not Found",
                    description=f"No moderation case found with ID `{target}`.",
                    color="error",
                )
                await safe_send(ctx, embed=embed)
                return

            embed = self._format_case_embed(ctx, log)
            await safe_send(ctx, embed=embed)
            return

        # Otherwise, try to resolve as a user and show their logs
        try:
            member_or_user = await MemberOrID().convert(ctx, target)
            await self._show_user_modlogs(ctx, member_or_user)
        except Exception:
            # Fallback to guild logs with a gentle hint
            embed = create_embed(
                title=f"{EMOJIS['error']} Not Found",
                description=(
                    "Couldn't resolve that as a user or case ID. "
                    "Try `modlogs @user`, `modlogs <user_id>`, or `modlogs <case_number>`."
                ),
                color="error",
            )
            await safe_send(ctx, embed=embed)

    @modlogs.command(name="case", aliases=["view", "info"])
    @require_permission(PermissionLevel.MODERATOR)
    async def modlogs_case(self, ctx: commands.Context, case: str):
        """View a specific moderation case by number or full Case ID.

        Usage: {prefix}modlogs case <case_number|case_id>
        Examples:
        - {prefix}modlogs case 42
        - {prefix}modlogs case {ctx.guild.id}-42
        """
        full_id = self._normalize_case_id(ctx.guild.id, case)
        log = await self.bot.db.get_moderation_log(ctx.guild.id, full_id)

        if not log:
            embed = create_embed(
                title=f"{EMOJIS['error']} Case Not Found",
                description=f"No moderation case found with ID `{case}`.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        embed = self._format_case_embed(ctx, log)
        await safe_send(ctx, embed=embed)

    async def _show_user_modlogs(self, ctx: commands.Context, user: MemberOrID):
        """Show moderation logs for a specific user"""
        logs = await self.bot.db.get_user_moderation_logs(
            ctx.guild.id, user.id, limit=100
        )

        if not logs:
            await safe_send(ctx, "No moderation logs found for this user.")
            return

        def sanitize_reason(reason):
            return re.sub(r"(https?://\S+)", r"<\1>", reason)

        entries = []
        for log in logs:
            moderator = self.bot.get_user(log["moderator_id"])
            mod_mention = moderator.mention if moderator else "Unknown"
            reason = sanitize_reason(log["reason"])
            case_number = str(log["case_id"]).split("-")[-1]
            entries.append(
                f"Case **{case_number}**: {log['action'].title()} by {mod_mention} - {reason}"
            )

        pages = ["\n".join(entries[i : i + 10]) for i in range(0, len(entries), 10)]
        paginator = Paginator(
            ctx,
            pages,
            show_page_count=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await paginator.start()

    async def _show_guild_modlogs(self, ctx: commands.Context):
        """Show recent moderation logs for the guild"""
        logs = await self.bot.db.get_guild_moderation_logs(ctx.guild.id, limit=100)

        if not logs:
            await safe_send(ctx, "No moderation logs found for this server.")
            return

        def sanitize_reason(reason):
            return re.sub(r"(https?://\S+)", r"<\1>", reason)

        entries = []
        for log in logs:
            user = self.bot.get_user(log["user_id"])
            user_name = user.mention if user else f"<@{log['user_id']}>"
            moderator = self.bot.get_user(log["moderator_id"])
            mod_mention = moderator.mention if moderator else "Unknown"
            reason = sanitize_reason(log["reason"])
            case_number = str(log["case_id"]).split("-")[-1]
            entries.append(
                f"Case **{case_number}**: {log['action'].title()} on {user_name} by {mod_mention} - {reason}"
            )

        pages = ["\n".join(entries[i : i + 10]) for i in range(0, len(entries), 10)]
        paginator = Paginator(
            ctx,
            pages,
            show_page_count=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await paginator.start()

    @modlogs.command(name="update")
    @require_permission(PermissionLevel.MODERATOR)
    async def modlogs_update(
        self, ctx: commands.Context, case_id: Union[int, str], *, reason: str
    ):
        """Updates the reason for a moderation log entry.

        **Usage:** `{prefix}modlogs update <case_id> <new_reason>`
        **Example:** `{prefix}modlogs update 123 Updated reason for action`
        """
        full_id = self._normalize_case_id(ctx.guild.id, case_id)
        log = await self.bot.db.get_moderation_log(ctx.guild.id, full_id)

        if not log:
            embed = create_embed(
                title=f"{EMOJIS['error']} Log Not Found",
                description=f"No moderation log found with case ID `{case_id}`.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        await self.bot.db.update_moderation_log(ctx.guild.id, full_id, reason)

        embed = create_embed(
            title="✅ Log Updated",
            description=f"Reason for case `{full_id}` has been updated.",
            color="success",
        )
        await safe_send(ctx, embed=embed)

    @commands.command(name="softban")
    @require_permission(PermissionLevel.SENIOR_MODERATOR)
    async def softban_user(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ):
        """Bans and immediately unbans a member to delete their recent messages.

        **Usage:** `{prefix}softban <member> [reason]`
        **Examples:**
        - `{prefix}softban @member Spam cleanup`
        - `{prefix}softban @member Message purge needed`
        """
        if not await self._can_moderate(ctx, member):
            return

        confirmed = await confirm_action(
            ctx,
            f"Are you sure you want to softban {member.mention}?\n"
            f"**Reason:** {reason}\n\n"
            f"This will ban and immediately unban them to delete their recent messages.",
        )

        if not confirmed:
            embed = create_embed(
                title=f"{EMOJIS['error']} Action Cancelled",
                description="Softban action was cancelled.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        await self._notify_user(member, "softbanned", reason, ctx.guild)

        try:
            await member.ban(
                reason=f"Softbanned by {ctx.author}: {reason}", delete_message_days=1
            )
            await asyncio.sleep(0.5)
            await member.unban(reason="Softban - immediate unban")
        except discord.Forbidden:
            embed = create_embed(
                title=f"{EMOJIS['error']} Permission Error",
                description="I don't have permission to ban/unban this member.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        case_id = await self.bot.db.add_moderation_log(
            guild_id=ctx.guild.id,
            user_id=member.id,
            moderator_id=ctx.author.id,
            action="softban",
            reason=reason,
        )

        embed = create_embed(
            title=f"{EMOJIS['ban']} Member Softbanned",
            description=f"**Member:** {member} ({member.id})\n"
            f"**Reason:** {reason}\n"
            f"**Case ID:** {case_id}",
            color="warning",
            timestamp=True,
        )

        await safe_send(ctx, embed=embed)
        self.logger.moderation_action(
            "softban", member.id, ctx.author.id, ctx.guild.id, reason
        )

    @commands.command(name="muted")
    @require_permission(PermissionLevel.MODERATOR)
    async def list_muted(self, ctx: commands.Context):
        """Shows a list of all currently muted members.

        **Usage:** `{prefix}muted`
        **Example:** `{prefix}muted`
        """
        config = await self.bot.db.get_guild_config(ctx.guild.id)
        mutes = config.get("mutes", [])

        if not mutes:
            embed = create_embed(
                title="🔇 No Active Mutes",
                description="No members are currently muted",
                color="info",
            )
            await safe_send(ctx, embed=embed)
            return

        embed = create_embed(title="🔇 Currently Muted Members", color="info")

        for mute in mutes[:10]:
            user_id = mute.get("member")
            until = mute.get("time")
            member = ctx.guild.get_member(int(user_id)) if user_id else None
            name = member.mention if member else f"<@{user_id}>"

            if until:
                embed.add_field(
                    name=name, value=f"Until <t:{int(until)}:F>", inline=False
                )
            else:
                embed.add_field(name=name, value="Indefinite", inline=False)

        await safe_send(ctx, embed=embed)

    @commands.command(name="softban")
    @require_permission(PermissionLevel.SENIOR_MODERATOR)
    async def softban_user(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ):
        """Bans and immediately unbans a member to delete their recent messages.

        **Usage:** `{prefix}softban <member> [reason]`
        **Examples:**
        - `{prefix}softban @member Spam cleanup`
        - `{prefix}softban @member Message purge needed`
        """
        if not await self._can_moderate(ctx, member):
            return

        confirmed = await confirm_action(
            ctx,
            f"Are you sure you want to softban {member.mention}?\n"
            f"**Reason:** {reason}\n\n"
            f"This will ban and immediately unban them to delete their recent messages.",
        )

        if not confirmed:
            embed = create_embed(
                title=f"{EMOJIS['error']} Action Cancelled",
                description="Softban action was cancelled.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        await self._notify_user(member, "softbanned", reason, ctx.guild)

        try:
            await member.ban(
                reason=f"Softbanned by {ctx.author}: {reason}", delete_message_days=1
            )
            await asyncio.sleep(0.5)
            await member.unban(reason="Softban - immediate unban")
        except discord.Forbidden:
            embed = create_embed(
                title=f"{EMOJIS['error']} Permission Error",
                description="I don't have permission to ban/unban this member.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        case_id = await self.bot.db.add_moderation_log(
            guild_id=ctx.guild.id,
            user_id=member.id,
            moderator_id=ctx.author.id,
            action="softban",
            reason=reason,
        )

        embed = create_embed(
            title=f"{EMOJIS['ban']} Member Softbanned",
            description=f"**Member:** {member} ({member.id})\n"
            f"**Reason:** {reason}\n"
            f"**Case ID:** {case_id}",
            color="warning",
            timestamp=True,
        )

        await safe_send(ctx, embed=embed)
        self.logger.moderation_action(
            "softban", member.id, ctx.author.id, ctx.guild.id, reason
        )

    @commands.command(name="muted")
    @require_permission(PermissionLevel.MODERATOR)
    async def list_muted(self, ctx: commands.Context):
        """Shows a list of all currently muted members.

        **Usage:** `{prefix}muted`
        **Example:** `{prefix}muted`
        """
        config = await self.bot.db.get_guild_config(ctx.guild.id)
        mutes = config.get("mutes", [])

        if not mutes:
            embed = create_embed(
                title="🔇 No Active Mutes",
                description="No members are currently muted",
                color="info",
            )
            await safe_send(ctx, embed=embed)
            return

        embed = create_embed(title="🔇 Currently Muted Members", color="info")

        for mute in mutes[:10]:
            user_id = mute.get("member")
            until = mute.get("time")
            member = ctx.guild.get_member(int(user_id)) if user_id else None
            name = member.mention if member else f"<@{user_id}>"

            if until:
                embed.add_field(
                    name=name, value=f"Until <t:{int(until)}:F>", inline=False
                )
            else:
                embed.add_field(name=name, value="Indefinite", inline=False)

        await safe_send(ctx, embed=embed)

    @commands.command(name="setwarnpunishment")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def set_warn_punishment(
        self,
        ctx: commands.Context,
        threshold: int,
        punishment: str,
        duration: str = None,
    ):
        """Sets an automatic punishment when a user reaches a certain number of warnings.

        **Usage:** `{prefix}setwarnpunishment <warnings> <punishment> [duration]`
        **Examples:**
        - `{prefix}setwarnpunishment 3 mute 1h`
        - `{prefix}setwarnpunishment 5 kick`
        - `{prefix}setwarnpunishment 7 ban 7d`
        """
        valid_punishments = ["mute", "kick", "softban", "ban", "tempban"]

        if punishment.lower() not in valid_punishments:
            embed = create_embed(
                title=f"{EMOJIS['error']} Invalid Punishment",
                description=f"Valid punishments: {', '.join(valid_punishments)}",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        punishment_config = {"threshold": threshold, "action": punishment.lower()}

        if duration:
            try:
                duration_delta = parse_time(duration)
                punishment_config["duration"] = int(duration_delta.total_seconds())
            except:
                embed = create_embed(
                    title=f"{EMOJIS['error']} Invalid Duration",
                    description="Use format like: 1h, 30m, 2d",
                    color="error",
                )
                await safe_send(ctx, embed=embed)
                return

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"warn_punishment": punishment_config}
        )

        duration_str = f" for {duration}" if duration else ""
        embed = create_embed(
            title="✅ Warning Punishment Set",
            description=f"Set automatic {punishment}{duration_str} at {threshold} warnings",
            color="success",
        )
        await safe_send(ctx, embed=embed)

    @commands.command(name="purge", aliases=["clean", "prune"])
    @require_permission(PermissionLevel.HELPER)
    async def purge_messages(
        self, ctx: commands.Context, limit: int, member: discord.Member = None
    ):
        """Deletes a specified number of messages from a channel.

        **Usage:** `{prefix}purge <amount> [user]`
        **Examples:**
        - `{prefix}purge 10` (deletes the last 10 messages)
        - `{prefix}purge 50 @user` (deletes the last 50 messages from a specific user)
        """
        if limit > 2000:
            embed = create_embed(
                title=f"{EMOJIS['error']} Limit Too High",
                description="Maximum limit is 2000 messages",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        try:
            await ctx.message.delete()
        except:
            pass

        if member:
            deleted = await ctx.channel.purge(
                limit=limit, check=lambda m: m.author == member
            )
        else:
            deleted = await ctx.channel.purge(limit=limit)

        embed = create_embed(
            title=f"{EMOJIS['success']} Messages Purged",
            description=f"Deleted {len(deleted)} messages"
            + (f" from {member.mention}" if member else ""),
            color="success",
        )

        msg = await safe_send(ctx, embed=embed)
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except:
            pass

    @commands.command(name="lockdown")
    @require_permission(PermissionLevel.MODERATOR)
    async def lockdown_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ):
        """Toggles the ability for @everyone to send messages in a channel.

        **Usage:** `{prefix}lockdown [channel]`
        **Examples:**
        - `{prefix}lockdown` (locks the current channel)
        - `{prefix}lockdown #general` (locks the #general channel)
        """
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)

        if overwrite.send_messages is False:
            overwrite.send_messages = None
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
            action = "unlocked"
            color = "success"
        else:
            overwrite.send_messages = False
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
            action = "locked"
            color = "warning"

        embed = create_embed(
            title=f"{EMOJIS['lock']} Channel {action.title()}",
            description=f"{channel.mention} has been {action}",
            color=color,
        )
        await safe_send(ctx, embed=embed)

    @commands.command(name="slowmode")
    @require_permission(PermissionLevel.MODERATOR)
    async def slowmode_channel(
        self, ctx: commands.Context, duration: str, channel: discord.TextChannel = None
    ):
        """Sets a slowmode delay for a channel.

        **Usage:** `{prefix}slowmode <duration> [channel]`
        **Examples:**
        - `{prefix}slowmode 5s` (sets a 5-second delay)
        - `{prefix}slowmode 1m #general` (sets a 1-minute delay in #general)
        - `{prefix}slowmode off` (disables slowmode)
        """
        channel = channel or ctx.channel

        if duration.lower() in ["off", "0", "0s"]:
            seconds = 0
        else:
            try:
                duration_delta = parse_time(duration)
                seconds = int(duration_delta.total_seconds())
            except:
                embed = create_embed(
                    title=f"{EMOJIS['error']} Invalid Duration",
                    description="Use format like: 10s, 5m (max 6h)",
                    color="error",
                )
                await safe_send(ctx, embed=embed)
                return

        if seconds > 21600:  # 6 hours
            embed = create_embed(
                title=f"{EMOJIS['error']} Duration Too Long",
                description="Maximum slowmode is 6 hours",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        await channel.edit(slowmode_delay=seconds)

        if seconds == 0:
            description = f"Slowmode disabled for {channel.mention}"
        else:
            description = f"Slowmode set to {duration} for {channel.mention}"

        embed = create_embed(
            title=f"{EMOJIS['clock']} Slowmode Updated",
            description=description,
            color="success",
        )
        await safe_send(ctx, embed=embed)

    @modlogs.command(name="all")
    @require_permission(PermissionLevel.MODERATOR)
    async def modlogs_all(self, ctx: commands.Context):
        """Shows all moderation logs for the server.

        **Usage:** `{prefix}modlogs all`
        """
        logs = await self.bot.db.get_guild_moderation_logs(ctx.guild.id, limit=100)

        if not logs:
            await safe_send(ctx, "No moderation logs found for this server.")
            return

        def sanitize_reason(reason):
            return re.sub(r"(https?://\S+)", r"<\1>", reason)

        entries = []
        for log in logs:
            user = self.bot.get_user(log["user_id"])
            user_name = user.mention if user else f"<@{log['user_id']}>"
            moderator = self.bot.get_user(log["moderator_id"])
            mod_mention = moderator.mention if moderator else "Unknown"
            reason = sanitize_reason(log["reason"])
            case_number = str(log["case_id"]).split("-")[-1]
            entries.append(
                f"Case **{case_number}**: {log['action'].title()} on {user_name} by {mod_mention} - {reason}"
            )

        pages = ["\n".join(entries[i : i + 10]) for i in range(0, len(entries), 10)]
        paginator = Paginator(
            ctx,
            pages,
            show_page_count=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await paginator.start()

    @modlogs.command(name="remove")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def modlogs_remove(self, ctx: commands.Context, case_id: Union[int, str]):
        """Removes a specific moderation log entry by its case ID.

        **Usage:** `{prefix}modlogs remove <case_id>`
        **Example:** `{prefix}modlogs remove 123`
        """
        full_id = self._normalize_case_id(ctx.guild.id, case_id)
        await self.bot.db.deactivate_punishment(full_id)
        embed = create_embed(
            title="✅ Log Removed",
            description=f"Moderation log with case ID `{full_id}` has been removed.",
            color="success",
        )
        await safe_send(ctx, embed=embed)

    @modlogs.command(name="purge")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def modlogs_purge(self, ctx: commands.Context, user: MemberOrID):
        """Removes all moderation logs for a specific user.

        **Usage:** `{prefix}modlogs purge <user>`
        **Example:** `{prefix}modlogs purge @user`
        """
        confirmed = await confirm_action(
            ctx,
            f"Are you sure you want to purge all moderation logs for {user}?\n"
            "This action is irreversible.",
        )

        if not confirmed:
            embed = create_embed(
                title="Action Cancelled",
                description="Moderation log purge cancelled.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        logs = await self.bot.db.get_user_moderation_logs(
            ctx.guild.id, user.id, limit=9999
        )
        for log in logs:
            await self.bot.db.deactivate_punishment(log["case_id"])

        embed = create_embed(
            title="✅ Logs Purged",
            description=f"All moderation logs for {user} have been purged.",
            color="success",
        )
        await safe_send(ctx, embed=embed)

    @commands.command(name="setpermission")
    @require_permission(PermissionLevel.ADMINISTRATOR)
    async def set_permission(
        self, ctx: commands.Context, role: discord.Role, level: str
    ):
        """Assigns a permission level to a role.

        **Usage:** `{prefix}setpermission <role> <level>`
        **Example:** `{prefix}setpermission @Moderator MODERATOR`

        Available levels: HELPER, MODERATOR, SENIOR_MODERATOR, ADMINISTRATOR.
        """
        level = level.upper()
        if level not in PermissionLevel.__members__:
            embed = create_embed(
                title=f"{EMOJIS['error']} Invalid Level",
                description="Please provide a valid permission level.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        permission_level = PermissionLevel[level]

        if permission_level >= PermissionLevel.SERVER_OWNER:
            embed = create_embed(
                title=f"{EMOJIS['error']} Invalid Level",
                description="You cannot assign a permission level this high.",
                color="error",
            )
            await safe_send(ctx, embed=embed)
            return

        config = await self.bot.db.get_guild_config(ctx.guild.id)
        permission_roles = config.get("permission_roles", {})
        permission_roles[str(role.id)] = permission_level.value

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"permission_roles": permission_roles}
        )

        embed = create_embed(
            title="✅ Permission Set",
            description=f"The permission level for {role.mention} has been set to **{level.title()}**.",
            color="success",
        )
        await safe_send(ctx, embed=embed)

    async def _check_auto_punishment(
        self,
        ctx: commands.Context,
        user: Union[discord.Member, discord.User],
        action: str,
    ):
        """Check and apply automatic punishments based on warning count."""
        if action != "warn":
            return

        guild_id = ctx.guild.id
        config = await self.bot.db.get_guild_config(guild_id)
        warn_cfg = config.get("warn_punishment") or {}

        threshold = int(warn_cfg.get("threshold") or 0)
        punish_action = (warn_cfg.get("action") or "").lower()
        duration_seconds = warn_cfg.get("duration")  # optional

        if threshold <= 0 or not punish_action:
            return

        # Count total warnings (lifetime) for this user in this guild
        try:
            warn_count = await self.bot.db.db.moderation_logs.count_documents(
                {"guild_id": guild_id, "user_id": user.id, "action": "warn"}
            )
        except Exception:
            return

        # Trigger at multiples of threshold (e.g., 2, 4, 6, ...)
        if warn_count % threshold != 0:
            return

        # Resolve member
        member: Optional[discord.Member] = (
            user if isinstance(user, discord.Member) else ctx.guild.get_member(user.id)
        )

        # Confirm with invoking moderator
        duration_td = timedelta(seconds=duration_seconds) if duration_seconds else None
        duration_text = f" for {format_duration(duration_td)}" if duration_td else ""
        target_display = (
            user.mention if isinstance(user, discord.Member) else f"<@{user.id}>"
        )
        confirm_msg = (
            f"{target_display} reached `{threshold}` warnings.\n"
            f"Apply auto-punishment: **{punish_action}**{duration_text}?"
        )
        approved = await confirm_action(ctx, confirm_msg)
        if not approved:
            await safe_send(
                ctx,
                embed=create_embed(
                    title=f"{EMOJIS['error']} Auto-Punishment Cancelled",
                    description="Moderator denied the automatic action.",
                    color="error",
                ),
            )
            return

        async def announce_applied(title: str, body_lines: list[str]):
            desc = "\n".join(body_lines)
            embed = create_embed(
                title=title, description=desc, color="warning", timestamp=True
            )
            await safe_send(ctx, embed=embed)

        # mute
        if punish_action == "mute":
            if not member:
                await announce_applied(
                    "⚠️ Auto-Punishment Skipped",
                    [
                        "User is not in the server; cannot apply mute.",
                        f"Warnings reached: {warn_count}/{threshold}",
                    ],
                )
                return

            if not await self._can_moderate(ctx, member):
                return

            mute_role = await self._get_mute_role(ctx.guild)
            if not mute_role:
                await announce_applied(
                    "⚠️ Auto-Punishment Skipped",
                    ["Mute role not configured or cannot be created."],
                )
                return

            try:
                await member.add_roles(
                    mute_role, reason=f"Auto-mute at {threshold} warns"
                )
            except discord.Forbidden:
                await announce_applied(
                    "⚠️ Auto-Punishment Failed",
                    ["I don't have permission to add the mute role."],
                )
                return

            case_id = await self.bot.db.add_moderation_log(
                guild_id=guild_id,
                user_id=member.id,
                moderator_id=ctx.author.id,
                action="mute",
                reason=f"Auto-mute: reached {threshold} warnings",
                duration=duration_seconds if duration_seconds else None,
            )

            if duration_seconds and duration_seconds > 0:
                asyncio.create_task(
                    self._schedule_unmute(
                        guild_id, member.id, timedelta(seconds=duration_seconds)
                    )
                )
                dur_text = format_duration(timedelta(seconds=duration_seconds))
                await self._notify_user(
                    member,
                    f"muted for {dur_text}",
                    f"Auto-mute: reached {threshold} warnings",
                    ctx.guild,
                )
            else:
                await self._notify_user(
                    member,
                    "muted",
                    f"Auto-mute: reached {threshold} warnings",
                    ctx.guild,
                )

            lines = [
                f"User: {member.mention}",
                f"Reason: Reached {threshold} warnings",
                f"Case ID: {case_id}",
            ]
            if duration_seconds:
                lines.append(
                    f"Duration: {format_duration(timedelta(seconds=duration_seconds))}"
                )
            await announce_applied(f"{EMOJIS['mute']} Automatic Mute Applied", lines)
            self.logger.moderation_action(
                "auto_mute",
                member.id,
                ctx.author.id,
                guild_id,
                f"Reached {threshold} warnings",
            )
            return

        # kick
        if punish_action == "kick":
            if not member:
                await announce_applied(
                    "⚠️ Auto-Punishment Skipped",
                    ["User is not in the server; cannot kick."],
                )
                return
            if not await self._can_moderate(ctx, member):
                return

            await self._notify_user(
                member, "kicked", f"Auto-kick: reached {threshold} warnings", ctx.guild
            )
            try:
                await member.kick(reason=f"Auto-kick at {threshold} warns")
            except discord.Forbidden:
                await announce_applied(
                    "⚠️ Auto-Punishment Failed",
                    ["I don't have permission to kick this member."],
                )
                return

            case_id = await self.bot.db.add_moderation_log(
                guild_id=guild_id,
                user_id=member.id,
                moderator_id=ctx.author.id,
                action="kick",
                reason=f"Auto-kick: reached {threshold} warnings",
            )
            await announce_applied(
                f"{EMOJIS['kick']} Automatic Kick Applied",
                [
                    f"User: {member.mention}",
                    f"Reason: Reached {threshold} warnings",
                    f"Case ID: {case_id}",
                ],
            )
            self.logger.moderation_action(
                "auto_kick",
                member.id,
                ctx.author.id,
                guild_id,
                f"Reached {threshold} warnings",
            )
            return

        # softban
        if punish_action == "softban":
            if not member:
                await announce_applied(
                    "⚠️ Auto-Punishment Skipped",
                    ["User is not in the server; cannot softban."],
                )
                return
            if not await self._can_moderate(ctx, member):
                return

            await self._notify_user(
                member,
                "softbanned",
                f"Auto-softban: reached {threshold} warnings",
                ctx.guild,
            )
            try:
                await member.ban(
                    reason=f"Auto-softban at {threshold} warns", delete_message_days=1
                )
                await asyncio.sleep(0.5)
                await ctx.guild.unban(member, reason="Auto-softban - immediate unban")
            except discord.Forbidden:
                await announce_applied(
                    "⚠️ Auto-Punishment Failed",
                    ["I lack permissions to (un)ban this member."],
                )
                return

            case_id = await self.bot.db.add_moderation_log(
                guild_id=guild_id,
                user_id=member.id,
                moderator_id=ctx.author.id,
                action="softban",
                reason=f"Auto-softban: reached {threshold} warnings",
            )
            await announce_applied(
                f"{EMOJIS['ban']} Automatic Softban Applied",
                [
                    f"User: {member.mention}",
                    f"Reason: Reached {threshold} warnings",
                    f"Case ID: {case_id}",
                ],
            )
            self.logger.moderation_action(
                "auto_softban",
                member.id,
                ctx.author.id,
                guild_id,
                f"Reached {threshold} warnings",
            )
            return

        # ban / tempban
        if punish_action in {"ban", "tempban"}:
            target_user: Union[discord.Member, discord.User] = user
            if not isinstance(target_user, (discord.Member, discord.User)):
                target_user = await ctx.bot.fetch_user(user.id)

            duration_td2 = (
                timedelta(seconds=duration_seconds) if duration_seconds else None
            )
            duration_text2 = (
                f" for {format_duration(duration_td2)}"
                if duration_td2
                else " permanently"
            )

            await self._notify_user(
                target_user,
                f"banned{duration_text2}",
                f"Auto-ban: reached {threshold} warnings",
                ctx.guild,
            )
            try:
                await ctx.guild.ban(
                    target_user,
                    reason=f"Auto-ban at {threshold} warns",
                    delete_message_days=1,
                )
            except discord.Forbidden:
                await announce_applied(
                    "⚠️ Auto-Punishment Failed",
                    ["I don't have permission to ban this user."],
                )
                return

            case_id = await self.bot.db.add_moderation_log(
                guild_id=guild_id,
                user_id=target_user.id,
                moderator_id=ctx.author.id,
                action="ban",
                reason=f"Auto-ban: reached {threshold} warnings",
                duration=int(duration_td2.total_seconds()) if duration_td2 else None,
            )

            if duration_td2:
                asyncio.create_task(
                    self._schedule_unban(guild_id, target_user.id, duration_td2)
                )

            lines = [
                f"User: {getattr(target_user, 'mention', str(target_user))}",
                f"Reason: Reached {threshold} warnings",
                f"Case ID: {case_id}",
            ]
            if duration_td2:
                lines.append(f"Duration: {format_duration(duration_td2)}")
            await announce_applied(f"{EMOJIS['ban']} Automatic Ban Applied", lines)
            self.logger.moderation_action(
                "auto_ban",
                target_user.id,
                ctx.author.id,
                guild_id,
                f"Reached {threshold} warnings",
            )
            return

        # Unknown action
        await announce_applied(
            "⚠️ Auto-Punishment Misconfigured",
            [
                f"Unknown action '{punish_action}'. Supported: mute, kick, softban, ban, tempban."
            ],
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Handles sticky mutes when a member rejoins."""
        # Check for active mute punishments in the database
        active_mutes = await self.bot.db.get_active_punishments(
            member.guild.id, "mute", member.id
        )

        if active_mutes:
            # Get the mute role for the server
            mute_role = await self._get_mute_role(member.guild)
            if mute_role:
                try:
                    await member.add_roles(
                        mute_role, reason="Sticky Mute: User rejoined"
                    )
                    self.logger.moderation_action(
                        "sticky_mute",
                        member.id,
                        self.bot.user.id,
                        member.guild.id,
                        "User rejoined while muted.",
                    )
                except discord.Forbidden:
                    self.logger.error(
                        f"Failed to re-apply sticky mute to {member.id} in {member.guild.id} due to permissions."
                    )
                except discord.HTTPException as e:
                    self.logger.error(
                        f"Failed to re-apply sticky mute to {member.id} in {member.guild.id}: {e}"
                    )


async def setup(bot):
    """Load the moderation extension"""
    await bot.add_cog(Moderation(bot))
