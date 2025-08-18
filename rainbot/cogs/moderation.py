import asyncio
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

import discord
from discord.ext import commands
from discord.ext.commands import BucketType, cooldown
from rainbot.main import RainBot
from ..services.database import DBDict, DEFAULT
from ..ext.utility import format_timedelta, tryint
from ..ext.command import command, group
import time

from ..ext.time import UserFriendlyTime
from ..ext.permissions import get_perm_level
from ..ext.utility import CannedStr


class MemberOrID(commands.IDConverter):
    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> Union[discord.Member, discord.User]:
        try:
            return await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            try:
                return await ctx.bot.fetch_user(int(argument))
            except (ValueError, TypeError):
                raise commands.BadArgument(f"Member {argument} not found")


def validate_case_number(case_num):
    """Validate case number input"""
    try:
        num = int(case_num)
        return num if 0 < num < 999999 else None
    except (ValueError, TypeError):
        return None


def validate_user_id(user_id):
    """Validate user ID input"""
    try:
        uid = validate_user_id(user_id)
        return uid if 0 < uid < 2**63 else None
    except (ValueError, TypeError):
        return None


class Moderation(commands.Cog):
    def __init__(self, bot: RainBot) -> None:
        self.bot = bot
        self.order = 2
        self.logger = logging.getLogger("rainbot.moderation")
        self.kick_confirm_timeouts = set()  # Track member IDs for which kick confirmation timed out

    # Helper to safely send to a channel given a channel object or ID
    async def _send_to_log(self, bot, target, *, content=None, embed=None):
        try:
            channel = None
            if hasattr(target, "send"):
                channel = target
            else:
                try:
                    channel_id = int(target) if target else None
                    if channel_id:
                        channel = bot.get_channel(channel_id)
                except (ValueError, TypeError):
                    channel = None
            if not channel:
                return
            if embed is not None and content is not None:
                await channel.send(content, embed=embed)
            elif embed is not None:
                await channel.send(embed=embed)
            else:
                await channel.send(content)
        except (ValueError, TypeError):
            # Swallow send errors to avoid crashing command handlers
            pass

    @group(6, invoke_without_command=True, usage="\u003cuser_id\u003e")
    async def modlogs(self, ctx: commands.Context, user: MemberOrID = None) -> None:
        """**View moderation logs for a user**

        This command displays a paginated list of all moderation actions taken against a specific user.

        **Usage:**
        `{prefix}modlogs <user>`

        **<user>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`

        **Subcommands:**
        - `all` - View all modlogs in the server.
        - `remove` - Remove a modlog entry.
        """
        if user is None:
            await ctx.invoke(self.bot.get_command("help"), command_or_cog="modlogs")
            return

        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)

        # Gather all moderation actions for the specific user
        modlogs = getattr(guild_config, "modlog", [])
        warns = getattr(guild_config, "warns", [])
        mutes = getattr(guild_config, "mutes", [])
        tempbans = getattr(guild_config, "tempbans", [])
        kicks = getattr(guild_config, "kicks", []) if hasattr(guild_config, "kicks") else []
        softbans = (
            getattr(guild_config, "softbans", []) if hasattr(guild_config, "softbans") else []
        )
        notes = getattr(guild_config, "notes", [])

        user_id = str(user.id)
        entries = []

        # Filter modlogs for this user
        for m in modlogs:
            if isinstance(m, dict) and m.get("member_id") == user_id:
                moderator = ctx.guild.get_member(int(m.get("moderator_id", 0)))
                mod_name = moderator.mention if moderator else f"<@{m.get('moderator_id', 0)}>"
                target_name = user.mention if hasattr(user, "mention") else f"<@{user_id}>"
                reason = m.get("reason", "No reason provided")
                case_number = m.get("case_number", 0)
                date = m.get("date", "Unknown")
                entries.append(
                    {
                        "date": date,
                        "case_number": case_number,
                        "type": "modlog",
                        "text": f"{date} Case #{case_number}: {target_name} by {mod_name} - {reason} [modlog]",
                    }
                )

        # Filter warns for this user
        for w in warns:
            if isinstance(w, dict) and w.get("member_id") == user_id:
                moderator = ctx.guild.get_member(int(w.get("moderator_id", 0)))
                mod_name = moderator.mention if moderator else f"<@{w.get('moderator_id', 0)}>"
                target_name = user.mention if hasattr(user, "mention") else f"<@{user_id}>"
                reason = w.get("reason", "No reason provided")
                case_number = w.get("case_number", 0)
                date = w.get("date", "Unknown")
                entries.append(
                    {
                        "date": date,
                        "case_number": case_number,
                        "type": "warn",
                        "text": f"{date} Warn #{case_number}: {target_name} by {mod_name} - {reason} [warn]",
                    }
                )

        # Filter mutes for this user
        for mute in mutes:
            if isinstance(mute, dict) and mute.get("member") == user_id:
                target_name = user.mention if hasattr(user, "mention") else f"<@{user_id}>"
                until = mute.get("time")
                until_str = f"until <t:{int(until)}:F>" if until else "indefinite"
                case_number = mute.get("case_number", 0)
                date = mute.get("date", "Unknown")
                entries.append(
                    {
                        "date": date,
                        "case_number": case_number,
                        "type": "mute",
                        "text": f"{date} Mute: {target_name} {until_str} [mute]",
                    }
                )

        # Filter tempbans for this user
        for tb in tempbans:
            if isinstance(tb, dict) and tb.get("member") == user_id:
                target_name = user.mention if hasattr(user, "mention") else f"<@{user_id}>"
                until = tb.get("time")
                until_str = f"until <t:{int(until)}:F>" if until else "indefinite"
                case_number = tb.get("case_number", 0)
                date = tb.get("date", "Unknown")
                entries.append(
                    {
                        "date": date,
                        "case_number": case_number,
                        "type": "tempban",
                        "text": f"{date} Tempban: {target_name} {until_str} [tempban]",
                    }
                )

        # Filter kicks for this user
        for k in kicks:
            if isinstance(k, dict) and k.get("member_id") == user_id:
                moderator = ctx.guild.get_member(int(k.get("moderator_id", 0)))
                mod_name = moderator.mention if moderator else f"<@{k.get('moderator_id', 0)}>"
                target_name = user.mention if hasattr(user, "mention") else f"<@{user_id}>"
                reason = k.get("reason", "No reason")
                case_number = k.get("case_number", 0)
                date = k.get("date", "Unknown")
                entries.append(
                    {
                        "date": date,
                        "case_number": case_number,
                        "type": "kick",
                        "text": f"{date} Kick: {target_name} by {mod_name} - {reason} [kick]",
                    }
                )

        # Filter softbans for this user
        for sb in softbans:
            if isinstance(sb, dict) and sb.get("member_id") == user_id:
                moderator = ctx.guild.get_member(int(sb.get("moderator_id", 0)))
                mod_name = moderator.mention if moderator else f"<@{sb.get('moderator_id', 0)}>"
                target_name = user.mention if hasattr(user, "mention") else f"<@{user_id}>"
                reason = sb.get("reason", "No reason")
                case_number = sb.get("case_number", 0)
                date = sb.get("date", "Unknown")
                entries.append(
                    {
                        "date": date,
                        "case_number": case_number,
                        "type": "softban",
                        "text": f"{date} Softban: {target_name} by {mod_name} - {reason} [softban]",
                    }
                )

        # Filter notes for this user
        for note in notes:
            if isinstance(note, dict) and note.get("member_id") == user_id:
                moderator = ctx.guild.get_member(int(note.get("moderator_id", 0)))
                mod_name = moderator.mention if moderator else f"<@{note.get('moderator_id', 0)}>"
                target_name = user.mention if hasattr(user, "mention") else f"<@{user_id}>"
                note_text = note.get("note", "No note")
                case_number = note.get("case_number", 0)
                date = note.get("date", "Unknown")
                entries.append(
                    {
                        "date": date,
                        "case_number": case_number,
                        "type": "note",
                        "text": f"{date} Note #{case_number}: {target_name} by {mod_name} - {note_text} [note]",
                    }
                )

        if not entries:
            name = getattr(user, "name", str(user.id))
            if hasattr(user, "discriminator") and name != str(user.id):
                name += f"#{user.discriminator}"
            await ctx.send(f"No moderation logs found for {name}.")
            return

        # Sort by case number (newest first)
        entries_sorted = sorted(entries, key=lambda x: x.get("case_number", 0), reverse=True)

        # Paginate
        page_size = 10
        pages = [
            entries_sorted[i : i + page_size] for i in range(0, len(entries_sorted), page_size)
        ]
        total_pages = len(pages)

        name = getattr(user, "name", str(user.id))
        if hasattr(user, "discriminator") and name != str(user.id):
            name += f"#{user.discriminator}"

        def format_page(page, page_num):
            fmt = f"**Moderation logs for {name} (Page {page_num+1}/{total_pages}):**\n"
            for entry in page:
                fmt += entry["text"] + "\n"
            return fmt

        page_num = 0
        msg = await ctx.send(format_page(pages[page_num], page_num))

        if total_pages > 1:
            await msg.add_reaction("⬅️")
            await msg.add_reaction("➡️")

            def check(reaction, user_react):
                return (
                    user_react == ctx.author
                    and reaction.message.id == msg.id
                    and str(reaction.emoji) in ["⬅️", "➡️"]
                )

            while True:
                try:
                    reaction, user_react = await ctx.bot.wait_for(
                        "reaction_add", timeout=60.0, check=check
                    )
                except asyncio.TimeoutError:
                    break

                if str(reaction.emoji) == "➡️" and page_num < total_pages - 1:
                    page_num += 1
                    await msg.edit(content=format_page(pages[page_num], page_num))
                    await msg.remove_reaction(reaction, user_react)
                elif str(reaction.emoji) == "⬅️" and page_num > 0:
                    page_num -= 1
                    await msg.edit(content=format_page(pages[page_num], page_num))
                    await msg.remove_reaction(reaction, user_react)
                else:
                    await msg.remove_reaction(reaction, user_react)

    @modlogs.command(name="all")
    async def modlogs_all(self, ctx: commands.Context) -> None:
        """**View all modlogs in the server**

        This command displays a paginated list of all moderation logs for the entire server.

        **Usage:**
        `{prefix}modlogs all`
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        # Gather all moderation actions
        modlogs = getattr(guild_config, "modlog", [])
        warns = getattr(guild_config, "warns", [])
        mutes = getattr(guild_config, "mutes", [])
        tempbans = getattr(guild_config, "tempbans", [])
        kicks = getattr(guild_config, "kicks", []) if hasattr(guild_config, "kicks") else []
        softbans = (
            getattr(guild_config, "softbans", []) if hasattr(guild_config, "softbans") else []
        )

        entries = []

        # Modlogs
        for m in modlogs:
            if not isinstance(m, dict):
                continue
            member = ctx.guild.get_member(int(m.get("member_id", 0)))
            member_name = member.mention if member else f"<@{m.get('member_id', 0)}>"
            moderator = ctx.guild.get_member(int(m.get("moderator_id", 0)))
            mod_name = moderator.mention if moderator else f"<@{m.get('moderator_id', 0)}>"
            reason = m.get("reason", "No reason provided")
            case_number = m.get("case_number", 0)
            date = m.get("date", "Unknown")
            entries.append(f"Case #{case_number}: {member_name} by {mod_name} - {reason} | {date}")

        # Warns
        for w in warns:
            if isinstance(w, dict):
                member = ctx.guild.get_member(int(w.get("member_id", 0)))
                member_name = member.mention if member else f"<@{w.get('member_id', 0)}>"
                moderator = ctx.guild.get_member(int(w.get("moderator_id", 0)))
                mod_name = moderator.mention if moderator else f"<@{w.get('moderator_id', 0)}>"
                reason = w.get("reason", "No reason")
                case_number = w.get("case_number", 0)
                date = w.get("date", "Unknown")
                entries.append(
                    f"Warn #{case_number}: {member_name} by {mod_name} - {reason} | {date}"
                )

        # Mutes
        for mute in mutes:
            if isinstance(mute, dict):
                member_id = mute.get("member", "")
                member = ctx.guild.get_member(int(member_id)) if member_id else None
                member_name = member.mention if member else f"<@{member_id}>"
                until = mute.get("time")
                until_str = f"until <t:{int(until)}:F>" if until else "indefinite"
                date = mute.get("date", "Unknown")
                entries.append(f"Mute: {member_name} {until_str} | {date}")

        # Tempbans
        for tb in tempbans:
            if isinstance(tb, dict):
                member_id = tb.get("member", "")
                member = ctx.guild.get_member(int(member_id)) if member_id else None
                member_name = member.mention if member else f"<@{member_id}>"
                until = tb.get("time")
                until_str = f"until <t:{int(until)}:F>" if until else "indefinite"
                date = tb.get("date", "Unknown")
                entries.append(f"Tempban: {member_name} {until_str} | {date}")

        # Kicks
        for k in kicks:
            if isinstance(k, dict):
                member_id = k.get("member_id", "")
                member = ctx.guild.get_member(int(member_id)) if member_id else None
                member_name = member.mention if member else f"<@{member_id}>"
                moderator = ctx.guild.get_member(int(k.get("moderator_id", 0)))
                mod_name = moderator.mention if moderator else f"<@{k.get('moderator_id', 0)}>"
                reason = k.get("reason", "No reason")
                case_number = k.get("case_number", 0)
                date = k.get("date", "Unknown")
                entries.append(
                    f"Kick #{case_number}: {member_name} by {mod_name} - {reason} | {date}"
                )

        # Softbans
        for sb in softbans:
            if isinstance(sb, dict):
                member_id = sb.get("member_id", "")
                member = ctx.guild.get_member(int(member_id)) if member_id else None
                member_name = member.mention if member else f"<@{member_id}>"
                moderator = ctx.guild.get_member(int(sb.get("moderator_id", 0)))
                mod_name = moderator.mention if moderator else f"<@{sb.get('moderator_id', 0)}>"
                reason = sb.get("reason", "No reason")
                case_number = sb.get("case_number", 0)
                date = sb.get("date", "Unknown")
                entries.append(
                    f"Softban #{case_number}: {member_name} by {mod_name} - {reason} | {date}"
                )

        if not entries:
            await ctx.send("No moderation logs found.")
            return

        # Paginate 10 per page
        pages = [entries[i : i + 10] for i in range(0, len(entries), 10)]
        page_num = 0
        msg = await ctx.send(
            f"**All Modlogs (Page {page_num + 1}/{len(pages)}):**\n" + "\n".join(pages[page_num])
        )

        if len(pages) > 1:
            await msg.add_reaction("⬅️")
            await msg.add_reaction("➡️")

            def check(reaction, user):
                return (
                    user == ctx.author
                    and reaction.message.id == msg.id
                    and str(reaction.emoji) in ["⬅️", "➡️"]
                )

            while True:
                try:
                    reaction, user = await ctx.bot.wait_for(
                        "reaction_add", timeout=60.0, check=check
                    )
                    if str(reaction.emoji) == "➡️" and page_num < len(pages) - 1:
                        page_num += 1
                        await msg.edit(
                            content=f"**All Modlogs (Page {page_num + 1}/{len(pages)}):**\n"
                            + "\n".join(pages[page_num])
                        )
                        await msg.remove_reaction(reaction.emoji, user)
                    elif str(reaction.emoji) == "⬅️" and page_num > 0:
                        page_num -= 1
                        await msg.edit(
                            content=f"**All Modlogs (Page {page_num + 1}/{len(pages)}):**\n"
                            + "\n".join(pages[page_num])
                        )
                        await msg.remove_reaction(reaction.emoji, user)
                    else:
                        await msg.remove_reaction(reaction.emoji, user)
                except Exception:
                    break

    @modlogs.command(name="remove", aliases=["delete", "del"], usage="<case_number>")
    async def modlogs_remove(self, ctx: commands.Context, case_number: int = None) -> None:
        """**Remove a modlog entry by case number**

        This command removes a specific moderation log entry, identified by its case number.
        A confirmation is required before deletion.

        **Usage:**
        `{prefix}modlogs remove <case_number>`

        **<case_number>:**
        The case number of the modlog entry to remove.

        **Example:**
        `{prefix}modlogs remove 123`
        """
        if case_number is None:
            prefix = getattr(ctx, "prefix", "!!")
            await ctx.send(
                f"❌ Please provide a case number to remove.\n"
                f"Usage: `{prefix}modlogs remove <case_number>`\n"
                f"Example: `{prefix}modlogs remove 123`"
            )
            return

        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)

        # Search across all moderation arrays
        modlogs = getattr(guild_config, "modlog", [])
        warns = getattr(guild_config, "warns", [])
        kicks = getattr(guild_config, "kicks", [])
        softbans = getattr(guild_config, "softbans", [])
        bans = getattr(guild_config, "bans", [])
        mutes = getattr(guild_config, "mutes", [])
        unmutes = getattr(guild_config, "unmutes", [])
        notes = getattr(guild_config, "notes", [])

        entry = None
        entry_type = None

        # Check modlogs
        for m in modlogs:
            if isinstance(m, dict) and m.get("case_number") == case_number:
                entry = m
                entry_type = "modlog"
                break

        # Check warns
        if not entry:
            for w in warns:
                if isinstance(w, dict) and w.get("case_number") == case_number:
                    entry = w
                    entry_type = "warns"
                    break

        # Check kicks
        if not entry:
            for k in kicks:
                if isinstance(k, dict) and k.get("case_number") == case_number:
                    entry = k
                    entry_type = "kicks"
                    break

        # Check softbans
        if not entry:
            for sb in softbans:
                if isinstance(sb, dict) and sb.get("case_number") == case_number:
                    entry = sb
                    entry_type = "softbans"
                    break

        # Check bans
        if not entry:
            for b in bans:
                if isinstance(b, dict) and b.get("case_number") == case_number:
                    entry = b
                    entry_type = "bans"
                    break

        # Check mutes
        if not entry:
            for m in mutes:
                if isinstance(m, dict) and m.get("case_number") == case_number:
                    entry = m
                    entry_type = "mutes"
                    break

        # Check unmutes
        if not entry:
            for u in unmutes:
                if isinstance(u, dict) and u.get("case_number") == case_number:
                    entry = u
                    entry_type = "unmutes"
                    break

        # Check notes
        if not entry:
            for n in notes:
                if isinstance(n, dict) and n.get("case_number") == case_number:
                    entry = n
                    entry_type = "notes"
                    break

        if not entry:
            await ctx.send(f"❌ Case #{case_number} does not exist.")
            return

        # Prepare details for confirmation
        member = (
            ctx.guild.get_member(int(entry.get("member_id", 0)))
            or f"<@{entry.get('member_id', 0)}>"
        )
        moderator = ctx.guild.get_member(int(entry.get("moderator_id", 0)))
        moderator_mention = moderator.mention if moderator else f"<@{entry.get('moderator_id', 0)}>"
        reason = entry.get("reason", entry.get("note", "No reason provided"))
        date = entry.get("date", "Unknown")

        embed = discord.Embed(
            title="Confirm Entry Removal",
            description=(
                f"Are you sure you want to remove {entry_type.title()} #{case_number}?\n\n"
                f"**Target:** {member}\n"
                f"**Reason:** {reason}\n"
                f"**Original Moderator:** {moderator_mention}\n"
                f"**Date:** {date}"
            ),
            color=discord.Color.red(),
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
            reaction, user = await ctx.bot.wait_for("reaction_add", timeout=30.0, check=check)
            if str(reaction.emoji) == "✅":
                await self.bot.db.update_guild_config(
                    ctx.guild.id, {"$pull": {entry_type: {"case_number": case_number}}}
                )
                await msg.edit(
                    embed=discord.Embed(
                        title="Entry Removed",
                        description=f"{entry_type.title()} #{case_number} has been successfully removed.",
                        color=discord.Color.green(),
                    )
                )
            else:
                await msg.edit(
                    embed=discord.Embed(
                        title="Entry Removal Cancelled",
                        description="Entry removal cancelled by user.",
                        color=discord.Color.red(),
                    )
                )
        except asyncio.TimeoutError:
            await msg.edit(
                embed=discord.Embed(
                    title="Entry Removal Cancelled",
                    description="Entry removal timed out. Command cancelled.",
                    color=discord.Color.red(),
                )
            )

    @modlogs.command(name="purge")
    async def modlogs_purge(self, ctx: commands.Context, user: MemberOrID) -> None:
        """**Delete all modlogs for a user**

        This command will remove all moderation logs for a given user. This is a destructive action and cannot be undone.

        **Usage:**
        `{prefix}modlogs purge <user>`

        **<user>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`
        """
        user_id = str(user.id)
        name = getattr(user, "name", str(user.id))
        if hasattr(user, "discriminator") and name != str(user.id):
            name += f"#{user.discriminator}"

        embed = discord.Embed(
            title="Confirm Modlog Purge",
            description=(
                f"Are you sure you want to delete all moderation logs for {name} ({user_id})?\n\n"
                "**This action is irreversible.**"
            ),
            color=discord.Color.red(),
        )
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        def check(reaction, u):
            return (
                u == ctx.author
                and str(reaction.emoji) in ["✅", "❌"]
                and reaction.message.id == msg.id
            )

        try:
            reaction, u = await ctx.bot.wait_for("reaction_add", timeout=30.0, check=check)
            if str(reaction.emoji) == "✅":
                guild_config = await self.bot.db.get_guild_config(ctx.guild.id)

                update_payload = {}
                log_types = [
                    "modlog",
                    "warns",
                    "mutes",
                    "tempbans",
                    "kicks",
                    "softbans",
                    "bans",
                    "notes",
                ]
                member_id_fields = {
                    "modlog": "member_id",
                    "warns": "member_id",
                    "mutes": "member",
                    "tempbans": "member",
                    "kicks": "member_id",
                    "softbans": "member_id",
                    "bans": "member_id",
                    "notes": "member_id",
                }

                deleted_counts = {}

                for log_type in log_types:
                    id_field = member_id_fields[log_type]
                    original_list = getattr(guild_config, log_type, [])
                    if original_list:
                        new_list = [
                            entry
                            for entry in original_list
                            if isinstance(entry, dict) and entry.get(id_field) != user_id
                        ]
                        update_payload[log_type] = new_list
                        deleted_counts[log_type] = len(original_list) - len(new_list)

                if update_payload:
                    await self.bot.db.update_guild_config(ctx.guild.id, {"$set": update_payload})

                deleted_summary = "\n".join(
                    [
                        f"• {log_type.title()}: {count}"
                        for log_type, count in deleted_counts.items()
                        if count > 0
                    ]
                )
                if not deleted_summary:
                    deleted_summary = "No logs found to delete."

                await msg.edit(
                    embed=discord.Embed(
                        title="Modlogs Purged",
                        description=f"All moderation logs for {name} ({user_id}) have been deleted.\n\n**Deleted Entries:**\n{deleted_summary}",
                        color=discord.Color.green(),
                    )
                )
            else:
                await msg.edit(
                    embed=discord.Embed(
                        title="Modlog Purge Cancelled",
                        description="Modlog purge cancelled by user.",
                        color=discord.Color.red(),
                    )
                )
        except asyncio.TimeoutError:
            await msg.edit(
                embed=discord.Embed(
                    title="Modlog Purge Cancelled",
                    description="Modlog purge timed out. Command cancelled.",
                    color=discord.Color.red(),
                )
            )

    async def cog_error(self, ctx: commands.Context, error: Exception) -> None:
        """Handles discord.Forbidden"""

    async def send_log(self, ctx: commands.Context, *args) -> None:
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        offset = guild_config.time_offset
        current_time = (
            f"<t:{int((ctx.message.created_at + timedelta(hours=offset)).timestamp())}:T>"
        )

        modlogs = guild_config.modlog
        if isinstance(modlogs, list):
            modlogs = {i["name"]: i["value"] for i in modlogs}

        modlogs = DBDict(
            {i: tryint(modlogs[i]) for i in modlogs if i},
            _default=DEFAULT["modlog"],
        )

        try:
            if ctx.command.name == "purge":
                fmt = f"{current_time} {ctx.author} purged {args[0]} messages in **#{ctx.channel.name}**"
                if args[1]:
                    fmt += f", from {args[1]}"
                channel = ctx.bot.get_channel(modlogs.message_purge)
                if channel and hasattr(channel, "send"):
                    await channel.send(fmt)
            elif ctx.command.name == "kick":
                fmt = f"{current_time} {ctx.author} kicked {args[0]} ({args[0].id}), reason: {args[1]}"
                channel = ctx.bot.get_channel(modlogs.member_kick)
                if channel and hasattr(channel, "send"):
                    await channel.send(fmt)
                else:
                    # DEBUG: Could not log to channel. Check your modlogs config or bot permissions.
                    pass
            elif ctx.command.name == "softban":
                fmt = f"{current_time} {ctx.author} softbanned {args[0]} ({args[0].id}), reason: {args[1]}"
                channel = ctx.bot.get_channel(modlogs.member_softban)
                if channel:
                    await channel.send(fmt)
            elif ctx.command.name == "ban":
                name = getattr(args[0], "name", "(no name)")
                if args[2]:
                    fmt = f"{current_time} {ctx.author} tempbanned {name} ({args[0].id}), reason: {args[1]} for {format_timedelta(args[2])}"
                else:
                    fmt = f"{current_time} {ctx.author} banned {name} ({args[0].id}), reason: {args[1]}"
                channel = ctx.bot.get_channel(modlogs.member_ban)
                if channel:
                    await channel.send(fmt)
            elif ctx.command.name == "unban":
                name = getattr(args[0], "name", "(no name)")
                fmt = (
                    f"{current_time} {ctx.author} unbanned {name} ({args[0].id}), reason: {args[1]}"
                )
                channel = ctx.bot.get_channel(modlogs.member_unban)
                if channel:
                    await channel.send(fmt)
            elif ctx.command.qualified_name == "modlogs remove":
                channel_id = getattr(modlogs, "member_warn", None)
                channel = ctx.bot.get_channel(channel_id) if channel_id else None
                if channel and hasattr(channel, "send"):
                    fmt = (
                        f"{current_time} {ctx.author} removed modlog case #{args[0]}: Reason: {args[1]}, "
                        f"Target: <@{args[2]}>, Moderator: <@{args[3]}>"
                    )
                    await channel.send(fmt)
                else:
                    print(
                        f"[send_log] Cannot find a valid channel for modlogs remove. ID: {channel_id}, channel: {channel}"
                    )
            elif ctx.command.qualified_name == "warn":
                fmt = f"{current_time} {ctx.author} warned {args[0].mention} (#{args[2]}), reason: {args[1]}"
                channel = ctx.bot.get_channel(modlogs.member_warn)
                if channel and hasattr(channel, "send"):
                    await channel.send(fmt)
                else:
                    # You may want to log this event for debugging
                    pass
            elif ctx.command.qualified_name == "warn remove":
                fmt = f"{current_time} {ctx.author} has deleted warn #{args[0]} - {args[1]}"
                channel = ctx.bot.get_channel(modlogs.member_warn)
                if channel and hasattr(channel, "send"):
                    await channel.send(fmt)
            elif ctx.command.name == "lockdown":
                fmt = f'{current_time} {ctx.author} has {"enabled" if args[0] else "disabled"} lockdown for {args[1].mention}'
                channel = ctx.bot.get_channel(modlogs.channel_lockdown)
                if channel:
                    await channel.send(fmt)
            elif ctx.command.name == "slowmode":
                fmt = f"{current_time} {ctx.author} has enabled slowmode for {args[0].mention} for {args[1]}"
                channel = ctx.bot.get_channel(modlogs.channel_slowmode)
                if channel:
                    await channel.send(fmt)
            elif ctx.command.name == "mute":
                name = getattr(args[0], "name", "(no name)")
                if args[2]:
                    fmt = f"{current_time} {ctx.author} muted {name} ({args[0].id}), reason: {args[1]} for {format_timedelta(args[2])}"
                else:
                    fmt = f"{current_time} {ctx.author} muted {name} ({args[0].id}), reason: {args[1]}"
                channel = ctx.bot.get_channel(modlogs.member_mute)
                if channel:
                    await channel.send(fmt)
            elif ctx.command.name == "unmute":
                name = getattr(args[0], "name", "(no name)")
                fmt = (
                    f"{current_time} {ctx.author} unmuted {name} ({args[0].id}), reason: {args[1]}"
                )
                channel = ctx.bot.get_channel(modlogs.member_unmute)
                if channel:
                    await channel.send(fmt)
            else:
                raise NotImplementedError(
                    f"{ctx.command.name} not implemented for commands/send_log"
                )
        except AttributeError:
            # channel not found [None.send()]
            pass

    @command(5)
    async def user(self, ctx: commands.Context, member: discord.Member) -> None:
        """**Get information about a user**

        This command displays detailed information about a server member, including their roles, join date, and account creation date.

        **Usage:**
        `{prefix}user <member>`

        **<member>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`

        **Example:**
        `{prefix}user @TestUser`
        """

        async def timestamp(created):
            delta = format_timedelta(ctx.message.created_at - created)
            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            created = created + timedelta(hours=guild_config.time_offset)
            return f"{delta} ago (<t:{int(created.timestamp())}:T>)"

        created = await timestamp(member.created_at)
        joined = await timestamp(member.joined_at) if member.joined_at else "Unknown"
        member_info = f"**Joined** {joined}\n"

        for n, i in enumerate(reversed(member.roles)):
            if i != ctx.guild.default_role:
                if n == 0:
                    member_info += "**Roles**: "
                member_info += i.name
                if n != len(member.roles) - 2:
                    member_info += ", "
                else:
                    member_info += "\n"

        em = discord.Embed(color=member.color)
        em.set_author(name=str(member), icon_url=str(member.display_avatar.url))
        em.add_field(
            name="Basic Information",
            value=f"**ID**: {member.id}\n**Nickname**: {member.nick}\n**Mention**: {member.mention}\n**Created** {created}",
            inline=False,
        )
        em.add_field(name="Member Information", value=member_info, inline=False)
        await ctx.send(embed=em)

    @group(6, invoke_without_command=True, usage="<member> <note>")
    async def note(
        self,
        ctx: commands.Context,
        member: MemberOrID = None,
        *,
        note: CannedStr = None,
    ) -> None:
        """**Manage notes for users**

        This command allows you to add, remove, and view notes about users.
        Notes are visible to moderators and can be used to track user behavior.

        **Usage:**
        `{prefix}note <member> <note>`

        **<member>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`

        **<note>:**
        The content of the note.

        **Subcommands:**
        - `remove` - Remove a note from a user.
        - `list` - List all notes for a user.

        **Example:**
        `{prefix}note @TestUser Investigating potential alt account.`
        """
        if ctx.invoked_subcommand is None:
            if member is None:
                await ctx.invoke(self.bot.get_command("help"), command_or_cog="note")
                return
            await self.add.callback(self, ctx, member=member, note=note)

    @note.command()
    async def add(self, ctx: commands.Context, member: MemberOrID, *, note: CannedStr):
        """**Add a note to a user**

        This command adds a private note to a user's record.

        **Usage:**
        `{prefix}note add <member> <note>`

        **<member>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`

        **<note>:**
        The content of the note.

        **Example:**
        `{prefix}note add @TestUser Investigating potential alt account.`
        """
        if (
            get_perm_level(self.bot, member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(
                self.bot, ctx.author, await self.bot.db.get_guild_config(ctx.guild.id)
            )[0]
        ):
            await ctx.send("You do not have permission to add a note to this user.")
        else:
            guild_data = await self.bot.db.get_guild_config(ctx.guild.id)
            notes = guild_data.notes

            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            current_date = f"<t:{int((ctx.message.created_at + timedelta(hours=guild_config.time_offset)).timestamp())}:D>"
            if not notes:
                case_number = 1
            else:
                case_number = notes[-1]["case_number"] + 1 if notes else 1

            push = {
                "case_number": case_number,
                "date": current_date,
                "member_id": str(member.id),
                "moderator_id": str(ctx.author.id),
                "note": note,
            }
            await self.bot.db.update_guild_config(ctx.guild.id, {"$push": {"notes": push}})
            await ctx.send(f"Note #{case_number} has been added for {member.mention}: {note}")

    @note.command(aliases=["delete", "del"])
    async def remove(self, ctx: commands.Context, case_number: int) -> None:
        """**Remove a note from a user**

        This command removes a note from a user's record, identified by its case number.

        **Usage:**
        `{prefix}note remove <case_number>`

        **<case_number>:**
        The case number of the note to remove.

        **Example:**
        `{prefix}note remove 456`
        """
        guild_data = await self.bot.db.get_guild_config(ctx.guild.id)
        notes = guild_data.notes
        note_to_remove = next(
            (note for note in notes if note.get("case_number") == case_number), None
        )

        if not note_to_remove:
            await ctx.send(f"Note #{case_number} does not exist.")
        else:
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$pull": {"notes": {"case_number": case_number}}}
            )
            member_id = note_to_remove.get("member_id")
            await ctx.send(f"Note #{case_number} has been removed from <@{member_id}>.")

    @note.command(name="list", aliases=["view"])
    async def _list(self, ctx: commands.Context, member: MemberOrID) -> None:
        """**View the notes of a user**

        This command displays all notes that have been added to a user's record.

        **Usage:**
        `{prefix}note list <member>`

        **<member>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`

        **Example:**
        `{prefix}note list @TestUser`
        """
        guild_data = await self.bot.db.get_guild_config(ctx.guild.id)
        notes = guild_data.notes
        user_notes = [note for note in notes if note.get("member_id") == str(member.id)]
        name = getattr(member, "name", str(member.id))
        if hasattr(member, "discriminator") and name != str(member.id):
            name += f"#{member.discriminator}"

        if not user_notes:
            await ctx.send(f"{name} has no notes.")
        else:
            embed = discord.Embed(title=f"Notes for {name}", color=discord.Color.blue())
            for note in user_notes:
                moderator = ctx.guild.get_member(int(note.get("moderator_id", 0)))
                moderator_name = (
                    moderator.mention if moderator else f"<@{note.get('moderator_id', 'Unknown')}>"
                )
                embed.add_field(
                    name=f"Note #{note.get('case_number', 'N/A')} on {note.get('date', 'Unknown Date')}",
                    value=f"**Moderator:** {moderator_name}\n**Note:** {note.get('note', 'N/A')}",
                    inline=False,
                )
            await ctx.send(embed=embed)

    @command(8, usage="<threshold> <punishment> [duration]")
    async def setwarnpunishment(
        self,
        ctx: commands.Context,
        threshold: int,
        punishment: str,
        duration: str = None,
    ) -> None:
        """**Set an automatic punishment for reaching a warning threshold**

        **Usage:**
        `{prefix}setwarnpunishment <threshold> <punishment> [duration]`

        **<threshold>:**
        The number of warnings required to trigger the punishment.

        **<punishment>:**
        The action to take. Can be `mute`, `kick`, `softban`, `ban`, or `tempban`.

        **[duration]:**
        - Required for `mute` and `tempban`.
        - Example: `1h`, `7d`.

        **Examples:**
        - `{prefix}setwarnpunishment 3 kick`
        - `{prefix}setwarnpunishment 5 mute 1h`
        - `{prefix}setwarnpunishment 10 ban`
        """
        punishment = punishment.lower()
        if punishment not in ["mute", "kick", "softban", "ban", "tempban"]:
            await ctx.send(
                "Invalid punishment type. Must be one of: `mute`, `kick`, `softban`, `ban`, `tempban`."
            )
            return

        if punishment in ["mute", "tempban"] and not duration:
            await ctx.send(f"You must provide a duration for the `{punishment}` punishment.")
            return

        punishment_config = {
            "threshold": threshold,
            "action": punishment,
        }

        if duration:
            try:
                time_converter = UserFriendlyTime()
                time_obj = await time_converter.convert(ctx, duration)
                if time_obj.dt:
                    punishment_config["duration"] = (
                        time_obj.dt - ctx.message.created_at
                    ).total_seconds()
            except commands.BadArgument:
                await ctx.send(f"Invalid duration format. Use formats like '1h', '30m', '2d'.")
                return

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$set": {"warn_punishment": punishment_config}}
        )

        duration_str = (
            f" for {format_timedelta(timedelta(seconds=punishment_config['duration']))}"
            if "duration" in punishment_config
            else ""
        )
        await ctx.send(
            f"Set automatic punishment to `{punishment}{duration_str}` at `{threshold}` warnings."
        )

    @group(6, invoke_without_command=True, usage="<member> <reason>")
    async def warn(
        self,
        ctx: commands.Context,
        member: MemberOrID = None,
        *,
        reason: CannedStr = None,
    ) -> None:
        """**Warn a user or manage warnings**

        This command allows you to warn a user.
        You can also use subcommands to manage warnings.

        **Usage:**
        `{prefix}warn <member> <reason>`

        **<member>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`

        **<reason>:**
        The reason for the warning.

        **Subcommands:**
        - `remove` - Remove a warning from a user.
        - `list` - List all warnings for a user.
        - `clear` - Clear all warnings from a user.
        """
        if ctx.invoked_subcommand is None:
            if member is None:
                await ctx.invoke(self.bot.get_command("help"), command_or_cog="warn")
                return

            reason = reason or "No reason provided."

            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            if (
                get_perm_level(self.bot, member, guild_config)[0]
                >= get_perm_level(self.bot, ctx.author, guild_config)[0]
            ):
                await ctx.send("User has insufficient permissions")
            else:
                guild_warns = guild_config.warns
                warns = list(filter(lambda w: w["member_id"] == str(member.id), guild_warns))

                num_warns = len(warns) + 1
                fmt = f"You have been warned in **{ctx.guild.name}**, reason: {reason}. This is warning #{num_warns}."

                dm_send_error = None
                try:
                    await member.send(fmt)
                except discord.Forbidden:
                    dm_send_error = "The user has PMs disabled or blocked the bot."
                except discord.NotFound:
                    dm_send_error = f"Could not find user with ID `{member.id}`."

                current_date = f"<t:{int((ctx.message.created_at + timedelta(hours=guild_config.time_offset)).timestamp())}:D>"
                if not guild_warns:
                    case_number = 1
                else:
                    case_number = guild_warns[-1]["case_number"] + 1
                push = {
                    "case_number": case_number,
                    "date": current_date,
                    "member_id": str(member.id),
                    "moderator_id": str(ctx.author.id),
                    "reason": reason,
                }
                await self.bot.db.update_guild_config(ctx.guild.id, {"$push": {"warns": push}})

                if ctx.author != ctx.guild.me:
                    if dm_send_error:
                        await ctx.send(
                            f"Warned {member.mention} (#{case_number}) for: {reason}\nNOTE: {dm_send_error}"
                        )
                    else:
                        await ctx.send(f"Warned {member.mention} (#{case_number}) for: {reason}")

                await self.send_log(ctx, member, reason, case_number)

                if dm_send_error and "Could not find user" in dm_send_error:
                    return

                # Check for automatic punishment
                punishment_config = getattr(guild_config, "warn_punishment", None)
                if punishment_config and isinstance(member, discord.Member):
                    threshold = punishment_config.get("threshold")
                    if threshold and threshold > 0 and num_warns % threshold == 0:
                        action = punishment_config["action"]
                        duration_seconds = punishment_config.get("duration")
                        duration = timedelta(seconds=duration_seconds) if duration_seconds else None
                        punishment_reason = (
                            f"Automatic punishment for reaching {num_warns} warnings."
                        )
                        duration_str = f" for {format_timedelta(duration)}" if duration else ""

                        embed = discord.Embed(
                            title="Confirm Automatic Punishment",
                            description=(
                                f"{member.mention} has reached {num_warns} warnings.\n"
                                f"The configured punishment is **{action.capitalize()}{duration_str}**.\n\n"
                                f"Do you want to apply this punishment?"
                            ),
                            color=discord.Color.orange(),
                        )
                        confirm_msg = await ctx.send(embed=embed)
                        await confirm_msg.add_reaction("✅")
                        await confirm_msg.add_reaction("❌")

                        def check(reaction, user):
                            return (
                                user == ctx.author
                                and str(reaction.emoji) in ["✅", "❌"]
                                and reaction.message.id == confirm_msg.id
                            )

                        try:
                            reaction, user = await self.bot.wait_for(
                                "reaction_add", timeout=60.0, check=check
                            )

                            if str(reaction.emoji) == "✅":
                                # Add a note about the punishment
                                await self.note.get_command("add").callback(
                                    self, ctx, member=member, note=punishment_reason
                                )

                                # Apply punishment
                                await confirm_msg.edit(
                                    embed=discord.Embed(
                                        title="Punishment Confirmed",
                                        description=f"Applying punishment to {member.mention}...",
                                        color=discord.Color.green(),
                                    )
                                )
                                if action == "kick":
                                    await self._perform_kick(ctx, member, punishment_reason)
                                elif action == "softban":
                                    await self._perform_softban(ctx, member, punishment_reason)
                                elif action == "ban":
                                    await self._perform_ban(ctx, member, punishment_reason)
                                elif action == "tempban":
                                    await self._perform_ban(
                                        ctx, member, punishment_reason, duration
                                    )
                                elif action == "mute":
                                    await self._perform_mute(
                                        ctx, member, punishment_reason, duration
                                    )

                            else:  # User reacted with ❌
                                await confirm_msg.edit(
                                    embed=discord.Embed(
                                        title="Punishment Cancelled",
                                        description="The automatic punishment was cancelled by the moderator.",
                                        color=discord.Color.red(),
                                    )
                                )

                        except asyncio.TimeoutError:
                            await confirm_msg.edit(
                                embed=discord.Embed(
                                    title="Punishment Cancelled",
                                    description="Confirmation timed out. The automatic punishment was not applied.",
                                    color=discord.Color.red(),
                                )
                            )

    @warn.command(name="remove", aliases=["delete", "del"])
    async def remove_(self, ctx: commands.Context, case_number: int) -> None:
        """**Remove a warning from a user**

        This command removes a warning from a user's record, identified by its case number.

        **Usage:**
        `{prefix}warn remove <case_number>`

        **<case_number>:**
        The case number of the warning to remove.

        **Example:**
        `{prefix}warn remove 789`
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        warns = guild_config.warns
        warn = next((w for w in warns if w.get("case_number") == case_number), None)
        if not warn:
            await ctx.send("Warning not found.")
            return
        warn_reason = warn["reason"]

        if not warn:
            await ctx.send(f"Warn #{case_number} does not exist.")
        else:
            await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"warns": warn}})
            await ctx.send(f"Warn #{case_number} removed from <@{warn['member_id']}>.")
            await self.send_log(ctx, case_number, warn_reason)

    @warn.command(name="clear")
    async def clear_(self, ctx: commands.Context, member: MemberOrID) -> None:
        """**Clear all warnings from a user**

        This command removes all warnings from a user's record.

        **Usage:**
        `{prefix}warn clear <member>`

        **<member>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`

        **Example:**
        `{prefix}warn clear @TestUser`
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        warns = guild_config.warns
        user_warns = [w for w in warns if w.get("member_id") == str(member.id)]

        if not user_warns:
            await ctx.send(f"{member.mention} has no warnings to clear.")
            return

        await self.bot.db.update_guild_config(
            ctx.guild.id, {"$pull": {"warns": {"member_id": str(member.id)}}}
        )
        await ctx.send(f"Cleared all warnings for {member.mention}.")

    recently_kicked = set()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Clear a user's warns when they leave the server."""
        if member.id in self.recently_kicked:
            self.recently_kicked.remove(member.id)
            return

        await self.bot.db.update_guild_config(
            member.guild.id, {"$pull": {"warns": {"member_id": str(member.id)}}}
        )

    @warn.command(name="list", aliases=["view"])
    async def list_(self, ctx: commands.Context, member: MemberOrID) -> None:
        """**View the warnings of a user**

        This command displays all warnings that have been issued to a user.

        **Usage:**
        `{prefix}warn list <member>`

        **<member>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`

        **Example:**
        `{prefix}warn list @TestUser`
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        warns = guild_config.warns
        warns = list(filter(lambda w: w["member_id"] == str(member.id), warns))
        name = getattr(member, "name", str(member.id))
        if name != str(member.id):
            name += f"#{member.discriminator}"

        if not warns:
            await ctx.send(f"{name} has no warns.")
        else:
            fmt = f"**{name} has {len(warns)} warns.**"
            for warn in warns:
                moderator = ctx.guild.get_member(int(warn["moderator_id"]))
                fmt += f"\n`{warn['date']}` Warn #{warn['case_number']}: {moderator} warned {name} for {warn['reason']}"

            await ctx.send(fmt)

    @command(6, usage="<member> [duration] [reason]")
    async def mute(
        self,
        ctx: commands.Context,
        member: MemberOrID,
        *,
        time: UserFriendlyTime(assume_reason=True) = None,
    ) -> None:
        """**Mute a member**

        This command prevents a member from sending messages and speaking in voice channels.

        **Usage:**
        `{prefix}mute <member> [duration] [reason]`

        **<member>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`

        **[duration]:**
        - Optional duration for the mute (e.g., `1h`, `30m`).
        - If not provided, the mute will be indefinite.

        **[reason]:**
        - An optional reason for the mute.

        **Examples:**
        - `{prefix}mute @TestUser 1h Spamming.`
        - `{prefix}mute @TestUser Being disruptive.`
        """
        # Handle auto-punishment calls
        if getattr(ctx, "_dummy", False):
            duration = None
            reason = None
            if time:
                if time.dt:
                    # Ensure both datetimes have the same timezone info
                    msg_time = ctx.message.created_at
                    if msg_time.tzinfo is None:
                        msg_time = msg_time.replace(tzinfo=timezone.utc)
                    if time.dt.tzinfo is None:
                        time_dt = time.dt.replace(tzinfo=timezone.utc)
                    else:
                        time_dt = time.dt
                    duration = time_dt - msg_time
                if time.arg:
                    reason = time.arg
            if not isinstance(member, discord.Member):
                member_obj = ctx.guild.get_member(getattr(member, "id", member))
                if not member_obj:
                    self.logger.warning(
                        f"Attempted to auto-mute user not in guild: {getattr(member, 'id', member)}"
                    )
                    return
                member = member_obj
            return await self._perform_mute(ctx, member, reason, duration)

        # Parse duration and reason from time parameter
        duration = None
        reason = "No reason provided"
        if time:
            if time.dt:
                # Ensure both datetimes have the same timezone info
                msg_time = ctx.message.created_at
                if msg_time.tzinfo is None:
                    msg_time = msg_time.replace(tzinfo=timezone.utc)
                if time.dt.tzinfo is None:
                    time_dt = time.dt.replace(tzinfo=timezone.utc)
                else:
                    time_dt = time.dt
                duration = time_dt - msg_time
            if time.arg:
                reason = time.arg

        # Check permission level
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        if (
            get_perm_level(self.bot, member, guild_config)[0]
            >= get_perm_level(self.bot, ctx.author, guild_config)[0]
        ):
            await ctx.send("User has insufficient permissions")
            return

        # Get member object if they're in the server
        member_obj = None
        if isinstance(member, discord.Member):
            member_obj = member
        else:
            member_obj = ctx.guild.get_member(getattr(member, "id", member))

        # If member is in server, mute them directly
        if member_obj:
            try:
                await self.bot.mute(ctx.author, member_obj, duration, reason=reason)
                user_mention = member_obj.mention
                if duration:
                    await ctx.send(
                        f"{user_mention} has been muted for {format_timedelta(duration)}. Reason: {reason}"
                    )
                else:
                    await ctx.send(f"{user_mention} has been muted indefinitely. Reason: {reason}")
                await self.send_log(ctx, member_obj, reason, duration)
            except Exception as e:
                await ctx.send(f"Failed to mute {member_obj.mention}: {e}")
        else:
            # Store sticky mute for when they join
            user_id = str(getattr(member, "id", member))
            mute_time = None
            if duration:
                import time as time_module

                mute_time = time_module.time() + duration.total_seconds()

            await self.bot.db.update_guild_config(
                ctx.guild.id,
                {
                    "$push": {
                        "mutes": {
                            "member": user_id,
                            "time": mute_time,
                            "reason": reason,
                            "sticky": True,
                        }
                    }
                },
            )
            user_mention = f"<@{user_id}>"
            if duration:
                await ctx.send(
                    f"{user_mention} has been muted for {format_timedelta(duration)} (will be applied when they join). Reason: {reason}"
                )
            else:
                await ctx.send(
                    f"{user_mention} has been muted indefinitely (will be applied when they join). Reason: {reason}"
                )
            await self.send_log(ctx, member, reason, duration)

    @command(6, name="muted")
    async def muted(self, ctx: commands.Context) -> None:
        """**List currently muted members**

        This command displays a list of all members who are currently muted in the server.

        **Usage:**
        `{prefix}muted`
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        mutes = getattr(guild_config, "mutes", [])
        if not mutes:
            await ctx.send("No active mutes.")
            return
        lines = []
        for entry in mutes:
            user_id = int(entry.get("member", 0))
            until = entry.get("time")
            member = ctx.guild.get_member(user_id) or self.bot.get_user(user_id)
            name = getattr(member, "mention", f"`{user_id}`")
            if until:
                lines.append(f"• {name} until <t:{int(until)}:F>")
            else:
                lines.append(f"• {name} (indefinite)")
        await ctx.send("Active mutes:\n" + "\n".join(lines))

    @command(6)
    async def unmute(
        self, ctx: commands.Context, member: MemberOrID, *, reason: CannedStr = "No reason"
    ) -> None:
        """**Unmute a member**

        This command removes the mute from a member, allowing them to send messages and speak again.

        **Usage:**
        `{prefix}unmute <member> [reason]`

        **<member>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`

        **[reason]:**
        - An optional reason for the unmute.

        **Example:**
        `{prefix}unmute @TestUser Appealed successfully.`
        """
        # Check permission level only if they're in the server
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        if (
            get_perm_level(self.bot, member, guild_config)[0]
            >= get_perm_level(self.bot, ctx.author, guild_config)[0]
        ):
            await ctx.send("User has insufficient permissions")
        else:
            user_id = getattr(member, "id", member)
            await self.bot.unmute(ctx.guild.id, user_id, None, reason=reason)
            user_mention = getattr(member, "mention", f"<@{user_id}>")
            await ctx.send(f"{user_mention} has been unmuted. Reason: {reason}")
            await self.send_log(ctx, member, reason)

    @command(6, aliases=["clean", "prune"], usage="<limit> [member]")
    async def purge(self, ctx: commands.Context, limit: int, *, member: MemberOrID = None) -> None:
        """**Bulk delete messages**

        This command deletes a specified number of messages from the current channel.
        You can also target messages from a specific user.

        **Usage:**
        `{prefix}purge <limit> [member]`

        **<limit>:**
        The number of messages to delete (max 2000).

        **[member]:**
        - Optional: Mention a user or provide their ID to delete messages from only that user.

        **Examples:**
        - `{prefix}purge 50`
        - `{prefix}purge 100 @TestUser`
        """
        count = min(2000, limit)
        try:
            await ctx.message.delete()
        except discord.NotFound:
            pass

        retries = 0
        if member:
            while count > 0:
                retries += 1
                last_message = -1
                previous = None
                async for m in ctx.channel.history(limit=50):
                    if m.author.id == member.id:
                        last_message = previous
                        break
                    previous = m.id

                if last_message != -1:
                    if last_message:
                        before = discord.Object(last_message)
                    else:
                        before = None

                    try:
                        deleted = await ctx.channel.purge(
                            limit=count, check=lambda m: m.author.id == member.id, before=before
                        )
                    except discord.NotFound:
                        pass
                    else:
                        count -= len(deleted)
                else:
                    break

                if retries > 20:
                    break
        else:
            deleted = await ctx.channel.purge(limit=count)
            count -= len(deleted)

        await ctx.send(f"Deleted {limit - count} messages", delete_after=3)
        await self.send_log(ctx, limit - count, member)

    @command(6)
    async def lockdown(self, ctx: commands.Context, channel: discord.TextChannel = None) -> None:
        """**Toggle send permissions for @everyone in a channel**

        This command prevents the `@everyone` role from sending messages in a specified channel.
        Running it again will unlock the channel.

        **Usage:**
        `{prefix}lockdown [channel]`

        **[channel]:**
        - Optional: The channel to lock down. If not provided, the current channel will be used.

        **Examples:**
        - `{prefix}lockdown`
        - `{prefix}lockdown #general`
        """
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)

        if overwrite.send_messages is None or overwrite.send_messages:
            overwrite.send_messages = False
            try:
                await channel.set_permissions(
                    ctx.guild.default_role, send_messages=False, add_reactions=False
                )
            except discord.Forbidden:
                pass  # Skip if no permission
            except discord.HTTPException:
                pass  # Skip on API error
            await ctx.send(f"Lockdown {self.bot.accept}")
            enable = True
        else:
            # dont change to "not overwrite.send_messages"
            overwrite.send_messages = None
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
            await ctx.send(f"Un-lockdown {self.bot.accept}")
            enable = False

        await self.send_log(ctx, enable, channel)

    @command(6, usage="[duration] [channel]")
    async def slowmode(
        self,
        ctx: commands.Context,
        *,
        time: UserFriendlyTime,
    ) -> None:
        """**Enable or disable channel slowmode**

        This command sets a cooldown on how often users can send messages in a channel.

        **Usage:**
        `{prefix}slowmode <duration> [channel]`

        **<duration>:**
        - The length of the slowmode (e.g., `10s`, `5m`).
        - Use `0s` or `off` to disable slowmode.
        - Maximum is 6 hours.

        **[channel]:**
        - Optional: The channel to apply the slowmode to. Defaults to the current channel.

        **Examples:**
        - `{prefix}slowmode 10s`
        - `{prefix}slowmode 5m #general`
        - `{prefix}slowmode off`
        """
        duration = timedelta()
        channel = ctx.channel
        if time.dt:
            duration = time.dt - ctx.message.created_at
        if time.arg:
            if isinstance(time.arg, str):
                try:
                    channel = await commands.TextChannelConverter().convert(ctx, time.arg)
                except commands.BadArgument:
                    if time.arg != "off":
                        raise
            else:
                channel = time.arg

        seconds = int(duration.total_seconds())

        if seconds > 21600:
            await ctx.send("Slowmode only supports up to 6h max at the moment")
        else:
            fmt = format_timedelta(duration, assume_forever=False)
            await channel.edit(slowmode_delay=int(duration.total_seconds()))
            await self.send_log(ctx, channel, fmt)
            if duration.total_seconds():
                await ctx.send(f"Enabled `{fmt}` slowmode on {channel.mention}")
            else:
                await ctx.send(f"Disabled slowmode on {channel.mention}")

    async def _perform_kick(
        self, ctx: commands.Context, member: discord.Member, reason: str
    ) -> None:
        """Helper to kick a member without user confirmation."""
        if not ctx.guild.me.guild_permissions.kick_members:
            await ctx.send("I don't have permission to kick members.")
            return

        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(
                f"I cannot kick {member.mention} due to role hierarchy.", delete_after=10
            )
            return

        try:
            await self.alert_user(ctx, member, reason, action_name="kicked")
            self.recently_kicked.add(member.id)
            await member.kick(reason=reason)
            await ctx.send(f"{member.mention} has been kicked. Reason: {reason}")
            await self.send_log(ctx, member, reason)
        except discord.Forbidden:
            await ctx.send(f"I don't have permission to kick {member.mention}.", delete_after=10)
        except discord.HTTPException as e:
            await ctx.send(f"Failed to kick {member.mention}: {e}", delete_after=10)

    async def _perform_softban(
        self, ctx: commands.Context, member: discord.Member, reason: str
    ) -> None:
        """Helper to softban a member without user confirmation."""
        if not ctx.guild.me.guild_permissions.ban_members:
            await ctx.send("I don't have permission to ban members.")
            return

        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(
                f"I cannot softban {member.mention} due to role hierarchy.", delete_after=10
            )
            return

        try:
            await self.alert_user(ctx, member, reason, action_name="softbanned")
            self.recently_kicked.add(member.id)
            await member.ban(reason=reason, delete_message_days=1)
            await member.unban(reason="Softban punishment")
            await ctx.send(f"{member.mention} has been softbanned. Reason: {reason}")
            await self.send_log(ctx, member, reason)
        except discord.Forbidden:
            await ctx.send(f"I don't have permission to softban {member.mention}.", delete_after=10)
        except discord.HTTPException as e:
            await ctx.send(f"Failed to softban {member.mention}: {e}", delete_after=10)

    async def _perform_ban(
        self,
        ctx: commands.Context,
        member: Union[discord.Member, discord.User],
        reason: str,
        duration: timedelta = None,
    ) -> None:
        """Helper to ban a member without user confirmation."""
        if not ctx.guild.me.guild_permissions.ban_members:
            await ctx.send("I don't have permission to ban members.")
            return

        if isinstance(member, discord.Member) and member.top_role >= ctx.guild.me.top_role:
            await ctx.send(f"I cannot ban {member.mention} due to role hierarchy.", delete_after=10)
            return

        try:
            await self.alert_user(ctx, member, reason, action_name="banned")
            self.recently_kicked.add(member.id)
            await ctx.guild.ban(member, reason=reason, delete_message_days=1)

            if duration:
                seconds = duration.total_seconds()
                unban_time = time.time() + seconds
                await self.bot.db.update_guild_config(
                    ctx.guild.id,
                    {
                        "$push": {
                            "tempbans": {
                                "member": str(member.id),
                                "time": unban_time,
                            }
                        }
                    },
                )
                self.bot.loop.create_task(self.bot.unban(ctx.guild.id, member.id, unban_time))
                await ctx.send(
                    f"{member.mention} has been temporarily banned for {format_timedelta(duration)}. Reason: {reason}"
                )
            else:
                await ctx.send(f"{member.mention} has been permanently banned. Reason: {reason}")

            await self.send_log(ctx, member, reason, duration)
        except discord.Forbidden:
            await ctx.send(f"I don't have permission to ban {member.mention}.", delete_after=10)
        except discord.HTTPException as e:
            await ctx.send(f"Failed to ban {member.mention}: {e}", delete_after=10)

    async def _perform_mute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        reason: str,
        duration: timedelta = None,
    ) -> None:
        """Helper to mute a member without user confirmation."""
        try:
            duration_text = format_timedelta(duration) if duration else "indefinitely"
            await self.alert_user(
                ctx,
                member,
                reason,
                action_name="muted",
                duration=duration_text,
            )
            await self.bot.mute(ctx.author, member, duration, reason=reason)

            if duration:
                await ctx.send(
                    f"{member.mention} has been muted for {duration_text}. Reason: {reason}"
                )
                await self.send_log(ctx, member, reason, duration)
            else:
                await ctx.send(f"{member.mention} has been muted indefinitely. Reason: {reason}")
                await self.send_log(ctx, member, reason, None)
        except Exception as e:
            self.logger.error(f"Error in mute: {e}")
            await ctx.send(f"Failed to mute {member.mention}: {e}", delete_after=10)

    @command(7)
    async def kick(
        self, ctx: commands.Context, member: MemberOrID, *, reason: CannedStr = None
    ) -> None:
        """**Kick a member from the server**

        This command removes a member from the server. They can rejoin if they have an invite.

        **Usage:**
        `{prefix}kick <member> [reason]`

        **<member>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`

        **[reason]:**
        - An optional reason for the kick.

        **Example:**
        `{prefix}kick @TestUser Breaking rules.`
        """
        if getattr(ctx, "_dummy", False):
            if not isinstance(member, discord.Member):
                member_obj = ctx.guild.get_member(getattr(member, "id", member))
                if not member_obj:
                    self.logger.warning(
                        f"Attempted to auto-kick user not in guild: {getattr(member, 'id', member)}"
                    )
                    return
                member = member_obj
            return await self._perform_kick(ctx, member, reason)
        # Permission level check
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        if (
            get_perm_level(self.bot, member, guild_config)[0]
            >= get_perm_level(self.bot, ctx.author, guild_config)[0]
        ):
            await ctx.send("User has insufficient permissions")
            return

        # Ensure member is a discord.Member object from the server
        if not isinstance(member, discord.Member):
            member_obj = ctx.guild.get_member(getattr(member, "id", member))
            if not member_obj:
                await ctx.send(
                    f"User {getattr(member, 'mention', member)} is not present in this server and cannot be kicked."
                )
                return
            member = member_obj

        # Check bot permissions
        if not ctx.guild.me.guild_permissions.kick_members:
            await ctx.send("I don't have permission to kick members!")
            return

        # Check role hierarchy
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send("I cannot kick this user due to role hierarchy!")
            return

        # Prevent kicking self or owner
        if member == ctx.guild.me:
            await ctx.send("I cannot kick myself!")
            return
        if member == ctx.guild.owner:
            await ctx.send("I cannot kick the server owner!")
            return

        # Only show confirmation dialog if member is present in the server
        if not ctx.guild.get_member(getattr(member, "id", member)):
            await ctx.send(
                f"User {getattr(member, 'mention', member)} is not present in this server and cannot be kicked."
            )
            return
        confirm_embed = discord.Embed(
            title="Confirm Kick",
            description=f"Are you sure you want to kick {member.mention} ({member.id})?\nReason: {reason if reason else 'No reason provided'}",
            color=discord.Color.orange(),
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
            await msg.edit(
                embed=discord.Embed(
                    title="Kick Cancelled",
                    description="Kick confirmation timed out. Command cancelled.",
                    color=discord.Color.red(),
                )
            )
            # Track that this member's kick confirmation timed out
            self.kick_confirm_timeouts.add(str(member.id))
            return

        if str(reaction.emoji) == "✅":
            try:
                await self.alert_user(ctx, member, reason)
                self.recently_kicked.add(member.id)
                await member.kick(reason=reason)
                await msg.edit(
                    embed=discord.Embed(
                        title="Kick Success",
                        description=f"{member.mention} ({member.id}) has been kicked. Reason: {reason}",
                        color=discord.Color.green(),
                    )
                )
                await self.send_log(ctx, member, reason)
            except discord.Forbidden:
                await msg.edit(
                    embed=discord.Embed(
                        title="Kick Failed",
                        description="I don't have permission to kick that member! They might have a higher role than me.",
                        color=discord.Color.red(),
                    )
                )
            except discord.NotFound:
                await msg.edit(
                    embed=discord.Embed(
                        title="Kick Failed",
                        description=f"Could not find user {member}",
                        color=discord.Color.red(),
                    )
                )
            except Exception as e:
                await msg.edit(
                    embed=discord.Embed(
                        title="Kick Failed",
                        description=f"Failed to kick member: {e}",
                        color=discord.Color.red(),
                    )
                )
        else:
            await msg.edit(
                embed=discord.Embed(
                    title="Kick Cancelled", description="Kick cancelled.", color=discord.Color.red()
                )
            )

    @command(7)
    async def softban(
        self, ctx: commands.Context, member: discord.Member, *, reason: CannedStr = None
    ) -> None:
        """**Ban and immediately unban a member to purge their messages**

        This command is a quick way to delete all messages from a user in the last 7 days.

        **Usage:**
        `{prefix}softban <member> [reason]`

        **<member>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`

        **[reason]:**
        - An optional reason for the softban.

        **Example:**
        `{prefix}softban @TestUser Advertising.`
        """
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        if (
            get_perm_level(self.bot, member, guild_config)[0]
            >= get_perm_level(self.bot, ctx.author, guild_config)[0]
        ):
            await ctx.send("User has insufficient permissions")
        else:
            await self.alert_user(ctx, member, reason)
            self.recently_kicked.add(member.id)
            try:
                await member.ban(reason=reason)
            except discord.Forbidden:
                await ctx.send("I don't have permission to ban this user.")
                return
            except discord.HTTPException as e:
                await ctx.send(f"Failed to ban user: {e}")
                return
            await asyncio.sleep(0.5)
            await member.unban(reason=reason)
            await ctx.send(f"{member.mention} has been softbanned (ban/unban). Reason: {reason}")
            await self.send_log(ctx, member, reason)

    @command(7, usage="<member> [duration] [reason]")
    async def ban(
        self,
        ctx: commands.Context,
        member: MemberOrID,
        time_or_reason: str = None,
        prune_days: int = None,
    ) -> None:
        if getattr(ctx, "_dummy", False):
            duration = None
            reason = None
            if time_or_reason:
                try:
                    uft = await UserFriendlyTime(default=False).convert(ctx, time_or_reason)
                    if uft.dt:
                        duration = uft.dt - ctx.message.created_at
                    if uft.arg:
                        reason = uft.arg
                except commands.BadArgument:
                    reason = time_or_reason
            return await self._perform_ban(ctx, member, reason, duration)
        """**Ban a member from the server**

        This command permanently removes a member from the server and prevents them from rejoining.
        You can also specify a duration for a temporary ban.

        **Usage:**
        `{prefix}ban <member> [duration] [reason]`

        **<member>:**
        - Mention the user, e.g., `@user`
        - Provide the user's ID, e.g., `123456789012345678`

        **[duration]:**
        - Optional duration for a temporary ban (e.g., `7d`, `1h`).

        **[reason]:**
        - An optional reason for the ban.

        **Examples:**
        - `{prefix}ban @TestUser Persistent rule-breaking.`
        - `{prefix}ban @TestUser 7d Cooling off period.`
        """
        # Check user permission level (only if they're in the server)
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        if (
            get_perm_level(self.bot, member, guild_config)[0]
            >= get_perm_level(self.bot, ctx.author, guild_config)[0]
        ):
            await ctx.send("User has insufficient permissions")
            return

        # Parse duration and reason
        duration = None
        reason = None
        if time_or_reason:
            try:
                uft = await UserFriendlyTime(default=False).convert(ctx, time_or_reason)
                if uft.dt:
                    duration = uft.dt - ctx.message.created_at
                if uft.arg:
                    reason = uft.arg
            except commands.BadArgument:
                reason = time_or_reason

        # Check bot permissions
        if not ctx.guild.me.guild_permissions.ban_members:
            await ctx.send("I don't have permission to ban members!")
            return

        # Check if user is already banned
        try:
            ban_entry = await ctx.guild.fetch_ban(member)
        except discord.NotFound:
            ban_entry = None

        if ban_entry:
            user_id = getattr(member, "id", member)
            display_name = getattr(member, "mention", str(member))
            await ctx.send(f"User {display_name} ({user_id}) is already banned.")
            return

        # Check role hierarchy
        if hasattr(member, "top_role") and member.top_role >= ctx.guild.me.top_role:
            await ctx.send("I cannot ban this user due to role hierarchy!")
            return

        # Prevent banning self or owner
        if hasattr(member, "id") and member.id == ctx.guild.me.id:
            await ctx.send("I cannot ban myself!")
            return
        if hasattr(member, "id") and member.id == ctx.guild.owner_id:
            await ctx.send("I cannot ban the server owner!")
            return

        # Get prune_days from config if not provided
        if prune_days is None:
            prune_days = getattr(guild_config, "ban_prune_days", 3)

        try:
            self.recently_kicked.add(member.id)
            await ctx.guild.ban(
                member,
                reason=f"{ctx.author}: {reason}" if reason else f"Ban by {ctx.author}",
                delete_message_days=prune_days,
            )

            # If temporary ban, schedule unban and record in DB
            if duration:
                seconds = duration.total_seconds()
                seconds += time.time()
                await self.bot.db.update_guild_config(
                    ctx.guild.id,
                    {
                        "$push": {
                            "tempbans": {
                                "member": str(getattr(member, "id", member)),
                                "time": seconds,
                            }
                        }
                    },
                )
                self.bot.loop.create_task(
                    self.bot.unban(ctx.guild.id, getattr(member, "id", member), seconds)
                )

            # Send confirmation
            user_id = getattr(member, "id", member)
            if duration:
                await ctx.send(
                    f"✅ {getattr(member, 'mention', member)} ({user_id}) has been banned for {format_timedelta(duration)}. Reason: {reason}"
                )
            else:
                await ctx.send(
                    f"✅ {getattr(member, 'mention', member)} ({user_id}) has been banned permanently. Reason: {reason}"
                )
        except discord.Forbidden:
            await ctx.send("I don't have permission to ban this user.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to ban user: {e}")

    async def alert_user(
        self,
        ctx: commands.Context,
        member,
        reason: str = None,
        *,
        duration: str = None,
        action_name: str = None,
    ) -> None:
        """Send a DM to a user about their punishment"""
        if not hasattr(member, "send"):
            # If member is just an ID, try to get the user object
            try:
                member = await ctx.bot.fetch_user(int(getattr(member, "id", member)))
            except (discord.HTTPException, discord.NotFound, ValueError, TypeError):
                # If we can't fetch the user, just return silently
                return

        try:
            action = action_name or (ctx.command.name if ctx.command else "moderated")
            msg = f"You have been {action} in **{ctx.guild.name}**."

            if reason:
                msg += f"\nReason: {reason}"

            if duration:
                msg += f"\nDuration: {duration}"

            await member.send(msg)
        except (discord.Forbidden, discord.HTTPException):
            # User has DMs disabled or blocked the bot
            pass
        except (discord.HTTPException, discord.ConnectionClosed, OSError):
            # Network or system errors, fail silently
            pass


async def setup(bot: RainBot) -> None:
    await bot.add_cog(Moderation(bot))

    async def remove_warn(self, ctx, case_number):
        warns = await self.bot.db.get_guild_warns(ctx.guild.id)
        warn = next((w for w in warns if w.get("case_number") == case_number), None)
        if not warn:
            await ctx.send(f"Modlog #{case_number} does not exist.")

            @command(7)
            async def kick(
                self, ctx: commands.Context, member: discord.Member, *, reason: CannedStr = None
            ) -> None:
                """Kick a member from the server with confirmation dialog."""
                if (
                    get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
                    >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[
                        0
                    ]
                ):
                    await ctx.send("User has insufficient permissions")
                    return
                if not isinstance(member, discord.Member):
                    member_obj = ctx.guild.get_member(getattr(member, "id", member))
                    if not member_obj:
                        await ctx.send(
                            f"User {getattr(member, 'mention', member)} is not present in this server and cannot be kicked."
                        )
                        return
                    member = member_obj
                if not ctx.guild.me.guild_permissions.kick_members:
                    await ctx.send("I don't have permission to kick members!")
                    return
                if member.top_role >= ctx.guild.me.top_role:
                    await ctx.send("I cannot kick this user due to role hierarchy!")
                    return
                if member == ctx.guild.me:
                    await ctx.send("I cannot kick myself!")
                    return
                if member == ctx.guild.owner:
                    await ctx.send("I cannot kick the server owner!")
                    return
                confirm_embed = discord.Embed(
                    title="Confirm Kick",
                    description=f"Are you sure you want to kick {member.mention} ({member.id})?\nReason: {reason if reason else 'No reason provided'}",
                    color=discord.Color.orange(),
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
                    await msg.edit(
                        embed=discord.Embed(
                            title="Kick Cancelled",
                            description="Kick confirmation timed out. Command cancelled.",
                            color=discord.Color.red(),
                        )
                    )
                    return
                if str(reaction.emoji) == "✅":
                    try:
                        await self.alert_user(ctx, member, reason)
                        await member.kick(reason=reason)
                        await msg.edit(
                            embed=discord.Embed(
                                title="Kick Success",
                                description=f"{member.mention} ({member.id}) has been kicked. Reason: {reason}",
                                color=discord.Color.green(),
                            )
                        )
                        await self.send_log(ctx, member, reason)
                    except discord.Forbidden:
                        await msg.edit(
                            embed=discord.Embed(
                                title="Kick Failed",
                                description="I don't have permission to kick that member! They might have a higher role than me.",
                                color=discord.Color.red(),
                            )
                        )
                    except discord.NotFound:
                        await msg.edit(
                            embed=discord.Embed(
                                title="Kick Failed",
                                description=f"Could not find user {member}",
                                color=discord.Color.red(),
                            )
                        )
                    except Exception as e:
                        await msg.edit(
                            embed=discord.Embed(
                                title="Kick Failed",
                                description=f"Failed to kick member: {e}",
                                color=discord.Color.red(),
                            )
                        )
                else:
                    await msg.edit(
                        embed=discord.Embed(
                            title="Kick Cancelled",
                            description="Kick cancelled.",
                            color=discord.Color.red(),
                        )
                    )

            @command(7, usage="<member> [duration] [reason]")
            async def ban(
                self,
                ctx: commands.Context,
                member: MemberOrID,
                *,
                time_or_reason: str = None,
                prune_days: int = None,
            ) -> None:
                """Ban a member from the server with confirmation dialog."""
                if (
                    get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
                    >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[
                        0
                    ]
                ):
                    await ctx.send("User has insufficient permissions")
                    return
                duration = None
                reason = None
                if time_or_reason:
                    try:
                        uft = await UserFriendlyTime(default=False).convert(ctx, time_or_reason)
                        if uft.dt:
                            duration = uft.dt - ctx.message.created_at
                        if uft.arg:
                            reason = uft.arg
                    except commands.BadArgument:
                        reason = time_or_reason
                confirm_embed = discord.Embed(
                    title="Confirm Ban",
                    description=f"Are you sure you want to ban {getattr(member, 'mention', member)} ({getattr(member, 'id', member)})?\nReason: {reason if reason else 'No reason provided'}",
                    color=discord.Color.red(),
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
                    await msg.edit(
                        embed=discord.Embed(
                            title="Ban Cancelled",
                            description="Ban confirmation timed out. Command cancelled.",
                            color=discord.Color.red(),
                        )
                    )
                    return
                if str(reaction.emoji) == "✅":
                    if not ctx.guild.me.guild_permissions.ban_members:
                        await msg.edit(
                            embed=discord.Embed(
                                title="Ban Failed",
                                description="I don't have permission to ban members!",
                                color=discord.Color.red(),
                            )
                        )
                        return
                    try:
                        await self.alert_user(ctx, member, reason)
                    except Exception:
                        pass
                    guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
                    if prune_days is None:
                        prune_days = getattr(guild_config, "ban_prune_days", 3)
                    try:
                        await ctx.guild.ban(
                            member,
                            reason=f"{ctx.author}: {reason}" if reason else f"Ban by {ctx.author}",
                            delete_message_days=prune_days,
                        )
                        await msg.edit(
                            embed=discord.Embed(
                                title="Ban Success",
                                description=f"{getattr(member, 'mention', member)} ({getattr(member, 'id', member)}) has been banned. Reason: {reason}",
                                color=discord.Color.green(),
                            )
                        )
                        await self.send_log(ctx, member, reason, duration)
                    except Exception as e:
                        await msg.edit(
                            embed=discord.Embed(
                                title="Ban Failed",
                                description=f"Failed to ban member: {e}",
                                color=discord.Color.red(),
                            )
                        )
                else:
                    await msg.edit(
                        embed=discord.Embed(
                            title="Ban Cancelled",
                            description="Ban cancelled.",
                            color=discord.Color.red(),
                        )
                    )

            @command(6, usage="<member> [duration] [reason]")
            async def mute(
                self,
                ctx: commands.Context,
                member: discord.Member,
                *,
                time: UserFriendlyTime = None,
            ) -> None:
                """Mute a member for an optional duration and reason with confirmation dialog."""
                if (
                    get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
                    >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[
                        0
                    ]
                ):
                    await ctx.send("User has insufficient permissions")
                    return
                if not isinstance(member, discord.Member):
                    member_obj = ctx.guild.get_member(getattr(member, "id", member))
                    if not member_obj:
                        await ctx.send(
                            f"User {getattr(member, 'mention', member)} is not present in this server and cannot be muted."
                        )
                        return
                    member = member_obj
                duration = None
                reason = None
                if time:
                    if time.dt:
                        duration = time.dt - ctx.message.created_at
                    if time.arg:
                        reason = time.arg
                confirm_embed = discord.Embed(
                    title="Confirm Mute",
                    description=f"Are you sure you want to mute {member.mention} ({member.id})?\nReason: {reason if reason else 'No reason provided'}",
                    color=discord.Color.orange(),
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
                    await msg.edit(
                        embed=discord.Embed(
                            title="Mute Cancelled",
                            description="Mute confirmation timed out. Command cancelled.",
                            color=discord.Color.red(),
                        )
                    )
                    return
                if str(reaction.emoji) == "✅":
                    try:
                        await self.alert_user(
                            ctx, member, reason, duration=format_timedelta(duration)
                        )
                        await self.bot.mute(ctx.author, member, duration, reason=reason)
                        await msg.edit(
                            embed=discord.Embed(
                                title="Mute Success",
                                description=f"{member.mention} has been muted for {format_timedelta(duration) if duration else 'indefinitely'}. Reason: {reason}",
                                color=discord.Color.green(),
                            )
                        )
                        await self.send_log(ctx, member, reason, duration)
                    except Exception as e:
                        await msg.edit(
                            embed=discord.Embed(
                                title="Mute Failed",
                                description=f"Failed to mute member: {e}",
                                color=discord.Color.red(),
                            )
                        )
                else:
                    await msg.edit(
                        embed=discord.Embed(
                            title="Mute Cancelled",
                            description="Mute cancelled.",
                            color=discord.Color.red(),
                        )
                    )

            @warn.command(6, name="remove", aliases=["delete", "del"])
            async def remove_modlog(self, ctx: commands.Context, case_number: int) -> None:
                """Remove a modlog entry by case number, with confirmation dialog."""
                guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
                modlogs = guild_config.modlog
                modlog = next((m for m in modlogs if m.get("case_number") == case_number), None)
                if not modlog:
                    await ctx.send(f"Modlog #{case_number} does not exist.")
                    return
                moderator = ctx.guild.get_member(int(modlog["moderator_id"]))
                confirm_embed = discord.Embed(
                    title="Confirm Modlog Removal",
                    description=f"Are you sure you want to remove Modlog #{case_number} for <@{modlog['member_id']}>?\nReason: {modlog['reason']}\nModerator: {moderator}",
                    color=discord.Color.red(),
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
                    await msg.edit(
                        embed=discord.Embed(
                            title="Modlog Removal Cancelled",
                            description="Modlog removal timed out. Command cancelled.",
                            color=discord.Color.red(),
                        )
                    )
                    return
                if str(reaction.emoji) == "✅":
                    await self.bot.db.update_guild_config(
                        ctx.guild.id, {"$pull": {"modlog": modlog}}
                    )
                    await msg.edit(
                        embed=discord.Embed(
                            title="Modlog Removed",
                            description=f"Modlog #{case_number} removed.",
                            color=discord.Color.green(),
                        )
                    )
                    # Sends log with all required info for modlog removal
                    await self.send_log(
                        ctx,
                        case_number,
                        modlog["reason"],
                        modlog["member_id"],
                        modlog["moderator_id"],
                    )
                else:
                    await msg.edit(
                        embed=discord.Embed(
                            title="Modlog Removal Cancelled",
                            description="Modlog removal cancelled.",
                            color=discord.Color.red(),
                        )
                    )

    async def remove_warn(self, ctx, case_number):
        warns = await self.bot.db.get_guild_warns(ctx.guild.id)
        warn = next((w for w in warns if w.get("case_number") == case_number), None)
        if not warn:
            await ctx.send(f"Modlog #{case_number} does not exist.")

            @command(7)
            async def kick(
                self, ctx: commands.Context, member: discord.Member, *, reason: CannedStr = None
            ) -> None:
                """Kick a member from the server with confirmation dialog."""
                if (
                    get_perm_level(
                        self.bot, member, await self.bot.db.get_guild_config(ctx.guild.id)
                    )[0]
                    >= get_perm_level(
                        self.bot, ctx.author, await self.bot.db.get_guild_config(ctx.guild.id)
                    )[0]
                ):
                    await ctx.send("User has insufficient permissions")
                    return
                if not isinstance(member, discord.Member):
                    member_obj = ctx.guild.get_member(getattr(member, "id", member))
                    if not member_obj:
                        await ctx.send(
                            f"User {getattr(member, 'mention', member)} is not present in this server and cannot be kicked."
                        )
                        return
                    member = member_obj
                if not ctx.guild.me.guild_permissions.kick_members:
                    await ctx.send("I don't have permission to kick members!")
                    return
                if member.top_role >= ctx.guild.me.top_role:
                    await ctx.send("I cannot kick this user due to role hierarchy!")
                    return
                if member == ctx.guild.me:
                    await ctx.send("I cannot kick myself!")
                    return
                if member == ctx.guild.owner:
                    await ctx.send("I cannot kick the server owner!")
                    return
                confirm_embed = discord.Embed(
                    title="Confirm Kick",
                    description=f"Are you sure you want to kick {member.mention} ({member.id})?\nReason: {reason if reason else 'No reason provided'}",
                    color=discord.Color.orange(),
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
                    await msg.edit(
                        embed=discord.Embed(
                            title="Kick Cancelled",
                            description="Kick confirmation timed out. Command cancelled.",
                            color=discord.Color.red(),
                        )
                    )
                    return
                if str(reaction.emoji) == "✅":
                    try:
                        await self.alert_user(ctx, member, reason)
                        await member.kick(reason=reason)
                        await msg.edit(
                            embed=discord.Embed(
                                title="Kick Success",
                                description=f"{member.mention} ({member.id}) has been kicked. Reason: {reason}",
                                color=discord.Color.green(),
                            )
                        )
                        await self.send_log(ctx, member, reason)
                    except discord.Forbidden:
                        await msg.edit(
                            embed=discord.Embed(
                                title="Kick Failed",
                                description="I don't have permission to kick that member! They might have a higher role than me.",
                                color=discord.Color.red(),
                            )
                        )
                    except discord.NotFound:
                        await msg.edit(
                            embed=discord.Embed(
                                title="Kick Failed",
                                description=f"Could not find user {member}",
                                color=discord.Color.red(),
                            )
                        )
                    except Exception as e:
                        await msg.edit(
                            embed=discord.Embed(
                                title="Kick Failed",
                                description=f"Failed to kick member: {e}",
                                color=discord.Color.red(),
                            )
                        )
                else:
                    await msg.edit(
                        embed=discord.Embed(
                            title="Kick Cancelled",
                            description="Kick cancelled.",
                            color=discord.Color.red(),
                        )
                    )

            @command(7, usage="<member> [duration] [reason]")
            async def ban(
                self,
                ctx: commands.Context,
                member: MemberOrID,
                *,
                time_or_reason: str = None,
                prune_days: int = None,
            ) -> None:
                """Ban a member from the server with confirmation dialog."""
                if (
                    get_perm_level(
                        self.bot, member, await self.bot.db.get_guild_config(ctx.guild.id)
                    )[0]
                    >= get_perm_level(
                        self.bot, ctx.author, await self.bot.db.get_guild_config(ctx.guild.id)
                    )[0]
                ):
                    await ctx.send("User has insufficient permissions")
                    return
                duration = None
                reason = None
                if time_or_reason:
                    try:
                        uft = await UserFriendlyTime(default=False).convert(ctx, time_or_reason)
                        if uft.dt:
                            duration = uft.dt - ctx.message.created_at
                        if uft.arg:
                            reason = uft.arg
                    except commands.BadArgument:
                        reason = time_or_reason
                confirm_embed = discord.Embed(
                    title="Confirm Ban",
                    description=f"Are you sure you want to ban {getattr(member, 'mention', member)} ({getattr(member, 'id', member)})?\nReason: {reason if reason else 'No reason provided'}",
                    color=discord.Color.red(),
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
                    await msg.edit(
                        embed=discord.Embed(
                            title="Ban Cancelled",
                            description="Ban confirmation timed out. Command cancelled.",
                            color=discord.Color.red(),
                        )
                    )
                    return
                if str(reaction.emoji) == "✅":
                    if not ctx.guild.me.guild_permissions.ban_members:
                        await msg.edit(
                            embed=discord.Embed(
                                title="Ban Failed",
                                description="I don't have permission to ban members!",
                                color=discord.Color.red(),
                            )
                        )
                        return
                    try:
                        await self.alert_user(ctx, member, reason)
                    except Exception:
                        pass
                    guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
                    if prune_days is None:
                        prune_days = getattr(guild_config, "ban_prune_days", 3)
                    try:
                        await ctx.guild.ban(
                            member,
                            reason=f"{ctx.author}: {reason}" if reason else f"Ban by {ctx.author}",
                            delete_message_days=prune_days,
                        )
                        await msg.edit(
                            embed=discord.Embed(
                                title="Ban Success",
                                description=f"{getattr(member, 'mention', member)} ({getattr(member, 'id', member)}) has been banned. Reason: {reason}",
                                color=discord.Color.green(),
                            )
                        )
                        await self.send_log(ctx, member, reason, duration)
                    except Exception as e:
                        await msg.edit(
                            embed=discord.Embed(
                                title="Ban Failed",
                                description=f"Failed to ban member: {e}",
                                color=discord.Color.red(),
                            )
                        )
                else:
                    await msg.edit(
                        embed=discord.Embed(
                            title="Ban Cancelled",
                            description="Ban cancelled.",
                            color=discord.Color.red(),
                        )
                    )

            @command(6, usage="<member> [duration] [reason]")
            async def mute(
                self,
                ctx: commands.Context,
                member: discord.Member,
                *,
                time: UserFriendlyTime = None,
            ) -> None:
                """Mute a member for an optional duration and reason with confirmation dialog."""
                if (
                    get_perm_level(
                        self.bot, member, await self.bot.db.get_guild_config(ctx.guild.id)
                    )[0]
                    >= get_perm_level(
                        self.bot, ctx.author, await self.bot.db.get_guild_config(ctx.guild.id)
                    )[0]
                ):
                    await ctx.send("User has insufficient permissions")
                    return
                if not isinstance(member, discord.Member):
                    member_obj = ctx.guild.get_member(getattr(member, "id", member))
                    if not member_obj:
                        await ctx.send(
                            f"User {getattr(member, 'mention', member)} is not present in this server and cannot be muted."
                        )
                        return
                    member = member_obj
                duration = None
                reason = None
                if time:
                    if time.dt:
                        duration = time.dt - ctx.message.created_at
                    if time.arg:
                        reason = time.arg
                confirm_embed = discord.Embed(
                    title="Confirm Mute",
                    description=f"Are you sure you want to mute {member.mention} ({member.id})?\nReason: {reason if reason else 'No reason provided'}",
                    color=discord.Color.orange(),
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
                    await msg.edit(
                        embed=discord.Embed(
                            title="Mute Cancelled",
                            description="Mute confirmation timed out. Command cancelled.",
                            color=discord.Color.red(),
                        )
                    )
                    return
                if str(reaction.emoji) == "✅":
                    try:
                        await self.alert_user(
                            ctx, member, reason, duration=format_timedelta(duration)
                        )
                        await self.bot.mute(ctx.author, member, duration, reason=reason)
                        await msg.edit(
                            embed=discord.Embed(
                                title="Mute Success",
                                description=f"{member.mention} has been muted for {format_timedelta(duration) if duration else 'indefinitely'}. Reason: {reason}",
                                color=discord.Color.green(),
                            )
                        )
                        await self.send_log(ctx, member, reason, duration)
                    except Exception as e:
                        await msg.edit(
                            embed=discord.Embed(
                                title="Mute Failed",
                                description=f"Failed to mute member: {e}",
                                color=discord.Color.red(),
                            )
                        )
                else:
                    await msg.edit(
                        embed=discord.Embed(
                            title="Mute Cancelled",
                            description="Mute cancelled.",
                            color=discord.Color.red(),
                        )
                    )

            @warn.command(6, name="remove", aliases=["delete", "del"])
            async def remove_modlog(self, ctx: commands.Context, case_number: int) -> None:
                """Remove a modlog entry by case number, with confirmation dialog."""
                guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
                modlogs = guild_config.modlog
                modlog = next((m for m in modlogs if m.get("case_number") == case_number), None)
                if not modlog:
                    await ctx.send(f"Modlog #{case_number} does not exist.")
                    return
                moderator = ctx.guild.get_member(int(modlog["moderator_id"]))
                confirm_embed = discord.Embed(
                    title="Confirm Modlog Removal",
                    description=f"Are you sure you want to remove Modlog #{case_number} for <@{modlog['member_id']}>?\nReason: {modlog['reason']}\nModerator: {moderator}",
                    color=discord.Color.red(),
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
                    await msg.edit(
                        embed=discord.Embed(
                            title="Modlog Removal Cancelled",
                            description="Modlog removal timed out. Command cancelled.",
                            color=discord.Color.red(),
                        )
                    )
                    return
                if str(reaction.emoji) == "✅":
                    await self.bot.db.update_guild_config(
                        ctx.guild.id, {"$pull": {"modlog": modlog}}
                    )
                    await msg.edit(
                        embed=discord.Embed(
                            title="Modlog Removed",
                            description=f"Modlog #{case_number} removed.",
                            color=discord.Color.green(),
                        )
                    )
                    # Sends log with all required info for modlog removal
                    await self.send_log(
                        ctx,
                        case_number,
                        modlog["reason"],
                        modlog["member_id"],
                        modlog["moderator_id"],
                    )
                else:
                    await msg.edit(
                        embed=discord.Embed(
                            title="Modlog Removal Cancelled",
                            description="Modlog removal cancelled.",
                            color=discord.Color.red(),
                        )
                    )

    async def remove_warn(self, ctx, case_number):
        warns = await self.bot.db.get_guild_warns(ctx.guild.id)
        warn = next((w for w in warns if w.get("case_number") == case_number), None)
        if not warn:
            await ctx.send(f"Modlog #{case_number} does not exist.")
            return
        moderator = ctx.guild.get_member(int(warn["moderator_id"]))
        confirm_embed = discord.Embed(
            title="Confirm Modlog Removal",
            description=f"Are you sure you want to remove Warn #{case_number} for <@{warn['member_id']}>?\nReason: {warn['reason']}\nModerator: {moderator}",
            color=discord.Color.red(),
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
            if str(reaction.emoji) == "✅":
                await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"warns": warn}})
                await ctx.send(f"Warn #{case_number} removed.")
                await self.send_log(
                    ctx, case_number, warn["reason"], warn["member_id"], warn["moderator_id"]
                )
            else:
                await ctx.send("Warn removal cancelled.")
        except asyncio.TimeoutError:
            await ctx.send("Warn removal timed out. Command cancelled.")
