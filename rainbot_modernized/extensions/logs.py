import discord
from discord.ext import commands
from core.database import Database
from utils.helpers import create_embed, status_embed, update_nested_config
from datetime import datetime


class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    async def log_event(self, guild_id, log_type, embed, channel_id_to_check=None):
        """Send log to appropriate channel"""
        config = await self.db.get_guild_config(guild_id)
        log_channels = config.get("log_channels", {})

        if channel_id_to_check:
            ignored_channels = config.get("ignored_channels", {}).get(log_type, [])
            if channel_id_to_check in ignored_channels:
                return

        channel_id = log_channels.get(log_type)
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        embed = create_embed(
            title="📥 Member Joined",
            description=f"{member.mention} ({member})",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Account Created",
            value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            inline=True,
        )
        embed.add_field(
            name="Member Count", value=str(member.guild.member_count), inline=True
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.timestamp = datetime.utcnow()

        await self.log_event(member.guild.id, "member", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        embed = create_embed(
            title="📤 Member Left",
            description=f"{member.mention} ({member})",
            color=discord.Color.red(),
        )
        embed.add_field(
            name="Joined At",
            value=(
                member.joined_at.strftime("%Y-%m-%d %H:%M:%S")
                if member.joined_at
                else "Unknown"
            ),
            inline=True,
        )
        embed.add_field(
            name="Member Count", value=str(member.guild.member_count), inline=True
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.timestamp = datetime.utcnow()

        await self.log_event(member.guild.id, "member", embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild:
            return

        embed = create_embed(
            title="🗑️ Message Deleted",
            description=f"Message by {message.author.mention} deleted in {message.channel.mention}",
            color=discord.Color.red(),
        )

        if message.content:
            embed.add_field(name="Content", value=message.content[:1024], inline=False)

        embed.add_field(
            name="Author", value=f"{message.author} ({message.author.id})", inline=True
        )
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.timestamp = datetime.utcnow()

        await self.log_event(
            message.guild.id, "message_delete", embed, message.channel.id
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or not before.guild or before.content == after.content:
            return

        embed = create_embed(
            title="✏️ Message Edited",
            description=f"Message by {before.author.mention} edited in {before.channel.mention}",
            color=discord.Color.orange(),
        )

        if before.content:
            embed.add_field(name="Before", value=before.content[:512], inline=False)
        if after.content:
            embed.add_field(name="After", value=after.content[:512], inline=False)

        embed.add_field(
            name="Author", value=f"{before.author} ({before.author.id})", inline=True
        )
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        # Add message link field
        message_link = f"https://discord.com/channels/{before.guild.id}/{before.channel.id}/{before.id}"
        embed.add_field(
            name="Jump to Message", value=f"[Click Here]({message_link})", inline=False
        )
        embed.timestamp = datetime.utcnow()

        await self.log_event(before.guild.id, "message_edit", embed, before.channel.id)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # Role changes
        if before.roles != after.roles:
            added_roles = set(after.roles) - set(before.roles)
            removed_roles = set(before.roles) - set(after.roles)

            if added_roles or removed_roles:
                embed = create_embed(
                    title="🎭 Role Update",
                    description=f"Roles updated for {after.mention}",
                    color=discord.Color.blue(),
                )

                if added_roles:
                    embed.add_field(
                        name="Added Roles",
                        value=", ".join(role.mention for role in added_roles),
                        inline=False,
                    )
                if removed_roles:
                    embed.add_field(
                        name="Removed Roles",
                        value=", ".join(role.mention for role in removed_roles),
                        inline=False,
                    )

                embed.timestamp = datetime.utcnow()
                await self.log_event(after.guild.id, "member", embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel == after.channel:
            return

        embed = create_embed(
            title="🔊 Voice Update",
            description=f"Voice activity for {member.mention}",
            color=discord.Color.purple(),
        )

        if before.channel and after.channel:
            embed.add_field(name="Action", value="Moved", inline=True)
            embed.add_field(name="From", value=before.channel.name, inline=True)
            embed.add_field(name="To", value=after.channel.name, inline=True)
        elif after.channel:
            embed.add_field(name="Action", value="Joined", inline=True)
            embed.add_field(name="Channel", value=after.channel.name, inline=True)
        elif before.channel:
            embed.add_field(name="Action", value="Left", inline=True)
            embed.add_field(name="Channel", value=before.channel.name, inline=True)

        embed.timestamp = datetime.utcnow()
        await self.log_event(member.guild.id, "voice", embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        embed = create_embed(
            title="📝 Channel Created",
            description=f"Channel {channel.mention} was created",
            color=discord.Color.green(),
        )
        embed.add_field(name="Type", value=str(channel.type).title(), inline=True)
        embed.add_field(
            name="Category",
            value=channel.category.name if channel.category else "None",
            inline=True,
        )
        embed.timestamp = datetime.utcnow()

        await self.log_event(channel.guild.id, "server", embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        embed = create_embed(
            title="🗑️ Channel Deleted",
            description=f"Channel **{channel.name}** was deleted",
            color=discord.Color.red(),
        )
        embed.add_field(name="Type", value=str(channel.type).title(), inline=True)
        embed.add_field(
            name="Category",
            value=channel.category.name if channel.category else "None",
            inline=True,
        )
        embed.timestamp = datetime.utcnow()

        await self.log_event(channel.guild.id, "server", embed)

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def logging(self, ctx):
        """Configure logging channels"""
        config = await self.db.get_guild_config(ctx.guild.id)
        log_channels = config.get("log_channels", {})

        embed = create_embed(
            title="📝 Logging Configuration", color=discord.Color.blue()
        )

        # Moderation
        mod_channel = (
            ctx.guild.get_channel(log_channels.get("moderation"))
            if log_channels.get("moderation")
            else None
        )
        embed.add_field(
            name="Moderation Actions",
            value=mod_channel.mention if mod_channel else "Not set",
            inline=True,
        )

        # Member events (join/leave/role updates)
        member_channel = (
            ctx.guild.get_channel(log_channels.get("member"))
            if log_channels.get("member")
            else None
        )
        embed.add_field(
            name="Member Events",
            value=member_channel.mention if member_channel else "Not set",
            inline=True,
        )

        # Message events (edits/deletes) — may be same or different channels
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
        embed.add_field(name="Message Events", value=msg_value, inline=True)

        # Voice events
        voice_channel = (
            ctx.guild.get_channel(log_channels.get("voice"))
            if log_channels.get("voice")
            else None
        )
        embed.add_field(
            name="Voice Events",
            value=voice_channel.mention if voice_channel else "Not set",
            inline=True,
        )

        # Server updates
        server_channel = (
            ctx.guild.get_channel(log_channels.get("server"))
            if log_channels.get("server")
            else None
        )
        embed.add_field(
            name="Server Events",
            value=server_channel.mention if server_channel else "Not set",
            inline=True,
        )

        await ctx.send(embed=embed)

    @logging.command(name="setmodlog")
    @commands.has_permissions(manage_guild=True)
    async def set_mod_log(self, ctx, channel: discord.TextChannel):
        """Sets the log channel for moderation actions"""
        await update_nested_config(
            self.db, ctx.guild.id, "log_channels", "moderation", channel.id
        )
        embed = status_embed(
            title="✅ Moderation Log Set",
            description=f"Moderation logs will be sent to {channel.mention}",
            status="success",
        )
        await ctx.send(embed=embed)

    @logging.command(name="ignore", aliases=["setlogignore"])
    @commands.has_permissions(manage_guild=True)
    async def ignore_log(self, ctx, log_type: str, channel: discord.TextChannel):
        """Ignore a channel for a specific log type"""
        valid_types = ["message_edit", "message_delete"]

        if log_type not in valid_types:
            embed = status_embed(
                title="❌ Invalid Log Type",
                description=f"Valid types for ignoring: {', '.join(valid_types)}",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        config = await self.db.get_guild_config(ctx.guild.id)
        ignored_channels = config.get("ignored_channels", {})

        if log_type not in ignored_channels:
            ignored_channels[log_type] = []

        if channel.id in ignored_channels[log_type]:
            embed = status_embed(
                title="⚠️ Already Ignored",
                description=f"{channel.mention} is already ignored for {log_type} logs.",
                status="info",
            )
            await ctx.send(embed=embed)
            return

        ignored_channels[log_type].append(channel.id)
        await self.db.update_guild_config(
            ctx.guild.id, {"ignored_channels": ignored_channels}
        )

        embed = status_embed(
            title="✅ Channel Ignored",
            description=f"{channel.mention} will now be ignored for {log_type} logs.",
            status="success",
        )
        await ctx.send(embed=embed)

    @logging.command(name="set", aliases=["setlog"])
    @commands.has_permissions(manage_guild=True)
    async def set_log(self, ctx, log_type: str, channel: discord.TextChannel):
        """Set a logging channel"""
        valid_types = [
            "member",
            "message_edit",
            "message_delete",
            "voice",
            "server",
            "moderation",
        ]

        if log_type not in valid_types:
            embed = status_embed(
                title="❌ Invalid Log Type",
                description=f"Valid types: {', '.join(valid_types)}",
                status="error",
            )
            await ctx.send(embed=embed)
            return

        await update_nested_config(
            self.db, ctx.guild.id, "log_channels", log_type, channel.id
        )

        title_map = {
            "member": "Member Events",
            "message_edit": "Message Edit Events",
            "message_delete": "Message Delete Events",
            "voice": "Voice Events",
            "server": "Server Events",
            "moderation": "Moderation Actions",
        }

        embed = status_embed(
            title="✅ Logging Updated",
            description=f"{title_map.get(log_type, log_type.title())} will be sent to {channel.mention}",
            status="success",
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Logs(bot))
