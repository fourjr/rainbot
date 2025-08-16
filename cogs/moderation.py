import asyncio
import re
import string
from datetime import timedelta
from time import time as unixs
from typing import Union

import discord
from discord.ext import commands

from bot import rainbot
from ext.command import command, group
from ext.database import DEFAULT, DBDict
from ext.time import UserFriendlyTime
from ext.utility import format_timedelta, get_perm_level, tryint, SafeFormat, CannedStr

MEMBER_ID_REGEX = re.compile(r"<@!?([0-9]+)>$")


class MemberOrID(commands.IDConverter):
    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> Union[discord.Member, discord.User]:
        result: Union[discord.Member, discord.User]
        try:
            result = await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            match = self._get_id_match(argument) or MEMBER_ID_REGEX.match(argument)
            if match:
                try:
                    result = await ctx.bot.fetch_user(int(match.group(1)))
                except discord.NotFound as e:
                    raise commands.BadArgument(f"Member {argument} not found") from e
            else:
                raise commands.BadArgument(f"Member {argument} not found")

        return result


class Moderation(commands.Cog):
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        bot = getattr(self, 'bot', None)
        if not bot:
            return
        guild_config = await bot.db.get_guild_config(guild.id)
        mutes = getattr(guild_config, "mutes", [])
        # Find mute entry for this member
        mute_entry = next((m for m in mutes if int(m.get("member", 0)) == member.id), None)
        if mute_entry:
            # Find mute role
            mute_role_id = getattr(guild_config, "mute_role", None)
            mute_role = guild.get_role(mute_role_id) if mute_role_id else None
            if mute_role and mute_role not in member.roles:
                try:
                    await member.add_roles(mute_role, reason="Reapplying mute after rejoin")
                except Exception:
                    pass

    @group(6, invoke_without_command=True)
    async def modlogs(self, ctx: commands.Context, member: MemberOrID = None) -> None:
        """View or manage moderation logs (warns, kicks, mutes, bans, etc.) for a user.

        Commands:
          modlogs <user>          View moderation logs for a specific user
          modlogs remove <case>   Remove a moderation log entry by case number"""
        if member is None:
            await ctx.invoke(self.bot.get_command("help"), command_or_cog="modlogs")
            return
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        warns = guild_config.warns
        warns = list(filter(lambda w: w["member_id"] == str(member.id), warns))
        # Optionally, you could add more moderation actions here (kicks, mutes, bans) if stored in DB
        name = getattr(member, "name", str(member.id))
        # Only show discriminator for bot accounts (Discord bots still have discriminators)
        if name != str(member.id) and getattr(member, "bot", False):
            name += f"#{getattr(member, 'discriminator', '')}"

        if len(warns) == 0:
            await ctx.send(f"{name} has no warns.")
        else:
            fmt = f"**{name} has {len(warns)} warns.**"
            for warn in warns:
                moderator = ctx.guild.get_member(int(warn["moderator_id"]))
                # Try to extract a unix timestamp from warn['date'] if possible, else just show as is
                # If warn['date'] is in <t:unix:D> format, extract the unix part
                date_str = warn["date"]
                unix_match = None
                if isinstance(date_str, str) and date_str.startswith("<t:"):
                    import re

                    m = re.match(r"<t:(\\d+):[A-Z]>", date_str)
                    if m:
                        unix_match = int(m.group(1))
                if unix_match:
                    timestamp_fmt = f"<t:{unix_match}:F>"
                else:
                    timestamp_fmt = date_str
                fmt += f"\n{timestamp_fmt} Warn #{warn['case_number']}: {moderator} warned {name} for {warn['reason']}"
            await ctx.send(fmt)

    @modlogs.command(6, name="remove", aliases=["delete", "del"])
    async def modlogs_remove(self, ctx: commands.Context, case_number: int) -> None:
        """Remove a moderation log entry.

        Args:
            case_number: The case number to remove

        Example:
            modlogs remove 123"""
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        warns = guild_config.warns
        warn = next((w for w in warns if w["case_number"] == case_number), None)
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
        except asyncio.TimeoutError:
            await ctx.send("Warn removal timed out. Command cancelled.")
            return
        if str(reaction.emoji) == "✅":
            await self.bot.db.update_guild_config(ctx.guild.id, {"$pull": {"warns": warn}})
            await ctx.send(f"Warn #{case_number} removed.")
            await self.send_log(
                ctx, case_number, warn["reason"], warn["member_id"], warn["moderator_id"]
            )
        else:
            await ctx.send("Warn removal cancelled.")

    """Basic moderation commands"""

    def __init__(self, bot: rainbot) -> None:
        self.bot = bot
        self.order = 2

    async def cog_error(self, ctx: commands.Context, error: Exception) -> None:
        """Handles discord.Forbidden"""
        if isinstance(error, discord.Forbidden):
            await ctx.send(
                f"I do not have the required permissions needed to run `{ctx.command.name}`."
            )

    async def alert_user(self, ctx: commands.Context, member, reason, *, duration=None) -> None:
        guild_config = await self.bot.db.get_guild_config(ctx.guild.id)
        offset = guild_config.time_offset
        # Discord relative/local timestamp for display in user's locale
        current_time = (
            f"<t:{int((ctx.message.created_at + timedelta(hours=offset)).timestamp())}:T>"
        )

        if guild_config.alert[ctx.command.name]:
            fmt = string.Formatter().vformat(
                guild_config.alert[ctx.command.name],
                [],
                SafeFormat(
                    time=current_time,
                    author=ctx.author,
                    user=member,
                    reason=reason,
                    duration=duration,
                    channel=ctx.channel,
                    guild=ctx.guild,
                ),
            )

            try:
                await member.send(fmt)
            except discord.Forbidden:
                pass

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
                await ctx.send(f"User {getattr(member, 'mention', member)} is not present in this server and cannot be muted.")
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
                await ctx.send(
                    f"{member.mention} has been muted indefinitely. Reason: {reason}"
                )

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
                    await ctx.send(f"User {getattr(member, 'mention', member)} is not present in this server and cannot be kicked.")
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

        try:
            await self.alert_user(ctx, member, reason)
            await member.kick(reason=reason)
            if ctx.author != ctx.guild.me:
                await ctx.send(f"{member.mention} ({member.id}) has been kicked. Reason: {reason}")
            await self.send_log(ctx, member, reason)
        except discord.Forbidden:
            await ctx.send("I don't have permission to kick that member! They might have a higher role than me.")
        except discord.NotFound:
            await ctx.send(f"Could not find user {member}")
        except Exception as e:
            try:
                await ctx.send(f"Failed to kick member: {e}")
            except Exception:
                pass

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
        *,
        time_or_reason: str = None,
        prune_days: int = None,
    ) -> None:
        """Ban a member from the server, optionally with a duration.

        Examples:
        - `!!ban @User Spamming` (permanent ban)
        - `!!ban @User 7d Spamming` (7 day ban)
        - `!!ban 123456789 24h Raid` (24 hour ban by ID)"""
        # Check user permission level
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
            return

        # Parse duration and reason. We accept free-form trailing text and try to parse it as a time first;
        # if parsing fails, treat the whole trailing text as a reason only.
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
                # Not a time string -> treat as plain reason (can be multiple words)
                reason = time_or_reason

        try:
            # Check bot permissions
            if not ctx.guild.me.guild_permissions.ban_members:
                await ctx.send("I don't have permission to ban members!")
                return

            # Check if user is already banned
            try:
                # fetch_ban accepts a user or user id
                ban_entry = await ctx.guild.fetch_ban(member)
            except discord.NotFound:
                ban_entry = None

            if ban_entry:
                user_id = getattr(member, "id", member)
                display_name = getattr(member, "mention", str(member))
                display_with_id = f"{display_name} ({user_id})"
                await ctx.send(f"{display_with_id} is already banned (Reason: {ban_entry.reason})")
                return

            # If member is in guild, perform role hierarchy check and alert them directly
            guild_member = None
            if isinstance(member, discord.Member):
                guild_member = member
            else:
                # Try to resolve to a guild member if possible
                try:
                    guild_member = ctx.guild.get_member(member.id)
                except Exception:
                    guild_member = None

            if guild_member:
                if guild_member.top_role >= ctx.guild.me.top_role:
                    await ctx.send("I cannot ban this user due to role hierarchy!")
                    return
                # Alert the user (DM) before banning
                await self.alert_user(
                    ctx, guild_member, reason, duration=format_timedelta(duration)
                )
            else:
                # User not in guild; attempt to DM the user object if possible
                try:
                    user_obj = (
                        member
                        if isinstance(member, (discord.User, discord.Member))
                        else await ctx.bot.fetch_user(int(str(member)))
                    )
                    await self.alert_user(
                        ctx, user_obj, reason, duration=format_timedelta(duration)
                    )
                except Exception:
                    # DM failed or not resolvable; continue to ban by id/object
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
                # schedule unban task on the bot
                self.bot.loop.create_task(
                    self.bot.unban(ctx.guild.id, getattr(member, "id", member), seconds)
                )

            # Send confirmation
            display_name = (
                str(guild_member)
                if guild_member
                else (
                    f"{getattr(member, 'name', None)}#{getattr(member, 'discriminator', '')}"
                    if hasattr(member, "name") and getattr(member, "bot", False)
                    else (
                        f"{getattr(member, 'name', None)}"
                        if hasattr(member, "name")
                        else f"User ID: {getattr(member, 'id', member)}"
                    )
                )
            )
            user_id = getattr(member, "id", member)
            if ctx.author != ctx.guild.me:
                if duration:
                    await ctx.send(
                        f"✅ {display_name} ({user_id}) has been banned for {format_timedelta(duration)}. Reason: {reason}"
                    )
                else:
                    await ctx.send(
                        f"✅ {display_name} ({user_id}) has been banned permanently. Reason: {reason}"
                    )

            # Log the ban
            await self.send_log(ctx, member, reason, duration)

        except discord.Forbidden:
            await ctx.send(
                "I don't have permission to ban that member! They might have a higher role than me."
            )
        except discord.NotFound:
            await ctx.send(f"Could not find user {member}")
        except Exception as e:
            # Log exception for debugging and inform the invoker
            try:
                await ctx.send(f"Failed to ban member: {e}")
            except Exception:
                pass

    @command(7, usage="<member> [duration] [reason]")
    async def unban(
        self,
        ctx: commands.Context,
        member: MemberOrID,
        *,
        time: UserFriendlyTime = None,
    ) -> None:
        """Unban a user by name#discriminator or ID.

        Examples:
        - `!!unban 123456789012345678`
        - `!!unban user#0001 Appeal accepted`
        """
        if (
            get_perm_level(member, await self.bot.db.get_guild_config(ctx.guild.id))[0]
            >= get_perm_level(ctx.author, await self.bot.db.get_guild_config(ctx.guild.id))[0]
        ):
            await ctx.send("User has insufficient permissions")
        else:
            duration = None
            reason = None
            if not time:
                duration = None
            else:
                if time.dt:
                    duration = time.dt - ctx.message.created_at
                if time.arg:
                    reason = time.arg

        if duration is None:
            try:
                await ctx.guild.unban(member, reason=reason)
            except discord.NotFound as e:
                await ctx.send(f"Unable to unban user: {e}")
            else:
                user_id = getattr(member, "id", member)
                await ctx.send(f"{member.mention} ({user_id}) has been unbanned. Reason: {reason}")
                await self.send_log(ctx, member, reason)
        else:
            await ctx.send(
                f"{member.mention} will be unbanned after {format_timedelta(duration)}. Reason: {reason}"
            )
            seconds = duration.total_seconds()
            seconds += unixs()
            await self.bot.db.update_guild_config(
                ctx.guild.id, {"$push": {"tempbans": {"member": str(member.id), "time": seconds}}}
            )
            self.bot.loop.create_task(self.bot.unban(ctx.guild.id, member.id, seconds))


async def setup(bot: rainbot) -> None:
    await bot.add_cog(Moderation(bot))
