import discord
from discord.ext import commands
from core.database import Database
from utils.helpers import create_embed
from utils.paginator import Paginator
from core.permissions import PermissionLevel
import psutil
import time
from datetime import datetime
import platform


class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.start_time = time.time()

    def _format_uptime(self, uptime_seconds: int) -> str:
        """Formats uptime in seconds into a human-readable string."""
        uptime_seconds = int(uptime_seconds)
        if uptime_seconds < 1:
            return "0 seconds"

        days = uptime_seconds // 86400
        hours = (uptime_seconds // 3600) % 24
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60

        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds > 0 or not parts:
            parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

        return ", ".join(parts)

    @commands.command(aliases=["botinfo"])
    async def about(self, ctx):
        """Shows information about the bot.

        **Usage:** `{prefix}about`
        **Alias:** `{prefix}botinfo`
        """
        uptime_seconds = time.time() - self.start_time
        uptime_str = self._format_uptime(uptime_seconds)

        embed = create_embed(
            title="🤖 About Rainbot",
            description="A powerful Discord moderation bot",
            color=discord.Color.blue(),
        )

        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Users", value=str(len(self.bot.users)), inline=True)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)

        embed.add_field(name="Python", value=platform.python_version(), inline=True)
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="Platform", value=platform.system(), inline=True)

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Made with ❤️ by the Rainbot team")

        await ctx.send(embed=embed)

    @commands.command(aliases=["serverinfo", "si"])
    async def server(self, ctx):
        """Displays detailed information about the server.

        **Usage:** `{prefix}server`
        **Aliases:** `{prefix}serverinfo`, `{prefix}si`
        """
        guild = ctx.guild

        # Ensure member cache is loaded for accurate counts
        if not guild.chunked:
            await guild.chunk(cache=True)

        # We use ctx.guild for member/channel lists, but fetch_guild for banner/description
        try:
            fetched_guild = await self.bot.fetch_guild(guild.id)
        except discord.Forbidden:
            fetched_guild = guild  # Fallback to context guild

        embed = create_embed(
            title=f"📊 Server Info: {guild.name}",
            color=discord.Color.blue(),
            timestamp=True,
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        if fetched_guild.banner:
            embed.set_image(url=fetched_guild.banner.with_format("png").url)

        # General Info
        general_info = (
            f"**Owner:** {guild.owner.mention if guild.owner else 'Unknown'}\n"
            f"**Created:** {discord.utils.format_dt(guild.created_at, style='R')}\n"
            f"**Verification:** {str(guild.verification_level).title()}"
        )
        embed.add_field(name="❯ General", value=general_info, inline=False)

        # Member Stats
        member_count = guild.member_count or len(guild.members)
        bot_count = sum(1 for member in guild.members if member.bot)
        human_count = member_count - bot_count

        member_stats = (
            f"**Total:** {member_count}\n"
            f"**Humans:** {human_count} | **Bots:** {bot_count}"
        )
        embed.add_field(name="❯ Members", value=member_stats, inline=True)

        # Channel Stats
        channel_stats = (
            f"**Total:** {len(guild.channels)}\n"
            f"**Text:** {len(guild.text_channels)}\n"
            f"**Voice:** {len(guild.voice_channels)}"
        )
        embed.add_field(name="❯ Channels", value=channel_stats, inline=True)

        # Boost Status
        boost_status = (
            f"**Level:** {guild.premium_tier}\n"
            f"**Boosts:** {guild.premium_subscription_count}"
        )
        embed.add_field(name="❯ Boosts", value=boost_status, inline=True)

        # Features & Emojis
        emojis = [str(e) for e in guild.emojis if e.available][:20]
        emoji_display = " ".join(emojis) if emojis else "None"

        embed.add_field(
            name=f"❯ Emojis [{len(guild.emojis)}]", value=emoji_display, inline=False
        )

        embed.set_footer(text=f"ID: {guild.id}")

        await ctx.send(embed=embed)

    @commands.command(aliases=["userinfo", "ui"])
    async def user(self, ctx, *, member: discord.Member = None):
        """Displays detailed information about a user.

        **Usage:** `{prefix}user [user]`
        **Aliases:** `{prefix}userinfo`, `{prefix}ui`
        **Examples:**
        - `{prefix}user` (shows your info)
        - `{prefix}user @user` (shows another user's info)
        """
        member = member or ctx.author

        # Fetch user object to get banner and global profile info
        try:
            user = await self.bot.fetch_user(member.id)
        except discord.NotFound:
            await ctx.send("Could not find that user.")
            return

        embed = create_embed(
            title=f"👤 {member.display_name}",
            color=(
                member.color
                if member.color != discord.Color.default()
                else discord.Color.blue()
            ),
            timestamp=True,
        )

        embed.set_thumbnail(url=member.display_avatar.url)
        if user.banner:
            embed.set_image(url=user.banner.with_format("png").url)

        # User Info
        user_info = (
            f"**Username:** `{user}`\n"
            f"**ID:** `{user.id}`\n"
            f"**Account Created:** {discord.utils.format_dt(user.created_at, style='R')}"
        )
        embed.add_field(name="❯ User Information", value=user_info, inline=False)

        # Member Info
        sorted_members = sorted(ctx.guild.members, key=lambda m: m.joined_at)
        join_pos = sorted_members.index(member) + 1

        member_info = (
            f"**Joined Server:** {discord.utils.format_dt(member.joined_at, style='R')}\n"
            f"**Join Position:** #{join_pos}\n"
            f"**Boosting Since:** {discord.utils.format_dt(member.premium_since, style='R') if member.premium_since else 'Not boosting'}"
        )
        embed.add_field(name="❯ Member Information", value=member_info, inline=False)

        # Roles
        if member.roles[1:]:  # Exclude @everyone
            # Reversed to show highest roles first
            roles = ", ".join(role.mention for role in reversed(member.roles[1:][:15]))
            if len(member.roles) > 16:
                roles += f" (+{len(member.roles) - 16} more)"
            embed.add_field(
                name=f"❯ Roles [{len(member.roles)-1}]", value=roles, inline=False
            )

        embed.set_footer(text=f"Requested by {ctx.author}")

        await ctx.send(embed=embed)

    @commands.command()
    async def stats(self, ctx):
        """Shows the bot's performance and usage statistics.

        **Usage:** `{prefix}stats`
        """
        process = psutil.Process()
        memory_usage = process.memory_info().rss / 1024 / 1024  # MB
        cpu_usage = process.cpu_percent()

        uptime_seconds = time.time() - self.start_time
        uptime_str = self._format_uptime(uptime_seconds)

        embed = create_embed(title="📊 Bot Statistics", color=discord.Color.blue())

        # Bot stats
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Users", value=str(len(self.bot.users)), inline=True)
        embed.add_field(name="Commands", value=str(len(self.bot.commands)), inline=True)

        # System stats
        embed.add_field(
            name="Memory Usage", value=f"{memory_usage:.1f} MB", inline=True
        )
        embed.add_field(name="CPU Usage", value=f"{cpu_usage:.1f}%", inline=True)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)

        # Discord stats
        embed.add_field(
            name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True
        )
        embed.add_field(
            name="Shards", value=str(self.bot.shard_count or 1), inline=True
        )
        embed.add_field(name="Version", value=discord.__version__, inline=True)

        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def eval(self, ctx, *, code: str):
        """Executes Python code (bot owner only).

        **Usage:** `{prefix}eval <code>`
        """
        import textwrap
        import io
        import contextlib

        code = code.strip("` ")
        if code.startswith("py"):
            code = code[2:]

        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(code, "  ")}'

        try:
            exec(to_compile, globals())
        except Exception as e:
            embed = create_embed(
                title="❌ Compilation Error",
                description=f"```py\n{e.__class__.__name__}: {e}\n```",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed)
            return

        func = globals()["func"]
        try:
            with contextlib.redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            embed = create_embed(
                title="❌ Runtime Error",
                description=f"```py\n{value}{e.__class__.__name__}: {e}\n```",
                color=discord.Color.red(),
            )
        else:
            value = stdout.getvalue()
            if ret is None:
                if value:
                    embed = create_embed(
                        title="✅ Evaluation Result",
                        description=f"```py\n{value}\n```",
                        color=discord.Color.green(),
                    )
                else:
                    embed = create_embed(
                        title="✅ Evaluation Complete",
                        description="No output",
                        color=discord.Color.green(),
                    )
            else:
                embed = create_embed(
                    title="✅ Evaluation Result",
                    description=f"```py\n{value}{ret}\n```",
                    color=discord.Color.green(),
                )

        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx, *, extension: str):
        """Reloads a bot extension (bot owner only).

        **Usage:** `{prefix}reload <extension>`
        **Example:** `{prefix}reload moderation`
        """
        try:
            await self.bot.reload_extension(f"extensions.{extension}")
            embed = create_embed(
                title="✅ Extension Reloaded",
                description=f"Successfully reloaded `{extension}`",
                color=discord.Color.green(),
            )
        except Exception as e:
            embed = create_embed(
                title="❌ Reload Failed",
                description=f"```py\n{e}\n```",
                color=discord.Color.red(),
            )

        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def load(self, ctx, *, extension: str):
        """Loads a bot extension (bot owner only).

        **Usage:** `{prefix}load <extension>`
        **Example:** `{prefix}load moderation`
        """
        try:
            await self.bot.load_extension(f"extensions.{extension}")
            embed = create_embed(
                title="✅ Extension Loaded",
                description=f"Successfully loaded `{extension}`",
                color=discord.Color.green(),
            )
        except Exception as e:
            embed = create_embed(
                title="❌ Load Failed",
                description=f"```py\n{e}\n```",
                color=discord.Color.red(),
            )

        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def unload(self, ctx, *, extension: str):
        """Unloads a bot extension (bot owner only).

        **Usage:** `{prefix}unload <extension>`
        **Example:** `{prefix}unload moderation`
        """
        try:
            await self.bot.unload_extension(f"extensions.{extension}")
            embed = create_embed(
                title="✅ Extension Unloaded",
                description=f"Successfully unloaded `{extension}`",
                color=discord.Color.green(),
            )
        except Exception as e:
            embed = create_embed(
                title="❌ Unload Failed",
                description=f"```py\n{e}\n```",
                color=discord.Color.red(),
            )

        await ctx.send(embed=embed)

    @commands.command(aliases=["health"])
    @commands.is_owner()
    async def serverhealth(self, ctx):
        """Displays the server's resource usage and health (bot owner only).

        **Usage:** `{prefix}serverhealth`
        **Alias:** `{prefix}health`
        """
        async with ctx.typing():
            # System-wide stats
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_cores = psutil.cpu_count(logical=False)
            cpu_logical_cores = psutil.cpu_count(logical=True)

            mem = psutil.virtual_memory()
            mem_total = mem.total / (1024**3)
            mem_used = mem.used / (1024**3)
            mem_percent = mem.percent

            swap = psutil.swap_memory()
            swap_total = swap.total / (1024**3)
            swap_used = swap.used / (1024**3)
            swap_percent = swap.percent

            # Disk partitions
            disk_info = ""
            partitions = psutil.disk_partitions()
            for partition in partitions:
                if "rw" in partition.opts and partition.fstype:
                    try:
                        usage = psutil.disk_usage(partition.mountpoint)
                        disk_info += f"**{partition.device}**: {usage.used / (1024**3):.2f}/{usage.total / (1024**3):.2f} GB ({usage.percent}%)\n"
                    except (PermissionError, FileNotFoundError):
                        continue

            if not disk_info:
                disk_info = "No readable disk partitions found."

            net = psutil.net_io_counters()
            net_sent = net.bytes_sent / (1024**2)
            net_recv = net.bytes_recv / (1024**2)

            # Bot process stats
            process = psutil.Process()
            process_mem_info = process.memory_info()
            process_mem_rss = process_mem_info.rss / (1024**2)  # MB
            process_cpu_percent = process.cpu_percent(
                interval=0.5
            )  # Use interval for accurate reading

            uptime_seconds = int(time.time() - self.start_time)
            uptime_str = self._format_uptime(uptime_seconds)

            # Determine embed color based on CPU usage
            if cpu_percent < 50:
                color = discord.Color.green()
            elif cpu_percent < 80:
                color = discord.Color.orange()
            else:
                color = discord.Color.red()

            embed = create_embed(
                title="🩺 Advanced Server Health", color=color, timestamp=True
            )

            # System Info
            embed.add_field(
                name="🖥️ System-Wide",
                value=(
                    f"**CPU:** {cpu_percent}% ({cpu_cores} Cores, {cpu_logical_cores} Threads)\n"
                    f"**RAM:** {mem_used:.2f}/{mem_total:.2f} GB ({mem_percent}%)\n"
                    f"**Swap:** {swap_used:.2f}/{swap_total:.2f} GB ({swap_percent}%)"
                ),
                inline=False,
            )

            # Disk Info
            embed.add_field(name="💽 Disk Partitions", value=disk_info, inline=False)

            # Bot Process Info
            embed.add_field(
                name="🤖 Bot Process",
                value=(
                    f"**CPU:** {process_cpu_percent:.1f}%\n"
                    f"**RAM:** {process_mem_rss:.2f} MB\n"
                    f"**Uptime:** {uptime_str}\n"
                    f"**Platform:** {platform.system()}"
                ),
                inline=False,
            )

            # Network & Discord Info
            embed.add_field(
                name="🌐 Network & Discord",
                value=(
                    f"**Sent:** {net_sent:.2f} MB | **Received:** {net_recv:.2f} MB\n"
                    f"**Latency:** {round(self.bot.latency * 1000)}ms | **Shards:** {self.bot.shard_count or 1}"
                ),
                inline=False,
            )

            footer_text = f"Python {platform.python_version()} | discord.py {discord.__version__}\n"
            footer_text += (
                "Note: Stats reflect the bot's environment (e.g., a container)."
            )
            embed.set_footer(text=footer_text)

        await ctx.send(embed=embed)

    @commands.command()
    async def ping(self, ctx):
        """Checks the bot's responsiveness and latency.

        **Usage:** `{prefix}ping`
        """
        import aiohttp
        from config.config import config

        # Websocket latency
        websocket_latency = round(self.bot.latency * 1000)

        # Message response time
        message_start = time.time()
        message = await ctx.send("🏓 Calculating ping...")
        message_latency = round((time.time() - message_start) * 1000)

        # Database latency
        db_latency = "N/A"
        try:
            db_start = time.time()
            await self.db.client.admin.command("ping")
            db_latency = f"{round((time.time() - db_start) * 1000)}ms"
        except Exception:
            db_latency = "Error"

        # API latency (if moderation API is configured)
        api_latency = "N/A"
        if config.api.moderation_api_url:
            try:
                api_start = time.time()
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{config.api.moderation_api_url}/health",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            api_latency = f"{round((time.time() - api_start) * 1000)}ms"
                        else:
                            api_latency = "Error"
            except Exception:
                api_latency = "Timeout"

        # Determine overall color based on websocket latency
        color = (
            discord.Color.green()
            if websocket_latency < 100
            else (
                discord.Color.orange()
                if websocket_latency < 300
                else discord.Color.red()
            )
        )

        embed = create_embed(
            title="🏓 Pong!", description="Connection latency measurements", color=color
        )

        embed.add_field(
            name="🌐 Websocket", value=f"{websocket_latency}ms", inline=True
        )
        embed.add_field(name="💬 Message", value=f"{message_latency}ms", inline=True)
        embed.add_field(name="🗄️ Database", value=db_latency, inline=True)
        embed.add_field(name="🔗 API", value=api_latency, inline=True)

        # Add status indicator
        if websocket_latency < 100:
            status = "🟢 Excellent"
        elif websocket_latency < 200:
            status = "🟡 Good"
        elif websocket_latency < 300:
            status = "🟠 Fair"
        else:
            status = "🔴 Poor"

        embed.add_field(name="📊 Status", value=status, inline=True)

        await message.edit(embed=embed)

    @commands.command()
    async def invite(self, ctx):
        """Shows the bot's invite link.

        **Usage:** `{prefix}invite`
        """
        embed = create_embed(
            title="📨 Invite rainbot",
            description=f"[Click here to invite me!](https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&scope=bot&permissions=2013785334)",
            color=discord.Color.blue(),
        )

        await ctx.send(embed=embed)

    @commands.command(aliases=["mypermissions"])
    async def myperms(self, ctx):
        """Checks your permission level.

        **Usage:** `{prefix}myperms`
        **Alias:** `{prefix}mypermissions`
        """
        if hasattr(self.bot, "permissions") and self.bot.permissions:
            user_level = await self.bot.permissions.get_user_level(
                ctx.guild, ctx.author
            )
            perm_level_name = PermissionLevel(user_level).name.replace("_", " ").title()

            embed = create_embed(
                title="🔐 My Permissions",
                description=f"Your permission level is **{user_level} ({perm_level_name})**.",
                color=discord.Color.blue(),
            )
            embed.set_footer(text=f"Checked for {ctx.author}")
        else:
            embed = create_embed(
                title="❌ Permission System Error",
                description="Permission system not initialized",
                color=discord.Color.red(),
            )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Utils(bot))
