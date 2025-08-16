import asyncio
from datetime import datetime, timedelta
from typing import Optional, Union

import discord
from discord.ext import commands
from bot import rainbot

from ext.command import command, group
from ext.time import UserFriendlyTime
from ext.utility import get_perm_level, CannedStr

# --- Helpers ---

def validate_case_number(case_num):
    try:
        num = int(case_num)
        return num if 0 < num < 999999 else None
    except (ValueError, TypeError):
        return None

def validate_user_id(user_id):
    try:
        uid = int(user_id)
        return uid if 0 < uid < 2**63 else None
    except (ValueError, TypeError):
        return None

async def maybe_dm(member, message):
    try:
        await member.send(message)
    except Exception:
        pass

def format_timedelta(delta, assume_forever=True):
    if not delta:
        return "forever" if assume_forever else "0 seconds"
    seconds = int(delta.total_seconds())
    if seconds < 1:
        return "0 seconds"
    periods = [
        (seconds // 86400, "day"),
        (seconds % 86400 // 3600, "hour"),
        (seconds % 3600 // 60, "minute"),
        (seconds % 60, "second"),
    ]
    return ", ".join(f"{v} {p}{'s' if v != 1 else ''}" for v, p in periods if v)

# --- Member/User type combo for argument parsing ---
class MemberOrID(commands.IDConverter):
    async def convert(self, ctx: commands.Context, argument: str) -> Union[discord.Member, discord.User]:
        try:
            return await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            try:
                return await ctx.bot.fetch_user(int(argument))
            except (ValueError, TypeError):
                raise commands.BadArgument(f"Member {argument} not found")

# --- Main Moderation Cog ---
class Moderation(commands.Cog):
    def __init__(self, bot: rainbot) -> None:
        self.bot = bot
        self.order = 2
        self.kick_confirm_timeouts = set()

    # --- Logging helper ---
    async def send_log(self, ctx, *args):
        # Dummy log stub (replace with real logging procedure if desired)
        pass

    # --- DM Helper ---
    async def alert_user(self, ctx, member, reason: str = None, *, duration: str = None):
        if not hasattr(member, "send"):
            try:
                member = await ctx.bot.fetch_user(int(getattr(member, "id", member)))
            except Exception:
                return
        msg = f"You have been {ctx.command.name if ctx.command else 'moderated'} in **{ctx.guild.name}**."
        if reason:
            msg += f"\nReason: {reason}"
        if duration:
            msg += f"\nDuration: {duration}"
        await maybe_dm(member, msg)

    # --- Modlogs Commands ---
    @group(6, invoke_without_command=True, usage="<user_id>")
    async def modlogs(self, ctx: commands.Context, user: MemberOrID = None):
        await ctx.send("Modlogs viewing not yet implemented here. Use `modlogs all`.")

    @modlogs.command(6, name="all")
    async def modlogs_all(self, ctx):
        # TODO: Implement paginated modlogs
        await ctx.send("All moderation logs listing is not implemented in rewrite demo.")

    @modlogs.command(6, name="remove", aliases=["delete", "del"], usage="<case_number>")
    async def remove_modlog(self, ctx: commands.Context, case_number: int = None):
        if case_number is None:
            await ctx.send("❌ Please provide a case number to remove.")
            return
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        modlogs = getattr(guild_config, "modlog", [])
        target = next((m for m in modlogs if m.get("case_number") == case_number), None)
        if not target:
            await ctx.send(f"Modlog #{case_number} does not exist.")
            return
        member = ctx.guild.get_member(int(target["member_id"])) or f"<@{target['member_id']}>"
        moderator = ctx.guild.get_member(int(target["moderator_id"]))
        moderator_name = moderator.mention if moderator else f"<@{target['moderator_id']}>"
        embed = discord.Embed(title="Confirm Modlog Removal",
            description=f"Are you sure you want to remove Modlog #{case_number}?\n\n"
                        f"**Target:** {member}\n**Reason:** {target['reason']}\n**Moderator:** {moderator_name}",
            color=discord.Color.red())
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅"); await msg.add_reaction("❌")
        def check(r, u): return u == ctx.author and r.message.id == msg.id and str(r.emoji) in ("✅", "❌")
        try:
            reaction, _ = await ctx.bot.wait_for("reaction_add", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await msg.edit(embed=discord.Embed(title="Cancelled", description="Timeout.", color=discord.Color.red()))
            return
        if str(reaction.emoji) == "✅":
            await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"modlog": target}})
            await msg.edit(embed=discord.Embed(title="Modlog Removed", description=f"Removed #{case_number}.", color=discord.Color.green()))
        else:
            await msg.edit(embed=discord.Embed(title="Cancelled", description="Operation cancelled.", color=discord.Color.red()))

    # --- Notes Commands ---
    @group(6, invoke_without_command=True)
    async def note(self, ctx):
        await ctx.invoke(self.bot.get_command("help"), command_or_cog="note")

    @note.command(6)
    async def add(self, ctx, member: MemberOrID, *, note):
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
        else:
            guild_data = await self.bot.db.get_guild_config(ctx.guild.id)
            notes = getattr(guild_data, "notes", [])
            case_number = notes[-1]["case_number"] + 1 if notes else 1
            now = int((ctx.message.created_at + timedelta(hours=getattr(guild_data, "time_offset", 0))).timestamp())
            push = {
                "case_number": case_number,
                "date": f"<t:{now}:D>",
                "member_id": str(member.id),
                "moderator_id": str(ctx.author.id),
                "note": note,
            }
            await self.bot.db.update_guild_config(ctx.guild.id, {"$push": {"notes": push}})
            await ctx.send(f"Note added for {member.mention}: {note}")

    @note.command(6, aliases=["delete", "del"])
    async def remove(self, ctx, case_number: int):
        guild_data = await self.bot.db.get_guild_config(ctx.guild.id)
        notes = getattr(guild_data, "notes", [])
        note = next((w for w in notes if w["case_number"] == case_number), None)
        if not note:
            await ctx.send(f"Note #{case_number} does not exist.")
            return
        await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"notes": note}})
        await ctx.send(f"Note #{case_number} removed from <@{note['member_id']}>.")

    @note.command(6, name="list", aliases=["view"])
    async def _list(self, ctx, member: MemberOrID):
        guild_data = await self.bot.db.get_guild_config(ctx.guild.id)
        notes = [w for w in getattr(guild_data, "notes", []) if w["member_id"] == str(member.id)]
        name = getattr(member, "name", str(member.id))
        if not notes:
            await ctx.send(f"{name} has no notes.")
        else:
            fmt = f"**{name} has {len(notes)} notes.**"
            for note in notes:
                moderator = ctx.guild.get_member(int(note["moderator_id"]))
                fmt += f"\n`{note['date']}` Note #{note['case_number']}: {moderator} noted {note['note']}"
            await ctx.send(fmt)

    # --- Warn Commands ---
    @group(6, invoke_without_command=True, usage="\u200b")
    async def warn(self, ctx, member: Union[MemberOrID, str] = None, *, reason: CannedStr = None):
        if isinstance(member, (discord.User, discord.Member)):
            if reason:
                await ctx.invoke(self.add_, member=member, reason=reason)
            else:
                await ctx.invoke(self.bot.get_command("help"), command_or_cog="warn add")
        else:
            await ctx.invoke(self.bot.get_command("help"), command_or_cog="warn")

    @warn.command(6, name="add")
    async def add_(self, ctx, member: MemberOrID, *, reason: CannedStr):
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
            return
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        guild_warns = getattr(guild_config, "warns", [])
        warns = [w for w in guild_warns if w["member_id"] == str(member.id)]
        case_number = guild_warns[-1]["case_number"] + 1 if guild_warns else 1
        now = int((ctx.message.created_at + timedelta(hours=getattr(guild_config, "time_offset", 0))).timestamp())
        push = {
            "case_number": case_number,
            "date": f"<t:{now}:D>",
            "member_id": str(member.id),
            "moderator_id": str(ctx.author.id),
            "reason": reason,
        }
        await self.bot.db.update_guild_config(ctx.guild.id, {"$push": {"warns": push}})
        await self.alert_user(ctx, member, reason)
        await ctx.send(f"Warned {member.mention} (#{case_number}) for: {reason}")
        await self.send_log(ctx, member, reason, case_number)

    @warn.command(6, name="remove", aliases=["delete", "del"])
    async def remove_warn(self, ctx, case_number: int):
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        warns = getattr(guild_config, "warns", [])
        warn = next((w for w in warns if w.get("case_number") == case_number), None)
        if not warn:
            await ctx.send("Warning not found.")
            return
        await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"warns": warn}})
        await ctx.send(f"Warn #{case_number} removed from <@{warn['member_id']}>.")
        await self.send_log(ctx, case_number, warn["reason"])

    @warn.command(6, name="list", aliases=["view"])
    async def list_warns(self, ctx, member: MemberOrID):
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        warns = [w for w in getattr(guild_config, "warns", []) if w["member_id"] == str(member.id)]
        name = getattr(member, "name", str(member.id))
        if not warns:
            await ctx.send(f"{name} has no warns.")
        else:
            fmt = f"**{name} has {len(warns)} warns.**"
            for warn in warns:
                moderator = ctx.guild.get_member(int(warn["moderator_id"]))
                fmt += f"\n`{warn['date']}` Warn #{warn['case_number']}: {moderator} warned {name} for {warn['reason']}"
            await ctx.send(fmt)

    # --- Mute, Unmute, Muted ---
    @command(6, usage="<member> [duration] [reason]")
    async def mute(self, ctx, member: discord.Member, *, time: UserFriendlyTime = None):
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
            return
        if not isinstance(member, discord.Member):
            member_obj = ctx.guild.get_member(getattr(member, "id", member))
            if not member_obj:
                await ctx.send("User is not present in this server and cannot be muted.")
                return
            member = member_obj
        duration = time.dt - ctx.message.created_at if time and time.dt else None
        reason = time.arg if time and time.arg else None
        await self.alert_user(ctx, member, reason, duration=format_timedelta(duration))
        await self.bot.mute(ctx.author, member, duration, reason=reason)
        if duration:
            await ctx.send(f"{member.mention} has been muted for {format_timedelta(duration)}. Reason: {reason}")
        else:
            await ctx.send(f"{member.mention} has been muted indefinitely. Reason: {reason}")

    @command(6, name="muted")
    async def muted(self, ctx):
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
    async def unmute(self, ctx, member: discord.Member, *, reason: CannedStr = "No reason"):
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
            return
        await self.alert_user(ctx, member, reason)
        await self.bot.unmute(ctx.guild.id, member.id, None, reason=reason)
        await ctx.send(f"{member.mention} has been unmuted. Reason: {reason}")

    # --- Purge ---
    @command(6, aliases=["clean", "prune"], usage="<limit> [member]")
    async def purge(self, ctx, limit: int, *, member: MemberOrID = None):
        count = min(2000, limit)
        try:
            await ctx.message.delete()
        except discord.NotFound:
            pass
        deleted = []
        if member:
            def check(m): return m.author.id == member.id
            deleted = await ctx.channel.purge(limit=count, check=check)
        else:
            deleted = await ctx.channel.purge(limit=count)
        await ctx.send(f"Deleted {len(deleted)} messages", delete_after=3)
        await self.send_log(ctx, len(deleted), member)

    # --- Kick, Ban, Softban ---
    @command(7)
    async def kick(self, ctx, member: discord.Member, *, reason: CannedStr = None):
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
            return
        if not isinstance(member, discord.Member):
            member_obj = ctx.guild.get_member(getattr(member, "id", member))
            if not member_obj:
                await ctx.send("User is not present in this server and cannot be kicked.")
                return
            member = member_obj
        if not ctx.guild.me.guild_permissions.kick_members:
            await ctx.send("I don't have permission to kick members!")
            return
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send("I cannot kick this user due to role hierarchy!")
            return
        if member == ctx.guild.me or member == ctx.guild.owner:
            await ctx.send("I cannot kick myself or the server owner!")
            return
        embed = discord.Embed(title="Confirm Kick", description=f"Kick {member.mention}?\nReason: {reason or 'No reason'}", color=discord.Color.orange())
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅"); await msg.add_reaction("❌")
        def check(r, u): return u == ctx.author and r.message.id == msg.id and str(r.emoji) in ("✅", "❌")
        try:
            reaction, _ = await ctx.bot.wait_for("reaction_add", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await msg.edit(embed=discord.Embed(title="Kick Cancelled", description="Kick confirmation timed out.", color=discord.Color.red()))
            return
        if str(reaction.emoji) == "✅":
            try:
                await self.alert_user(ctx, member, reason)
                await member.kick(reason=reason)
                await msg.edit(embed=discord.Embed(title="Kick Success", description=f"{member.mention} has been kicked.", color=discord.Color.green()))
                await self.send_log(ctx, member, reason)
            except Exception as e:
                await msg.edit(embed=discord.Embed(title="Kick Failed", description=f"Failed to kick: {e}", color=discord.Color.red()))
        else:
            await msg.edit(embed=discord.Embed(title="Kick Cancelled", description="Cancelled.", color=discord.Color.red()))

    @command(7)
    async def softban(self, ctx, member: discord.Member, *, reason: CannedStr = None):
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
            return
        await self.alert_user(ctx, member, reason)
        try:
            await member.ban(reason=reason)
            await asyncio.sleep(0.5)
            await member.unban(reason=reason)
            await ctx.send(f"{member.mention} has been softbanned (ban/unban)."); await self.send_log(ctx, member, reason)
        except Exception as e:
            await ctx.send(f"Failed softban: {e}")

    @command(7, usage="<member> [duration] [reason]")
    async def ban(self, ctx, member: MemberOrID, time_or_reason: str = None, prune_days: int = None):
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
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
        embed = discord.Embed(title="Confirm Ban", description=f"Ban {getattr(member, 'mention', member)}?\nReason: {reason or 'No reason'}", color=discord.Color.red())
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅"); await msg.add_reaction("❌")
        def check(r, u): return u == ctx.author and r.message.id == msg.id and str(r.emoji) in ("✅", "❌")
        try:
            reaction, _ = await ctx.bot.wait_for("reaction_add", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("Ban confirmation timed out.")
            return
        if str(reaction.emoji) == "✅":
            if not ctx.guild.me.guild_permissions.ban_members:
                await ctx.send("I don't have permission to ban members!"); return
            try:
                await self.alert_user(ctx, member, reason)
                await ctx.guild.ban(member, reason=f"{ctx.author}: {reason}" if reason else f"Ban by {ctx.author}", delete_message_days=prune_days or 0)
                await ctx.send(f"✅ {getattr(member, 'mention', member)} has been banned. Reason: {reason}")
                await self.send_log(ctx, member, reason, duration)
            except Exception as e:
                await ctx.send(f"Failed to ban: {e}")
        else:
            await ctx.send("Ban cancelled.")

    # --- Lockdown ---
    @command(6)
    async def lockdown(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        if overwrite.send_messages is None or overwrite.send_messages:
            overwrite.send_messages = False
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
            await ctx.send(f"Lockdown {self.bot.accept if hasattr(self.bot, 'accept') else '[locked]'}")
            enable = True
        else:
            overwrite.send_messages = None
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
            await ctx.send(f"Un-lockdown {self.bot.accept if hasattr(self.bot, 'accept') else '[unlocked]'}")
            enable = False
        await self.send_log(ctx, enable, channel)

    # --- Slowmode ---
    @command(6, usage="[duration] [channel]")
    async def slowmode(self, ctx, *, time: UserFriendlyTime):
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

    # --- User Info ---
    @command(5)
    async def user(self, ctx, member: discord.Member):
        async def timestamp(created):
            delta = format_timedelta(ctx.message.created_at - created)
            guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
            created = created + timedelta(hours=getattr(guild_config, "time_offset", 0))
            return f"{delta} ago (<t:{int(created.timestamp())}:T>)"
        created = await timestamp(member.created_at)
        joined = await timestamp(member.joined_at) if member.joined_at else "Unknown"
        member_info = f"**Joined** {joined}\n"
        roles = [i.name for i in reversed(member.roles) if i != ctx.guild.default_role]
        if roles:
            member_info += "**Roles**: " + ", ".join(roles) + "\n"
        em = discord.Embed(color=member.color)
        em.set_author(name=str(member), icon_url=str(member.display_avatar.url))
        em.add_field(name="Basic Information", value=f"**ID**: {member.id}\n**Nickname**: {member.nick}\n**Mention**: {member.mention}\n**Created** {created}", inline=False)
        em.add_field(name="Member Information", value=member_info, inline=False)
        await ctx.send(embed=em)

# Extension loader
async def setup(bot):
    await bot.add_cog(Moderation(bot))
