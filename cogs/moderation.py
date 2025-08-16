import discord
import asyncio
from datetime import timedelta
from time import time as unixs
from typing import Union
from ext.utility import SafeFormat, tryint, CannedStr, format_timedelta, get_perm_level
from ext.database import DEFAULT, DBDict
from discord.ext import commands
from bot import rainbot
from ext.command import command, group
from ext.time import UserFriendlyTime


class MemberOrID(commands.IDConverter):
    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> Union[discord.Member, discord.User]:
        try:
            return await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            try:
                return await ctx.bot.fetch_user(int(argument))
            except Exception:
                raise commands.BadArgument(f"Member {argument} not found")


class Moderation(commands.Cog):
    # ...existing code...
    @group(6, invoke_without_command=True, usage="<user_id>")
    async def modlogs(self, ctx: commands.Context, user: MemberOrID = None) -> None:
        """View all modlogs for a user by ID or mention."""
        # ...existing code...

    @modlogs.command(6, name="all")
    async def modlogs_all(self, ctx: commands.Context) -> None:
        """View all modlogs in the server, paginated 10 per page."""
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
            if isinstance(m, dict):
                member = ctx.guild.get_member(int(m["member_id"]))
                member_name = member.mention if member else f"<@{m['member_id']}>"
                moderator = ctx.guild.get_member(int(m["moderator_id"]))
                mod_name = moderator.mention if moderator else f"<@{m['moderator_id']}>"
                entries.append(
                    {
                        "date": m["date"],
                        "case_number": m.get("case_number", 0),
                        "type": "modlog",
                        "text": f"{m['date']} Case #{m['case_number']}: {member_name} - {mod_name} - {m['reason']} [modlog]",
                    }
                )
        # Warns
        for w in warns:
            if isinstance(w, dict):
                member = ctx.guild.get_member(int(w["member_id"]))
                member_name = member.mention if member else f"<@{w['member_id']}>"
                moderator = ctx.guild.get_member(int(w["moderator_id"]))
                mod_name = moderator.mention if moderator else f"<@{w['moderator_id']}>"
                entries.append(
                    {
                        "date": w["date"],
                        "case_number": w.get("case_number", 0),
                        "type": "warn",
                        "text": f"{w['date']} Warn #{w['case_number']}: {member_name} - {mod_name} - {w['reason']} [warn]",
                    }
                )
        # Mutes
        for mute in mutes:
            if isinstance(mute, dict):
                member_id = mute.get("member", "")
                member = ctx.guild.get_member(int(member_id)) if member_id else None
                member_name = member.mention if member else f"<@{member_id}>"
                until = mute.get("time")
                until_str = f"until <t:{int(until)}:F>" if until else "indefinite"
                entries.append(
                    {
                        "date": mute.get("date", ""),
                        "case_number": mute.get("case_number", 0),
                        "type": "mute",
                        "text": f"Mute: {member_name} {until_str} [mute]",
                    }
                )
        # Tempbans
        for tb in tempbans:
            if isinstance(tb, dict):
                member_id = tb.get("member", "")
                member = ctx.guild.get_member(int(member_id)) if member_id else None
                member_name = member.mention if member else f"<@{member_id}>"
                until = tb.get("time")
                until_str = f"until <t:{int(until)}:F>" if until else "indefinite"
                entries.append(
                    {
                        "date": tb.get("date", ""),
                        "case_number": tb.get("case_number", 0),
                        "type": "tempban",
                        "text": f"Tempban: {member_name} {until_str} [tempban]",
                    }
                )
        # Kicks
        for k in kicks:
            if isinstance(k, dict):
                member_id = k.get("member_id", "")
                member = ctx.guild.get_member(int(member_id)) if member_id else None
                member_name = member.mention if member else f"<@{member_id}>"
                moderator = ctx.guild.get_member(int(k.get("moderator_id", 0)))
                mod_name = moderator.mention if moderator else f"<@{k.get('moderator_id', 0)}>"
                reason = k.get("reason", "No reason")
                entries.append(
                    {
                        "date": k.get("date", ""),
                        "case_number": k.get("case_number", 0),
                        "type": "kick",
                        "text": f"{k.get('date', '')} Kick: {member_name} - {mod_name} - {reason} [kick]",
                    }
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
                entries.append(
                    {
                        "date": sb.get("date", ""),
                        "case_number": sb.get("case_number", 0),
                        "type": "softban",
                        "text": f"{sb.get('date', '')} Softban: {member_name} - {mod_name} - {reason} [softban]",
                    }
                )

        # Sort newest to oldest by case_number if present, else by date
        def sort_key(e):
            return e.get("case_number", 0) or 0

        entries_sorted = sorted(entries, key=sort_key, reverse=True)

        # Paginate
        page_size = 10
        pages = [
            entries_sorted[i : i + page_size] for i in range(0, len(entries_sorted), page_size)
        ]
        total_pages = len(pages)

        def format_page(page, page_num):
            fmt = f"**All Moderation Actions (Page {page_num+1}/{total_pages}):**\n"
            for entry in page:
                fmt += entry["text"] + "\n"
            return fmt

        page_num = 0
        if not pages:
            await ctx.send("No moderation actions found in this server.")
            return
        msg = await ctx.send(format_page(pages[page_num], page_num))
        if total_pages > 1:
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
                except asyncio.TimeoutError:
                    break
                if str(reaction.emoji) == "➡️" and page_num < total_pages - 1:
                    page_num += 1
                    await msg.edit(content=format_page(pages[page_num], page_num))
                    await msg.remove_reaction(reaction, user)
                elif str(reaction.emoji) == "⬅️" and page_num > 0:
                    page_num -= 1
                    await msg.edit(content=format_page(pages[page_num], page_num))
                    await msg.remove_reaction(reaction, user)
                else:
                    await msg.remove_reaction(reaction, user)

    # ...existing code...
    # Only keep one correct implementation of kick, ban, mute, warn, remove_warn, modlogs remove, with confirmation dialog and embed editing. Fix indentation and remove stray code.
    @group(6, invoke_without_command=True, usage="<user_id>")
    async def modlogs(self, ctx: commands.Context, user: MemberOrID = None) -> None:
        """View all modlogs for a user by ID or mention."""
        if user is None:
            # Get current server prefix
            prefix = getattr(ctx, "prefix", "!!")
            embed = discord.Embed(
                title=f"📖 {prefix}modlogs <user_id>",
                description="View all modlogs for a user by ID or mention.",
                color=discord.Color.blue(),
            )
            embed.add_field(name="🔒 Permission Level", value="6", inline=False)
            embed.add_field(
                name="📂 Subcommands",
                value="• `remove` - Remove a modlog entry by case number, with confirmation dialog.",
                inline=False,
            )
            embed.add_field(
                name="Usage", value=f"`{prefix}modlogs remove <case_number>`", inline=False
            )
            embed.add_field(name="Example", value=f"`{prefix}modlogs remove 123`", inline=False)
            await ctx.send(embed=embed)
            return
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        # Accept both MemberOrID and raw string/ID
        if isinstance(user, (discord.Member, discord.User)):
            user_id = str(user.id)
            user_name = user.mention
        else:
            try:
                user_id = str(int(user))
            except Exception:
                user_id = str(user)
            user_name = f"<@{user_id}>"

        # Gather all moderation actions for the user
        modlogs = getattr(guild_config, "modlog", [])
        warns = getattr(guild_config, "warns", [])
        mutes = getattr(guild_config, "mutes", [])
        tempbans = getattr(guild_config, "tempbans", [])
        # Add more if needed (e.g., kicks, softbans) if stored separately

        entries = []
        # Modlogs
        for m in modlogs:
            if isinstance(m, dict) and str(m.get("member_id", "")) == user_id:
                moderator = ctx.guild.get_member(int(m["moderator_id"]))
                mod_name = moderator.mention if moderator else f"<@{m['moderator_id']}>"
                entries.append(
                    f"{m['date']} Case #{m['case_number']}: {mod_name} - {m['reason']} [modlog]"
                )
        # Warns
        for w in warns:
            if isinstance(w, dict) and str(w.get("member_id", "")) == user_id:
                moderator = ctx.guild.get_member(int(w["moderator_id"]))
                mod_name = moderator.mention if moderator else f"<@{w['moderator_id']}>"
                entries.append(
                    f"{w['date']} Warn #{w['case_number']}: {mod_name} - {w['reason']} [warn]"
                )
        # Mutes
        for mute in mutes:
            if isinstance(mute, dict) and str(mute.get("member", "")) == user_id:
                until = mute.get("time")
                until_str = f"until <t:{int(until)}:F>" if until else "indefinite"
                entries.append(f"Mute: {user_name} {until_str} [mute]")
        # Tempbans
        for tb in tempbans:
            if isinstance(tb, dict) and str(tb.get("member", "")) == user_id:
                until = tb.get("time")
                until_str = f"until <t:{int(until)}:F>" if until else "indefinite"
                entries.append(f"Tempban: {user_name} {until_str} [tempban]")

        if not entries:
            await ctx.send(f"No modlogs found for {user_name} ({user_id}).")
            return
        fmt = f"**Modlogs for {user_name} ({user_id}):**\n" + "\n".join(entries)
        await ctx.send(fmt)

    @modlogs.command(6, name="remove", aliases=["delete", "del"], usage="<case_number>")
    async def remove(self, ctx: commands.Context, case_number: int) -> None:
        """Remove a modlog entry by case number, with confirmation dialog."""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        modlogs = getattr(guild_config, "modlog", [])
        modlog = next((m for m in modlogs if m.get("case_number") == case_number), None)
        if not modlog:
            await ctx.send(f"Modlog #{case_number} does not exist.")
            return
        moderator = ctx.guild.get_member(int(modlog["moderator_id"]))
        confirm_embed = discord.Embed(
            title="Confirm Modlog Removal",
            description=f"Are you sure you want to remove Modlog #{case_number} for ID:{modlog['member_id']}?\nReason: {modlog['reason']}\nModerator: {moderator.name if moderator else f'ID:{modlog['moderator_id']}' }",
            color=discord.Color.red(),
        )
        msg = await ctx.send(embed=confirm_embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id
        try:
            reaction, user = await ctx.bot.wait_for("reaction_add", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await msg.edit(embed=discord.Embed(title="Modlog Removal Cancelled", description="Modlog removal timed out. Command cancelled.", color=discord.Color.red()))
            return
        if str(reaction.emoji) == "✅":
            await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"modlog": modlog}})
            await msg.edit(embed=discord.Embed(title="Modlog Removed", description=f"Modlog #{case_number} removed.", color=discord.Color.green()))
            await self.send_log(ctx, case_number, modlog["reason"], modlog["member_id"], modlog["moderator_id"])
        else:
            await msg.edit(embed=discord.Embed(title="Modlog Removal Cancelled", description="Modlog removal cancelled.", color=discord.Color.red()))

    # ...existing code...

    # ...existing code...
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
            async def remove_warn(self, ctx: commands.Context, case_number: int) -> None:
                """Remove a warn with confirmation dialog."""
                guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
                warns = guild_config.warns
                warn = next((w for w in warns if w.get("case_number") == case_number), None)
                if not warn:
                    await ctx.send(f"Warn #{case_number} does not exist.")
                    return
                moderator = ctx.guild.get_member(int(warn["moderator_id"]))
                confirm_embed = discord.Embed(
                    title="Confirm Warn Removal",
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
                    reaction, user = await ctx.bot.wait_for(
                        "reaction_add", timeout=30.0, check=check
                    )
                except asyncio.TimeoutError:
                    await msg.edit(
                        embed=discord.Embed(
                            title="Warn Removal Cancelled",
                            description="Warn removal timed out. Command cancelled.",
                            color=discord.Color.red(),
                        )
                    )
                    return
                if str(reaction.emoji) == "✅":
                    await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"warns": warn}})
                    await msg.edit(
                        embed=discord.Embed(
                            title="Warn Removed",
                            description=f"Warn #{case_number} removed.",
                            color=discord.Color.green(),
                        )
                    )
                    await self.send_log(
                        ctx, case_number, warn["reason"], warn["member_id"], warn["moderator_id"]
                    )
                else:
                    await msg.edit(
                        embed=discord.Embed(
                            title="Warn Removal Cancelled",
                            description="Warn removal cancelled.",
                            color=discord.Color.red(),
                        )
                    )

            @modlogs.command(6, name="remove", aliases=["delete", "del"])
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

    """Basic moderation commands"""

    def __init__(self, bot: rainbot) -> None:
        self.bot = bot
        self.order = 2
        self.kick_confirm_timeouts = set()  # Track member IDs for which kick confirmation timed out

    async def cog_error(self, ctx: commands.Context, error: Exception) -> None:
        """Handles discord.Forbidden"""

    async def send_log(self, ctx: commands.Context, *args) -> None:
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        offset = guild_config.time_offset
        current_time = (
            f"<t:{int((ctx.message.created_at + timedelta(hours=offset)).timestamp())}:T>"
        )

        modlogs = DBDict(
            {i: tryint(guild_config.modlog[i]) for i in guild_config.modlog if i},
            _default=DEFAULT["modlog"],
        )

        try:
            if ctx.command.name == "purge":
                fmt = f"{current_time} {ctx.author} purged {args[0]} messages in **#{ctx.channel.name}**"
                if args[1]:
                    fmt += f", from {args[1]}"
                channel = ctx.bot.get_channel(modlogs.message_purge)
                if channel:
                    await channel.send(fmt)
            elif ctx.command.name == "kick":
                fmt = f"{current_time} {ctx.author} kicked {args[0]} ({args[0].id}), reason: {args[1]}"
                channel = ctx.bot.get_channel(modlogs.member_kick)
                if channel:
                    await channel.send(fmt)
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
            elif ctx.command.qualified_name == "warn add":
                fmt = f"{current_time} {ctx.author} warned #{args[2]} {args[0]} ({args[0].id}), reason: {args[1]}"
                channel = ctx.bot.get_channel(modlogs.member_warn)
                if channel:
                    await channel.send(fmt)
            elif ctx.command.qualified_name == "warn remove":
                fmt = f"{current_time} {ctx.author} has deleted warn #{args[0]} - {args[1]}"
                channel = ctx.bot.get_channel(modlogs.member_warn)
                if channel:
                    await channel.send(fmt)
            elif ctx.command.qualified_name == "modlogs remove":
                case_num, original_reason, member_id, mod_id = args
                member = ctx.guild.get_member(int(member_id)) or f"<@{member_id}>"
                original_mod = ctx.guild.get_member(int(mod_id)) or f"<@{mod_id}>"
                fmt = f"{current_time} {ctx.author} has deleted modlog #{case_num}\n• Target: {member} ({member_id})\n• Original Moderator: {original_mod}\n• Original Reason: {original_reason}"
                channel = ctx.bot.get_channel(modlogs.member_warn)
                if channel:
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

            else:
                raise NotImplementedError(
                    f"{ctx.command.name} not implemented for commands/send_log"
                )
        except AttributeError:
            # channel not found [None.send()]
            pass

    @command(5)
    async def user(self, ctx: commands.Context, member: discord.Member) -> None:
        """Get a user's info"""

        async def timestamp(created):
            delta = format_timedelta(ctx.message.created_at - created)
            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            created = created + timedelta(hours=guild_config.time_offset)
            return f"{delta} ago (<t:{int(created.timestamp())}:T>)"

        created = await timestamp(member.created_at)
        joined = await timestamp(member.joined_at)
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

    @group(6, invoke_without_command=True)
    async def note(self, ctx: commands.Context) -> None:
        """Manage notes"""
        await ctx.invoke(self.bot.get_command("help"), command_or_cog="note")

    @note.command(6)
    async def add(self, ctx: commands.Context, member: MemberOrID, *, note):
        """Add a note"""
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
        else:
            guild_data = await self.bot.db.get_guild_config(ctx.guild.id)
            notes = guild_data.notes

            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            current_date = f"<t:{int((ctx.message.created_at + timedelta(hours=guild_config.time_offset)).timestamp())}:D>"
            if len(notes) == 0:
                case_number = 1
            else:
                case_number = notes[-1]["case_number"] + 1

            push = {
                "case_number": case_number,
                "date": current_date,
                "member_id": str(member.id),
                "moderator_id": str(ctx.author.id),
                "note": note,
            }
            await self.bot.db.update_guild_config(ctx.guild.id, {"$push": {"notes": push}})
            await ctx.send(f"Note added for {member.mention}: {note}")

    @note.command(6, aliases=["delete", "del"])
    async def remove(self, ctx: commands.Context, case_number: int) -> None:
        """Remove a note"""
        guild_data = await self.bot.db.get_guild_config(ctx.guild.id)
        notes = guild_data.notes
        note = list(filter(lambda w: w["case_number"] == case_number, notes))
        if len(note) == 0:
            await ctx.send(f"Note #{case_number} does not exist.")
        else:
            await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"notes": note[0]}})
            await ctx.send(f"Note #{case_number} removed from <@{note[0]['member_id']}>.")

    @note.command(6, name="list", aliases=["view"])
    async def _list(self, ctx: commands.Context, member: MemberOrID) -> None:
        """View the notes of a user"""
        guild_data = await self.bot.db.get_guild_config(ctx.guild.id)
        notes = guild_data.notes
        notes = list(filter(lambda w: w["member_id"] == str(member.id), notes))
        name = getattr(member, "name", str(member.id))
        if name != str(member.id):
            name += f"#{member.discriminator}"

        if len(notes) == 0:
            await ctx.send(f"{name} has no notes.")
        else:
            fmt = f"**{name} has {len(notes)} notes.**"
            for note in notes:
                moderator = ctx.guild.get_member(int(note["moderator_id"]))
                fmt += f"\n`{note['date']}` Note #{note['case_number']}: {moderator} noted {note['note']}"

            await ctx.send(fmt)

    @group(6, invoke_without_command=True, usage="\u200b")
    async def warn(
        self,
        ctx: commands.Context,
        member: Union[MemberOrID, str] = None,
        *,
        reason: CannedStr = None,
    ) -> None:
        """Manage warns"""
        if isinstance(member, (discord.User, discord.Member)):
            if reason:
                ctx.command = self.add_
                await ctx.invoke(self.add_, member=member, reason=reason)
            else:
                await ctx.invoke(self.bot.get_command("help"), command_or_cog="warn add")
        else:
            await ctx.invoke(self.bot.get_command("help"), command_or_cog="warn")

    @warn.command(6, name="add")
    async def add_(self, ctx: commands.Context, member: MemberOrID, *, reason: CannedStr) -> None:
        """Warn a user

        Can also be used as `warn <member> [reason]`"""
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
        else:
            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            guild_warns = guild_config.warns
            warn_punishments = guild_config.warn_punishments
            warn_punishment_limits = [i.warn_number for i in warn_punishments]
            warns = list(filter(lambda w: w["member_id"] == str(member.id), guild_warns))

            cmd = None
            punish = False

            num_warns = len(warns) + 1
            fmt = f"You have been warned in **{ctx.guild.name}**, reason: {reason}. This is warning #{num_warns}."

            if warn_punishments:
                punishments = list(filter(lambda x: int(x) == num_warns, warn_punishment_limits))
                if not punishments:
                    punish = False
                    above = list(filter(lambda x: int(x) > num_warns, warn_punishment_limits))
                    if above:
                        closest = min(map(int, above))
                        cmd = warn_punishments.get_kv("warn_number", closest).punishment
                        if cmd == "ban":
                            cmd = "bann"
                        if cmd == "mute":
                            cmd = "mut"
                        fmt += f" You will be {cmd}ed on warning {closest}."
                else:
                    punish = True
                    punishment = warn_punishments.get_kv("warn_number", max(map(int, punishments)))
                    cmd = punishment.punishment
                    if cmd == "ban":
                        cmd = "bann"
                    if cmd == "mute":
                        cmd = "mut"
                    fmt += f" You have been {cmd}ed from the server."

            try:
                await member.send(fmt)
            except discord.Forbidden:
                if ctx.author != ctx.guild.me:
                    await ctx.send("The user has PMs disabled or blocked the bot.")
            finally:
                guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
                current_date = f"<t:{int((ctx.message.created_at + timedelta(hours=guild_config.time_offset)).timestamp())}:D>"
                if len(guild_warns) == 0:
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
                    await ctx.send(f"Warned {member.mention} (#{case_number}) for: {reason}")
                await self.send_log(ctx, member, reason, case_number)

                # apply punishment
                if punish:
                    if cmd == "bann":
                        cmd = "ban"
                    if cmd == "mut":
                        cmd = "mute"
                    ctx.command = self.bot.get_command(cmd)
                    ctx.author = ctx.guild.me

                    if punishment.get("duration"):
                        time = UserFriendlyTime(default=False)
                        time.dt = ctx.message.created_at + timedelta(seconds=punishment.duration)
                        time.arg = f"Hit warn limit {num_warns}"
                        kwargs = {"time": time}
                    else:
                        kwargs = {"reason": f"Hit warn limit {num_warns}"}

                    # If previous kick confirmation timed out for this member, resend dialog
                    if cmd == "kick" and str(member.id) in self.kick_confirm_timeouts:
                        await ctx.send(
                            f"Previous kick confirmation for {member} timed out. Resending confirmation dialog."
                        )
                        self.kick_confirm_timeouts.remove(str(member.id))
                        await self.kick(ctx, member, reason=kwargs.get("reason"))
                    else:
                        await ctx.invoke(ctx.command, member, **kwargs)

    @warn.command(6, name="remove", aliases=["delete", "del"])
    async def remove_(self, ctx: commands.Context, case_number: int) -> None:
        """Remove a warn"""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        warns = guild_config.warns
        warn = list(filter(lambda w: w["case_number"] == case_number, warns))[0]
        warn_reason = warn["reason"]

        if len(warn) == 0:
            await ctx.send(f"Warn #{case_number} does not exist.")
        else:
            await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"warns": warn}})
            await ctx.send(f"Warn #{case_number} removed from <@{warn['member_id']}>.")
            await self.send_log(ctx, case_number, warn_reason)

    @warn.command(6, name="list", aliases=["view"])
    async def list_(self, ctx: commands.Context, member: MemberOrID) -> None:
        """View the warns of a user"""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        warns = guild_config.warns
        warns = list(filter(lambda w: w["member_id"] == str(member.id), warns))
        name = getattr(member, "name", str(member.id))
        if name != str(member.id):
            name += f"#{member.discriminator}"

        if len(warns) == 0:
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
        member: discord.Member,
        *,
        time: UserFriendlyTime = None,
    ) -> None:
        """Mute a member for an optional duration and reason.

        Usage:
        - `!!mute @User 10m Spamming`
        - `!!mute 123456789012345678 1h`  (by ID)
        - `!!mute @User`  (indefinite mute)
        """
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
            return

        # Check if member is in the server
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
        if not time:
            duration = None
        else:
            if time.dt:
                duration = time.dt - ctx.message.created_at
            if time.arg:
                reason = time.arg
        await self.alert_user(ctx, member, reason, duration=format_timedelta(duration))
        await self.bot.mute(ctx.author, member, duration, reason=reason)

        if ctx.author != ctx.guild.me:
            if duration:
                await ctx.send(
                    f"{member.mention} has been muted for {format_timedelta(duration)}. Reason: {reason}"
                )
            else:
                await ctx.send(f"{member.mention} has been muted indefinitely. Reason: {reason}")

    @command(6, name="muted")
    async def muted(self, ctx: commands.Context) -> None:
        """List currently muted members for this server.

        Example: `!!muted`
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
        self, ctx: commands.Context, member: discord.Member, *, reason: CannedStr = "No reason"
    ) -> None:
        """Unmute a previously muted member.

        Example: `!!unmute @User Apologized`
        """
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
        else:
            await self.alert_user(ctx, member, reason)
            await self.bot.unmute(ctx.guild.id, member.id, None, reason=reason)
            await ctx.send(f"{member.mention} has been unmuted. Reason: {reason}")

    @command(6, aliases=["clean", "prune"], usage="<limit> [member]")
    async def purge(self, ctx: commands.Context, limit: int, *, member: MemberOrID = None) -> None:
        """Bulk delete messages in the current channel.

        Usage:
        - `!!purge 50`  (delete last 50 messages)
        - `!!purge 100 @User`  (delete up to 100 messages from a specific user)
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
        """Toggle send permissions for @everyone in a channel.

        Examples:
        - `!!lockdown` (toggle current channel)
        - `!!lockdown #general`
        """
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)

        if overwrite.send_messages is None or overwrite.send_messages:
            overwrite.send_messages = False
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
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
        """Enable or disable channel slowmode (max 6h).

        Examples:
        - `!!slowmode 2h`
        - `!!slowmode 2h #general`
        - `!!slowmode off`
        - `!!slowmode 0s #general`
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

    @command(7)
    async def kick(
        self, ctx: commands.Context, member: discord.Member, *, reason: CannedStr = None
    ) -> None:
        """Kick a member from the server.

        Example: `!!kick @User Spamming`
        """
        # Permission level check
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
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
        """Ban then immediately unban to purge messages.

        Example: `!!softban @User Advertising`
        """
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
        else:
            await self.alert_user(ctx, member, reason)
            await member.ban(reason=reason)
            await asyncio.sleep(2)
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
        # Check user permission level
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
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

        # Confirmation dialog
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
            reaction, user = await ctx.bot.wait_for("reaction_add", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("Ban confirmation timed out. Command cancelled.")
            return

        if str(reaction.emoji) == "✅":
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

            # DM user if possible
            try:
                await self.alert_user(ctx, member, reason)
            except Exception:
                pass

            # Get prune_days from config if not provided
            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            if prune_days is None:
                prune_days = getattr(guild_config, "ban_prune_days", 3)
            # If disabled (0 or False), do not prune any messages
            if not prune_days:
                await ctx.guild.ban(
                    member, reason=f"{ctx.author}: {reason}" if reason else f"Ban by {ctx.author}"
                )
            else:
                await ctx.guild.ban(
                    member,
                    reason=f"{ctx.author}: {reason}" if reason else f"Ban by {ctx.author}",
                    delete_message_days=prune_days,
                )

            # If temporary ban, schedule unban and record in DB
            if duration:
                seconds = duration.total_seconds()
                seconds += unixs()
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
            if ctx.author != ctx.guild.me:
                if duration:
                    await ctx.send(
                        f"✅ {getattr(member, 'mention', member)} ({user_id}) has been banned for {format_timedelta(duration)}. Reason: {reason}"
                    )
                else:
                    await ctx.send(
                        f"✅ {getattr(member, 'mention', member)} ({user_id}) has been banned permanently. Reason: {reason}"
                    )

            # Log the ban
            await self.send_log(ctx, member, reason, duration)
        else:
            await ctx.send("Ban cancelled.")

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

    """Basic moderation commands"""

    def __init__(self, bot: rainbot) -> None:
        self.bot = bot
        self.order = 2

    async def cog_error(self, ctx: commands.Context, error: Exception) -> None:
        """Handles discord.Forbidden"""

    async def send_log(self, ctx: commands.Context, *args) -> None:
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        offset = guild_config.time_offset
        current_time = (
            f"<t:{int((ctx.message.created_at + timedelta(hours=offset)).timestamp())}:T>"
        )

        modlogs = DBDict(
            {i: tryint(guild_config.modlog[i]) for i in guild_config.modlog if i},
            _default=DEFAULT["modlog"],
        )

        try:
            if ctx.command.name == "purge":
                fmt = f"{current_time} {ctx.author} purged {args[0]} messages in **#{ctx.channel.name}**"
                if args[1]:
                    fmt += f", from {args[1]}"
                channel = ctx.bot.get_channel(modlogs.message_purge)
                if channel:
                    await channel.send(fmt)
            elif ctx.command.name == "kick":
                fmt = f"{current_time} {ctx.author} kicked {args[0]} ({args[0].id}), reason: {args[1]}"
                channel = ctx.bot.get_channel(modlogs.member_kick)
                if channel:
                    await channel.send(fmt)
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
            elif ctx.command.qualified_name == "warn add":
                fmt = f"{current_time} {ctx.author} warned #{args[2]} {args[0]} ({args[0].id}), reason: {args[1]}"
                channel = ctx.bot.get_channel(modlogs.member_warn)
                if channel:
                    await channel.send(fmt)
            elif ctx.command.qualified_name == "warn remove":
                fmt = f"{current_time} {ctx.author} has deleted warn #{args[0]} - {args[1]}"
                channel = ctx.bot.get_channel(modlogs.member_warn)
                if channel:
                    await channel.send(fmt)
            elif ctx.command.qualified_name == "modlogs remove":
                case_num, original_reason, member_id, mod_id = args
                member = ctx.guild.get_member(int(member_id)) or f"<@{member_id}>"
                original_mod = ctx.guild.get_member(int(mod_id)) or f"<@{mod_id}>"
                fmt = f"{current_time} {ctx.author} has deleted modlog #{case_num}\n• Target: {member} ({member_id})\n• Original Moderator: {original_mod}\n• Original Reason: {original_reason}"
                channel = ctx.bot.get_channel(modlogs.member_warn)
                if channel:
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

            else:
                raise NotImplementedError(
                    f"{ctx.command.name} not implemented for commands/send_log"
                )
        except AttributeError:
            # channel not found [None.send()]
            pass

    @command(5)
    async def user(self, ctx: commands.Context, member: discord.Member) -> None:
        """Get a user's info"""

        async def timestamp(created):
            delta = format_timedelta(ctx.message.created_at - created)
            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            created = created + timedelta(hours=guild_config.time_offset)
            return f"{delta} ago (<t:{int(created.timestamp())}:T>)"

        created = await timestamp(member.created_at)
        joined = await timestamp(member.joined_at)
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

    @group(6, invoke_without_command=True)
    async def note(self, ctx: commands.Context) -> None:
        """Manage notes"""
        await ctx.invoke(self.bot.get_command("help"), command_or_cog="note")

    @note.command(6)
    async def add(self, ctx: commands.Context, member: MemberOrID, *, note):
        """Add a note"""
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
        else:
            guild_data = await self.bot.db.get_guild_config(ctx.guild.id)
            notes = guild_data.notes

            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            current_date = f"<t:{int((ctx.message.created_at + timedelta(hours=guild_config.time_offset)).timestamp())}:D>"
            if len(notes) == 0:
                case_number = 1
            else:
                case_number = notes[-1]["case_number"] + 1

            push = {
                "case_number": case_number,
                "date": current_date,
                "member_id": str(member.id),
                "moderator_id": str(ctx.author.id),
                "note": note,
            }
            await self.bot.db.update_guild_config(ctx.guild.id, {"$push": {"notes": push}})
            await ctx.send(f"Note added for {member.mention}: {note}")

    @note.command(6, aliases=["delete", "del"])
    async def remove(self, ctx: commands.Context, case_number: int) -> None:
        """Remove a note"""
        guild_data = await self.bot.db.get_guild_config(ctx.guild.id)
        notes = guild_data.notes
        note = list(filter(lambda w: w["case_number"] == case_number, notes))
        if len(note) == 0:
            await ctx.send(f"Note #{case_number} does not exist.")
        else:
            await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"notes": note[0]}})
            await ctx.send(f"Note #{case_number} removed from <@{note[0]['member_id']}>.")

    @note.command(6, name="list", aliases=["view"])
    async def _list(self, ctx: commands.Context, member: MemberOrID) -> None:
        """View the notes of a user"""
        guild_data = await self.bot.db.get_guild_config(ctx.guild.id)
        notes = guild_data.notes
        notes = list(filter(lambda w: w["member_id"] == str(member.id), notes))
        name = getattr(member, "name", str(member.id))
        if name != str(member.id):
            name += f"#{member.discriminator}"

        if len(notes) == 0:
            await ctx.send(f"{name} has no notes.")
        else:
            fmt = f"**{name} has {len(notes)} notes.**"
            for note in notes:
                moderator = ctx.guild.get_member(int(note["moderator_id"]))
                fmt += f"\n`{note['date']}` Note #{note['case_number']}: {moderator} noted {note['note']}"

            await ctx.send(fmt)

    @group(6, invoke_without_command=True, usage="\u200b")
    async def warn(
        self,
        ctx: commands.Context,
        member: Union[MemberOrID, str] = None,
        *,
        reason: CannedStr = None,
    ) -> None:
        """Manage warns"""
        if isinstance(member, (discord.User, discord.Member)):
            if reason:
                ctx.command = self.add_
                await ctx.invoke(self.add_, member=member, reason=reason)
            else:
                await ctx.invoke(self.bot.get_command("help"), command_or_cog="warn add")
        else:
            await ctx.invoke(self.bot.get_command("help"), command_or_cog="warn")

    @warn.command(6, name="add")
    async def add_(self, ctx: commands.Context, member: MemberOrID, *, reason: CannedStr) -> None:
        """Warn a user

        Can also be used as `warn <member> [reason]`"""
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
        else:
            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            guild_warns = guild_config.warns
            warn_punishments = guild_config.warn_punishments
            warn_punishment_limits = [i.warn_number for i in warn_punishments]
            warns = list(filter(lambda w: w["member_id"] == str(member.id), guild_warns))

            cmd = None
            punish = False

            num_warns = len(warns) + 1
            fmt = f"You have been warned in **{ctx.guild.name}**, reason: {reason}. This is warning #{num_warns}."

            if warn_punishments:
                punishments = list(filter(lambda x: int(x) == num_warns, warn_punishment_limits))
                if not punishments:
                    punish = False
                    above = list(filter(lambda x: int(x) > num_warns, warn_punishment_limits))
                    if above:
                        closest = min(map(int, above))
                        cmd = warn_punishments.get_kv("warn_number", closest).punishment
                        if cmd == "ban":
                            cmd = "bann"
                        if cmd == "mute":
                            cmd = "mut"
                        fmt += f" You will be {cmd}ed on warning {closest}."
                else:
                    punish = True
                    punishment = warn_punishments.get_kv("warn_number", max(map(int, punishments)))
                    cmd = punishment.punishment
                    if cmd == "ban":
                        cmd = "bann"
                    if cmd == "mute":
                        cmd = "mut"
                    fmt += f" You have been {cmd}ed from the server."

            try:
                await member.send(fmt)
            except discord.Forbidden:
                if ctx.author != ctx.guild.me:
                    await ctx.send("The user has PMs disabled or blocked the bot.")
            finally:
                guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
                current_date = f"<t:{int((ctx.message.created_at + timedelta(hours=guild_config.time_offset)).timestamp())}:D>"
                if len(guild_warns) == 0:
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
                    await ctx.send(f"Warned {member.mention} (#{case_number}) for: {reason}")
                await self.send_log(ctx, member, reason, case_number)

                # apply punishment
                if punish:
                    if cmd == "bann":
                        cmd = "ban"
                    if cmd == "mut":
                        cmd = "mute"
                    ctx.command = self.bot.get_command(cmd)
                    ctx.author = ctx.guild.me
                    kwargs = {"reason": f"Hit warn limit {num_warns}"}
                    if punishment.get("duration"):
                        time_obj = UserFriendlyTime(default=False)
                        time_obj.dt = ctx.message.created_at + timedelta(
                            seconds=punishment.duration
                        )
                        time_obj.arg = f"Hit warn limit {num_warns}"
                        kwargs = {"time": time_obj}
                    await ctx.invoke(ctx.command, member, **kwargs)

    @warn.command(6, name="remove", aliases=["delete", "del"])
    async def remove_(self, ctx: commands.Context, case_number: int) -> None:
        """Remove a warn"""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        warns = guild_config.warns
        warn = list(filter(lambda w: w["case_number"] == case_number, warns))[0]
        warn_reason = warn["reason"]

        if len(warn) == 0:
            await ctx.send(f"Warn #{case_number} does not exist.")
        else:
            await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"warns": warn}})
            await ctx.send(f"Warn #{case_number} removed from <@{warn['member_id']}>.")
            await self.send_log(ctx, case_number, warn_reason)

    @warn.command(6, name="list", aliases=["view"])
    async def list_(self, ctx: commands.Context, member: MemberOrID) -> None:
        """View the warns of a user"""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        warns = guild_config.warns
        warns = list(filter(lambda w: w["member_id"] == str(member.id), warns))
        name = getattr(member, "name", str(member.id))
        if name != str(member.id):
            name += f"#{member.discriminator}"

        if len(warns) == 0:
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
        member: discord.Member,
        *,
        time: UserFriendlyTime = None,
    ) -> None:
        """Mute a member for an optional duration and reason.

        Usage:
        - `!!mute @User 10m Spamming`
        - `!!mute 123456789012345678 1h`  (by ID)
        - `!!mute @User`  (indefinite mute)
        """
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
            return

        # Check if member is in the server
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
        if not time:
            duration = None
        else:
            if time.dt:
                duration = time.dt - ctx.message.created_at
            if time.arg:
                reason = time.arg
        await self.alert_user(ctx, member, reason, duration=format_timedelta(duration))
        await self.bot.mute(ctx.author, member, duration, reason=reason)

        if ctx.author != ctx.guild.me:
            if duration:
                await ctx.send(
                    f"{member.mention} has been muted for {format_timedelta(duration)}. Reason: {reason}"
                )
            else:
                await ctx.send(f"{member.mention} has been muted indefinitely. Reason: {reason}")

    @command(6, name="muted")
    async def muted(self, ctx: commands.Context) -> None:
        """List currently muted members for this server.

        Example: `!!muted`
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
        self, ctx: commands.Context, member: discord.Member, *, reason: CannedStr = "No reason"
    ) -> None:
        """Unmute a previously muted member.

        Example: `!!unmute @User Apologized`
        """
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
        else:
            await self.alert_user(ctx, member, reason)
            await self.bot.unmute(ctx.guild.id, member.id, None, reason=reason)
            await ctx.send(f"{member.mention} has been unmuted. Reason: {reason}")

    @command(6, aliases=["clean", "prune"], usage="<limit> [member]")
    async def purge(self, ctx: commands.Context, limit: int, *, member: MemberOrID = None) -> None:
        """Bulk delete messages in the current channel.

        Usage:
        - `!!purge 50`  (delete last 50 messages)
        - `!!purge 100 @User`  (delete up to 100 messages from a specific user)
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
        """Toggle send permissions for @everyone in a channel.

        Examples:
        - `!!lockdown` (toggle current channel)
        - `!!lockdown #general`
        """
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)

        if overwrite.send_messages is None or overwrite.send_messages:
            overwrite.send_messages = False
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
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
        """Enable or disable channel slowmode (max 6h).

        Examples:
        - `!!slowmode 2h`
        - `!!slowmode 2h #general`
        - `!!slowmode off`
        - `!!slowmode 0s #general`
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

    @command(7)
    async def kick(
        self, ctx: commands.Context, member: discord.Member, *, reason: CannedStr = None
    ) -> None:
        """Kick a member from the server.

        Example: `!!kick @User Spamming`
        """
        # Permission level check
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
            return

        # Check if member is in the server
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

        # Confirmation dialog
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
            await ctx.send("Kick confirmation timed out. Command cancelled.")
            return

        if str(reaction.emoji) == "✅":
            try:
                await self.alert_user(ctx, member, reason)
                await member.kick(reason=reason)
                await ctx.send(f"{member.mention} ({member.id}) has been kicked. Reason: {reason}")
                await self.send_log(ctx, member, reason)
            except discord.Forbidden:
                await ctx.send(
                    "I don't have permission to kick that member! They might have a higher role than me."
                )
            except discord.NotFound:
                await ctx.send(f"Could not find user {member}")
            except Exception as e:
                try:
                    await ctx.send(f"Failed to kick member: {e}")
                except Exception:
                    pass
        else:
            await ctx.send("Kick cancelled.")

    @command(7)
    async def softban(
        self, ctx: commands.Context, member: discord.Member, *, reason: CannedStr = None
    ) -> None:
        """Ban then immediately unban to purge messages.

        Example: `!!softban @User Advertising`
        """
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
        else:
            await self.alert_user(ctx, member, reason)
            await member.ban(reason=reason)
            await asyncio.sleep(2)
            await member.unban(reason=reason)
            await ctx.send(f"{member.mention} has been softbanned (ban/unban). Reason: {reason}")
            await self.send_log(ctx, member, reason)

    # ...existing code...


# Extension loader required by discord.py
async def setup(bot):
    await bot.add_cog(Moderation(bot))
