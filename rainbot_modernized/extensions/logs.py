import discord
from discord.ext import commands
from core.database import Database
from utils.helpers import create_embed
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

        log_types = {
            "member": "Member Events",
            "message": "Message Events",
            "voice": "Voice Events",
            "server": "Server Events",
            "moderation": "Moderation Actions",
        }

        for log_type, name in log_types.items():
            channel_id = log_channels.get(log_type)
            channel = ctx.guild.get_channel(channel_id) if channel_id else None
            value = channel.mention if channel else "Not set"
            embed.add_field(name=name, value=value, inline=True)

        await ctx.send(embed=embed)

    @logging.command()
    @commands.has_permissions(manage_guild=True)
    async def ignore(self, ctx, log_type: str, channel: discord.TextChannel):
        """Ignore a channel for a specific log type"""
        valid_types = ["message_edit", "message_delete"]

        if log_type not in valid_types:
            embed = create_embed(
                title="❌ Invalid Log Type",
                description=f"Valid types for ignoring: {', '.join(valid_types)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        config = await self.db.get_guild_config(ctx.guild.id)
        ignored_channels = config.get("ignored_channels", {})

        if log_type not in ignored_channels:
            ignored_channels[log_type] = []

        if channel.id in ignored_channels[log_type]:
            embed = create_embed(
                title="⚠️ Already Ignored",
                description=f"{channel.mention} is already ignored for {log_type} logs.",
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)
            return

        ignored_channels[log_type].append(channel.id)
        await self.db.update_guild_config(
            ctx.guild.id, {"ignored_channels": ignored_channels}
        )

        embed = create_embed(
            title="✅ Channel Ignored",
            description=f"{channel.mention} will now be ignored for {log_type} logs.",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @logging.command()
    @commands.has_permissions(manage_guild=True)
    async def set(self, ctx, log_type: str, channel: discord.TextChannel):
        """Set a logging channel"""
        valid_types = [
            "member_join",
            "member_leave",
            "message_edit",
            "message_delete",
            "voice_activity",
            "server_updates",
            "moderation",
        ]

        if log_type not in valid_types:
            embed = create_embed(
                title="❌ Invalid Log Type",
                description=f"Valid types: {', '.join(valid_types)}",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        config = await self.db.get_guild_config(ctx.guild.id)
        log_channels = config.get("log_channels", {})
        log_channels[log_type] = channel.id

        await self.db.update_guild_config(ctx.guild.id, {"log_channels": log_channels})

        embed = create_embed(
            title="✅ Logging Updated",
            description=f"{log_type.title()} logs will be sent to {channel.mention}",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Logs(bot))
