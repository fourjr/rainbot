import discord
from discord.ext import commands
import json
import string
from collections import defaultdict
from typing import Union
from core.database import Database
from utils.decorators import has_permissions
from utils.helpers import (
    create_embed,
    status_embed,
    update_nested_config,
    remove_nested_config,
)


class SafeFormat(dict):
    def __missing__(self, key):
        return f"{{{key}}}"


class SafeString(str):
    def __format__(self, format_spec):
        return str(self)


class EventsAnnouncer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.invite_cache = defaultdict(set)
        bot.loop.create_task(self.populate_invite_cache())

    async def populate_invite_cache(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            try:
                self.invite_cache[guild.id] = {i for i in await guild.invites()}
            except discord.Forbidden:
                pass

    async def get_used_invite(self, guild):
        try:
            current_invites = {i for i in await guild.invites()}
        except discord.Forbidden:
            return SafeString("{unable to get invite}")

        for old_invite in self.invite_cache[guild.id]:
            for new_invite in current_invites:
                if old_invite.id == new_invite.id and new_invite.uses > old_invite.uses:
                    self.invite_cache[guild.id] = current_invites
                    return new_invite

        self.invite_cache[guild.id] = current_invites
        return SafeString("{unable to get invite}")

    def apply_vars(self, member, message, invite=None):
        return string.Formatter().vformat(
            message,
            [],
            SafeFormat(
                member=member,
                guild=member.guild,
                bot=self.bot.user,
                invite=invite or SafeString("{invite}"),
            ),
        )

    def format_message(self, member, message, invite=None):
        try:
            message_dict = json.loads(message)
            # Handle embed
            if "embed" in message_dict:
                embed_data = message_dict["embed"]
                for key, value in embed_data.items():
                    if isinstance(value, str):
                        embed_data[key] = self.apply_vars(member, value, invite)
                message_dict["embed"] = discord.Embed.from_dict(embed_data)

            if "content" in message_dict:
                message_dict["content"] = self.apply_vars(
                    member, message_dict["content"], invite
                )

            return message_dict
        except json.JSONDecodeError:
            # Plain text message
            content = self.apply_vars(member, message, invite)
            return {"content": content}

    @commands.command(name="seteventannouncement")
    @has_permissions(level=5)
    async def set_event_announcement(
        self,
        ctx,
        event_type: str,
        channel: Union[discord.TextChannel, str] = None,
        *,
        message: str = None,
    ):
        """Configure member join/leave announcements"""
        valid_events = ["member_join", "member_remove"]

        if event_type not in valid_events:
            embed = status_embed(
                title="❌ Invalid Event",
                description=f"Valid events: {', '.join(valid_events)}",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        if channel and channel != "dm" and not isinstance(channel, discord.TextChannel):
            embed = status_embed(
                title="❌ Invalid Channel",
                description="Channel must be a text channel mention or 'dm'",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        # Clear announcement when message is None
        if message is None:
            await remove_nested_config(
                self.db, ctx.guild.id, "events_announce", event_type
            )
            embed = status_embed(
                title="✅ Announcement Cleared",
                description=f"Announcement for `{event_type}` has been cleared",
                status="success",
            )
            await ctx.send(embed=embed)
            return

        # Test the message format
        try:
            formatted = self.format_message(ctx.author, message)
            if channel == "dm":
                await ctx.author.send(**formatted)
                channel_id = "dm"
            else:
                await channel.send(**formatted)
                channel_id = str(channel.id)

            value = {"channel_id": channel_id, "message": message}
            await update_nested_config(
                self.db, ctx.guild.id, "events_announce", event_type, value
            )

            embed = status_embed(
                title="✅ Announcement Set",
                description=f"Announcement for `{event_type}` has been set and test message sent",
                status="success",
            )
            await ctx.send(embed=embed)

        except Exception as e:
            embed = status_embed(
                title="❌ Invalid Message Format",
                description=f"Error: {str(e)}",
                status="error",
            )
            await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        config = await self.db.get_guild_config(member.guild.id)
        events_config = config.get("events_announce", {})
        join_config = events_config.get("member_join")

        if not join_config:
            return

        invite = await self.get_used_invite(member.guild)

        if join_config["channel_id"] == "dm":
            channel = member
        else:
            channel = member.guild.get_channel(int(join_config["channel_id"]))

        if channel:
            try:
                message = self.format_message(member, join_config["message"], invite)
                await channel.send(**message)
            except:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        config = await self.db.get_guild_config(member.guild.id)
        events_config = config.get("events_announce", {})
        leave_config = events_config.get("member_remove")

        if not leave_config:
            return

        if leave_config["channel_id"] == "dm":
            return  # Can't DM someone who left

        channel = member.guild.get_channel(int(leave_config["channel_id"]))

        if channel:
            try:
                message = self.format_message(member, leave_config["message"])
                await channel.send(**message)
            except:
                pass


async def setup(bot):
    await bot.add_cog(EventsAnnouncer(bot))
