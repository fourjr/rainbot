"""
Reminder system for rainbot - allows users to set reminders with various time formats
"""

import discord
from discord.ext import commands, tasks
from discord.utils import escape_markdown
from datetime import datetime, timedelta, timezone
from typing import Optional
import re
import secrets

from utils.helpers import create_embed
from utils.constants import COLORS, EMOJIS


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.short_term = {}
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    def parse_timedelta(self, time_str: str) -> Optional[timedelta]:
        """Parse time string into timedelta"""
        match = re.fullmatch(r"(\d+)(s|m|h|d|w|mo|y)", time_str.strip().lower())
        if not match:
            return None

        num, unit = match.groups()
        num = int(num)

        match unit:
            case "s":
                return timedelta(seconds=num)
            case "m":
                return timedelta(minutes=num)
            case "h":
                return timedelta(hours=num)
            case "d":
                return timedelta(days=num)
            case "w":
                return timedelta(weeks=num)
            case "mo":
                return timedelta(days=30 * num)
            case "y":
                return timedelta(days=365 * num)

    @commands.command(aliases=["remind"])
    async def reminder(self, ctx, time: str, *, message: str = ""):
        f"""Set a reminder for yourself

        **Usage:** `{ctx.prefix}reminder <time> [message] [--dm]`
        **Time units:** s (seconds), m (minutes), h (hours), d (days), w (weeks), mo (months), y (years)
        **Flags:** --dm (sends reminder in DMs instead of channel)

        **Examples:**
        • `{ctx.prefix}reminder 1h Take a break`
        • `{ctx.prefix}reminder 30m Check the oven --dm`
        • `{ctx.prefix}reminder 1d Submit report`

        The bot will ping you when the time is up!
        """
        delta = self.parse_timedelta(time)
        if not delta:
            embed = create_embed(
                title=f"{EMOJIS['error']} Invalid Time Format",
                description="Use time units: `s`, `m`, `h`, `d`, `w`, `mo`, `y`\n"
                "Example: `1h30m` or `2d`",
                color=COLORS["error"],
            )
            return await ctx.send(embed=embed)

        dm = "--dm" in message
        if dm:
            message = message.replace("--dm", "").strip()

        remind_time = datetime.now(timezone.utc) + delta
        reminder_id = secrets.token_hex(3)
        jump_link = ctx.message.jump_url

        stored_data = {
            "_id": reminder_id,
            "user_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "guild_id": ctx.guild.id if ctx.guild else None,
            "message": message,
            "remind_at": remind_time,
            "dm": dm,
            "jump_url": jump_link,
            "created_at": datetime.now(timezone.utc),
        }

        # Store short-term reminders in memory, long-term in database
        if delta.total_seconds() < 60:
            self.short_term[reminder_id] = stored_data
        else:
            await self.db.db.reminders.insert_one(stored_data)

        formatted_time = f"<t:{int(remind_time.timestamp())}:R>"
        location = "via DM" if dm else "in this channel"

        embed = create_embed(
            title=f"{EMOJIS['success']} Reminder Set",
            description=f"Reminder `{reminder_id}` set {location} for {formatted_time}",
            color=COLORS["success"],
        )

        if message:
            embed.add_field(name="Message", value=message, inline=False)

        await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True, aliases=["reminders"])
    async def remindlist(self, ctx):
        f"""List your active reminders

        **Usage:** `{ctx.prefix}remindlist`
        **Aliases:** `{ctx.prefix}reminders`

        Shows all your pending reminders with their IDs and times.
        """
        # Get reminders from database
        db_reminders = (
            await self.db.db.reminders.find({"user_id": ctx.author.id})
            .sort("remind_at", 1)
            .to_list(length=100)
        )

        # Get short-term reminders from memory
        memory_reminders = [
            r for r in self.short_term.values() if r["user_id"] == ctx.author.id
        ]

        reminders = db_reminders + memory_reminders

        if not reminders:
            embed = create_embed(
                title=f"{EMOJIS['info']} No Active Reminders",
                description="You have no active reminders set.",
                color=COLORS["info"],
            )
            return await ctx.send(embed=embed)

        lines = []
        for r in reminders:
            rid = r["_id"]
            when = r["remind_at"]
            when_str = f"<t:{int(when.timestamp())}:R>"
            where = "DM" if r.get("dm") else "Channel"
            msg = f"`{rid}` - {when_str} ({where})"
            if r.get("message"):
                msg += f": {escape_markdown(r['message'])}"
            lines.append(msg)

        embed = create_embed(
            title=f"{EMOJIS['clock']} Your Reminders",
            description="\n".join(lines),
            color=COLORS["primary"],
        )
        embed.set_footer(text=f"Use {ctx.prefix}remindcancel <ID> to cancel a reminder")

        await ctx.send(embed=embed)

    @commands.command(aliases=["remindcancel", "cancelreminder"])
    async def remindercancel(self, ctx, reminder_id: str):
        f"""Cancel a reminder by its ID

        **Usage:** `{ctx.prefix}remindercancel <ID>`
        **Aliases:** `{ctx.prefix}remindcancel`, `{ctx.prefix}cancelreminder`

        **Example:** `{ctx.prefix}remindercancel abc123`

        Only your own reminders can be cancelled.
        """
        # Check short-term reminders first
        if reminder_id in self.short_term:
            if self.short_term[reminder_id]["user_id"] != ctx.author.id:
                embed = create_embed(
                    title=f"{EMOJIS['error']} Permission Denied",
                    description="You can only cancel your own reminders.",
                    color=COLORS["error"],
                )
                return await ctx.send(embed=embed)

            del self.short_term[reminder_id]
            embed = create_embed(
                title=f"{EMOJIS['success']} Reminder Cancelled",
                description=f"Reminder `{reminder_id}` has been cancelled.",
                color=COLORS["success"],
            )
            return await ctx.send(embed=embed)

        # Check database reminders
        reminder = await self.db.db.reminders.find_one({"_id": reminder_id})
        if not reminder:
            embed = create_embed(
                title=f"{EMOJIS['error']} Reminder Not Found",
                description=f"No reminder found with ID `{reminder_id}`",
                color=COLORS["error"],
            )
            return await ctx.send(embed=embed)

        if reminder["user_id"] != ctx.author.id:
            embed = create_embed(
                title=f"{EMOJIS['error']} Permission Denied",
                description="You can only cancel your own reminders.",
                color=COLORS["error"],
            )
            return await ctx.send(embed=embed)

        await self.db.db.reminders.delete_one({"_id": reminder_id})
        embed = create_embed(
            title=f"{EMOJIS['success']} Reminder Cancelled",
            description=f"Reminder `{reminder_id}` has been cancelled.",
            color=COLORS["success"],
        )
        await ctx.send(embed=embed)

    @tasks.loop(seconds=5)
    async def check_reminders(self):
        """Check for reminders that need to be sent"""
        now = datetime.now(timezone.utc)

        # Handle short-term reminders
        for rid, reminder in list(self.short_term.items()):
            if reminder["remind_at"] <= now:
                await self.send_reminder(reminder)
                del self.short_term[rid]

        # Handle database reminders
        reminders = await self.db.db.reminders.find(
            {"remind_at": {"$lte": now}}
        ).to_list(length=100)

        for reminder in reminders:
            await self.send_reminder(reminder)
            await self.db.db.reminders.delete_one({"_id": reminder["_id"]})

    async def send_reminder(self, reminder):
        """Send a reminder to the user"""
        user = self.bot.get_user(reminder["user_id"])
        if not user:
            return

        # Construct the plaintext message
        message_content = reminder.get("message") or "Your reminder is ready!"

        content = f"{EMOJIS['bell']} **Reminder!**\n> {message_content}"

        if reminder.get("jump_url"):
            content += f"\n\n*You can view the original message [here]({reminder['jump_url']})*."

        if reminder.get("dm"):
            try:
                await user.send(content)
            except discord.Forbidden:
                # If DM fails, try to send in the original channel
                if reminder.get("channel_id"):
                    channel = self.bot.get_channel(reminder["channel_id"])
                    if channel:
                        try:
                            await channel.send(f"{user.mention}\n{content}")
                        except discord.Forbidden:
                            pass
        else:
            channel = self.bot.get_channel(reminder["channel_id"])
            if channel:
                try:
                    await channel.send(f"{user.mention}\n{content}")
                except discord.Forbidden:
                    pass

    @check_reminders.before_loop
    async def before_reminder_loop(self):
        """Wait for bot to be ready before starting the reminder loop"""
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Reminders(bot))
