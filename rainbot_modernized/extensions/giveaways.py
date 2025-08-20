import discord
from discord.ext import commands, tasks
from core.database import Database
from utils.decorators import has_permissions
from utils.helpers import create_embed
import asyncio
import random
from datetime import datetime, timedelta, timezone
import re


class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        """Check for ended giveaways"""
        active_giveaways = await self.db.get_active_giveaways()

        for giveaway in active_giveaways:
            if datetime.now(timezone.utc) >= giveaway["end_time"]:
                await self._end_giveaway(giveaway)

    @check_giveaways.before_loop
    async def before_check_giveaways(self):
        await self.bot.wait_until_ready()

    def parse_duration(self, duration_str: str) -> timedelta:
        """Parse duration string like '1h', '30m', '2d'"""
        pattern = r"(\d+)([smhd])"
        matches = re.findall(pattern, duration_str.lower())

        if not matches:
            raise ValueError("Invalid duration format")

        total_seconds = 0
        for amount, unit in matches:
            amount = int(amount)
            if unit == "s":
                total_seconds += amount
            elif unit == "m":
                total_seconds += amount * 60
            elif unit == "h":
                total_seconds += amount * 3600
            elif unit == "d":
                total_seconds += amount * 86400

        return timedelta(seconds=total_seconds)

    @commands.group(invoke_without_command=True)
    async def giveaway(self, ctx):
        f"""Manage server giveaways and prize distributions
        
        **Usage:** `{ctx.prefix}giveaway <subcommand>`
        **Quick Commands:**
        • `{ctx.prefix}gstart 1h 1 Discord Nitro` (start giveaway)
        • `{ctx.prefix}gend 123456789` (end early)
        • `{ctx.prefix}greroll 123456789` (reroll winners)
        • `{ctx.prefix}giveaway list` (show active giveaways)
        
        First set up with `{ctx.prefix}setgiveaway #channel 🎉`
        """
        embed = create_embed(
            title="🎉 Giveaway System",
            description="Use the following commands:",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="Start", value="`!gstart <duration> <winners> <prize>`", inline=False
        )
        embed.add_field(name="End", value="`!gend <message_id>`", inline=False)
        embed.add_field(name="Stop", value="`!gstop <message_id>`", inline=False)
        embed.add_field(name="Reroll", value="`!greroll <message_id>`", inline=False)
        embed.add_field(name="List", value="`!giveaway list`", inline=False)
        await ctx.send(embed=embed)

    @commands.command(aliases=["gstart"])
    @has_permissions(level=2)
    async def giveaway_start(self, ctx, duration: str, winners: int, *, prize: str):
        f"""Start a new giveaway with specified duration, winner count, and prize
        
        **Usage:** `{ctx.prefix}gstart <duration> <winners> <prize>`
        **Examples:**
        • `{ctx.prefix}gstart 1h 1 Discord Nitro`
        • `{ctx.prefix}gstart 3d 2 $50 Steam Gift Cards`
        • `{ctx.prefix}gstart 1w 5 Custom Discord Bot`
        
        Duration: 30s, 5m, 2h, 1d, 1w | Winners: 1-20
        """
        guild_config = await self.db.get_guild_config(ctx.guild.id)
        giveaway_config = guild_config.get("giveaway_config", {})

        channel_id = giveaway_config.get("channel_id")
        if not channel_id:
            embed = create_embed(
                title="❌ Giveaway Channel Not Set",
                description="Please set a giveaway channel with `!setgiveaway`",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            embed = create_embed(
                title="❌ Giveaway Channel Not Found",
                description="The configured giveaway channel could not be found.",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        try:
            duration_delta = self.parse_duration(duration)
        except ValueError:
            embed = create_embed(
                title="❌ Invalid Duration",
                description="Use format like: 1h, 30m, 2d, 1h30m",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if winners < 1 or winners > 20:
            embed = create_embed(
                title="❌ Invalid Winners",
                description="Winners must be between 1 and 20",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        end_time = datetime.now(timezone.utc) + duration_delta

        emoji = giveaway_config.get("emoji", "🎉")

        embed = create_embed(
            title=f"{emoji} GIVEAWAY {emoji}",
            description=f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** <t:{int(end_time.timestamp())}:R>",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="How to Enter", value=f"React with {emoji} to enter!", inline=False
        )
        embed.set_footer(
            text=f"Hosted by {ctx.author}", icon_url=ctx.author.display_avatar.url
        )

        message = await channel.send(embed=embed)
        await message.add_reaction(emoji)

        # Store in database
        await self.db.create_giveaway(
            guild_id=ctx.guild.id,
            channel_id=channel.id,
            message_id=message.id,
            host_id=ctx.author.id,
            prize=prize,
            winners=winners,
            end_time=end_time,
        )

    @commands.command(aliases=["gend"])
    @has_permissions(level=2)
    async def giveaway_end(self, ctx, message_id: int):
        """End an active giveaway before its scheduled time"""
        giveaway = await self.db.get_giveaway(message_id)

        if not giveaway:
            embed = create_embed(
                title="❌ Giveaway Not Found",
                description="No active giveaway found with that message ID",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if giveaway["guild_id"] != ctx.guild.id:
            embed = create_embed(
                title="❌ Wrong Server",
                description="That giveaway is not in this server",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        await self._end_giveaway(giveaway)

        embed = create_embed(
            title="✅ Giveaway Ended",
            description="The giveaway has been ended early",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["greroll"])
    @has_permissions(level=2)
    async def giveaway_reroll(self, ctx, message_id: int):
        """Select new random winners for a completed giveaway"""
        giveaway = await self.db.get_giveaway(message_id)

        if not giveaway:
            embed = create_embed(
                title="❌ Giveaway Not Found",
                description="No giveaway found with that message ID",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if giveaway["active"]:
            embed = create_embed(
                title="❌ Giveaway Active",
                description="Cannot reroll an active giveaway",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        # Get the original message
        try:
            channel = self.bot.get_channel(giveaway["channel_id"])
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            embed = create_embed(
                title="❌ Message Not Found",
                description="The giveaway message was deleted",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        # Get participants
        guild_config = await self.db.get_guild_config(giveaway["guild_id"])
        emoji = guild_config.get("giveaway_config", {}).get("emoji", "🎉")
        reaction = discord.utils.get(message.reactions, emoji=emoji)
        if not reaction:
            embed = create_embed(
                title="❌ No Participants",
                description="No one participated in this giveaway",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        participants = []
        async for user in reaction.users():
            if not user.bot:
                participants.append(user)

        if len(participants) == 0:
            embed = create_embed(
                title="❌ No Valid Participants",
                description="No valid participants found",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        # Select winners
        winner_count = min(giveaway["winners"], len(participants))
        winners = random.sample(participants, winner_count)

        # Announce reroll
        winner_mentions = ", ".join(winner.mention for winner in winners)
        embed = create_embed(
            title="🎉 Giveaway Rerolled!",
            description=f"**New Winner(s):** {winner_mentions}\n**Prize:** {giveaway['prize']}",
            color=discord.Color.gold(),
        )

        await ctx.send(embed=embed)

    async def _end_giveaway(self, giveaway):
        """End a giveaway and pick winners"""
        try:
            channel = self.bot.get_channel(giveaway["channel_id"])
            message = await channel.fetch_message(giveaway["message_id"])
        except discord.NotFound:
            await self.db.end_giveaway(giveaway["message_id"])
            return

        # Get participants
        guild_config = await self.db.get_guild_config(giveaway["guild_id"])
        emoji = guild_config.get("giveaway_config", {}).get("emoji", "🎉")
        reaction = discord.utils.get(message.reactions, emoji=emoji)
        participants = []

        if reaction:
            async for user in reaction.users():
                if not user.bot:
                    participants.append(user)

        # Update original message
        embed = create_embed(
            title="🎉 GIVEAWAY ENDED 🎉",
            description=f"**Prize:** {giveaway['prize']}\n**Winners:** {giveaway['winners']}",
            color=discord.Color.red(),
        )

        if len(participants) == 0:
            embed.add_field(name="Result", value="No valid participants", inline=False)
        else:
            # Select winners
            winner_count = min(giveaway["winners"], len(participants))
            winners = random.sample(participants, winner_count)

            winner_mentions = ", ".join(winner.mention for winner in winners)
            embed.add_field(name="Winner(s)", value=winner_mentions, inline=False)

            # Announce winners
            winner_embed = create_embed(
                title="🎉 Congratulations!",
                description=f"**Winner(s):** {winner_mentions}\n**Prize:** {giveaway['prize']}",
                color=discord.Color.gold(),
            )

            await channel.send(embed=winner_embed)

        embed.set_footer(text="Giveaway ended")
        await message.edit(embed=embed)

        # Mark as ended in database
        await self.db.end_giveaway(giveaway["message_id"])

    @commands.command(aliases=["setg"])
    @has_permissions(level=2)
    async def setgiveaway(
        self, ctx, channel: discord.TextChannel, emoji: str, role: discord.Role = None
    ):
        f"""Set the default channel, emoji, and optional role requirement for giveaways
        
        **Usage:** `{ctx.prefix}setgiveaway <channel> <emoji> [role]`
        **Examples:**
        • `{ctx.prefix}setgiveaway #giveaways 🎉`
        • `{ctx.prefix}setgiveaway #events 🎁 @Member`
        • `{ctx.prefix}setg #contests ✨`
        
        Required before starting giveaways. Role requirement is optional.
        """
        await self.db.update_guild_config(
            ctx.guild.id,
            {
                "giveaway_config.channel_id": channel.id,
                "giveaway_config.emoji": str(emoji),
                "giveaway_config.required_role": role.id if role else None,
            },
        )

        embed = create_embed(
            title="✅ Giveaway Settings Updated",
            description=f"**Channel:** {channel.mention}\n**Emoji:** {emoji}\n**Required Role:** {role.mention if role else 'None'}",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["gstats"])
    @has_permissions(level=1)
    async def giveaway_stats(self, ctx, message_id: int):
        """Display participant count and other statistics for a giveaway"""
        giveaway = await self.db.get_giveaway(message_id)

        if not giveaway or giveaway["guild_id"] != ctx.guild.id:
            embed = create_embed(
                title="❌ Giveaway Not Found",
                description="No giveaway found with that message ID in this server",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        try:
            channel = self.bot.get_channel(giveaway["channel_id"])
            message = await channel.fetch_message(giveaway["message_id"])
        except discord.NotFound:
            embed = create_embed(
                title="❌ Message Not Found",
                description="The giveaway message was deleted",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        guild_config = await self.db.get_guild_config(ctx.guild.id)
        emoji = guild_config.get("giveaway_config", {}).get("emoji", "🎉")

        reaction = discord.utils.get(message.reactions, emoji=emoji)
        participants = []
        if reaction:
            async for user in reaction.users():
                if not user.bot:
                    participants.append(user)

        embed = create_embed(
            title=f"📊 Giveaway Stats for '{giveaway['prize']}'",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Participants", value=str(len(participants)), inline=False)
        embed.add_field(
            name="Ends",
            value=f"<t:{int(giveaway['end_time'].timestamp())}:R>",
            inline=False,
        )
        embed.add_field(
            name="Active", value="Yes" if giveaway["active"] else "No", inline=False
        )

        await ctx.send(embed=embed)

    @commands.command(aliases=["geditdesc"])
    @has_permissions(level=2)
    async def giveaway_edit_description(
        self, ctx, message_id: int, *, new_description: str
    ):
        """Change the prize description of an active giveaway"""
        giveaway = await self.db.get_giveaway(message_id)

        if (
            not giveaway
            or not giveaway["active"]
            or giveaway["guild_id"] != ctx.guild.id
        ):
            embed = create_embed(
                title="❌ Giveaway Not Found",
                description="No active giveaway found with that message ID in this server",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        await self.db.update_giveaway(message_id, {"prize": new_description})

        try:
            channel = self.bot.get_channel(giveaway["channel_id"])
            message = await channel.fetch_message(giveaway["message_id"])
            original_embed = message.embeds[0]
            original_embed.description = f"**Prize:** {new_description}\n**Winners:** {giveaway['winners']}\n**Ends:** <t:{int(giveaway['end_time'].timestamp())}:R>"
            await message.edit(embed=original_embed)
        except discord.NotFound:
            pass

        embed = create_embed(
            title="✅ Description Updated",
            description=f"The description for the giveaway has been updated.",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["geditwinners"])
    @has_permissions(level=2)
    async def giveaway_edit_winners(self, ctx, message_id: int, new_winners: int):
        """Change how many winners will be selected for an active giveaway"""
        giveaway = await self.db.get_giveaway(message_id)

        if (
            not giveaway
            or not giveaway["active"]
            or giveaway["guild_id"] != ctx.guild.id
        ):
            embed = create_embed(
                title="❌ Giveaway Not Found",
                description="No active giveaway found with that message ID in this server",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        if new_winners < 1 or new_winners > 20:
            embed = create_embed(
                title="❌ Invalid Winners",
                description="Winners must be between 1 and 20",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        await self.db.update_giveaway(message_id, {"winners": new_winners})

        try:
            channel = self.bot.get_channel(giveaway["channel_id"])
            message = await channel.fetch_message(giveaway["message_id"])
            original_embed = message.embeds[0]
            original_embed.description = f"**Prize:** {giveaway['prize']}\n**Winners:** {new_winners}\n**Ends:** <t:{int(giveaway['end_time'].timestamp())}:R>"
            await message.edit(embed=original_embed)
        except discord.NotFound:
            pass

        embed = create_embed(
            title="✅ Winners Updated",
            description=f"The number of winners for the giveaway has been updated.",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["gstop"])
    @has_permissions(level=2)
    async def giveaway_stop(self, ctx, message_id: int):
        """Stop an active giveaway and immediately draw winners"""
        giveaway = await self.db.get_giveaway(message_id)

        if (
            not giveaway
            or not giveaway["active"]
            or giveaway["guild_id"] != ctx.guild.id
        ):
            embed = create_embed(
                title="❌ Giveaway Not Found",
                description="No active giveaway found with that message ID in this server",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        await self._end_giveaway(giveaway)

        embed = create_embed(
            title="✅ Giveaway Stopped",
            description="The giveaway has been stopped and the winners have been drawn.",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @giveaway.command(name="list")
    @has_permissions(level=1)
    async def giveaway_list(self, ctx):
        """Show all currently running giveaways in the server"""
        giveaways = await self.db.get_guild_giveaways(ctx.guild.id)

        if not giveaways:
            embed = create_embed(
                title="🎉 Active Giveaways",
                description="No active giveaways in this server",
                color=discord.Color.blue(),
            )
        else:
            embed = create_embed(
                title="🎉 Active Giveaways", color=discord.Color.gold()
            )

            for giveaway in giveaways[:10]:  # Limit to 10
                channel = self.bot.get_channel(giveaway["channel_id"])
                channel_name = channel.name if channel else "Unknown"

                embed.add_field(
                    name=giveaway["prize"][:50],
                    value=f"Channel: #{channel_name}\nEnds: <t:{int(giveaway['end_time'].timestamp())}:R>",
                    inline=True,
                )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Giveaways(bot))
